#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试Windows服务查询功能
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from process_priority_manager import analyze_all_services, setup_logging
import logging

def test_service_query():
    """测试服务查询功能"""
    # 设置日志
    setup_logging()
    logger = logging.getLogger('test_service_query')
    
    print("=" * 80)
    print("测试Windows服务查询功能")
    print("=" * 80)
    
    try:
        # 查询所有服务
        print("\n1. 查询所有Windows服务...")
        services = analyze_all_services()
        
        print(f"\n找到 {len(services)} 个服务")
        
        # 统计信息
        running_count = sum(1 for s in services if s['is_running'])
        stopped_count = len(services) - running_count
        
        print(f"运行中: {running_count} 个")
        print(f"已停止: {stopped_count} 个")
        
        # 显示前10个运行中的服务
        print("\n2. 运行中的服务示例（前10个）:")
        print("-" * 80)
        running_services = [s for s in services if s['is_running']][:10]
        for i, service in enumerate(running_services, 1):
            print(f"{i}. {service['name']}")
            print(f"   显示名称: {service['display_name']}")
            print(f"   状态: {service['status']}")
            print(f"   启动类型: {service['start_type']}")
            print(f"   PID: {service.get('pid', 'N/A')}")
            print(f"   当前优先级: {service.get('current_priority', 'N/A')}")
            print(f"   类别: {service.get('category_display', 'N/A')}")
            print()
        
        # 显示前10个已停止的服务
        print("\n3. 已停止的服务示例（前10个）:")
        print("-" * 80)
        stopped_services = [s for s in services if not s['is_running']][:10]
        for i, service in enumerate(stopped_services, 1):
            print(f"{i}. {service['name']}")
            print(f"   显示名称: {service['display_name']}")
            print(f"   状态: {service['status']}")
            print(f"   启动类型: {service['start_type']}")
            print(f"   类别: {service.get('category_display', 'N/A')}")
            print()
        
        # 测试关键词过滤
        print("\n4. 测试关键词过滤（搜索包含'windows'的服务）:")
        print("-" * 80)
        windows_services = analyze_all_services(keyword='windows')
        print(f"找到 {len(windows_services)} 个包含'windows'的服务")
        for i, service in enumerate(windows_services[:5], 1):
            print(f"{i}. {service['name']} - {service['status']}")
        
        print("\n" + "=" * 80)
        print("测试完成！")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n测试失败: {e}")
        return False

if __name__ == '__main__':
    success = test_service_query()
    sys.exit(0 if success else 1)
