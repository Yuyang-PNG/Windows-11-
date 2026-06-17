import os
import json
import pickle
import numpy as np
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from ml.feature_engineering import FeatureEngineer


class AutoTrainer:
    """自动训练器 - 自动化数据收集、模型训练和部署"""
    
    def __init__(self, model_dir: str = 'ml/models', min_samples: int = 100):
        self.model_dir = model_dir
        self.min_samples = min_samples
        self.feature_engineer = FeatureEngineer()
        self._lock = threading.RLock()
        self._training_in_progress = False
        self._last_train_time = None
        self._model_performance = {}
        
        self._ensure_dir()
    
    def _ensure_dir(self):
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
    
    def _get_model_path(self, model_name: str = 'auto_scoring_model') -> str:
        return os.path.join(self.model_dir, f'{model_name}.pkl')
    
    def _get_pipeline_path(self, model_name: str = 'auto_scoring_model') -> str:
        return os.path.join(self.model_dir, f'{model_name}_pipeline.pkl')
    
    def _get_stats_path(self) -> str:
        return os.path.join(self.model_dir, 'training_stats.json')
    
    def collect_training_data(self, history_manager) -> List[Dict[str, Any]]:
        """从历史管理器收集训练数据"""
        snapshots = history_manager.get_recent_snapshots(minutes=4320, limit=5000)
        
        training_data = []
        for snap in snapshots:
            metrics = {
                'cpu': snap.get('cpu_percent', 0),
                'memory': snap.get('memory_percent', 0),
                'threads': snap.get('num_threads', 1),
                'io_read': snap.get('io_read', 0),
                'io_write': snap.get('io_write', 0),
                'uptime': snap.get('uptime', 3600),
                'category': snap.get('category', 'unknown'),
                'status': snap.get('status', 'running'),
                'proc_type': snap.get('proc_type', 'unknown')
            }
            
            training_data.append({
                'metrics': metrics,
                'score': snap.get('score', 50),
                'timestamp': snap.get('timestamp')
            })
        
        return training_data
    
    def prepare_features(self, training_data: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray]:
        """准备特征和标签"""
        X = self.feature_engineer.batch_extract_features(training_data)
        y = np.array([record['score'] for record in training_data], dtype=np.float64)
        
        return X, y
    
    def build_pipeline(self, model_type: str = 'random_forest') -> Pipeline:
        """构建机器学习管道"""
        if model_type == 'gradient_boosting':
            model = GradientBoostingRegressor(
                n_estimators=150,
                max_depth=8,
                learning_rate=0.1,
                random_state=42
            )
        else:
            model = RandomForestRegressor(
                n_estimators=200,
                max_depth=12,
                min_samples_split=5,
                min_samples_leaf=3,
                random_state=42
            )
        
        pipeline = Pipeline([
            ('imputer', SimpleImputer(strategy='mean')),
            ('scaler', RobustScaler()),
            ('model', model)
        ])
        
        return pipeline
    
    def train(self, X: np.ndarray, y: np.ndarray, model_type: str = 'random_forest', 
              validate: bool = True) -> Dict[str, Any]:
        """训练模型"""
        if len(X) < self.min_samples:
            return {
                'status': 'error',
                'message': f'数据不足，需要至少{self.min_samples}条样本，当前{len(X)}条'
            }
        
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            pipeline = self.build_pipeline(model_type)
            pipeline.fit(X_train, y_train)
            
            # 评估
            y_pred_train = pipeline.predict(X_train)
            y_pred_test = pipeline.predict(X_test)
            
            results = {
                'status': 'success',
                'train_samples': len(X_train),
                'test_samples': len(X_test),
                'train_mae': mean_absolute_error(y_train, y_pred_train),
                'test_mae': mean_absolute_error(y_test, y_pred_test),
                'train_mse': mean_squared_error(y_train, y_pred_train),
                'test_mse': mean_squared_error(y_test, y_pred_test),
                'train_r2': r2_score(y_train, y_pred_train),
                'test_r2': r2_score(y_test, y_pred_test),
                'model_type': model_type
            }
            
            # 交叉验证
            if validate:
                cv_scores = cross_val_score(pipeline, X, y, cv=5, scoring='r2')
                results['cv_r2_mean'] = np.mean(cv_scores)
                results['cv_r2_std'] = np.std(cv_scores)
            
            # 特征重要性
            model = pipeline.named_steps['model']
            if hasattr(model, 'feature_importances_'):
                results['feature_importance'] = dict(
                    zip(self.feature_engineer.feature_names, model.feature_importances_)
                )
            
            # 保存模型
            with open(self._get_model_path(), 'wb') as f:
                pickle.dump(model, f)
            
            with open(self._get_pipeline_path(), 'wb') as f:
                pickle.dump(pipeline, f)
            
            # 保存训练统计
            results['training_time'] = datetime.now().isoformat()
            self._save_training_stats(results)
            
            self._last_train_time = datetime.now()
            self._model_performance = results
            
            return results
        
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _save_training_stats(self, stats: Dict[str, Any]):
        """保存训练统计"""
        try:
            existing = {}
            if os.path.exists(self._get_stats_path()):
                with open(self._get_stats_path(), 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            
            history = existing.get('history', [])
            history.append(stats)
            
            with open(self._get_stats_path(), 'w', encoding='utf-8') as f:
                json.dump({
                    'last_training': stats,
                    'history': history[-20:],
                    'total_trainings': len(history)
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存训练统计失败: {e}")
    
    def auto_train(self, history_manager, model_type: str = 'random_forest') -> Dict[str, Any]:
        """自动执行训练流程"""
        with self._lock:
            if self._training_in_progress:
                return {'status': 'error', 'message': '训练正在进行中'}
            
            self._training_in_progress = True
            
            try:
                # 收集数据
                data = self.collect_training_data(history_manager)
                if len(data) < self.min_samples:
                    return {
                        'status': 'error',
                        'message': f'数据不足，需要至少{self.min_samples}条样本，当前{len(data)}条'
                    }
                
                # 准备特征
                X, y = self.prepare_features(data)
                
                # 训练
                result = self.train(X, y, model_type)
                
                return result
            finally:
                self._training_in_progress = False
    
    def schedule_training(self, history_manager, interval_hours: int = 24):
        """定时自动训练"""
        def trainer_loop():
            while True:
                try:
                    result = self.auto_train(history_manager)
                    if result['status'] == 'success':
                        print(f"自动训练完成: R2={result['test_r2']:.4f}")
                    else:
                        print(f"自动训练失败: {result.get('message')}")
                except Exception as e:
                    print(f"定时训练异常: {e}")
                
                time.sleep(interval_hours * 3600)
        
        thread = threading.Thread(target=trainer_loop, daemon=True)
        thread.start()
        return thread
    
    def get_training_stats(self) -> Dict[str, Any]:
        """获取训练统计"""
        if os.path.exists(self._get_stats_path()):
            with open(self._get_stats_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def get_model_performance(self) -> Dict[str, Any]:
        """获取当前模型性能"""
        return self._model_performance
    
    def needs_retraining(self, min_improvement: float = 0.02) -> bool:
        """判断是否需要重新训练"""
        if self._last_train_time is None:
            return True
        
        # 超过一周没有训练
        if datetime.now() - self._last_train_time > timedelta(days=7):
            return True
        
        # 性能下降超过阈值
        if self._model_performance:
            test_r2 = self._model_performance.get('test_r2', 0)
            if test_r2 < 0.6:  # R2低于0.6需要重新训练
                return True
        
        return False
    
    def predict(self, metrics: Dict[str, Any], system_metrics: Optional[Dict[str, Any]] = None) -> float:
        """使用训练好的模型进行预测"""
        try:
            with open(self._get_pipeline_path(), 'rb') as f:
                pipeline = pickle.load(f)
            
            features = self.feature_engineer.create_feature_vector(metrics, system_metrics)
            score = pipeline.predict(features)[0]
            
            return min(100, max(0, score))
        except FileNotFoundError:
            return self._fallback_score(metrics)
        except Exception as e:
            print(f"预测失败，使用回退评分: {e}")
            return self._fallback_score(metrics)
    
    def _fallback_score(self, metrics: Dict[str, Any]) -> float:
        """回退评分方法"""
        category = metrics.get('category', 'unknown')
        category_scores = {
            'gaming': 75, 'design': 65, 'ai': 65, 'video': 55,
            'development': 55, 'browser': 45, 'productivity': 45,
            'system': 50, 'security': 40, 'utility': 40, 'unknown': 45
        }
        
        base = category_scores.get(category, 45)
        cpu_score = min(25, metrics.get('cpu', 0) * 0.5)
        memory_score = min(20, metrics.get('memory', 0) * 0.4)
        
        return min(100, base + cpu_score + memory_score)
    
    def compare_models(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """比较不同模型的性能"""
        results = {}
        
        for model_type in ['random_forest', 'gradient_boosting']:
            pipeline = self.build_pipeline(model_type)
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            pipeline.fit(X_train, y_train)
            y_pred = pipeline.predict(X_test)
            
            results[model_type] = {
                'mae': mean_absolute_error(y_test, y_pred),
                'mse': mean_squared_error(y_test, y_pred),
                'r2': r2_score(y_test, y_pred)
            }
        
        best_model = max(results.keys(), key=lambda k: results[k]['r2'])
        results['best_model'] = best_model
        
        return results