import os
import pickle
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional

class RLTrainer:
    def __init__(self, agent=None):
        self.agent = agent
        self.history_manager = None
        self.model_path = 'ml/models/rl_agent.pkl'
    
    def set_agent(self, agent):
        self.agent = agent
    
    def set_history_manager(self, history_manager):
        self.history_manager = history_manager
    
    def train_from_history(self, episodes: int = 100) -> Dict:
        """从历史数据训练RL代理"""
        if not self.agent or not self.history_manager:
            return {'status': 'error', 'message': 'Agent或HistoryManager未初始化'}
        
        for episode in range(episodes):
            snapshots = self.history_manager.get_recent_snapshots(minutes=60, limit=100)
            
            for i in range(len(snapshots) - 1):
                current = snapshots[i]
                next_snapshot = snapshots[i + 1]
                
                state = self.agent.get_state(
                    current.get('cpu_percent', 0),
                    current.get('memory_percent', 0),
                    current.get('category', 'unknown'),
                    datetime.now().hour,
                    current.get('category') == 'gaming'
                )
                
                action = self.agent.choose_action(state)
                
                system_metrics = {
                    'cpu_percent': next_snapshot.get('cpu_percent', 0),
                    'memory_percent': next_snapshot.get('memory_percent', 0)
                }
                reward = self.agent.calculate_reward(current, system_metrics)
                
                next_state = self.agent.get_state(
                    next_snapshot.get('cpu_percent', 0),
                    next_snapshot.get('memory_percent', 0),
                    next_snapshot.get('category', 'unknown'),
                    datetime.now().hour,
                    next_snapshot.get('category') == 'gaming'
                )
                
                self.agent.learn(state, action, reward, next_state)
            
            if episode % 10 == 0:
                print(f"Episode {episode}/{episodes} completed")
        
        self.save_model()
        return {'status': 'success', 'episodes': episodes}
    
    def save_model(self):
        """保存模型"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        with open(self.model_path, 'wb') as f:
            pickle.dump(self.agent, f)
    
    def load_model(self) -> bool:
        """加载模型"""
        if not os.path.exists(self.model_path):
            return False
        try:
            with open(self.model_path, 'rb') as f:
                self.agent = pickle.load(f)
            return True
        except Exception as e:
            print(f"加载RL模型失败: {e}")
            return False
    
    def get_model_info(self) -> Dict:
        """获取模型信息"""
        if not self.agent:
            return {'status': 'not_loaded'}
        return {
            'status': 'loaded',
            'q_table_size': len(self.agent.q_table) if hasattr(self.agent, 'q_table') else 0,
            'learning_rate': self.agent.learning_rate if hasattr(self.agent, 'learning_rate') else 0,
            'discount_factor': self.agent.discount_factor if hasattr(self.agent, 'discount_factor') else 0,
            'epsilon': self.agent.epsilon if hasattr(self.agent, 'epsilon') else 0
        }