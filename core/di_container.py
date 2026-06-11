from typing import Any, Dict, Type, Optional, Callable
from core.singleton import Singleton


class DIContainer(metaclass=Singleton):
    def __init__(self):
        self._services: Dict[Type, Any] = {}
        self._singletons: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}

    def register(self, interface: Type, implementation: Any, singleton: bool = True):
        if singleton:
            self._singletons[interface] = implementation
        else:
            self._services[interface] = implementation

    def register_factory(self, interface: Type, factory: Callable):
        self._factories[interface] = factory

    def resolve(self, interface: Type) -> Any:
        if interface in self._singletons:
            return self._singletons[interface]
        
        if interface in self._factories:
            instance = self._factories[interface]()
            self._singletons[interface] = instance
            return instance
        
        if interface in self._services:
            return self._services[interface]
        
        raise ValueError(f"No service registered for {interface}")

    def try_resolve(self, interface: Type) -> Optional[Any]:
        try:
            return self.resolve(interface)
        except ValueError:
            return None

    def contains(self, interface: Type) -> bool:
        return interface in self._singletons or interface in self._services or interface in self._factories

    def unregister(self, interface: Type):
        self._singletons.pop(interface, None)
        self._services.pop(interface, None)
        self._factories.pop(interface, None)

    def clear(self):
        self._singletons.clear()
        self._services.clear()
        self._factories.clear()


class ServiceProvider:
    @staticmethod
    def get(interface: Type) -> Any:
        return DIContainer().resolve(interface)

    @staticmethod
    def try_get(interface: Type) -> Optional[Any]:
        return DIContainer().try_resolve(interface)

    @staticmethod
    def register(interface: Type, implementation: Any, singleton: bool = True):
        DIContainer().register(interface, implementation, singleton)

    @staticmethod
    def register_factory(interface: Type, factory: Callable):
        DIContainer().register_factory(interface, factory)

    @staticmethod
    def contains(interface: Type) -> bool:
        return DIContainer().contains(interface)


def inject(interface: Type):
    def decorator(func):
        def wrapper(*args, **kwargs):
            instance = ServiceProvider.try_get(interface)
            if instance:
                kwargs[interface.__name__.lower()] = instance
            return func(*args, **kwargs)
        return wrapper
    return decorator


class AppModule:
    @staticmethod
    def register_services():
        from config.config_manager import ConfigManager
        from monitoring.history_manager import HistoryManager
        from monitoring.performance_counter import PerformanceCounter
        from monitoring.network_monitor import NetworkMonitor
        from ml.scoring_model import MLScoringModel
        from ml.smart_classifier import SmartAppClassifier
        from core.classifier import AppClassifier
        from core.scorer import PriorityScorer
        from core.gpu_manager import GPUManager
        from core.alerting import AlertManager, AlertMonitor

        ServiceProvider.register_factory(ConfigManager, lambda: ConfigManager())
        ServiceProvider.register_factory(HistoryManager, lambda: HistoryManager())
        ServiceProvider.register_factory(PerformanceCounter, lambda: PerformanceCounter())
        ServiceProvider.register_factory(NetworkMonitor, lambda: NetworkMonitor())
        ServiceProvider.register_factory(MLScoringModel, lambda: MLScoringModel())
        ServiceProvider.register_factory(SmartAppClassifier, lambda: SmartAppClassifier())
        ServiceProvider.register_factory(AppClassifier, lambda: AppClassifier())
        ServiceProvider.register_factory(PriorityScorer, lambda: PriorityScorer())
        ServiceProvider.register_factory(GPUManager, lambda: GPUManager())
        ServiceProvider.register_factory(AlertManager, lambda: AlertManager())
        ServiceProvider.register_factory(AlertMonitor, lambda: AlertMonitor())

    @staticmethod
    def initialize():
        AppModule.register_services()
        
        config_manager = ServiceProvider.get(ConfigManager)
        smart_classifier = ServiceProvider.get(SmartAppClassifier)
        
        categories = config_manager.get_app_categories().get('categories', {})
        if categories:
            result = smart_classifier.train(categories)
            if result['status'] == 'success':
                from core.logger import get_logger
                logger = get_logger(__name__)
                logger.info(f"智能分类器训练成功，样本数: {result['samples']}")