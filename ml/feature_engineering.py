import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


class FeatureEngineer:
    """特征工程模块 - 提供进程数据的特征提取和处理功能"""
    
    # 类别编码映射
    CATEGORY_MAP = {
        'gaming': 0,
        'design': 1,
        'ai': 2,
        'video': 3,
        'development': 4,
        'browser': 5,
        'productivity': 6,
        'system': 7,
        'security': 8,
        'utility': 9,
        'communication': 10,
        'music': 11,
        'cloud': 12,
        'unknown': 13
    }
    
    STATUS_MAP = {
        'running': 0,
        'sleeping': 1,
        'waiting': 2,
        'stopped': 3,
        'zombie': 4
    }
    
    PROCESS_TYPE_MAP = {
        'user_app': 0,
        'system': 1,
        'service': 2,
        'background': 3,
        'unknown': 4
    }
    
    def __init__(self):
        self.feature_names = self._get_feature_names()
    
    def _get_feature_names(self) -> List[str]:
        """获取所有特征名称"""
        base_features = ['cpu', 'memory', 'threads', 'io_read', 'io_write', 'uptime_hours']
        category_features = [f'category_{cat}' for cat in self.CATEGORY_MAP.keys()]
        status_features = [f'status_{status}' for status in self.STATUS_MAP.keys()]
        process_type_features = [f'proc_type_{pt}' for pt in self.PROCESS_TYPE_MAP.keys()]
        derived_features = ['cpu_memory_ratio', 'thread_density', 'is_active', 'is_recent', 'system_load_factor']
        
        return base_features + category_features + status_features + process_type_features + derived_features
    
    def extract_basic_features(self, metrics: Dict[str, Any]) -> List[float]:
        """提取基础特征"""
        features = []
        
        # CPU使用率 (0-100)
        features.append(min(100, max(0, metrics.get('cpu', 0))))
        
        # 内存使用率 (0-100)
        features.append(min(100, max(0, metrics.get('memory', 0))))
        
        # 线程数 (对数缩放)
        threads = max(1, metrics.get('threads', 1))
        features.append(np.log(threads))
        
        # IO读取速率 (MB/s)
        features.append(max(0, metrics.get('io_read', 0)))
        
        # IO写入速率 (MB/s)
        features.append(max(0, metrics.get('io_write', 0)))
        
        # 运行时间 (小时，最大24小时)
        uptime = min(24, max(0, metrics.get('uptime', 3600) / 3600))
        features.append(uptime)
        
        return features
    
    def extract_categorical_features(self, metrics: Dict[str, Any]) -> List[float]:
        """提取类别特征（独热编码）"""
        features = []
        
        # 应用类别独热编码
        category = metrics.get('category', 'unknown')
        for cat in self.CATEGORY_MAP.keys():
            features.append(1.0 if category == cat else 0.0)
        
        # 进程状态独热编码
        status = metrics.get('status', 'sleeping')
        for stat in self.STATUS_MAP.keys():
            features.append(1.0 if status == stat else 0.0)
        
        # 进程类型独热编码
        proc_type = metrics.get('proc_type', 'unknown')
        for pt in self.PROCESS_TYPE_MAP.keys():
            features.append(1.0 if proc_type == pt else 0.0)
        
        return features
    
    def extract_derived_features(self, metrics: Dict[str, Any], system_metrics: Optional[Dict[str, Any]] = None) -> List[float]:
        """提取派生特征"""
        features = []
        
        cpu = metrics.get('cpu', 0)
        memory = metrics.get('memory', 0)
        threads = metrics.get('threads', 1)
        uptime = metrics.get('uptime', 3600)
        
        # CPU/内存比率
        if memory > 0:
            features.append(cpu / memory)
        else:
            features.append(0.0)
        
        # 线程密度（每核线程数）
        cpu_count = system_metrics.get('cpu_count', 4) if system_metrics else 4
        features.append(threads / cpu_count)
        
        # 是否活跃（CPU > 5% 或 内存 > 1%）
        features.append(1.0 if cpu > 5 or memory > 1 else 0.0)
        
        # 是否是最近启动的进程（小于30分钟）
        features.append(1.0 if uptime < 1800 else 0.0)
        
        # 系统负载因子（系统负载越高，进程优先级调整越保守）
        if system_metrics:
            system_load = (system_metrics.get('cpu_percent', 0) + system_metrics.get('memory_percent', 0)) / 200
            features.append(system_load)
        else:
            features.append(0.5)
        
        return features
    
    def extract_all_features(self, metrics: Dict[str, Any], system_metrics: Optional[Dict[str, Any]] = None) -> np.ndarray:
        """提取所有特征并返回numpy数组"""
        basic = self.extract_basic_features(metrics)
        categorical = self.extract_categorical_features(metrics)
        derived = self.extract_derived_features(metrics, system_metrics)
        
        return np.array(basic + categorical + derived, dtype=np.float64)
    
    def create_feature_vector(self, metrics: Dict[str, Any], system_metrics: Optional[Dict[str, Any]] = None) -> np.ndarray:
        """创建标准化的特征向量"""
        features = self.extract_all_features(metrics, system_metrics)
        return features.reshape(1, -1)
    
    def batch_extract_features(self, records: List[Dict[str, Any]], system_metrics: Optional[Dict[str, Any]] = None) -> np.ndarray:
        """批量提取特征"""
        features = []
        for record in records:
            metrics = record.get('metrics', record)
            feat = self.extract_all_features(metrics, system_metrics)
            features.append(feat)
        
        return np.array(features, dtype=np.float64)
    
    def get_feature_importance_template(self) -> Dict[str, float]:
        """获取特征重要性模板"""
        return {name: 0.0 for name in self.feature_names}
    
    @staticmethod
    def normalize_features(X: np.ndarray, feature_ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> np.ndarray:
        """归一化特征"""
        X_normalized = X.copy()
        
        # 默认特征范围
        default_ranges = {
            'cpu': (0, 100),
            'memory': (0, 100),
            'threads': (0, np.log(100)),
            'io_read': (0, 1000),
            'io_write': (0, 1000),
            'uptime_hours': (0, 24)
        }
        
        ranges = feature_ranges or default_ranges
        
        for i, name in enumerate(['cpu', 'memory', 'threads', 'io_read', 'io_write', 'uptime_hours']):
            if i < X_normalized.shape[1]:
                min_val, max_val = ranges.get(name, (0, 1))
                range_val = max_val - min_val
                if range_val > 0:
                    X_normalized[:, i] = (X_normalized[:, i] - min_val) / range_val
        
        return X_normalized
    
    @staticmethod
    def add_temporal_features(X: np.ndarray, timestamps: Optional[List[datetime]] = None) -> np.ndarray:
        """添加时间特征"""
        if timestamps is None or len(timestamps) != X.shape[0]:
            return X
        
        temporal_features = []
        for ts in timestamps:
            # 小时（0-23，正弦编码）
            hour_norm = ts.hour / 23.0
            temporal_features.append([
                np.sin(2 * np.pi * hour_norm),
                np.cos(2 * np.pi * hour_norm),
                ts.isoweekday() / 7.0,  # 星期几
                1.0 if ts.hour >= 9 and ts.hour <= 18 else 0.0  # 是否工作时间
            ])
        
        temporal_array = np.array(temporal_features, dtype=np.float64)
        return np.concatenate([X, temporal_array], axis=1)


class FeatureSelector:
    """特征选择器 - 基于重要性选择特征"""
    
    def __init__(self, threshold: float = 0.01):
        self.threshold = threshold
        self.selected_indices = None
    
    def fit(self, feature_importances: np.ndarray, feature_names: List[str]):
        """根据特征重要性选择特征"""
        mask = feature_importances >= self.threshold
        self.selected_indices = np.where(mask)[0]
        
        selected_names = [feature_names[i] for i in self.selected_indices]
        dropped_names = [feature_names[i] for i in np.where(~mask)[0]]
        
        return {
            'selected': selected_names,
            'dropped': dropped_names,
            'selected_count': len(selected_names),
            'dropped_count': len(dropped_names)
        }
    
    def transform(self, X: np.ndarray) -> np.ndarray:
        """应用特征选择"""
        if self.selected_indices is None:
            return X
        return X[:, self.selected_indices]
    
    def fit_transform(self, X: np.ndarray, feature_importances: np.ndarray, feature_names: List[str]) -> np.ndarray:
        """拟合并转换"""
        self.fit(feature_importances, feature_names)
        return self.transform(X)