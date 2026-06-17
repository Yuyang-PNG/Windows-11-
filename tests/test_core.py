import unittest
import threading
import time
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock


class TestTTLCache(unittest.TestCase):
    def test_cache_set_get(self):
        from core.classifier import TTLCache
        
        cache = TTLCache(ttl_seconds=60)
        cache.set('test_key', 'test_value')
        result = cache.get('test_key')
        
        self.assertEqual(result, 'test_value')

    def test_cache_expiration(self):
        from core.classifier import TTLCache
        
        cache = TTLCache(ttl_seconds=1)
        cache.set('test_key', 'test_value')
        time.sleep(1.1)
        result = cache.get('test_key')
        
        self.assertIsNone(result)

    def test_cache_invalidation(self):
        from core.classifier import TTLCache
        
        cache = TTLCache(ttl_seconds=60)
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        
        cache.invalidate('key1')
        self.assertIsNone(cache.get('key1'))
        self.assertEqual(cache.get('key2'), 'value2')
        
        cache.invalidate()
        self.assertIsNone(cache.get('key2'))

    def test_cache_size(self):
        from core.classifier import TTLCache
        
        cache = TTLCache(ttl_seconds=60)
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        
        self.assertEqual(len(cache), 2)


class TestAppClassifier(unittest.TestCase):
    def test_classify_gaming(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        category, info = classifier.classify('game.exe')
        
        self.assertEqual(category, 'gaming')
        self.assertEqual(info['description'], '游戏应用')

    def test_classify_browser(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        category, info = classifier.classify('chrome.exe')
        
        self.assertEqual(category, 'browser')
        self.assertEqual(info['description'], '浏览器')

    def test_classify_productivity(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        category, info = classifier.classify('winword.exe')
        
        self.assertEqual(category, 'productivity')
        self.assertEqual(info['description'], '办公软件')

    def test_classify_unknown(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        category, info = classifier.classify('unknown_process.exe')
        
        self.assertEqual(category, 'unknown')

    def test_cache_clear(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        classifier.classify('test.exe')
        initial_size = classifier.get_cache_size()
        
        classifier.clear_cache()
        
        self.assertEqual(classifier.get_cache_size(), 0)


class TestPriorityScorer(unittest.TestCase):
    def test_score_to_priority(self):
        from core.scorer import PriorityScorer
        
        scorer = PriorityScorer()
        
        priority_key, display = scorer.score_to_priority(90)
        self.assertEqual(priority_key, 'high')
        
        priority_key, display = scorer.score_to_priority(75)
        self.assertEqual(priority_key, 'above_normal')
        
        priority_key, display = scorer.score_to_priority(50)
        self.assertEqual(priority_key, 'normal')
        
        priority_key, display = scorer.score_to_priority(30)
        self.assertEqual(priority_key, 'below_normal')
        
        priority_key, display = scorer.score_to_priority(10)
        self.assertEqual(priority_key, 'idle')

    def test_rule_based_scoring(self):
        from core.scorer import PriorityScorer
        
        scorer = PriorityScorer()
        metrics = {
            'category': 'gaming',
            'cpu': 80,
            'memory': 50,
            'threads': 8,
            'io': 20,
            'uptime': 3600,
            'status': 'running'
        }
        system_metrics = {'cpu_percent': 50}
        
        score = scorer._rule_based_scoring(metrics, system_metrics)
        
        self.assertGreater(score, 70)
        self.assertLessEqual(score, 100)


class TestDIContainer(unittest.TestCase):
    def test_register_and_resolve(self):
        from core.di_container import DIContainer, ServiceProvider
        
        DIContainer().clear()
        
        class TestService:
            def __init__(self):
                self.value = 42
        
        ServiceProvider.register_factory(TestService, lambda: TestService())
        instance = ServiceProvider.get(TestService)
        
        self.assertIsInstance(instance, TestService)
        self.assertEqual(instance.value, 42)

    def test_try_resolve_nonexistent(self):
        from core.di_container import ServiceProvider
        
        class NonexistentService:
            pass
        
        result = ServiceProvider.try_get(NonexistentService)
        
        self.assertIsNone(result)

    def test_singleton_behavior(self):
        from core.di_container import DIContainer, ServiceProvider
        
        DIContainer().clear()
        
        class SingletonService:
            def __init__(self):
                self.id = id(self)
        
        ServiceProvider.register_factory(SingletonService, lambda: SingletonService())
        
        instance1 = ServiceProvider.get(SingletonService)
        instance2 = ServiceProvider.get(SingletonService)
        
        self.assertEqual(instance1.id, instance2.id)


class TestAlertManager(unittest.TestCase):
    def test_trigger_alert(self):
        from core.alerting import AlertManager, AlertLevel
        
        alert_manager = AlertManager()
        alert = alert_manager.info('Test Title', 'Test Message', {'key': 'value'})
        
        self.assertEqual(alert.level, AlertLevel.INFO)
        self.assertEqual(alert.title, 'Test Title')
        self.assertEqual(alert.message, 'Test Message')
        self.assertEqual(alert.details, {'key': 'value'})
        self.assertFalse(alert.acknowledged)

    def test_acknowledge_alert(self):
        from core.alerting import AlertManager
        
        alert_manager = AlertManager()
        alert = alert_manager.warning('Test', 'Test')
        
        result = alert_manager.acknowledge_alert(alert.id)
        
        self.assertTrue(result)
        self.assertTrue(alert.acknowledged)

    def test_get_alerts_filtered(self):
        from core.alerting import AlertManager, AlertLevel
        
        alert_manager = AlertManager()
        alert_manager.clear_alerts()
        
        alert_manager.debug('Debug', 'Debug msg')
        alert_manager.info('Info', 'Info msg')
        alert_manager.warning('Warning', 'Warning msg')
        
        alerts = alert_manager.get_alerts(level=AlertLevel.WARNING)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['title'], 'Warning')


class TestGPUManager(unittest.TestCase):
    def test_get_gpu_info(self):
        from core.gpu_manager import GPUManager
        
        gpu_manager = GPUManager()
        gpus = gpu_manager.get_gpu_info()
        
        self.assertIsInstance(gpus, list)

    def test_gpu_recommendation(self):
        from core.gpu_manager import GPUManager
        from core.di_container import ServiceProvider, AppModule
        
        AppModule.register_services()
        
        gpu_manager = GPUManager()
        recommendation = gpu_manager.get_gpu_recommendation('game.exe')
        
        self.assertEqual(recommendation['category'], 'gaming')


class TestThreadSafety(unittest.TestCase):
    def test_cache_thread_safety(self):
        from core.classifier import TTLCache
        
        cache = TTLCache(ttl_seconds=60)
        errors = []
        
        def writer():
            try:
                for i in range(100):
                    cache.set(f'key_{i}', f'value_{i}')
            except Exception as e:
                errors.append(e)
        
        threads = []
        for _ in range(10):
            t = threading.Thread(target=writer)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(cache), 100)


class TestSingleton(unittest.TestCase):
    def test_singleton_instance(self):
        from core.singleton import Singleton
        
        class TestClass(metaclass=Singleton):
            def __init__(self):
                self.value = 100
        
        instance1 = TestClass()
        instance2 = TestClass()
        
        self.assertIs(instance1, instance2)
        self.assertEqual(instance1.value, instance2.value)
    
    def test_singleton_thread_safety(self):
        from core.singleton import Singleton
        
        class ThreadSafeClass(metaclass=Singleton):
            def __init__(self):
                self.counter = 0
        
        errors = []
        
        def access_singleton():
            try:
                instance = ThreadSafeClass()
                for _ in range(100):
                    instance.counter += 1
            except Exception as e:
                errors.append(e)
        
        threads = []
        for _ in range(10):
            t = threading.Thread(target=access_singleton)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(ThreadSafeClass().counter, 1000)
    
    def test_singleton_clear(self):
        from core.singleton import Singleton
        
        class ClearableClass(metaclass=Singleton):
            def __init__(self):
                self.value = 50
        
        instance1 = ClearableClass()
        instance1.value = 100
        
        Singleton.clear_instance(ClearableClass)
        
        instance2 = ClearableClass()
        self.assertNotEqual(instance1.value, instance2.value)
        self.assertEqual(instance2.value, 50)


class TestConfigValidator(unittest.TestCase):
    def test_validate_valid_config(self):
        from config.config_validator import ConfigValidator
        
        config = {
            'version': '1.1',
            'categories': {
                'test': {
                    'description': 'Test',
                    'suggested_gpu': 'auto',
                    'priority': 'high'
                }
            }
        }
        
        is_valid, errors = ConfigValidator.validate('app_categories', config)
        
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_validate_invalid_config(self):
        from config.config_validator import ConfigValidator
        
        config = {
            'version': '1.0',
            'categories': {
                'test': {
                    'description': 123,
                    'suggested_gpu': 'auto'
                }
            }
        }
        
        is_valid, errors = ConfigValidator.validate('app_categories', config)
        
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
    
    def test_fix_config(self):
        from config.config_validator import ConfigValidator
        
        config = {
            'version': '1.0',
            'categories': {
                'test': {
                    'description': 123,
                    'suggested_gpu': 'auto'
                }
            }
        }
        
        fixed = ConfigValidator.fix_config('app_categories', config)
        
        self.assertEqual(fixed['version'], '1.1')
        self.assertIsInstance(fixed['categories']['test']['description'], str)
    
    def test_version_compatibility(self):
        from config.config_validator import ConfigValidator
        
        old_config = {'version': '0.9', 'categories': {}}
        is_valid, errors = ConfigValidator.validate('app_categories', old_config)
        
        self.assertFalse(is_valid)
        self.assertIn('过旧', errors[0])


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_load_default_config(self):
        from config.config_manager import ConfigManager
        
        config_manager = ConfigManager(config_dir=self.test_dir)
        
        categories = config_manager.get_app_categories()
        self.assertIn('gaming', categories['categories'])
        self.assertIn('version', categories)
    
    def test_save_and_load_gpu_settings(self):
        from config.config_manager import ConfigManager
        
        config_manager = ConfigManager(config_dir=self.test_dir)
        
        settings = {
            'gpu_settings': {'game.exe': 'discrete'},
            'priority_rules': {}
        }
        
        success = config_manager.save_gpu_settings(settings)
        self.assertTrue(success)
        
        loaded = config_manager.get_gpu_settings()
        self.assertEqual(loaded['gpu_settings']['game.exe'], 'discrete')
    
    def test_validate_all_configs(self):
        from config.config_manager import ConfigManager
        
        config_manager = ConfigManager(config_dir=self.test_dir)
        reports = config_manager.validate_all_configs()
        
        self.assertIn('app_categories', reports)
        self.assertTrue(reports['app_categories']['valid'])


class TestAppClassifierAdvanced(unittest.TestCase):
    def test_classify_with_path(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        category, info = classifier.classify('test.exe', exe_path='C:\\Steam\\steamapps\\test.exe')
        
        self.assertEqual(category, 'gaming')
    
    def test_classify_with_window_title(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        category, info = classifier.classify('unknown.exe', window_title='- Steam')
        
        self.assertEqual(category, 'gaming')
    
    def test_classify_development_tools(self):
        from core.classifier import AppClassifier
        
        classifier = AppClassifier()
        
        category, info = classifier.classify('code.exe')
        self.assertEqual(category, 'development')
        
        category, info = classifier.classify('idea64.exe')
        self.assertEqual(category, 'development')


class TestPriorityScorerAdvanced(unittest.TestCase):
    def test_get_priority_key(self):
        from core.scorer import PriorityScorer
        import psutil
        
        scorer = PriorityScorer()
        
        result = scorer.get_priority_key(psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(result, 'high')
        
        result = scorer.get_priority_key(999)
        self.assertEqual(result, 'normal')
    
    def test_different_category_scores(self):
        from core.scorer import PriorityScorer
        
        scorer = PriorityScorer()
        
        gaming_metrics = {
            'category': 'gaming',
            'cpu': 50,
            'memory': 30,
            'threads': 4,
            'io': 10,
            'uptime': 3600,
            'status': 'running'
        }
        
        browser_metrics = {
            'category': 'browser',
            'cpu': 30,
            'memory': 40,
            'threads': 8,
            'io': 5,
            'uptime': 7200,
            'status': 'running'
        }
        
        gaming_score = scorer._rule_based_scoring(gaming_metrics, {'cpu_percent': 30})
        browser_score = scorer._rule_based_scoring(browser_metrics, {'cpu_percent': 30})
        
        self.assertGreater(gaming_score, browser_score)


if __name__ == '__main__':
    unittest.main()
