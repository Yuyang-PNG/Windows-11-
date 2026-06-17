import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.rl_agent import RLPriorityAgent
from ml.rl_trainer import RLTrainer


def test_rl_agent_creation():
    """测试RLPriorityAgent创建"""
    agent = RLPriorityAgent()
    assert agent is not None
    assert agent.learning_rate == 0.1
    assert agent.discount_factor == 0.9
    assert agent.epsilon == 1.0
    assert len(agent.q_table) == 0
    print("✅ test_rl_agent_creation passed")


def test_get_state():
    """测试状态转换"""
    agent = RLPriorityAgent()
    state = agent.get_state(50.0, 60.0, 'gaming', 14, True)
    
    assert isinstance(state, tuple)
    assert len(state) == 5
    assert state[0] == 2  # 50/20 = 2
    assert state[1] == 3  # 60/20 = 3
    assert state[4] == 1  # is_gaming = True
    print("✅ test_get_state passed")


def test_choose_action():
    """测试动作选择"""
    agent = RLPriorityAgent()
    state = (2, 3, 5, 14, 1)
    
    # 初始epsilon=1.0，应该随机选择
    action = agent.choose_action(state)
    assert action in [0, 1, 2, 3, 4]
    
    # 设置epsilon=0强制贪婪
    agent.epsilon = 0.0
    agent.q_table[state] = [0.0, 0.0, 10.0, 0.0, 0.0]  # action 2有最高Q值
    action = agent.choose_action(state)
    assert action == 2
    print("✅ test_choose_action passed")


def test_learn():
    """测试Q学习更新"""
    agent = RLPriorityAgent()
    
    state = (1, 2, 3, 10, 0)
    next_state = (2, 3, 4, 11, 0)
    action = 2
    reward = 5.0
    
    initial_q = agent.q_table.get(state, [0.0] * 5)[action]
    agent.learn(state, action, reward, next_state)
    new_q = agent.q_table[state][action]
    
    # Q值应该增加
    assert new_q > initial_q
    print("✅ test_learn passed")


def test_calculate_reward():
    """测试奖励计算"""
    agent = RLPriorityAgent()
    
    # 游戏进程获得高优先级应该有正奖励
    process = {'category': 'gaming', 'priority': 'high'}
    system_metrics = {'cpu_percent': 50, 'memory_percent': 50}
    reward = agent.calculate_reward(process, system_metrics)
    assert reward == 10.0
    
    # 非游戏进程被错误提升应该有负奖励
    process = {'category': 'browser', 'priority': 'high'}
    system_metrics = {'cpu_percent': 50, 'memory_percent': 50}
    reward = agent.calculate_reward(process, system_metrics)
    assert reward == -3.0
    
    # 高CPU惩罚
    process = {'category': 'browser', 'priority': 'normal'}
    system_metrics = {'cpu_percent': 95, 'memory_percent': 50}
    reward = agent.calculate_reward(process, system_metrics)
    assert reward < 0
    print("✅ test_calculate_reward passed")


def test_get_action_name():
    """测试动作名称映射"""
    agent = RLPriorityAgent()
    
    assert agent.get_action_name(0) == 'IDLE_PRIORITY_CLASS'
    assert agent.get_action_name(1) == 'BELOW_NORMAL_PRIORITY_CLASS'
    assert agent.get_action_name(2) == 'NORMAL_PRIORITY_CLASS'
    assert agent.get_action_name(3) == 'ABOVE_NORMAL_PRIORITY_CLASS'
    assert agent.get_action_name(4) == 'HIGH_PRIORITY_CLASS'
    print("✅ test_get_action_name passed")


def test_rl_trainer_init():
    """测试RLTrainer初始化"""
    agent = RLPriorityAgent()
    trainer = RLTrainer(agent)
    
    assert trainer.agent is agent
    assert trainer.history_manager is None
    assert trainer.model_path == 'ml/models/rl_agent.pkl'
    print("✅ test_rl_trainer_init passed")


def test_rl_trainer_model_info():
    """测试获取模型信息"""
    agent = RLPriorityAgent()
    trainer = RLTrainer(agent)
    
    info = trainer.get_model_info()
    
    assert info['status'] == 'loaded'
    assert 'q_table_size' in info
    assert 'learning_rate' in info
    assert 'discount_factor' in info
    assert 'epsilon' in info
    print("✅ test_rl_trainer_model_info passed")


def test_rl_trainer_no_agent():
    """测试无Agent时的模型信息"""
    trainer = RLTrainer()
    info = trainer.get_model_info()
    
    assert info['status'] == 'not_loaded'
    print("✅ test_rl_trainer_no_agent passed")


def test_full_episode():
    """测试完整的Q学习回合"""
    agent = RLPriorityAgent()
    
    # 模拟几个状态转换
    states = [
        (1, 2, 3, 10, 0),
        (2, 3, 4, 11, 0),
        (3, 4, 5, 12, 1),
    ]
    
    for i in range(len(states) - 1):
        state = states[i]
        next_state = states[i + 1]
        
        action = agent.choose_action(state)
        reward = float(i + 1)
        
        agent.learn(state, action, reward, next_state)
    
    # 验证Q表有更新
    assert len(agent.q_table) > 0
    
    # 验证epsilon有衰减
    assert agent.epsilon < 1.0
    print("✅ test_full_episode passed")


if __name__ == '__main__':
    test_rl_agent_creation()
    test_get_state()
    test_choose_action()
    test_learn()
    test_calculate_reward()
    test_get_action_name()
    test_rl_trainer_init()
    test_rl_trainer_model_info()
    test_rl_trainer_no_agent()
    test_full_episode()
    print("\n✅ 所有测试通过!")