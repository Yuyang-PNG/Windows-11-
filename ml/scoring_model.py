import os
import json
import pickle
import numpy as np
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.impute import SimpleImputer

class MLScoringModel:
    def __init__(self, model_dir='ml/models'):
        self.model_dir = model_dir
        self.model = None
        self.scaler = None
        self.imputer = None
        self.feature_names = [
            'cpu', 'memory', 'threads', 'io', 'uptime_hours', 
            'is_gaming', 'is_design', 'is_ai', 'is_video', 
            'is_browser', 'is_productivity', 'is_system', 'is_running'
        ]
        self._ensure_dir()
        self._load_model()
    
    def _ensure_dir(self):
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
    
    def _get_model_path(self):
        return os.path.join(self.model_dir, 'scoring_model.pkl')
    
    def _get_scaler_path(self):
        return os.path.join(self.model_dir, 'scaler.pkl')
    
    def _get_imputer_path(self):
        return os.path.join(self.model_dir, 'imputer.pkl')
    
    def _load_model(self):
        try:
            with open(self._get_model_path(), 'rb') as f:
                self.model = pickle.load(f)
            
            with open(self._get_scaler_path(), 'rb') as f:
                self.scaler = pickle.load(f)
            
            with open(self._get_imputer_path(), 'rb') as f:
                self.imputer = pickle.load(f)
            
            return True
        except FileNotFoundError:
            self._create_default_model()
            return False
        except Exception as e:
            print(f"加载模型失败: {e}")
            self._create_default_model()
            return False
    
    def _create_default_model(self):
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.imputer = SimpleImputer(strategy='mean')
    
    def _extract_features(self, metrics):
        features = []
        
        features.append(metrics.get('cpu', 0))
        features.append(metrics.get('memory', 0))
        features.append(metrics.get('threads', 1))
        features.append(metrics.get('io', 0))
        features.append(min(metrics.get('uptime', 3600) / 3600, 24))
        
        category = metrics.get('category', 'unknown')
        features.append(1 if category == 'gaming' else 0)
        features.append(1 if category == 'design' else 0)
        features.append(1 if category == 'ai' else 0)
        features.append(1 if category == 'video' else 0)
        features.append(1 if category == 'browser' else 0)
        features.append(1 if category == 'productivity' else 0)
        features.append(1 if category == 'system' else 0)
        
        status = metrics.get('status', 'sleeping')
        features.append(1 if status == 'running' else 0)
        
        return np.array(features).reshape(1, -1)
    
    def predict_score(self, metrics):
        if self.model is None:
            return self._fallback_score(metrics)
        
        try:
            features = self._extract_features(metrics)
            features = self.imputer.transform(features)
            features = self.scaler.transform(features)
            score = self.model.predict(features)[0]
            return min(100, max(0, score))
        except Exception as e:
            print(f"预测失败，使用回退评分: {e}")
            return self._fallback_score(metrics)
    
    def _fallback_score(self, metrics):
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
    
    def train_model(self, historical_data):
        if len(historical_data) < 50:
            print(f"数据不足 ({len(historical_data)}条)，跳过训练")
            return {'status': 'error', 'message': '数据不足'}
        
        try:
            X = []
            y = []
            
            for record in historical_data:
                features = self._extract_features(record['metrics']).flatten()
                X.append(features)
                y.append(record['score'])
            
            X = np.array(X)
            y = np.array(y)
            
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )
            
            self.imputer.fit(X_train)
            X_train = self.imputer.transform(X_train)
            X_test = self.imputer.transform(X_test)
            
            self.scaler.fit(X_train)
            X_train = self.scaler.transform(X_train)
            X_test = self.scaler.transform(X_test)
            
            self.model.fit(X_train, y_train)
            
            y_pred_train = self.model.predict(X_train)
            y_pred_test = self.model.predict(X_test)
            
            train_mae = mean_absolute_error(y_train, y_pred_train)
            test_mae = mean_absolute_error(y_test, y_pred_test)
            r2 = r2_score(y_test, y_pred_test)
            
            with open(self._get_model_path(), 'wb') as f:
                pickle.dump(self.model, f)
            
            with open(self._get_scaler_path(), 'wb') as f:
                pickle.dump(self.scaler, f)
            
            with open(self._get_imputer_path(), 'wb') as f:
                pickle.dump(self.imputer, f)
            
            return {
                'status': 'success',
                'train_samples': len(X_train),
                'test_samples': len(X_test),
                'train_mae': train_mae,
                'test_mae': test_mae,
                'r2_score': r2,
                'feature_importance': dict(zip(self.feature_names, self.model.feature_importances_))
            }
        
        except Exception as e:
            print(f"训练失败: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def prepare_training_data(self, history_manager):
        snapshots = history_manager.get_recent_snapshots(minutes=1440, limit=1000)
        
        training_data = []
        for snap in snapshots:
            metrics = {
                'cpu': snap.get('cpu_percent', 0),
                'memory': snap.get('memory_percent', 0),
                'threads': snap.get('num_threads', 1),
                'io': 0,
                'uptime': 3600,
                'category': snap.get('category', 'unknown'),
                'status': 'running' if snap.get('cpu_percent', 0) > 1 else 'sleeping'
            }
            
            training_data.append({
                'metrics': metrics,
                'score': snap.get('score', 50)
            })
        
        return training_data
    
    def get_model_info(self):
        if self.model is None:
            return {'status': 'not_trained'}
        
        try:
            return {
                'status': 'loaded',
                'model_type': type(self.model).__name__,
                'feature_names': self.feature_names,
                'feature_importance': dict(zip(self.feature_names, self.model.feature_importances_))
            }
        except:
            return {'status': 'loaded', 'model_type': type(self.model).__name__}
    
    def reset_model(self):
        self._create_default_model()
        for path in [self._get_model_path(), self._get_scaler_path(), self._get_imputer_path()]:
            if os.path.exists(path):
                os.remove(path)
        return True