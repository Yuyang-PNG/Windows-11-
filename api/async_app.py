import asyncio
import json
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

class ProcessPriorityAsyncAPI:
    def __init__(self, port=5000):
        if not FASTAPI_AVAILABLE:
            raise ImportError("FastAPI not available. Please install fastapi and uvicorn.")
        
        self.app = FastAPI(title="Process Priority Manager API", version="2.0.0")
        self.port = port
        self.server_thread = None
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        self._setup_middleware()
        self._register_routes()
        
        self.config_manager = None
        self.history_manager = None
        self.perf_counter = None
        self.network_monitor = None
        self.ml_model = None
        self.smart_classifier = None
        self.analyze_process_func = None
        self.set_priority_func = None
        self.is_admin_func = None
        self.get_system_metrics_func = None
        self.analyze_all_processes_func = None
    
    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def set_dependencies(self, **kwargs):
        self.config_manager = kwargs.get('config_manager')
        self.history_manager = kwargs.get('history_manager')
        self.perf_counter = kwargs.get('perf_counter')
        self.network_monitor = kwargs.get('network_monitor')
        self.ml_model = kwargs.get('ml_model')
        self.smart_classifier = kwargs.get('smart_classifier')
        self.analyze_process_func = kwargs.get('analyze_process_func')
        self.set_priority_func = kwargs.get('set_priority_func')
        self.is_admin_func = kwargs.get('is_admin_func')
        self.get_system_metrics_func = kwargs.get('get_system_metrics_func')
        self.analyze_all_processes_func = kwargs.get('analyze_all_processes_func')
    
    def _register_routes(self):
        @self.app.get("/api/health", tags=["Health"])
        async def health_check():
            return {
                'status': 'ok',
                'timestamp': datetime.now().isoformat(),
                'version': '2.0.0',
                'mode': 'async'
            }
        
        @self.app.get("/api/processes", tags=["Processes"])
        async def get_processes():
            try:
                import psutil
                
                async def fetch_processes():
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
                    return processes
                
                processes = await asyncio.get_event_loop().run_in_executor(
                    self.executor, fetch_processes
                )
                
                return {
                    'success': True,
                    'data': processes,
                    'count': len(processes)
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/processes/{pid}", tags=["Processes"])
        async def get_process(pid: int):
            try:
                import psutil
                
                async def fetch_process_info():
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
                    
                    return info
                
                try:
                    info = await asyncio.get_event_loop().run_in_executor(
                        self.executor, fetch_process_info
                    )
                    return {'success': True, 'data': info}
                except psutil.NoSuchProcess:
                    raise HTTPException(status_code=404, detail='Process not found')
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        class PriorityRequest(BaseModel):
            priority: str = 'NORMAL_PRIORITY_CLASS'
        
        @self.app.put("/api/processes/{pid}/priority", tags=["Processes"])
        async def set_process_priority(pid: int, request: PriorityRequest):
            try:
                if not self.is_admin_func or not await asyncio.get_event_loop().run_in_executor(
                    self.executor, self.is_admin_func
                ):
                    raise HTTPException(status_code=403, detail='Admin privileges required')
                
                if self.set_priority_func:
                    success = await asyncio.get_event_loop().run_in_executor(
                        self.executor, self.set_priority_func, pid, request.priority
                    )
                    if success:
                        return {'success': True, 'message': 'Priority updated successfully'}
                    else:
                        raise HTTPException(status_code=500, detail='Failed to set priority')
                else:
                    raise HTTPException(status_code=500, detail='Priority function not available')
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        class AnalyzeRequest(BaseModel):
            use_ml: bool = False
        
        @self.app.post("/api/analyze", tags=["Analysis"])
        async def analyze_processes(request: AnalyzeRequest, background_tasks: BackgroundTasks):
            try:
                async def run_analysis():
                    if self.analyze_all_processes_func:
                        return self.analyze_all_processes_func(use_ml=request.use_ml)
                    return []
                
                results = await asyncio.get_event_loop().run_in_executor(
                    self.executor, run_analysis
                )
                
                if self.history_manager:
                    background_tasks.add_task(
                        self.history_manager.record_process_snapshot, results
                    )
                
                return {
                    'success': True,
                    'data': results,
                    'count': len(results),
                    'scoring_method': 'ml' if request.use_ml else 'rule_based'
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/report", tags=["Reports"])
        async def get_report():
            try:
                if not self.history_manager:
                    raise HTTPException(status_code=500, detail='History manager not available')
                
                async def generate_report():
                    return self.history_manager.generate_report()
                
                report = await asyncio.get_event_loop().run_in_executor(
                    self.executor, generate_report
                )
                return {'success': True, 'data': report}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/anomalies", tags=["Monitoring"])
        async def get_anomalies():
            try:
                if not self.history_manager:
                    raise HTTPException(status_code=500, detail='History manager not available')
                
                async def detect_anomalies():
                    return self.history_manager.detect_anomalies()
                
                anomalies = await asyncio.get_event_loop().run_in_executor(
                    self.executor, detect_anomalies
                )
                return {'success': True, 'data': anomalies, 'count': len(anomalies)}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/system", tags=["System"])
        async def get_system_stats():
            try:
                async def fetch_stats():
                    if self.get_system_metrics_func:
                        return self.get_system_metrics_func()
                    
                    import psutil
                    return {
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
                
                stats = await asyncio.get_event_loop().run_in_executor(
                    self.executor, fetch_stats
                )
                
                if self.perf_counter:
                    async def get_perf_data():
                        return self.perf_counter.get_all_metrics()
                    
                    perf_data = await asyncio.get_event_loop().run_in_executor(
                        self.executor, get_perf_data
                    )
                    stats['performance_counter'] = perf_data
                
                return {'success': True, 'data': stats}
            
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/config", tags=["Config"])
        async def get_config():
            try:
                if not self.config_manager:
                    raise HTTPException(status_code=500, detail='Config manager not available')
                
                async def fetch_config():
                    return {
                        'app_categories': self.config_manager.get_app_categories(),
                        'scoring_rules': self.config_manager.get_scoring_rules(),
                        'cross_factors': self.config_manager.get_cross_factors()
                    }
                
                config = await asyncio.get_event_loop().run_in_executor(
                    self.executor, fetch_config
                )
                return {'success': True, 'data': config}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/config/categories", tags=["Config"])
        async def get_categories():
            try:
                if not self.config_manager:
                    raise HTTPException(status_code=500, detail='Config manager not available')
                
                async def fetch_categories():
                    return self.config_manager.get_all_category_ids()
                
                categories = await asyncio.get_event_loop().run_in_executor(
                    self.executor, fetch_categories
                )
                return {'success': True, 'data': categories}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/config/weights", tags=["Config"])
        async def get_weights():
            try:
                if not self.config_manager:
                    raise HTTPException(status_code=500, detail='Config manager not available')
                
                async def fetch_weights():
                    return self.config_manager.get_priority_scoring_weights()
                
                weights = await asyncio.get_event_loop().run_in_executor(
                    self.executor, fetch_weights
                )
                return {'success': True, 'data': weights}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/ml/train", tags=["ML"])
        async def train_ml_model():
            try:
                if not self.ml_model or not self.history_manager:
                    raise HTTPException(status_code=500, detail='ML model or history manager not available')
                
                async def train_model():
                    data = self.ml_model.prepare_training_data(self.history_manager)
                    return self.ml_model.train_model(data)
                
                result = await asyncio.get_event_loop().run_in_executor(
                    self.executor, train_model
                )
                
                return {'success': result['status'] == 'success', 'data': result}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/ml/info", tags=["ML"])
        async def get_ml_info():
            try:
                if not self.ml_model:
                    raise HTTPException(status_code=500, detail='ML model not available')
                
                async def get_info():
                    return self.ml_model.get_model_info()
                
                info = await asyncio.get_event_loop().run_in_executor(
                    self.executor, get_info
                )
                return {'success': True, 'data': info}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/ml/classifier/info", tags=["ML"])
        async def get_classifier_info():
            try:
                if not self.smart_classifier:
                    raise HTTPException(status_code=500, detail='Smart classifier not available')
                
                async def get_info():
                    return self.smart_classifier.get_model_info()
                
                info = await asyncio.get_event_loop().run_in_executor(
                    self.executor, get_info
                )
                return {'success': True, 'data': info}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        class PredictRequest(BaseModel):
            metrics: dict
        
        @self.app.post("/api/ml/predict", tags=["ML"])
        async def ml_predict(request: PredictRequest):
            try:
                if not self.ml_model:
                    raise HTTPException(status_code=500, detail='ML model not available')
                
                async def predict():
                    return self.ml_model.predict_score(request.metrics)
                
                score = await asyncio.get_event_loop().run_in_executor(
                    self.executor, predict
                )
                return {'success': True, 'data': {'score': score}}
            
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    
    def start(self):
        if self.running:
            return False
        
        self.running = True
        self.server_thread = threading.Thread(target=self._run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        print(f"FastAPI异步服务已启动: http://localhost:{self.port}")
        return True
    
    def _run_server(self):
        try:
            import uvicorn
            uvicorn.run(
                self.app,
                host='0.0.0.0',
                port=self.port,
                log_level='info',
                access_log=True
            )
        except Exception as e:
            print(f"FastAPI服务启动失败: {e}")
            self.running = False
    
    def stop(self):
        self.running = False
        if self.server_thread:
            self.server_thread.join(timeout=5)
        self.executor.shutdown(wait=True)
        print("FastAPI异步服务已停止")
        return True