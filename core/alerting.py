import threading
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from core.logger import get_logger


class AlertLevel:
    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class Alert:
    def __init__(self, level: str, title: str, message: str, details: Optional[Dict] = None):
        self.id = f"{int(time.time())}_{hash(title + message) % 100000}"
        self.level = level
        self.title = title
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()
        self.acknowledged = False

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'level': self.level,
            'title': self.title,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
            'acknowledged': self.acknowledged
        }


class AlertHandler:
    def send(self, alert: Alert) -> bool:
        raise NotImplementedError


class ConsoleAlertHandler(AlertHandler):
    def send(self, alert: Alert) -> bool:
        level_colors = {
            AlertLevel.DEBUG: '\033[94m',
            AlertLevel.INFO: '\033[92m',
            AlertLevel.WARNING: '\033[93m',
            AlertLevel.ERROR: '\033[91m',
            AlertLevel.CRITICAL: '\033[95m'
        }
        color = level_colors.get(alert.level, '')
        print(f"{color}[{alert.level.upper()}] {alert.title}: {alert.message}\033[0m")
        if alert.details:
            print(f"  Details: {alert.details}")
        return True


class FileAlertHandler(AlertHandler):
    def __init__(self, log_file: str = 'alerts.log'):
        self._log_file = log_file

    def send(self, alert: Alert) -> bool:
        try:
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{alert.timestamp.isoformat()}] [{alert.level.upper()}] {alert.title}: {alert.message}\n")
                if alert.details:
                    f.write(f"  Details: {alert.details}\n")
            return True
        except Exception as e:
            print(f"写入告警日志失败: {e}")
            return False


class WebhookAlertHandler(AlertHandler):
    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    def send(self, alert: Alert) -> bool:
        try:
            import requests
            payload = alert.to_dict()
            response = requests.post(self._webhook_url, json=payload, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"发送Webhook告警失败: {e}")
            return False


class AlertManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._handlers = []
                cls._instance._alerts = []
                cls._instance._max_alerts = 1000
                cls._instance._alert_rules = []
                cls._instance._logger = get_logger(__name__)
                cls._instance._add_default_handlers()
            return cls._instance

    def _add_default_handlers(self):
        self.add_handler(ConsoleAlertHandler())
        self.add_handler(FileAlertHandler())

    def add_handler(self, handler: AlertHandler):
        self._handlers.append(handler)

    def remove_handler(self, handler: AlertHandler):
        self._handlers.remove(handler)

    def add_alert_rule(self, rule: Dict):
        self._alert_rules.append(rule)

    def remove_alert_rule(self, rule_id: str):
        self._alert_rules = [r for r in self._alert_rules if r.get('id') != rule_id]

    def trigger_alert(self, level: str, title: str, message: str, details: Optional[Dict] = None) -> Alert:
        alert = Alert(level, title, message, details)
        
        for handler in self._handlers:
            try:
                handler.send(alert)
            except Exception as e:
                self._logger.error(f"告警处理器 {handler.__class__.__name__} 执行失败: {e}")
        
        self._alerts.insert(0, alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts.pop()
        
        self._logger.info(f"告警已触发: {level} - {title}")
        return alert

    def debug(self, title: str, message: str, details: Optional[Dict] = None):
        return self.trigger_alert(AlertLevel.DEBUG, title, message, details)

    def info(self, title: str, message: str, details: Optional[Dict] = None):
        return self.trigger_alert(AlertLevel.INFO, title, message, details)

    def warning(self, title: str, message: str, details: Optional[Dict] = None):
        return self.trigger_alert(AlertLevel.WARNING, title, message, details)

    def error(self, title: str, message: str, details: Optional[Dict] = None):
        return self.trigger_alert(AlertLevel.ERROR, title, message, details)

    def critical(self, title: str, message: str, details: Optional[Dict] = None):
        return self.trigger_alert(AlertLevel.CRITICAL, title, message, details)

    def acknowledge_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return True
        return False

    def get_alerts(self, level: Optional[str] = None, acknowledged: Optional[bool] = None) -> List[Dict]:
        filtered = self._alerts
        if level:
            filtered = [a for a in filtered if a.level == level]
        if acknowledged is not None:
            filtered = [a for a in filtered if a.acknowledged == acknowledged]
        return [a.to_dict() for a in filtered]

    def get_unacknowledged_count(self) -> int:
        return sum(1 for a in self._alerts if not a.acknowledged)

    def clear_alerts(self):
        self._alerts.clear()

    def check_rules(self, metrics: Dict) -> List[Alert]:
        triggered_alerts = []
        
        for rule in self._alert_rules:
            condition = rule.get('condition')
            if self._evaluate_condition(condition, metrics):
                alert = self.trigger_alert(
                    rule.get('level', AlertLevel.WARNING),
                    rule.get('title', '规则触发'),
                    rule.get('message', '监控规则已触发'),
                    {'rule_id': rule.get('id'), 'metrics': metrics}
                )
                triggered_alerts.append(alert)
        
        return triggered_alerts

    def _evaluate_condition(self, condition: Dict, metrics: Dict) -> bool:
        field = condition.get('field')
        operator = condition.get('operator')
        value = condition.get('value')
        
        field_value = metrics.get(field, 0)
        
        if operator == '>':
            return field_value > value
        elif operator == '<':
            return field_value < value
        elif operator == '>=':
            return field_value >= value
        elif operator == '<=':
            return field_value <= value
        elif operator == '==':
            return field_value == value
        elif operator == '!=':
            return field_value != value
        elif operator == 'contains':
            return value in str(field_value)
        
        return False


class AlertMonitor:
    def __init__(self):
        self._logger = get_logger(__name__)
        self._alert_manager = AlertManager()
        self._running = False
        self._thread = None
        self._check_interval = 30

    def start(self):
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop)
        self._thread.daemon = True
        self._thread.start()
        self._logger.info("告警监控器已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._logger.info("告警监控器已停止")

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_system_health()
            except Exception as e:
                self._logger.error(f"监控循环异常: {e}")
            
            for _ in range(self._check_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _check_system_health(self):
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
        
        metrics = {
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent,
            'disk_percent': disk_percent
        }
        
        if cpu_percent > 95:
            self._alert_manager.warning(
                'CPU使用率过高',
                f"CPU使用率达到 {cpu_percent:.1f}%",
                {'cpu_percent': cpu_percent}
            )
        
        if memory_percent > 90:
            self._alert_manager.warning(
                '内存使用率过高',
                f"内存使用率达到 {memory_percent:.1f}%",
                {'memory_percent': memory_percent}
            )
        
        if disk_percent > 95:
            self._alert_manager.critical(
                '磁盘空间不足',
                f"磁盘使用率达到 {disk_percent:.1f}%",
                {'disk_percent': disk_percent}
            )
        
        self._alert_manager.check_rules(metrics)

    def add_custom_check(self, name: str, check_func: Callable, threshold: float):
        def wrapper():
            result = check_func()
            if result > threshold:
                self._alert_manager.warning(
                    f"{name}超限",
                    f"{name}值达到 {result:.2f} (阈值: {threshold})",
                    {'value': result, 'threshold': threshold}
                )
        
        import schedule
        schedule.every(self._check_interval).seconds.do(wrapper)