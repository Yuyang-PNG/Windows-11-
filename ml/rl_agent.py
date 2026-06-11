import numpy as np
import random
import json
import os
import threading
from datetime import datetime
from collections import deque

class DQNAgent:
    def __init__(self, state_size=10, action_size=5, model_dir='ml/models'):
        self.state_size = state_size
        self.action_size = action_size
        self.model_dir = model_dir
        
        self.gamma = 0.95
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        
        self.memory = deque(maxlen=2000)
        self._lock = threading.RLock()
        
        self._init_model()
        self._ensure_dir()
    
    def _init_model(self):
        try:
            import tensorflow as tf
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Dense, Dropout
            from tensorflow.keras.optimizers import Adam
            
            self.model = Sequential([
                Dense(64, input_dim=self.state_size, activation='relu'),
                Dropout(0.2),
                Dense(64, activation='relu'),
                Dropout(0.2),
                Dense(self.action_size, activation='linear')
            ])
            
            self.model.compile(optimizer=Adam(learning_rate=self.learning_rate),
                              loss='mse')
            
            self._load_model()
        except ImportError:
            self.model = None
            self._use_fallback = True
    
    def _ensure_dir(self):
        if not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)
    
    def _get_model_path(self):
        return os.path.join(self.model_dir, 'dqn_model.h5')
    
    def _load_model(self):
        try:
            if os.path.exists(self._get_model_path()):
                self.model.load_weights(self._get_model_path())
                print("DQN模型加载成功")
        except Exception as e:
            print(f"加载DQN模型失败: {e}")
    
    def _save_model(self):
        try:
            self.model.save_weights(self._get_model_path())
        except Exception as e:
            print(f"保存DQN模型失败: {e}")
    
    def _preprocess_state(self, metrics):
        features = []
        
        features.append(metrics.get('cpu_percent', 0) / 100.0)
        features.append(metrics.get('memory_percent', 0) / 100.0)
        features.append(metrics.get('gpu_memory_percent', 0) / 100.0)
        features.append(metrics.get('process_cpu', 0) / 100.0)
        features.append(metrics.get('process_memory', 0) / 100.0)
        features.append(metrics.get('is_foreground', 0))
        features.append(metrics.get('gpu_utilization', 0) / 100.0)
        features.append(metrics.get('network_io', 0) / 1000.0)
        features.append(metrics.get('disk_io', 0) / 1000.0)
        features.append(metrics.get('priority_score', 50) / 100.0)
        
        while len(features) < self.state_size:
            features.append(0.0)
        
        return np.array(features).reshape(1, self.state_size)
    
    def act(self, state):
        if self._use_fallback or self.model is None:
            return self._fallback_action(state)
        
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)
        
        act_values = self.model.predict(state, verbose=0)
        return np.argmax(act_values[0])
    
    def _fallback_action(self, state):
        priority_score = state[0][-1] * 100
        if priority_score >= 80:
            return 4
        elif priority_score >= 60:
            return 3
        elif priority_score >= 40:
            return 2
        elif priority_score >= 20:
            return 1
        return 0
    
    def remember(self, state, action, reward, next_state, done):
        with self._lock:
            self.memory.append((state, action, reward, next_state, done))
    
    def replay(self, batch_size=32):
        if self._use_fallback or self.model is None:
            return
        
        with self._lock:
            if len(self.memory) < batch_size:
                return
            
            minibatch = random.sample(self.memory, batch_size)
            
            for state, action, reward, next_state, done in minibatch:
                target = reward
                if not done:
                    target = reward + self.gamma * np.amax(self.model.predict(next_state, verbose=0)[0])
                
                target_f = self.model.predict(state, verbose=0)
                target_f[0][action] = target
                
                self.model.fit(state, target_f, epochs=1, verbose=0)
            
            if self.epsilon > self.epsilon_min:
                self.epsilon *= self.epsilon_decay
    
    def update_target_model(self):
        pass
    
    def train_on_batch(self, experiences):
        if self._use_fallback or self.model is None:
            return
        
        states = np.array([exp[0][0] for exp in experiences])
        actions = np.array([exp[1] for exp in experiences])
        rewards = np.array([exp[2] for exp in experiences])
        next_states = np.array([exp[3][0] for exp in experiences])
        dones = np.array([exp[4] for exp in experiences])
        
        targets = rewards.copy()
        not_done_mask = ~dones
        targets[not_done_mask] += self.gamma * np.amax(
            self.model.predict(next_states[not_done_mask], verbose=0), axis=1
        )
        
        target_f = self.model.predict(states, verbose=0)
        for i, action in enumerate(actions):
            target_f[i][action] = targets[i]
        
        self.model.fit(states, target_f, epochs=1, verbose=0)
    
    def save(self):
        self._save_model()
    
    def get_action_name(self, action):
        action_map = {
            0: 'IDLE_PRIORITY_CLASS',
            1: 'BELOW_NORMAL_PRIORITY_CLASS',
            2: 'NORMAL_PRIORITY_CLASS',
            3: 'ABOVE_NORMAL_PRIORITY_CLASS',
            4: 'HIGH_PRIORITY_CLASS'
        }
        return action_map.get(action, 'NORMAL_PRIORITY_CLASS')

class RLPriorityManager:
    def __init__(self):
        self.agent = DQNAgent()
        self._reward_history = deque(maxlen=100)
        self._total_reward = 0
        self._episode_count = 0
        self._lock = threading.RLock()
    
    def calculate_reward(self, process_info, system_metrics):
        reward = 0.0
        
        process_cpu = process_info.get('cpu_percent', 0)
        process_memory = process_info.get('memory_percent', 0)
        system_cpu = system_metrics.get('cpu_percent', 0)
        system_memory = system_metrics.get('memory_percent', 0)
        is_foreground = process_info.get('is_foreground', False)
        
        if is_foreground:
            reward += 1.0
            if process_cpu > 10:
                reward += 0.5
        
        if system_cpu < 70:
            reward += 0.3
        elif system_cpu > 90:
            reward -= 0.5
        
        if system_memory < 70:
            reward += 0.2
        elif system_memory > 90:
            reward -= 0.3
        
        if process_info.get('category') == 'gaming':
            reward += 0.5
            if process_info.get('gpu_usage', 0) > 50:
                reward += 0.3
        
        stability_bonus = 1.0 - abs(process_cpu - process_info.get('expected_cpu', process_cpu)) / 100
        reward += stability_bonus * 0.2
        
        return reward
    
    def get_state(self, process_info, system_metrics):
        return self.agent._preprocess_state({
            'cpu_percent': system_metrics.get('cpu_percent', 0),
            'memory_percent': system_metrics.get('memory_percent', 0),
            'gpu_memory_percent': system_metrics.get('gpu_memory_percent', 0),
            'process_cpu': process_info.get('cpu_percent', 0),
            'process_memory': process_info.get('memory_percent', 0),
            'is_foreground': 1 if process_info.get('is_foreground', False) else 0,
            'gpu_utilization': process_info.get('gpu_usage', 0),
            'network_io': process_info.get('network_io', 0),
            'disk_io': process_info.get('disk_io', 0),
            'priority_score': process_info.get('priority_score', 50)
        })
    
    def suggest_priority(self, process_info, system_metrics):
        state = self.get_state(process_info, system_metrics)
        action = self.agent.act(state)
        return self.agent.get_action_name(action), action
    
    def learn(self, process_info, system_metrics, action, next_system_metrics):
        state = self.get_state(process_info, system_metrics)
        reward = self.calculate_reward(process_info, next_system_metrics)
        
        next_process_info = process_info.copy()
        next_state = self.get_state(next_process_info, next_system_metrics)
        
        done = False
        
        self.agent.remember(state, action, reward, next_state, done)
        
        with self._lock:
            self._total_reward += reward
            self._reward_history.append(reward)
        
        self.agent.replay()
        
        return reward
    
    def get_metrics(self):
        with self._lock:
            return {
                'total_reward': self._total_reward,
                'average_reward': np.mean(self._reward_history) if self._reward_history else 0,
                'epsilon': self.agent.epsilon,
                'memory_size': len(self.agent.memory),
                'episode_count': self._episode_count
            }
    
    def save_model(self):
        self.agent.save()
    
    def set_epsilon(self, epsilon):
        self.agent.epsilon = max(self.agent.epsilon_min, min(1.0, epsilon))