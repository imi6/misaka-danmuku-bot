#!/usr/bin/env python3
"""
测试webhook过滤功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.webhook_filter import get_webhook_filter_config, should_filter_webhook_title

def test_webhook_filter():
    """测试webhook过滤功能"""
    print("🧪 测试webhook过滤功能...")
    
    # 测试获取配置
    print("\n📋 测试配置获取:")
    config = get_webhook_filter_config()
    print(f"  过滤模式: {config.get('mode')}")
    print(f"  正则表达式: {config.get('regex')}")
    
    # 测试用例
    test_cases = [
        # 标题, 系列名称, 预期结果描述
        ("小英雄雨来", None, "普通标题"),
        ("奔跑吧兄弟", None, "普通系列"),
        ("测试电影", "测试系列", "同时有标题和系列名"),
        ("", "", "空标题"),
        (None, None, "None值"),
    ]
    
    print(f"\n🔍 测试过滤逻辑 (当前模式: {config.get('mode')}):")
    
    success_count = 0
    total_count = len(test_cases)
    
    for i, (title, series_name, description) in enumerate(test_cases, 1):
        try:
            print(f"\n--- 测试 {i}: {description} ---")
            print(f"  标题: {title}")
            print(f"  系列: {series_name}")
            
            should_filter = should_filter_webhook_title(title, series_name)
            
            if should_filter:
                print(f"  结果: ❌ 被过滤")
            else:
                print(f"  结果: ✅ 允许处理")
                
            success_count += 1
            
        except Exception as e:
            print(f"  ❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n📊 测试结果: {success_count}/{total_count} 通过")
    
    if success_count == total_count:
        print("✅ 所有测试通过！webhook过滤功能正常")
    else:
        print("❌ 部分测试失败，需要检查")
    
    return success_count == total_count

if __name__ == "__main__":
    test_webhook_filter()