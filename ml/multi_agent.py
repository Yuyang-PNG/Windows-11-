"""
多智能体协同优化模块
实现多进程间的资源协调和全局优化
"""
import time
import threading
import numpy as np
from typing import Dict, List, Any, Tuple, Optional, Callable
from collections import defaultdict, deque
from dataclasses import dataclass, field
import logging

logger = logging.getLogger('process_priority_manager')

# 尝试导入TensorFlow
try:
    import tensorflow as tf
    from tensorflow.keras.models import Model
    from tensorflow.keras.layers import Input, Dense, Concatenate
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False


@dataclass
class AgentState:
    """智能体状态"""
    agent_id: int
    process_info: Dict[str, Any]
    local_state: np.ndarray
    last_action: int
    last_reward: float


@dataclass
class GlobalState:
    """全局状态"""
    system_cpu: float
    system_memory: float
    system_gpu: float
    active_processes: int
    resource_contention: float  # 资源竞争程度


class LocalAgent:
    """
    局部智能体
    
    负责单个进程的优先级决策
    """
    
    def __init__(self, agent_id: int, state_size: int = 10, action_size: int = 5):
        """
        初始化局部智能体
        
        Args:
            agent_id: 智能体ID
            state_size: 状态维度
            action_size: 动作数量
        """
        self._agent_id = agent_id
        self._state_size = state_size
        self._action_size = action_size
        
        # 简化的Q表（用于无TensorFlow时的回退）
        self._q_table = defaultdict(lambda: np.zeros(action_size))
        
        # 策略网络
        self._policy_net = None
        self._use_nn = TF_AVAILABLE
        
        if TF_AVAILABLE:
            self._init_policy_network()
        
        # 历史记录
        self._action_history = deque(maxlen=100)
        self._reward_history = deque(maxlen=100)
        
        # 探索参数
        self._epsilon = 0.3
        self._epsilon_decay = 0.995
        self._epsilon_min = 0.05
    
    def _init_policy_network(self):
        """初始化策略网络"""
        inputs = Input(shape=(self._state_size,))
        x = Dense(64, activation='relu')(inputs)
        x = Dense(32, activation='relu')(x)
        outputs = Dense(self._action_size, activation='softmax')(x)
        
        self._policy_net = Model(inputs=inputs, outputs=outputs)
        self._policy_net.compile(
            optimizer='adam',
            loss='categorical_crossentropy'
        )
    
    def get_action(self, state: np.ndarray, training: bool = True) -> int:
        """
        获取动作
        
        Args:
            state: 状态向量
            training: 是否训练模式
            
        Returns:
            动作索引
        """
        # 探索
        if training and np.random.rand() < self._epsilon:
            return np.random.randint(self._action_size)
        
        # 利用
        if self._use_nn and self._policy_net is not None:
            try:
                probs = self._policy_net.predict(state.reshape(1, -1), verbose=0)[0]
                return int(np.argmax(probs))
            except Exception:
                pass
        
        # 回退到Q表
        state_key = tuple(state.round(2))
        return int(np.argmax(self._q_table[state_key]))
    
    def update(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        global_reward: float
    ):
        """
        更新策略
        
        Args:
            state: 当前状态
            action: 动作
            reward: 局部奖励
            next_state: 下一状态
            global_reward: 全局奖励
        """
        # 记录历史
        self._action_history.append(action)
        self._reward_history.append(reward)
        
        # 衰减探索率
        if self._epsilon > self._epsilon_min:
            self._epsilon *= self._epsilon_decay
        
        # 更新Q表（简化版）
        state_key = tuple(state.round(2))
        next_key = tuple(next_state.round(2))
        
        # 结合局部和全局奖励
        combined_reward = 0.7 * reward + 0.3 * global_reward
        
        # Q学习更新
        alpha = 0.1  # 学习率
        gamma = 0.9  # 折扣因子
        
        self._q_table[state_key][action] += alpha * (
            combined_reward + gamma * np.max(self._q_table[next_key]) - self._q_table[state_key][action]
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'agent_id': self._agent_id,
            'epsilon': self._epsilon,
            'avg_reward': np.mean(self._reward_history) if self._reward_history else 0.0,
            'action_dist': np.bincount(list(self._action_history), minlength=5).tolist() if self._action_history else [0]*5
        }


class GlobalCoordinator:
    """
    全局协调器
    
    协调多个局部智能体，实现全局优化
    """
    
    def __init__(self, num_agents: int = 100):
        """
        初始化全局协调器
        
        Args:
            num_agents: 最大智能体数量
        """
        self._num_agents = num_agents
        self._agents: Dict[int, LocalAgent] = {}
        self._lock = threading.RLock()
        
        # 全局状态
        self._global_state = GlobalState(
            system_cpu=0.0,
            system_memory=0.0,
            system_gpu=0.0,
            active_processes=0,
            resource_contention=0.0
        )
        
        # 公平性参数
        self._fairness_weight = 0.4
        self._efficiency_weight = 0.6
        
        # 资源分配历史
        self._allocation_history = deque(maxlen=60)
        
        # 统计
        self._stats = {
            'total_coordinations': 0,
            'global_rewards': deque(maxlen=100),
            'fairness_scores': deque(maxlen=100)
        }
    
    def get_or_create_agent(self, agent_id: int) -> LocalAgent:
        """获取或创建智能体"""
        with self._lock:
            if agent_id not in self._agents:
                self._agents[agent_id] = LocalAgent(agent_id)
            return self._agents[agent_id]
    
    def remove_agent(self, agent_id: int):
        """移除智能体"""
        with self._lock:
            self._agents.pop(agent_id, None)
    
    def update_global_state(self, system_metrics: Dict[str, Any]):
        """更新全局状态"""
        self._global_state = GlobalState(
            system_cpu=system_metrics.get('cpu_percent', 0),
            system_memory=system_metrics.get('memory_percent', 0),
            system_gpu=system_metrics.get('gpu_percent', 0),
            active_processes=len(self._agents),
            resource_contention=self._calculate_contention(system_metrics)
        )
    
    def _calculate_contention(self, system_metrics: Dict[str, Any]) -> float:
        """计算资源竞争程度"""
        cpu = system_metrics.get('cpu_percent', 0) / 100.0
        memory = system_metrics.get('memory_percent', 0) / 100.0
        
        # 简单的竞争度量
        contention = (cpu * 0.6 + memory * 0.4)
        
        # 如果资源紧张，竞争程度更高
        if cpu > 0.8 or memory > 0.8:
            contention = min(1.0, contention * 1.5)
        
        return contention
    
    def calculate_global_reward(
        self,
        actions: Dict[int, int],
        process_infos: Dict[int, Dict[str, Any]]
    ) -> float:
        """
        计算全局奖励
        
        Args:
            actions: 各智能体的动作
            process_infos: 各进程的信息
            
        Returns:
            全局奖励值
        """
        # 效率奖励
        efficiency = self._calculate_efficiency(actions, process_infos)
        
        # 公平性奖励
        fairness = self._calculate_fairness(actions, process_infos)
        
        # 系统稳定性奖励
        stability = self._calculate_stability()
        
        # 组合奖励
        global_reward = (
            self._efficiency_weight * efficiency +
            self._fairness_weight * fairness +
            0.2 * stability
        )
        
        # 记录统计
        self._stats['global_rewards'].append(global_reward)
        self._stats['fairness_scores'].append(fairness)
        
        return global_reward
    
    def _calculate_efficiency(
        self,
        actions: Dict[int, int],
        process_infos: Dict[int, Dict[str, Any]]
    ) -> float:
        """计算效率得分"""
        if not actions:
            return 1.0
        
        efficiency_scores = []
        
        for agent_id, action in actions.items():
            info = process_infos.get(agent_id, {})
            priority_score = info.get('priority_score', 50)
            
            # 期望动作
            expected_action = self._get_expected_action(priority_score)
            
            # 动作匹配度
            match_score = 1.0 - abs(action - expected_action) / 4.0
            efficiency_scores.append(match_score)
        
        return np.mean(efficiency_scores) if efficiency_scores else 1.0
    
    def _calculate_fairness(
        self,
        actions: Dict[int, int],
        process_infos: Dict[int, Dict[str, Any]]
    ) -> float:
        """
        计算公平性得分（基于基尼系数）
        
        基尼系数越低，公平性越高
        """
        if len(actions) < 2:
            return 1.0
        
        # 计算各进程的资源分配
        allocations = []
        for agent_id, action in actions.items():
            info = process_infos.get(agent_id, {})
            # 高优先级动作获得更多资源
            allocation = (action + 1) * info.get('cpu_percent', 1)
            allocations.append(allocation)
        
        # 计算基尼系数
        allocations = np.array(sorted(allocations))
        n = len(allocations)
        
        if n == 0 or np.sum(allocations) == 0:
            return 1.0
        
        cumulative = np.cumsum(allocations)
        gini = (n + 1 - 2 * np.sum(cumulative) / np.sum(allocations)) / n
        
        # 公平性 = 1 - 基尼系数
        return 1.0 - gini
    
    def _calculate_stability(self) -> float:
        """计算系统稳定性得分"""
        cpu = self._global_state.system_cpu / 100.0
        memory = self._global_state.system_memory / 100.0
        contention = self._global_state.resource_contention
        
        # 资源使用越低，稳定性越高
        stability = 1.0 - (cpu * 0.4 + memory * 0.3 + contention * 0.3)
        
        return max(0.0, stability)
    
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
    
    def coordinate(
        self,
        process_infos: Dict[int, Dict[str, Any]],
        system_metrics: Dict[str, Any]
    ) -> Dict[int, Tuple[int, str]]:
        """
        协调多智能体决策
        
        Args:
            process_infos: 各进程信息
            system_metrics: 系统指标
            
        Returns:
            各进程的决策结果 {pid: (action, action_name)}
        """
        self._stats['total_coordinations'] += 1
        
        # 更新全局状态
        self.update_global_state(system_metrics)
        
        # 收集各智能体的决策
        actions = {}
        states = {}
        
        for pid, info in process_infos.items():
            agent = self.get_or_create_agent(pid)
            
            # 构建状态向量
            state = self._build_state(info, system_metrics)
            states[pid] = state
            
            # 获取动作
            action = agent.get_action(state, training=True)
            actions[pid] = action
        
        # 计算全局奖励
        global_reward = self.calculate_global_reward(actions, process_infos)
        
        # 更新各智能体
        for pid, action in actions.items():
            agent = self._agents.get(pid)
            if agent is None:
                continue
            
            info = process_infos.get(pid, {})
            local_reward = self._calculate_local_reward(info, action, system_metrics)
            
            # 更新智能体
            next_state = self._build_state(info, system_metrics)
            agent.update(states[pid], action, local_reward, next_state, global_reward)
        
        # 构建结果
        action_names = ['IDLE', 'BELOW_NORMAL', 'NORMAL', 'ABOVE_NORMAL', 'HIGH']
        results = {
            pid: (action, action_names[action])
            for pid, action in actions.items()
        }
        
        # 记录分配历史
        self._allocation_history.append({
            'timestamp': time.time(),
            'actions': dict(actions),
            'global_reward': global_reward
        })
        
        return results
    
    def _build_state(
        self,
        process_info: Dict[str, Any],
        system_metrics: Dict[str, Any]
    ) -> np.ndarray:
        """构建状态向量"""
        return np.array([
            process_info.get('cpu_percent', 0) / 100.0,
            process_info.get('memory_percent', 0) / 100.0,
            process_info.get('priority_score', 50) / 100.0,
            1.0 if process_info.get('is_foreground', False) else 0.0,
            system_metrics.get('cpu_percent', 0) / 100.0,
            system_metrics.get('memory_percent', 0) / 100.0,
            self._global_state.resource_contention,
            process_info.get('num_threads', 1) / 100.0,
            min(process_info.get('uptime_seconds', 0) / 3600.0, 1.0),
            1.0 if process_info.get('category') == 'gaming' else 0.0
        ])
    
    def _calculate_local_reward(
        self,
        process_info: Dict[str, Any],
        action: int,
        system_metrics: Dict[str, Any]
    ) -> float:
        """计算局部奖励"""
        reward = 0.0
        
        # 前台进程奖励
        if process_info.get('is_foreground', False):
            reward += 0.5
        
        # 动作匹配奖励
        priority_score = process_info.get('priority_score', 50)
        expected = self._get_expected_action(priority_score)
        
        if action == expected:
            reward += 0.3
        else:
            reward -= 0.1 * abs(action - expected)
        
        # 游戏进程额外奖励
        if process_info.get('category') == 'gaming':
            reward += 0.2
        
        return reward
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_coordinations': self._stats['total_coordinations'],
            'active_agents': len(self._agents),
            'avg_global_reward': np.mean(list(self._stats['global_rewards'])) if self._stats['global_rewards'] else 0.0,
            'avg_fairness': np.mean(list(self._stats['fairness_scores'])) if self._stats['fairness_scores'] else 1.0,
            'global_state': {
                'system_cpu': self._global_state.system_cpu,
                'system_memory': self._global_state.system_memory,
                'resource_contention': self._global_state.resource_contention
            }
        }


class MultiAgentSystem:
    """
    多智能体系统
    
    整合局部智能体和全局协调器
    """
    
    def __init__(self):
        self._coordinator = GlobalCoordinator()
        self._lock = threading.RLock()
        
        # 进程状态缓存
        self._process_states: Dict[int, Dict[str, Any]] = {}
        
        # 回调
        self._on_decision: Optional[Callable[[int, int, str], None]] = None
    
    def register_process(self, pid: int, process_info: Dict[str, Any]):
        """注册进程"""
        with self._lock:
            self._process_states[pid] = process_info
    
    def unregister_process(self, pid: int):
        """注销进程"""
        with self._lock:
            self._process_states.pop(pid, None)
            self._coordinator.remove_agent(pid)
    
    def update_process(self, pid: int, process_info: Dict[str, Any]):
        """更新进程状态"""
        with self._lock:
            self._process_states[pid] = process_info
    
    def make_decisions(
        self,
        system_metrics: Dict[str, Any]
    ) -> Dict[int, Tuple[int, str]]:
        """
        进行决策
        
        Args:
            system_metrics: 系统指标
            
        Returns:
            各进程的决策结果
        """
        with self._lock:
            results = self._coordinator.coordinate(self._process_states, system_metrics)
            
            # 触发回调
            if self._on_decision:
                for pid, (action, action_name) in results.items():
                    self._on_decision(pid, action, action_name)
            
            return results
    
    def set_decision_callback(self, callback: Callable[[int, int, str], None]):
        """设置决策回调"""
        self._on_decision = callback
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._coordinator.get_stats()
    
    def get_agent_stats(self, pid: int) -> Optional[Dict[str, Any]]:
        """获取特定智能体统计"""
        agent = self._coordinator._agents.get(pid)
        if agent:
            return agent.get_stats()
        return None


class ResourceNegotiator:
    """
    资源协商器
    
    处理进程间的资源竞争和协商
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 资源池
        self._resource_pool = {
            'cpu': 100.0,  # 百分比
            'memory': 100.0,
            'gpu': 100.0
        }
        
        # 当前分配
        self._allocations: Dict[int, Dict[str, float]] = {}
        
        # 优先级队列
        self._priority_queue: List[Tuple[int, float]] = []  # (pid, priority)
    
    def request_resources(
        self,
        pid: int,
        requirements: Dict[str, float],
        priority: float
    ) -> Dict[str, float]:
        """
        请求资源
        
        Args:
            pid: 进程ID
            requirements: 资源需求 {'cpu': 30, 'memory': 20}
            priority: 优先级
            
        Returns:
            实际分配的资源
        """
        with self._lock:
            allocation = {}
            
            for resource, required in requirements.items():
                available = self._resource_pool.get(resource, 0)
                
                # 当前已分配给其他进程的
                allocated_to_others = sum(
                    alloc.get(resource, 0)
                    for p, alloc in self._allocations.items()
                    if p != pid
                )
                
                # 实际可用
                actual_available = available - allocated_to_others
                
                # 分配
                allocated = min(required, actual_available)
                allocation[resource] = allocated
            
            # 更新分配
            self._allocations[pid] = allocation
            
            return allocation
    
    def release_resources(self, pid: int):
        """释放资源"""
        with self._lock:
            self._allocations.pop(pid, None)
    
    def get_resource_usage(self) -> Dict[str, float]:
        """获取资源使用情况"""
        with self._lock:
            usage = defaultdict(float)
            
            for alloc in self._allocations.values():
                for resource, amount in alloc.items():
                    usage[resource] += amount
            
            return dict(usage)
    
    def negotiate(
        self,
        requests: List[Tuple[int, Dict[str, float], float]]
    ) -> Dict[int, Dict[str, float]]:
        """
        协商资源分配
        
        Args:
            requests: [(pid, requirements, priority), ...]
            
        Returns:
            {pid: allocation}
        """
        # 按优先级排序
        sorted_requests = sorted(requests, key=lambda x: x[2], reverse=True)
        
        results = {}
        
        for pid, requirements, priority in sorted_requests:
            allocation = self.request_resources(pid, requirements, priority)
            results[pid] = allocation
        
        return results


# 便捷函数
def create_multi_agent_system() -> MultiAgentSystem:
    """创建多智能体系统"""
    return MultiAgentSystem()


def create_resource_negotiator() -> ResourceNegotiator:
    """创建资源协商器"""
    return ResourceNegotiator()
