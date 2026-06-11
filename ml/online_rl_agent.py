"""
在线强化学习模块
实现在线学习和自适应调整的DQN智能体
"""
import os
import time
import threading
import numpy as np
from collections import deque
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger('process_priority_manager')

# 尝试导入TensorFlow
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, clone_model
    from tensorflow.keras.layers import Dense, Dropout, BatchNormalization
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.callbacks import EarlyStopping
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    logger.warning("TensorFlow不可用，在线RL将使用简化模式")


class PrioritizedExperienceReplay:
    """
    优先级经验回放
    
    给予高TD误差样本更高的采样概率
    使用环形缓冲区实现 O(1) 的添加和删除操作
    """
    
    def __init__(self, capacity: int = 10000, alpha: float = 0.6, beta: float = 0.4):
        """
        初始化
        
        Args:
            capacity: 缓冲区容量
            alpha: 优先级指数
            beta: 重要性采样指数
        """
        self._capacity = capacity
        self._alpha = alpha
        self._beta = beta
        
        # 使用预分配的列表实现环形缓冲区
        self._buffer = [None] * capacity
        self._priorities = [0.0] * capacity
        
        # 维护读写指针
        self._head = 0  # 下一个要删除的位置
        self._tail = 0  # 下一个要添加的位置
        self._size = 0  # 当前元素数量
        
        self._max_priority = 1.0
        self._lock = threading.Lock()
    
    def add(self, experience: Tuple, priority: float = None):
        """添加经验 - O(1) 时间复杂度"""
        priority = priority or self._max_priority
        
        with self._lock:
            # 如果缓冲区已满，移动头指针
            if self._size >= self._capacity:
                self._head = (self._head + 1) % self._capacity
            else:
                self._size += 1
            
            # 在尾部添加新元素
            self._buffer[self._tail] = experience
            self._priorities[self._tail] = priority ** self._alpha
            self._tail = (self._tail + 1) % self._capacity
    
    def __getitem__(self, index: int):
        """支持按索引访问 - O(1) 时间复杂度"""
        if index >= self._size:
            raise IndexError("Index out of range")
        # 计算环形缓冲区中的实际位置
        actual_index = (self._head + index) % self._capacity
        return self._buffer[actual_index]
    
    def __len__(self):
        """返回当前元素数量"""
        return self._size
    
    def sample(self, batch_size: int) -> Tuple[List, List[int], np.ndarray]:
        """
        采样
        
        Returns:
            (experiences, indices, importance_weights)
        """
        with self._lock:
            if self._size < batch_size:
                return [], [], np.array([])
            
            # 计算采样概率
            priorities = np.array([self._priorities[(self._head + i) % self._capacity] 
                                   for i in range(self._size)])
            probs = priorities / priorities.sum()
            
            # 采样
            indices = np.random.choice(self._size, batch_size, p=probs, replace=False)
            experiences = [self._buffer[(self._head + i) % self._capacity] for i in indices]
            
            # 计算重要性权重
            weights = (self._size * probs[indices]) ** (-self._beta)
            weights = weights / weights.max()
            
            return experiences, list(indices), weights
    
    def update_priorities(self, indices: List[int], priorities: np.ndarray):
        """更新优先级"""
        with self._lock:
            for idx, priority in zip(indices, priorities):
                if idx < self._size:
                    actual_index = (self._head + idx) % self._capacity
                    self._priorities[actual_index] = priority ** self._alpha
                    self._max_priority = max(self._max_priority, priority)


class OnlineDQNAgent:
    """
    在线DQN智能体
    
    支持在线学习、自适应学习率和优先级经验回放
    """
    
    def __init__(
        self,
        state_size: int = 12,
        action_size: int = 5,
        model_dir: str = 'ml/models',
        learning_rate: float = 0.001,
        gamma: float = 0.95,
        epsilon: float = 1.0,
        epsilon_min: float = 0.01,
        epsilon_decay: float = 0.995,
        target_update_freq: int = 100,
        online_update_freq: int = 10
    ):
        """
        初始化在线DQN智能体
        
        Args:
            state_size: 状态维度
            action_size: 动作数量
            model_dir: 模型保存目录
            learning_rate: 学习率
            gamma: 折扣因子
            epsilon: 探索率
            epsilon_min: 最小探索率
            epsilon_decay: 探索率衰减
            target_update_freq: 目标网络更新频率
            online_update_freq: 在线更新频率
        """
        self._state_size = state_size
        self._action_size = action_size
        self._model_dir = model_dir
        self._learning_rate = learning_rate
        self._gamma = gamma
        self._epsilon = epsilon
        self._epsilon_min = epsilon_min
        self._epsilon_decay = epsilon_decay
        self._target_update_freq = target_update_freq
        self._online_update_freq = online_update_freq
        
        self._lock = threading.RLock()
        self._step_count = 0
        self._update_count = 0
        
        # 经验回放
        self._memory = PrioritizedExperienceReplay(capacity=20000)
        
        # 模型
        self._model = None
        self._target_model = None
        self._use_fallback = not TF_AVAILABLE
        
        if TF_AVAILABLE:
            self._init_model()
        
        # 自适应学习率参数
        self._adaptive_lr = True
        self._lr_history = deque(maxlen=100)
        self._reward_history = deque(maxlen=100)
        
        # 在线学习统计
        self._stats = {
            'total_steps': 0,
            'online_updates': 0,
            'exploration_actions': 0,
            'exploitation_actions': 0,
            'avg_reward': 0.0,
            'avg_loss': 0.0
        }
        
        self._ensure_dir()
    
    def _ensure_dir(self):
        """确保模型目录存在"""
        if not os.path.exists(self._model_dir):
            os.makedirs(self._model_dir)
    
    def _init_model(self):
        """初始化神经网络模型"""
        # 主网络
        self._model = Sequential([
            Dense(128, input_dim=self._state_size, activation='relu'),
            BatchNormalization(),
            Dropout(0.2),
            Dense(128, activation='relu'),
            BatchNormalization(),
            Dropout(0.2),
            Dense(64, activation='relu'),
            Dense(self._action_size, activation='linear')
        ])
        
        self._model.compile(
            optimizer=Adam(learning_rate=self._learning_rate),
            loss='mse'
        )
        
        # 目标网络
        self._target_model = clone_model(self._model)
        self._target_model.set_weights(self._model.get_weights())
        
        # 尝试加载已保存的模型
        self._load_model()
    
    def _preprocess_state(self, metrics: Dict[str, Any]) -> np.ndarray:
        """
        预处理状态
        
        Args:
            metrics: 状态指标
            
        Returns:
            状态向量
        """
        features = [
            metrics.get('cpu_percent', 0) / 100.0,
            metrics.get('memory_percent', 0) / 100.0,
            metrics.get('gpu_memory_percent', 0) / 100.0,
            metrics.get('process_cpu', 0) / 100.0,
            metrics.get('process_memory', 0) / 100.0,
            1.0 if metrics.get('is_foreground', False) else 0.0,
            metrics.get('gpu_utilization', 0) / 100.0,
            min(metrics.get('network_io', 0) / 1000.0, 1.0),
            min(metrics.get('disk_io', 0) / 1000.0, 1.0),
            metrics.get('priority_score', 50) / 100.0,
            metrics.get('thread_count', 1) / 100.0,
            min(metrics.get('uptime_hours', 0) / 24.0, 1.0)
        ]
        
        # 确保维度正确
        while len(features) < self._state_size:
            features.append(0.0)
        
        return np.array(features[:self._state_size]).reshape(1, -1)
    
    def act(self, state: np.ndarray, training: bool = True) -> int:
        """
        选择动作
        
        Args:
            state: 状态向量
            training: 是否训练模式
            
        Returns:
            动作索引
        """
        if self._use_fallback:
            return self._fallback_action(state)
        
        # 探索-利用权衡
        if training and np.random.rand() <= self._epsilon:
            self._stats['exploration_actions'] += 1
            return np.random.randint(self._action_size)
        
        # 利用
        with self._lock:
            q_values = self._model.predict(state, verbose=0)[0]
            self._stats['exploitation_actions'] += 1
            return int(np.argmax(q_values))
    
    def _fallback_action(self, state: np.ndarray) -> int:
        """回退动作选择（基于规则）"""
        priority_score = state[0][9] * 100 if state.shape[1] > 9 else 50
        
        if priority_score >= 80:
            return 4  # HIGH
        elif priority_score >= 60:
            return 3  # ABOVE_NORMAL
        elif priority_score >= 40:
            return 2  # NORMAL
        elif priority_score >= 20:
            return 1  # BELOW_NORMAL
        return 0  # IDLE
    
    def remember(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        priority: float = None
    ):
        """存储经验"""
        self._memory.add((state, action, reward, next_state, done), priority)
    
    def _calculate_td_error(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool
    ) -> float:
        """计算TD误差"""
        if self._use_fallback:
            return abs(reward)
        
        current_q = self._model.predict(state, verbose=0)[0][action]
        
        if done:
            target = reward
        else:
            next_q = self._target_model.predict(next_state, verbose=0)[0]
            target = reward + self._gamma * np.max(next_q)
        
        return abs(target - current_q)
    
    def online_update(self, batch_size: int = 32) -> Optional[float]:
        """
        在线更新
        
        Args:
            batch_size: 批大小
            
        Returns:
            平均损失
        """
        if self._use_fallback or len(self._memory) < batch_size:
            return None
        
        # 采样
        experiences, indices, weights = self._memory.sample(batch_size)
        if not experiences:
            return None
        
        # 准备数据
        states = np.vstack([e[0] for e in experiences])
        actions = np.array([e[1] for e in experiences])
        rewards = np.array([e[2] for e in experiences])
        next_states = np.vstack([e[3] for e in experiences])
        dones = np.array([e[4] for e in experiences])
        
        # 计算目标Q值
        current_qs = self._model.predict(states, verbose=0)
        next_qs = self._target_model.predict(next_states, verbose=0)
        
        targets = current_qs.copy()
        td_errors = []
        
        for i in range(batch_size):
            if dones[i]:
                target = rewards[i]
            else:
                target = rewards[i] + self._gamma * np.max(next_qs[i])
            
            td_error = abs(target - current_qs[i][actions[i]])
            td_errors.append(td_error + 1e-6)
            
            targets[i][actions[i]] = target
        
        # 加权训练
        with self._lock:
            sample_weights = weights.reshape(-1, 1)
            history = self._model.fit(
                states, targets,
                sample_weight=sample_weights,
                epochs=1,
                verbose=0
            )
            loss = history.history['loss'][0]
        
        # 更新优先级
        self._memory.update_priorities(indices, np.array(td_errors))
        
        # 更新统计
        self._stats['online_updates'] += 1
        self._stats['avg_loss'] = 0.9 * self._stats['avg_loss'] + 0.1 * loss
        
        return loss
    
    def act_and_learn(
        self,
        state: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        done: bool = False
    ) -> Tuple[int, Optional[float]]:
        """
        决策并学习（一体化操作）
        
        Args:
            state: 当前状态
            reward: 奖励
            next_state: 下一状态
            done: 是否终止
            
        Returns:
            (动作, 损失)
        """
        # 选择动作
        action = self.act(state, training=True)
        
        # 计算TD误差作为优先级
        td_error = self._calculate_td_error(state, action, reward, next_state, done)
        
        # 存储经验
        self.remember(state, action, reward, next_state, done, td_error + 1e-6)
        
        # 记录奖励历史
        self._reward_history.append(reward)
        self._stats['avg_reward'] = np.mean(self._reward_history)
        
        # 自适应学习率
        if self._adaptive_lr and len(self._reward_history) >= 10:
            self._adjust_learning_rate()
        
        # 在线更新
        loss = None
        self._step_count += 1
        self._stats['total_steps'] += 1
        
        if self._step_count % self._online_update_freq == 0:
            loss = self.online_update()
        
        # 更新目标网络
        if self._step_count % self._target_update_freq == 0:
            self._update_target_model()
        
        # 衰减探索率
        if self._epsilon > self._epsilon_min:
            self._epsilon *= self._epsilon_decay
        
        return action, loss
    
    def _adjust_learning_rate(self):
        """自适应调整学习率"""
        if self._use_fallback:
            return
        
        # 计算最近奖励趋势
        recent_rewards = list(self._reward_history)[-20:]
        avg_reward = np.mean(recent_rewards)
        reward_std = np.std(recent_rewards)
        
        # 根据奖励调整学习率
        current_lr = float(tf.keras.backend.get_value(self._model.optimizer.learning_rate))
        
        if avg_reward > 0.5 and reward_std < 0.2:
            # 表现好且稳定，降低学习率
            new_lr = current_lr * 0.95
        elif avg_reward < -0.3 or reward_std > 0.5:
            # 表现差或不稳定，提高学习率
            new_lr = current_lr * 1.05
        else:
            new_lr = current_lr
        
        # 限制范围
        new_lr = max(1e-5, min(1e-2, new_lr))
        
        if abs(new_lr - current_lr) / current_lr > 0.01:
            tf.keras.backend.set_value(self._model.optimizer.learning_rate, new_lr)
            self._lr_history.append(new_lr)
            logger.debug(f"学习率调整: {current_lr:.6f} -> {new_lr:.6f}")
    
    def _update_target_model(self):
        """更新目标网络"""
        if not self._use_fallback:
            with self._lock:
                self._target_model.set_weights(self._model.get_weights())
            self._update_count += 1
    
    def _load_model(self):
        """加载模型"""
        try:
            model_path = os.path.join(self._model_dir, 'online_dqn.h5')
            if os.path.exists(model_path):
                self._model.load_weights(model_path)
                self._target_model.set_weights(self._model.get_weights())
                logger.info("在线DQN模型加载成功")
        except Exception as e:
            logger.warning(f"加载模型失败: {e}")
    
    def save_model(self):
        """保存模型"""
        if self._use_fallback:
            return
        
        try:
            model_path = os.path.join(self._model_dir, 'online_dqn.h5')
            with self._lock:
                self._model.save_weights(model_path)
        except Exception as e:
            logger.warning(f"保存模型失败: {e}")
    
    def get_action_name(self, action: int) -> str:
        """获取动作名称"""
        action_map = {
            0: 'IDLE_PRIORITY_CLASS',
            1: 'BELOW_NORMAL_PRIORITY_CLASS',
            2: 'NORMAL_PRIORITY_CLASS',
            3: 'ABOVE_NORMAL_PRIORITY_CLASS',
            4: 'HIGH_PRIORITY_CLASS'
        }
        return action_map.get(action, 'NORMAL_PRIORITY_CLASS')
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            'epsilon': self._epsilon,
            'memory_size': len(self._memory),
            'learning_rate': float(tf.keras.backend.get_value(
                self._model.optimizer.learning_rate
            )) if not self._use_fallback and self._model else self._learning_rate,
            'target_updates': self._update_count
        }


class OnlineRLPriorityManager:
    """
    在线RL优先级管理器
    
    整合在线DQN智能体，提供完整的优先级管理功能
    """
    
    def __init__(self):
        self._agent = OnlineDQNAgent()
        self._lock = threading.RLock()
        self._process_states: Dict[int, Dict[str, Any]] = {}
        
        # 奖励计算参数
        self._reward_weights = {
            'foreground': 1.0,
            'gaming': 0.5,
            'system_stability': 0.3,
            'efficiency': 0.2
        }
    
    def calculate_reward(
        self,
        process_info: Dict[str, Any],
        system_metrics: Dict[str, Any],
        action: int
    ) -> float:
        """
        计算奖励
        
        Args:
            process_info: 进程信息
            system_metrics: 系统指标
            action: 执行的动作
            
        Returns:
            奖励值
        """
        reward = 0.0
        
        # 前台进程奖励
        if process_info.get('is_foreground', False):
            reward += self._reward_weights['foreground']
            if process_info.get('cpu_percent', 0) > 10:
                reward += 0.3
        
        # 游戏进程奖励
        if process_info.get('category') == 'gaming':
            reward += self._reward_weights['gaming']
            if process_info.get('gpu_usage', 0) > 50:
                reward += 0.2
        
        # 系统稳定性奖励
        system_cpu = system_metrics.get('cpu_percent', 0)
        system_memory = system_metrics.get('memory_percent', 0)
        
        if system_cpu < 70:
            reward += self._reward_weights['system_stability']
        elif system_cpu > 90:
            reward -= 0.4
        
        if system_memory < 70:
            reward += 0.2
        elif system_memory > 90:
            reward -= 0.3
        
        # 效率奖励（动作与进程重要性匹配）
        priority_score = process_info.get('priority_score', 50)
        expected_action = self._get_expected_action(priority_score)
        
        if action == expected_action:
            reward += self._reward_weights['efficiency']
        else:
            reward -= 0.1 * abs(action - expected_action)
        
        return reward
    
    def _get_expected_action(self, priority_score: float) -> int:
        """根据优先级分数获取期望动作"""
        if priority_score >= 80:
            return 4
        elif priority_score >= 60:
            return 3
        elif priority_score >= 40:
            return 2
        elif priority_score >= 20:
            return 1
        return 0
    
    def suggest_priority(
        self,
        process_info: Dict[str, Any],
        system_metrics: Dict[str, Any]
    ) -> Tuple[str, int]:
        """
        建议优先级
        
        Args:
            process_info: 进程信息
            system_metrics: 系统指标
            
        Returns:
            (优先级名称, 动作索引)
        """
        state = self._agent._preprocess_state({
            'cpu_percent': system_metrics.get('cpu_percent', 0),
            'memory_percent': system_metrics.get('memory_percent', 0),
            'gpu_memory_percent': system_metrics.get('gpu_memory_percent', 0),
            'process_cpu': process_info.get('cpu_percent', 0),
            'process_memory': process_info.get('memory_percent', 0),
            'is_foreground': process_info.get('is_foreground', False),
            'gpu_utilization': process_info.get('gpu_usage', 0),
            'network_io': process_info.get('network_io', 0),
            'disk_io': process_info.get('disk_io', 0),
            'priority_score': process_info.get('priority_score', 50),
            'thread_count': process_info.get('num_threads', 1),
            'uptime_hours': process_info.get('uptime_seconds', 0) / 3600
        })
        
        action = self._agent.act(state, training=False)
        return self._agent.get_action_name(action), action
    
    def learn(
        self,
        process_info: Dict[str, Any],
        system_metrics: Dict[str, Any],
        action: int,
        next_system_metrics: Dict[str, Any]
    ) -> Tuple[float, Optional[float]]:
        """
        学习
        
        Args:
            process_info: 进程信息
            system_metrics: 当前系统指标
            action: 执行的动作
            next_system_metrics: 下一步系统指标
            
        Returns:
            (奖励, 损失)
        """
        # 获取状态
        state = self._agent._preprocess_state({
            'cpu_percent': system_metrics.get('cpu_percent', 0),
            'memory_percent': system_metrics.get('memory_percent', 0),
            'gpu_memory_percent': system_metrics.get('gpu_memory_percent', 0),
            'process_cpu': process_info.get('cpu_percent', 0),
            'process_memory': process_info.get('memory_percent', 0),
            'is_foreground': process_info.get('is_foreground', False),
            'gpu_utilization': process_info.get('gpu_usage', 0),
            'network_io': process_info.get('network_io', 0),
            'disk_io': process_info.get('disk_io', 0),
            'priority_score': process_info.get('priority_score', 50),
            'thread_count': process_info.get('num_threads', 1),
            'uptime_hours': process_info.get('uptime_seconds', 0) / 3600
        })
        
        # 计算奖励
        reward = self.calculate_reward(process_info, next_system_metrics, action)
        
        # 获取下一状态
        next_state = self._agent._preprocess_state({
            'cpu_percent': next_system_metrics.get('cpu_percent', 0),
            'memory_percent': next_system_metrics.get('memory_percent', 0),
            'gpu_memory_percent': next_system_metrics.get('gpu_memory_percent', 0),
            'process_cpu': process_info.get('cpu_percent', 0),
            'process_memory': process_info.get('memory_percent', 0),
            'is_foreground': process_info.get('is_foreground', False),
            'gpu_utilization': process_info.get('gpu_usage', 0),
            'network_io': process_info.get('network_io', 0),
            'disk_io': process_info.get('disk_io', 0),
            'priority_score': process_info.get('priority_score', 50),
            'thread_count': process_info.get('num_threads', 1),
            'uptime_hours': process_info.get('uptime_seconds', 0) / 3600
        })
        
        # 在线学习
        _, loss = self._agent.act_and_learn(state, reward, next_state, done=False)
        
        return reward, loss
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        return self._agent.get_stats()
    
    def save_model(self):
        """保存模型"""
        self._agent.save_model()


# 便捷函数
def create_online_rl_agent(**kwargs) -> OnlineDQNAgent:
    """创建在线DQN智能体"""
    return OnlineDQNAgent(**kwargs)


def create_online_rl_manager() -> OnlineRLPriorityManager:
    """创建在线RL优先级管理器"""
    return OnlineRLPriorityManager()
