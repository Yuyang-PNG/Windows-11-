import os
import json
import pickle
import threading
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

class SmartAppClassifier:
    def __init__(self, model_dir='ml/models'):
        self.model_dir = model_dir
        self.pipeline = None
        self.label_encoder = None
        self._lock = threading.RLock()
        self._ensure_dir()
        self._load_or_init_model()
    
    def _ensure_dir(self):
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
    
    def _get_model_path(self):
        return os.path.join(self.model_dir, 'classifier_pipeline.pkl')
    
    def _get_label_encoder_path(self):
        return os.path.join(self.model_dir, 'label_encoder.pkl')
    
    def _load_or_init_model(self):
        try:
            with open(self._get_model_path(), 'rb') as f:
                self.pipeline = pickle.load(f)
            
            with open(self._get_label_encoder_path(), 'rb') as f:
                self.label_encoder = pickle.load(f)
            
            return True
        except FileNotFoundError:
            self._init_default_model()
            return False
        except Exception as e:
            print(f"加载分类器模型失败: {e}")
            self._init_default_model()
            return False
    
    def _init_default_model(self):
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=5000,
                lowercase=True
            )),
            ('classifier', MultinomialNB(alpha=1.0))
        ])
        self.label_encoder = LabelEncoder()
    
    def _prepare_training_data(self, categories):
        X = []
        y = []
        
        for category, info in categories.items():
            if category == 'unknown':
                continue
            
            keywords = info.get('keywords', [])
            paths = info.get('paths', [])
            window_titles = info.get('window_titles', [])
            company_keywords = info.get('company_keywords', [])
            
            for kw in keywords:
                if isinstance(kw, str):
                    X.append(kw)
                    y.append(category)
            
            for path in paths:
                if isinstance(path, str):
                    X.append(path)
                    y.append(category)
            
            for title in window_titles:
                if isinstance(title, str):
                    X.append(title)
                    y.append(category)
            
            for company in company_keywords:
                if isinstance(company, str):
                    X.append(company)
                    y.append(category)
        
        return X, y
    
    def train(self, categories):
        with self._lock:
            X, y = self._prepare_training_data(categories)
            
            if len(X) < 5:
                print(f"配置文件训练数据不足 ({len(X)}条)，尝试使用内置默认分类数据")
                try:
                    from process_priority_manager import APP_CATEGORIES
                    default_X, default_y = self._prepare_training_data(APP_CATEGORIES)
                    X.extend(default_X)
                    y.extend(default_y)
                    print(f"补充默认数据后共 {len(X)} 条训练样本")
                except ImportError:
                    print("无法加载默认分类数据")
            
            if len(X) < 5:
                print(f"训练数据不足 ({len(X)}条)，跳过训练")
                return {'status': 'error', 'message': '数据不足'}
            
            if len(set(y)) < 2:
                print(f"分类类别不足 ({len(set(y))}个)，至少需要2个类别")
                return {'status': 'error', 'message': '类别不足'}
            
            self.label_encoder.fit(y)
            y_encoded = self.label_encoder.transform(y)
            
            self.pipeline.fit(X, y_encoded)
            
            with open(self._get_model_path(), 'wb') as f:
                pickle.dump(self.pipeline, f)
            
            with open(self._get_label_encoder_path(), 'wb') as f:
                pickle.dump(self.label_encoder, f)
            
            return {
                'status': 'success',
                'samples': len(X),
                'categories': list(self.label_encoder.classes_)
            }
    
    def predict(self, process_name, exe_path="", window_title="", threshold=0.3):
        with self._lock:
            features = [process_name]
            if exe_path:
                features.append(os.path.basename(exe_path))
                features.append(os.path.dirname(exe_path))
            if window_title:
                features.append(window_title)
            
            try:
                if not hasattr(self.pipeline.named_steps['classifier'], 'classes_'):
                    return 'unknown', 0.0
                
                X = [' '.join(features)]
                probs = self.pipeline.predict_proba(X)[0]
                
                max_prob = max(probs)
                category_idx = probs.argmax()
                category = self.label_encoder.inverse_transform([category_idx])[0]
                
                if max_prob >= threshold:
                    return category, max_prob
                return 'unknown', max_prob
            
            except Exception as e:
                print(f"分类预测失败: {e}")
                return 'unknown', 0.0
    
    def predict_with_fallback(self, process_name, exe_path="", window_title="", company_name=""):
        category, confidence = self.predict(process_name, exe_path, window_title)
        
        if category != 'unknown' and confidence >= 0.4:
            return category, confidence, 'ml'
        
        return None, confidence, 'fallback'
    
    def get_model_info(self):
        try:
            return {
                'status': 'loaded' if self.pipeline else 'not_trained',
                'categories': list(self.label_encoder.classes_) if self.label_encoder else [],
                'feature_count': len(self.pipeline.named_steps['tfidf'].vocabulary_) if self.pipeline else 0
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def reset_model(self):
        with self._lock:
            self._init_default_model()
            for path in [self._get_model_path(), self._get_label_encoder_path()]:
                if os.path.exists(path):
                    os.remove(path)
        return True