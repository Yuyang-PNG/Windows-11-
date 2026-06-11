import os
import json
import threading
from datetime import datetime

try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

class ProcessPriorityAPI:
    def __init__(self, port=5000, debug=False):
        if not FLASK_AVAILABLE:
            raise ImportError("Flask not available. Please install flask and flask-cors.")
        
        self.app = Flask(__name__)
        CORS(self.app)
        self.port = port
        self.debug = debug
        self.server_thread = None
        self.running = False
        
        self._register_routes()
        
        self.config_manager = None
        self.history_manager = None
        self.perf_counter = None
        self.network_monitor = None
        self.ml_model = None
        self.analyze_process_func = None
        self.set_priority_func = None
        self.is_admin_func = None
    
    def set_dependencies(self, config_manager=None, history_manager=None, 
                        perf_counter=None, network_monitor=None,
                        ml_model=None, analyze_process_func=None,
                        set_priority_func=None, is_admin_func=None):
        self.config_manager = config_manager
        self.history_manager = history_manager
        self.perf_counter = perf_counter
        self.network_monitor = network_monitor
        self.ml_model = ml_model
        self.analyze_process_func = analyze_process_func
        self.set_priority_func = set_priority_func
        self.is_admin_func = is_admin_func
    
    def _register_routes(self):
        @self.app.route('/')
        def dashboard():
            dashboard_path = os.path.join(os.path.dirname(__file__), '..', 'dashboard', 'index.html')
            if os.path.exists(dashboard_path):
                with open(dashboard_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return "<h1>Process Priority Manager Dashboard</h1><p>Dashboard not found</p>"
        
        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            return jsonify({
                'status': 'ok',
                'timestamp': datetime.now().isoformat(),
                'version': '1.1.0'
            })
        
        @self.app.route('/api/processes', methods=['GET'])
        def get_processes():
            try:
                import psutil
                
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent']):
                    try:
                        info = proc.info
                        processes.append({
                            'pid': info['pid'],
                            'name': info['name'],
                            'status': info['status'],
                            'cpu_percent': info['cpu_percent'],
                            'memory_percent': info['memory_percent']
                        })
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue
                
                return jsonify({
                    'success': True,
                    'data': processes,
                    'count': len(processes)
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/processes/<int:pid>', methods=['GET'])
        def get_process(pid):
            try:
                import psutil
                
                process = psutil.Process(pid)
                
                info = {
                    'pid': process.pid,
                    'name': process.name(),
                    'status': process.status(),
                    'cpu_percent': process.cpu_percent(),
                    'memory_percent': process.memory_percent(),
                    'memory_info': {
                        'rss': process.memory_info().rss,
                        'vms': process.memory_info().vms
                    },
                    'num_threads': process.num_threads(),
                    'create_time': datetime.fromtimestamp(process.create_time()).isoformat()
                }
                
                if self.network_monitor:
                    info['network'] = self.network_monitor.get_process_network_summary(process)
                
                return jsonify({'success': True, 'data': info})
            
            except psutil.NoSuchProcess:
                return jsonify({'success': False, 'error': 'Process not found'}), 404
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/processes/<int:pid>/priority', methods=['PUT'])
        def set_process_priority(pid):
            try:
                if not self.is_admin_func or not self.is_admin_func():
                    return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
                
                data = request.get_json()
                priority = data.get('priority', 'NORMAL_PRIORITY_CLASS')
                
                if self.set_priority_func:
                    success = self.set_priority_func(pid, priority)
                    if success:
                        return jsonify({'success': True, 'message': 'Priority updated successfully'})
                    else:
                        return jsonify({'success': False, 'error': 'Failed to set priority'}), 500
                else:
                    return jsonify({'success': False, 'error': 'Priority function not available'}), 500
            
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/analyze', methods=['POST'])
        def analyze_processes():
            try:
                data = request.get_json()
                use_ml = data.get('use_ml', False)
                
                results = []
                
                if self.analyze_process_func:
                    import psutil
                    
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            result = self.analyze_process_func(proc, use_ml=use_ml)
                            if result:
                                results.append(result)
                        except Exception:
                            continue
                
                return jsonify({
                    'success': True,
                    'data': results,
                    'count': len(results),
                    'scoring_method': 'ml' if use_ml else 'rule_based'
                })
            
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/report', methods=['GET'])
        def get_report():
            try:
                if self.history_manager:
                    report = self.history_manager.generate_report()
                    return jsonify({'success': True, 'data': report})
                else:
                    return jsonify({'success': False, 'error': 'History manager not available'}), 500
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/anomalies', methods=['GET'])
        def get_anomalies():
            try:
                if self.history_manager:
                    anomalies = self.history_manager.detect_anomalies()
                    return jsonify({'success': True, 'data': anomalies, 'count': len(anomalies)})
                else:
                    return jsonify({'success': False, 'error': 'History manager not available'}), 500
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/system', methods=['GET'])
        def get_system_stats():
            try:
                import psutil
                
                stats = {
                    'cpu': {
                        'percent': psutil.cpu_percent(),
                        'count': psutil.cpu_count(),
                        'freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
                    },
                    'memory': {
                        'percent': psutil.virtual_memory().percent,
                        'total': psutil.virtual_memory().total,
                        'available': psutil.virtual_memory().available,
                        'used': psutil.virtual_memory().used
                    },
                    'disk': {
                        'percent': psutil.disk_usage('/').percent,
                        'total': psutil.disk_usage('/').total,
                        'free': psutil.disk_usage('/').free
                    },
                    'network': self.network_monitor.get_total_network_stats() if self.network_monitor else {}
                }
                
                if self.perf_counter:
                    perf_data = self.perf_counter.get_all_metrics()
                    stats['performance_counter'] = perf_data
                
                return jsonify({'success': True, 'data': stats})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            try:
                if self.config_manager:
                    config = {
                        'app_categories': self.config_manager.get_app_categories(),
                        'scoring_rules': self.config_manager.get_scoring_rules(),
                        'cross_factors': self.config_manager.get_cross_factors()
                    }
                    return jsonify({'success': True, 'data': config})
                else:
                    return jsonify({'success': False, 'error': 'Config manager not available'}), 500
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/config/categories', methods=['GET'])
        def get_categories():
            try:
                if self.config_manager:
                    categories = self.config_manager.get_all_category_ids()
                    return jsonify({'success': True, 'data': categories})
                else:
                    return jsonify({'success': False, 'error': 'Config manager not available'}), 500
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/config/weights', methods=['GET'])
        def get_weights():
            try:
                if self.config_manager:
                    weights = self.config_manager.get_priority_scoring_weights()
                    return jsonify({'success': True, 'data': weights})
                else:
                    return jsonify({'success': False, 'error': 'Config manager not available'}), 500
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/ml/train', methods=['POST'])
        def train_ml_model():
            try:
                if not self.ml_model or not self.history_manager:
                    return jsonify({'success': False, 'error': 'ML model or history manager not available'}), 500
                
                data = self.ml_model.prepare_training_data(self.history_manager)
                result = self.ml_model.train_model(data)
                
                return jsonify({'success': result['status'] == 'success', 'data': result})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/ml/info', methods=['GET'])
        def get_ml_info():
            try:
                if self.ml_model:
                    info = self.ml_model.get_model_info()
                    return jsonify({'success': True, 'data': info})
                else:
                    return jsonify({'success': False, 'error': 'ML model not available'}), 500
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/ml/predict', methods=['POST'])
        def ml_predict():
            try:
                if not self.ml_model:
                    return jsonify({'success': False, 'error': 'ML model not available'}), 500
                
                data = request.get_json()
                metrics = data.get('metrics', {})
                
                score = self.ml_model.predict_score(metrics)
                return jsonify({'success': True, 'data': {'score': score}})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
    
    def start(self):
        """启动API服务（后台线程）"""
        if self.running:
            return False
        
        self.running = True
        self.server_thread = threading.Thread(target=self._run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        print(f"API服务已启动: http://localhost:{self.port}")
        return True
    
    def _run_server(self):
        """运行Flask服务器"""
        try:
            self.app.run(host='0.0.0.0', port=self.port, debug=self.debug, use_reloader=False)
        except Exception as e:
            print(f"API服务启动失败: {e}")
            self.running = False
    
    def stop(self):
        """停止API服务"""
        self.running = False
        if self.server_thread:
            self.server_thread.join(timeout=5)
        print("API服务已停止")
        return True