import psutil
import time
from typing import Tuple, Dict, Optional, Any, List
from core.di_container import ServiceProvider
from core.logger import get_logger
from core.constants import PRIORITY_LEVELS, PRIORITY_DISPLAY, PRIORITY_THRESHOLDS, DEFAULT_WEIGHTS, CATEGORY_BASE_SCORES, PROCESS_TYPE_BONUS, STATUS_SCORES


class PriorityScorer:

    def __init__(self):
        self._logger = get_logger(__name__)
        self._classifier: Optional[Any] = None

    def _get_classifier(self) -> Optional[Any]:
        if self._classifier is None:
            from core.classifier import AppClassifier
            self._classifier = ServiceProvider.try_get(AppClassifier)
        return self._classifier

    def _get_ml_model(self) -> Optional[Any]:
        from ml.scoring_model import MLScoringModel
        return ServiceProvider.try_get(MLScoringModel)

    def score_to_priority(self, score: float) -> Tuple[str, str]:
        high_thresh, above_normal_thresh, normal_thresh, below_normal_thresh = PRIORITY_THRESHOLDS
        if score >= high_thresh:
            return 'high', PRIORITY_DISPLAY['high']
        elif score >= above_normal_thresh:
            return 'above_normal', PRIORITY_DISPLAY['above_normal']
        elif score >= normal_thresh:
            return 'normal', PRIORITY_DISPLAY['normal']
        elif score >= below_normal_thresh:
            return 'below_normal', PRIORITY_DISPLAY['below_normal']
        else:
            return 'idle', PRIORITY_DISPLAY['idle']

    def get_priority_key(self, priority_value: int) -> str:
        for key, value in PRIORITY_LEVELS.items():
            if value == priority_value:
                return key
        return 'normal'

    def _get_process_window_title(self, pid: int) -> Optional[str]:
        try:
            import win32gui
            import win32process

            def callback(hwnd, extra):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid and win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        extra.append(title)
                return True

            titles = []
            win32gui.EnumWindows(callback, titles)
            return titles[0] if titles else None
        except:
            return None

    def _get_process_company_name(self, exe_path: str) -> Optional[str]:
        try:
            import win32api
            info = win32api.GetFileVersionInfo(exe_path, "\\")
            return info.get('CompanyName', '')
        except:
            return None

    def calculate_score(self, process: psutil.Process, system_metrics: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str], Optional[Dict[str, Any]]]:
        try:
            cpu_percent = process.cpu_percent(interval=None)
            if cpu_percent > 100:
                cpu_percent = 50

            memory_percent = process.memory_percent()

            try:
                memory_info = process.memory_info()
                memory_rss = memory_info.rss / (1024 ** 2)
                memory_vms = memory_info.vms / (1024 ** 2)
            except:
                memory_rss = 0
                memory_vms = 0

            try:
                io_counters = process.io_counters()
                io_read = io_counters.read_bytes / (1024 ** 2)
                io_write = io_counters.write_bytes / (1024 ** 2)
            except:
                io_read = 0
                io_write = 0

            try:
                num_threads = process.num_threads()
            except:
                num_threads = 1

            try:
                create_time = process.create_time()
                uptime = time.time() - create_time
            except:
                uptime = 3600

            try:
                status = process.status()
            except:
                status = 'running'

            process_name = process.name().lower()

            exe_path = ""
            try:
                exe_path = process.exe()
            except:
                pass

            window_title = self._get_process_window_title(process.pid)
            company_name = self._get_process_company_name(exe_path) if exe_path else None

            classifier = self._get_classifier()
            if classifier:
                category, cat_info = classifier.classify(process.name(), exe_path, window_title, company_name)
            else:
                category, cat_info = 'unknown', {'description': '未知应用', 'suggested_gpu': 'auto', 'priority': 'medium'}

            metrics = {
                'cpu': min(100, cpu_percent),
                'memory': min(100, memory_percent),
                'threads': num_threads,
                'io': min(100, (io_read + io_write) / 50),
                'uptime': uptime,
                'status': status,
                'category': category,
                'proc_type': category,
                'exe_path': exe_path,
                'window_title': window_title,
                'company_name': company_name
            }

            score = self._compute_score(metrics, system_metrics)

            return min(100, max(0, score)), cpu_percent, memory_percent, category, {
                'memory_rss': memory_rss,
                'memory_vms': memory_vms,
                'io_read': io_read,
                'io_write': io_write,
                'num_threads': num_threads,
                'category_info': cat_info
            }

        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return None, None, None, None, None

    def _compute_score(self, metrics: Dict[str, Any], system_metrics: Dict[str, Any]) -> float:
        ml_model = self._get_ml_model()
        
        if ml_model:
            try:
                return ml_model.predict_score(metrics)
            except Exception as e:
                self._logger.warning(f"ML评分失败，使用规则引擎: {e}")

        return self._rule_based_scoring(metrics, system_metrics)

    def _rule_based_scoring(self, metrics: Dict, system_metrics: Dict) -> float:
        category = metrics.get('category', 'unknown')
        cpu = metrics.get('cpu', 0)
        memory = metrics.get('memory', 0)
        threads = metrics.get('threads', 1)
        io = metrics.get('io', 0)
        uptime = metrics.get('uptime', 3600)
        status = metrics.get('status', 'running')

        base_score = CATEGORY_BASE_SCORES.get(category, 45)

        cpu_weight = DEFAULT_WEIGHTS.get('cpu_weight', 25)
        memory_weight = DEFAULT_WEIGHTS.get('memory_weight', 20)
        threads_weight = DEFAULT_WEIGHTS.get('threads_weight', 10)
        io_weight = DEFAULT_WEIGHTS.get('io_weight', 8)

        cpu_score = min(cpu_weight, cpu * (cpu_weight / 50))
        memory_score = min(memory_weight, memory * (memory_weight / 50))
        thread_score = min(threads_weight, min(threads, 50) * (threads_weight / 50))
        io_score = min(io_weight, io * (io_weight / 40))

        uptime_hours = uptime / 3600
        if uptime_hours < 0.5:
            uptime_score = 5
        elif uptime_hours < 2:
            uptime_score = 3
        elif uptime_hours > 24:
            uptime_score = -5
        else:
            uptime_score = 0

        status_score = STATUS_SCORES.get(status, 0)

        system_load = system_metrics.get('cpu_percent', 0) / 100
        load_adjustment = -10 if system_load > 0.8 else 0

        total_score = base_score + cpu_score + memory_score + thread_score + io_score + uptime_score + status_score + load_adjustment

        return min(100, max(0, total_score))

    def analyze_process(self, process: psutil.Process, use_ml: bool = True) -> Optional[Dict]:
        try:
            system_metrics = self._get_system_metrics()
            score, cpu_percent, memory_percent, category, details = self.calculate_score(process, system_metrics)

            if score is None:
                return None

            priority_key, priority_display = self.score_to_priority(score)

            return {
                'pid': process.pid,
                'name': process.name(),
                'category': category,
                'category_desc': details.get('category_info', {}).get('description', '未知'),
                'score': round(score, 2),
                'priority': priority_key,
                'priority_display': priority_display,
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'memory_rss': round(details.get('memory_rss', 0), 2),
                'memory_vms': round(details.get('memory_vms', 0), 2),
                'num_threads': details.get('num_threads', 1),
                'io_read': round(details.get('io_read', 0), 2),
                'io_write': round(details.get('io_write', 0), 2),
                'suggested_gpu': details.get('category_info', {}).get('suggested_gpu', 'auto'),
                'uptime': self._format_uptime(details.get('uptime', 0) if 'uptime' in details else 3600)
            }
        except Exception as e:
            self._logger.error(f"分析进程失败 {process.pid}: {e}")
            return None

    def _get_system_metrics(self) -> Dict:
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.01),
            'memory_percent': psutil.virtual_memory().percent,
            'cpu_count': psutil.cpu_count() or 1
        }

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"