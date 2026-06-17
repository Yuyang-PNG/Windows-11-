"""
多维特征分类器
融合文本特征、行为特征、路径特征和网络特征进行智能分类
"""
import os
import re
import time
import threading
import pickle
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
from datetime import datetime
import logging

logger = logging.getLogger('process_priority_manager')

# 尝试导入ML库
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.neural_network import MLPClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn不可用，多维特征分类器将使用简化模式")


class TextFeatureExtractor:
    """
    文本特征提取器
    
    从进程名、路径、窗口标题等提取文本特征
    """
    
    def __init__(self, max_features: int = 3000):
        self._max_features = max_features
        self._vectorizer = None
        self._lock = threading.Lock()
        
        if SKLEARN_AVAILABLE:
            self._vectorizer = TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=max_features,
                lowercase=True,
                min_df=1
            )
    
    def fit(self, texts: List[str]):
        """训练文本特征提取器"""
        if not SKLEARN_AVAILABLE or not texts:
            return
        
        with self._lock:
            self._vectorizer.fit(texts)
    
    def transform(self, texts: List[str]) -> np.ndarray:
        """提取文本特征"""
        if not SKLEARN_AVAILABLE or not texts or self._vectorizer is None:
            return np.zeros((len(texts), 100))
        
        with self._lock:
            try:
                return self._vectorizer.transform(texts).toarray()
            except Exception:
                return np.zeros((len(texts), 100))
    
    def fit_transform(self, texts: List[str]) -> np.ndarray:
        """训练并提取特征"""
        if not SKLEARN_AVAILABLE or not texts:
            return np.zeros((len(texts), 100))
        
        with self._lock:
            try:
                return self._vectorizer.fit_transform(texts).toarray()
            except Exception:
                return np.zeros((len(texts), 100))


class BehaviorFeatureExtractor:
    """
    行为特征提取器
    
    从进程行为数据提取特征：CPU、内存、IO、线程等
    """
    
    def __init__(self):
        # 特征维度定义
        self._feature_names = [
            'cpu_percent',      # CPU使用率
            'memory_percent',   # 内存使用率
            'num_threads',      # 线程数
            'io_read_rate',     # IO读取速率
            'io_write_rate',    # IO写入速率
            'uptime_seconds',   # 运行时长
            'is_foreground',    # 是否前台
            'has_window',       # 是否有窗口
            'network_activity', # 网络活动
            'gpu_usage'         # GPU使用率
        ]
        self._scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self._lock = threading.Lock()
    
    def extract(self, process_info: Dict[str, Any]) -> np.ndarray:
        """
        提取行为特征
        
        Args:
            process_info: 进程信息字典
            
        Returns:
            特征向量
        """
        features = [
            min(100, process_info.get('cpu_percent', 0)) / 100.0,
            min(100, process_info.get('memory_percent', 0)) / 100.0,
            min(100, process_info.get('num_threads', 1)) / 100.0,
            min(1000, process_info.get('io_read_rate', 0)) / 1000.0,
            min(1000, process_info.get('io_write_rate', 0)) / 1000.0,
            min(86400, process_info.get('uptime_seconds', 0)) / 86400.0,  # 归一化到1天
            1.0 if process_info.get('is_foreground', False) else 0.0,
            1.0 if process_info.get('has_window', False) else 0.0,
            min(100, process_info.get('network_activity', 0)) / 100.0,
            min(100, process_info.get('gpu_usage', 0)) / 100.0
        ]
        
        return np.array(features)
    
    def extract_batch(self, process_infos: List[Dict[str, Any]]) -> np.ndarray:
        """批量提取特征"""
        return np.array([self.extract(info) for info in process_infos])
    
    def fit_transform(self, process_infos: List[Dict[str, Any]]) -> np.ndarray:
        """训练并转换"""
        features = self.extract_batch(process_infos)
        
        if SKLEARN_AVAILABLE and len(features) > 0:
            with self._lock:
                return self._scaler.fit_transform(features)
        
        return features
    
    def transform(self, process_infos: List[Dict[str, Any]]) -> np.ndarray:
        """转换特征"""
        features = self.extract_batch(process_infos)
        
        if SKLEARN_AVAILABLE and self._scaler is not None:
            with self._lock:
                try:
                    return self._scaler.transform(features)
                except Exception:
                    return features
        
        return features


class PathFeatureExtractor:
    """
    路径特征提取器
    
    从可执行路径提取特征：目录结构、签名信息等
    """
    
    def __init__(self):
        # 已知的程序目录模式
        self._known_patterns = {
            'system': ['windows\\system32', 'windows\\syswow64'],
            'program_files': ['program files', 'program files (x86)'],
            'user': ['users\\', 'appdata'],
            'games': ['steam', 'epic games', 'games', 'gog'],
            'dev': ['python', 'nodejs', 'java', 'code', 'visual studio'],
            'portable': ['portable', 'tools', 'bin']
        }
        
        # 已知的公司/签名
        self._known_companies = {
            'microsoft': ['microsoft', 'windows'],
            'google': ['google', 'chrome'],
            'mozilla': ['mozilla', 'firefox'],
            'valve': ['valve', 'steam'],
            'adobe': ['adobe'],
            'jetbrains': ['jetbrains'],
            'tencent': ['tencent', 'qq', 'wechat'],
            'netease': ['netease'],
            'mihoyo': ['mihoyo', '米哈游']
        }
    
    def extract(self, exe_path: str, company_name: str = None) -> np.ndarray:
        """
        提取路径特征
        
        Args:
            exe_path: 可执行文件路径
            company_name: 公司名称
            
        Returns:
            特征向量
        """
        path_lower = (exe_path or '').lower()
        company_lower = (company_name or '').lower()
        
        features = []
        
        # 目录模式特征
        for pattern_name, patterns in self._known_patterns.items():
            matched = any(p in path_lower for p in patterns)
            features.append(1.0 if matched else 0.0)
        
        # 公司特征
        for company_key, patterns in self._known_companies.items():
            matched = any(p in company_lower or p in path_lower for p in patterns)
            features.append(1.0 if matched else 0.0)
        
        # 路径深度特征
        depth = path_lower.count('\\') if path_lower else 0
        features.append(min(depth / 10.0, 1.0))
        
        # 是否为系统路径
        is_system = 'windows' in path_lower or 'system32' in path_lower
        features.append(1.0 if is_system else 0.0)
        
        # 是否为用户安装
        is_user = 'users' in path_lower or 'appdata' in path_lower
        features.append(1.0 if is_user else 0.0)
        
        return np.array(features)
    
    def extract_batch(
        self,
        exe_paths: List[str],
        company_names: List[str] = None
    ) -> np.ndarray:
        """批量提取"""
        company_names = company_names or [None] * len(exe_paths)
        return np.array([
            self.extract(path, company)
            for path, company in zip(exe_paths, company_names)
        ])


class NetworkFeatureExtractor:
    """
    网络特征提取器
    
    从网络连接信息提取特征
    """
    
    def __init__(self):
        # 已知的网络服务端口
        self._known_ports = {
            'web': [80, 443, 8080, 8443],
            'game': [27015, 27016, 7777, 25565],  # Steam, Minecraft
            'chat': [5222, 5223, 443],  # XMPP, etc
            'file': [21, 22, 445, 139],  # FTP, SSH, SMB
            'database': [3306, 5432, 27017, 6379]  # MySQL, PostgreSQL, MongoDB, Redis
        }
    
    def extract(self, network_info: Dict[str, Any]) -> np.ndarray:
        """
        提取网络特征
        
        Args:
            network_info: 网络信息字典
            
        Returns:
            特征向量
        """
        features = []
        
        # 连接数特征
        connections = network_info.get('connections', 0)
        features.append(min(connections / 100.0, 1.0))
        
        # 监听端口数
        listening = network_info.get('listening_ports', 0)
        features.append(min(listening / 20.0, 1.0))
        
        # 已知端口类型
        ports = network_info.get('ports', [])
        for port_type, port_list in self._known_ports.items():
            has_port = any(p in ports for p in port_list)
            features.append(1.0 if has_port else 0.0)
        
        # 流量特征
        bytes_sent = network_info.get('bytes_sent', 0)
        bytes_recv = network_info.get('bytes_recv', 0)
        features.append(min(bytes_sent / 1e9, 1.0))  # 归一化到1GB
        features.append(min(bytes_recv / 1e9, 1.0))
        
        # 是否有外部连接
        has_external = network_info.get('has_external_connection', False)
        features.append(1.0 if has_external else 0.0)
        
        return np.array(features)
    
    def extract_batch(self, network_infos: List[Dict[str, Any]]) -> np.ndarray:
        """批量提取"""
        return np.array([self.extract(info) for info in network_infos])


class MultiModalClassifier:
    """
    多模态分类器
    
    融合文本、行为、路径、网络等多维特征进行分类
    """
    
    def __init__(self, model_dir: str = 'ml/models'):
        """
        初始化多模态分类器
        
        Args:
            model_dir: 模型保存目录
        """
        self._model_dir = model_dir
        self._lock = threading.RLock()
        
        # 特征提取器
        self._text_extractor = TextFeatureExtractor()
        self._behavior_extractor = BehaviorFeatureExtractor()
        self._path_extractor = PathFeatureExtractor()
        self._network_extractor = NetworkFeatureExtractor()
        
        # 分类器
        self._text_classifier = None
        self._behavior_classifier = None
        self._fusion_classifier = None
        self._label_encoder = LabelEncoder() if SKLEARN_AVAILABLE else None
        
        # 特征权重
        self._weights = {
            'text': 0.35,
            'behavior': 0.25,
            'path': 0.25,
            'network': 0.15
        }
        
        # 缓存
        self._prediction_cache = {}
        self._cache_ttl = 300  # 5分钟
        
        self._ensure_dir()
    
    def _ensure_dir(self):
        """确保模型目录存在"""
        if not os.path.exists(self._model_dir):
            os.makedirs(self._model_dir)
    
    def _prepare_training_data(
        self,
        categories: Dict[str, Dict[str, Any]]
    ) -> Tuple[List[str], List[Dict], List[str], List[str]]:
        """
        准备训练数据
        
        Returns:
            (texts, behaviors, paths, labels)
        """
        texts = []
        behaviors = []
        paths = []
        labels = []
        
        for category, info in categories.items():
            if category == 'unknown':
                continue
            
            keywords = info.get('keywords', [])
            category_paths = info.get('paths', [])
            window_titles = info.get('window_titles', [])
            company_keywords = info.get('company_keywords', [])
            
            # 文本特征
            for kw in keywords:
                texts.append(kw)
                labels.append(category)
            
            for title in window_titles:
                texts.append(title)
                labels.append(category)
            
            # 路径特征
            for path in category_paths:
                paths.append(path)
                labels.append(category)
            
            # 模拟行为特征（基于类别特征）
            base_behavior = self._get_category_behavior(category)
            for _ in range(len(keywords)):
                behaviors.append(base_behavior)
        
        return texts, behaviors, paths, labels
    
    def _get_category_behavior(self, category: str) -> Dict[str, Any]:
        """获取类别典型行为特征"""
        behavior_profiles = {
            'gaming': {
                'cpu_percent': 50, 'memory_percent': 30, 'num_threads': 20,
                'gpu_usage': 60, 'is_foreground': True, 'has_window': True
            },
            'video': {
                'cpu_percent': 30, 'memory_percent': 20, 'num_threads': 10,
                'gpu_usage': 20, 'is_foreground': True, 'has_window': True
            },
            'browser': {
                'cpu_percent': 15, 'memory_percent': 25, 'num_threads': 30,
                'network_activity': 50, 'is_foreground': True, 'has_window': True
            },
            'development': {
                'cpu_percent': 25, 'memory_percent': 40, 'num_threads': 15,
                'is_foreground': True, 'has_window': True
            },
            'design': {
                'cpu_percent': 40, 'memory_percent': 50, 'num_threads': 10,
                'gpu_usage': 40, 'is_foreground': True, 'has_window': True
            },
            'ai': {
                'cpu_percent': 60, 'memory_percent': 60, 'num_threads': 8,
                'gpu_usage': 80, 'is_foreground': True, 'has_window': True
            },
            'system': {
                'cpu_percent': 5, 'memory_percent': 5, 'num_threads': 5,
                'is_foreground': False, 'has_window': False
            },
            'communication': {
                'cpu_percent': 10, 'memory_percent': 15, 'num_threads': 20,
                'network_activity': 30, 'is_foreground': False, 'has_window': True
            }
        }
        
        return behavior_profiles.get(category, {
            'cpu_percent': 20, 'memory_percent': 20, 'num_threads': 10
        })
    
    def train(self, categories: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        训练分类器
        
        Args:
            categories: 类别配置
            
        Returns:
            训练结果
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn不可用'}
        
        with self._lock:
            texts, behaviors, paths, labels = self._prepare_training_data(categories)
            
            if len(set(labels)) < 2:
                return {'status': 'error', 'message': '类别数量不足'}
            
            # 编码标签
            self._label_encoder.fit(labels)
            y = self._label_encoder.transform(labels)
            
            # 训练文本分类器
            if texts:
                text_features = self._text_extractor.fit_transform(texts)
                if len(text_features) > 0 and text_features.shape[1] > 0:
                    self._text_classifier = RandomForestClassifier(
                        n_estimators=50,
                        max_depth=10,
                        random_state=42
                    )
                    # 对齐特征和标签
                    min_len = min(len(text_features), len(y))
                    self._text_classifier.fit(text_features[:min_len], y[:min_len])
            
            # 训练行为分类器
            if behaviors:
                behavior_features = self._behavior_extractor.fit_transform(behaviors)
                if len(behavior_features) > 0:
                    self._behavior_classifier = MLPClassifier(
                        hidden_layer_sizes=(64, 32),
                        max_iter=200,
                        random_state=42
                    )
                    min_len = min(len(behavior_features), len(y))
                    self._behavior_classifier.fit(behavior_features[:min_len], y[:min_len])
            
            # 保存模型
            self._save_model()
            
            return {
                'status': 'success',
                'samples': len(labels),
                'categories': list(self._label_encoder.classes_)
            }
    
    def predict(
        self,
        process_name: str,
        exe_path: str = '',
        window_title: str = '',
        company_name: str = '',
        process_info: Dict[str, Any] = None,
        network_info: Dict[str, Any] = None
    ) -> Tuple[str, float, Dict[str, float]]:
        """
        预测进程类别
        
        Args:
            process_name: 进程名
            exe_path: 可执行路径
            window_title: 窗口标题
            company_name: 公司名称
            process_info: 进程行为信息
            network_info: 网络信息
            
        Returns:
            (类别, 置信度, 各特征贡献)
        """
        # 检查缓存
        cache_key = (process_name.lower(), exe_path.lower() if exe_path else '')
        cached = self._get_cached_prediction(cache_key)
        if cached:
            return cached
        
        with self._lock:
            contributions = {}
            all_probs = []
            
            # 文本特征预测
            if self._text_classifier is not None:
                text = f"{process_name} {window_title} {exe_path}"
                text_feat = self._text_extractor.transform([text])
                try:
                    probs = self._text_classifier.predict_proba(text_feat)[0]
                    all_probs.append(probs * self._weights['text'])
                    contributions['text'] = float(max(probs))
                except Exception:
                    pass
            
            # 行为特征预测
            if self._behavior_classifier is not None and process_info:
                behavior_feat = self._behavior_extractor.transform([process_info])
                try:
                    probs = self._behavior_classifier.predict_proba(behavior_feat)[0]
                    all_probs.append(probs * self._weights['behavior'])
                    contributions['behavior'] = float(max(probs))
                except Exception:
                    pass
            
            # 路径特征预测（基于规则）
            path_feat = self._path_extractor.extract(exe_path, company_name)
            path_score = self._score_path_features(path_feat)
            contributions['path'] = path_score
            
            # 融合预测
            if all_probs:
                fused_probs = sum(all_probs)
                category_idx = np.argmax(fused_probs)
                confidence = float(fused_probs[category_idx])
                category = self._label_encoder.inverse_transform([category_idx])[0]
            else:
                # 回退到路径特征
                category = self._predict_by_path(exe_path, company_name)
                confidence = path_score
            
            # 缓存结果
            self._cache_prediction(cache_key, (category, confidence, contributions))
            
            return category, confidence, contributions
    
    def _score_path_features(self, path_features: np.ndarray) -> float:
        """计算路径特征得分"""
        # 简单加权求和
        weights = np.array([0.1, 0.1, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1, 0.05, 0.05])
        if len(path_features) >= len(weights):
            return float(np.dot(path_features[:len(weights)], weights))
        return 0.5
    
    def _predict_by_path(self, exe_path: str, company_name: str) -> str:
        """基于路径预测类别"""
        path_lower = (exe_path or '').lower()
        company_lower = (company_name or '').lower()
        
        # 游戏路径
        game_patterns = ['steam', 'epic', 'games', 'gog', 'battle.net', 'riot']
        if any(p in path_lower for p in game_patterns):
            return 'gaming'
        
        # 开发工具路径
        dev_patterns = ['python', 'nodejs', 'code', 'visual studio', 'jetbrains', 'eclipse']
        if any(p in path_lower for p in dev_patterns):
            return 'development'
        
        # 设计软件路径
        design_patterns = ['adobe', 'autodesk', 'blender']
        if any(p in path_lower for p in design_patterns):
            return 'design'
        
        # 系统路径
        if 'windows\\system32' in path_lower or 'windows\\syswow64' in path_lower:
            return 'system'
        
        return 'unknown'
    
    def _get_cached_prediction(self, key: Tuple) -> Optional[Tuple]:
        """获取缓存的预测结果"""
        if key in self._prediction_cache:
            result, timestamp = self._prediction_cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return result
            del self._prediction_cache[key]
        return None
    
    def _cache_prediction(self, key: Tuple, result: Tuple):
        """缓存预测结果"""
        self._prediction_cache[key] = (result, time.time())
        
        # 清理过期缓存
        if len(self._prediction_cache) > 1000:
            current_time = time.time()
            expired = [
                k for k, (_, t) in self._prediction_cache.items()
                if current_time - t > self._cache_ttl
            ]
            for k in expired:
                del self._prediction_cache[k]
    
    def _save_model(self):
        """保存模型"""
        try:
            model_path = os.path.join(self._model_dir, 'multimodal_classifier.pkl')
            with open(model_path, 'wb') as f:
                pickle.dump({
                    'text_classifier': self._text_classifier,
                    'behavior_classifier': self._behavior_classifier,
                    'label_encoder': self._label_encoder,
                    'weights': self._weights
                }, f)
        except Exception as e:
            logger.warning(f"保存模型失败: {e}")
    
    def _load_model(self) -> bool:
        """加载模型"""
        try:
            model_path = os.path.join(self._model_dir, 'multimodal_classifier.pkl')
            if os.path.exists(model_path):
                with open(model_path, 'rb') as f:
                    data = pickle.load(f)
                self._text_classifier = data.get('text_classifier')
                self._behavior_classifier = data.get('behavior_classifier')
                self._label_encoder = data.get('label_encoder')
                self._weights = data.get('weights', self._weights)
                return True
        except Exception as e:
            logger.warning(f"加载模型失败: {e}")
        return False
    
    def get_info(self) -> Dict[str, Any]:
        """获取分类器信息"""
        return {
            'status': 'trained' if self._text_classifier else 'not_trained',
            'categories': list(self._label_encoder.classes_) if self._label_encoder else [],
            'weights': self._weights,
            'cache_size': len(self._prediction_cache)
        }


# 便捷函数
def create_multimodal_classifier(model_dir: str = 'ml/models') -> MultiModalClassifier:
    """创建多模态分类器"""
    return MultiModalClassifier(model_dir=model_dir)
