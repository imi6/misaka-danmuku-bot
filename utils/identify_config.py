#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def initialize_identify_config() -> bool:
    """
    初始化识别词配置文件
    
    在项目启动时创建 /app/config/identify.txt 文件（如果不存在）
    参考 user.json 的管理方式，提供持久化的识别词映射存储
    
    Returns:
        bool: 初始化成功返回True，失败返回False
    """
    try:
        config_file = Path("app/config/identify.txt")
        
        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果文件不存在，创建文件并添加说明注释和示例数据
        if not config_file.exists():
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write("# 影视名称自定义识别词文件\n")
                f.write("# 格式：原始名称 S季度 => 转换后名称 S季度\n")
                f.write("# 示例：中餐厅 S09 => 中餐厅·非洲创业季 S01\n\n")
                
                f.write("# 中餐厅系列映射\n")
                f.write("中餐厅 S09 => 中餐厅·非洲创业季 S01\n\n")
                
                f.write("# 可以添加更多映射规则\n")
                f.write("# 格式说明：\n")
                f.write("# - 左侧：Emby通知中的剧集名称和季度（如\"中餐厅 S09\"）\n")
                f.write("# - 右侧：转换后的标准化显示格式（如\"中餐厅·非洲创业季 S01\"）\n")
                f.write("# \n")
                f.write("# 注意事项：\n")
                f.write("# - 每行一个映射规则\n")
                f.write("# - 使用 \" => \" 分隔符\n")
                f.write("# - 以 # 开头的行为注释\n")
                f.write("# - 空行会被忽略\n")
            
            logger.info(f"✅ 识别词配置文件已创建: {config_file.absolute()}")
        else:
            logger.info(f"✅ 识别词配置文件已存在: {config_file.absolute()}")
        
        # 验证文件可读写
        if config_file.is_file() and os.access(config_file, os.R_OK | os.W_OK):
            logger.info(f"✅ 识别词配置文件权限正常")
            return True
        else:
            logger.error(f"❌ 识别词配置文件权限异常: {config_file.absolute()}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 初始化识别词配置文件失败: {e}")
        return False

def get_identify_config_path() -> Path:
    """
    获取识别词配置文件路径
    
    Returns:
        Path: 配置文件路径对象
    """
    return Path("app/config/identify.txt")

def validate_identify_config() -> bool:
    """
    验证识别词配置文件的有效性
    
    Returns:
        bool: 文件有效返回True，无效返回False
    """
    try:
        config_file = get_identify_config_path()
        
        if not config_file.exists():
            logger.warning(f"⚠️ 识别词配置文件不存在: {config_file.absolute()}")
            return False
        
        if not config_file.is_file():
            logger.error(f"❌ 识别词配置路径不是文件: {config_file.absolute()}")
            return False
        
        if not os.access(config_file, os.R_OK | os.W_OK):
            logger.error(f"❌ 识别词配置文件权限不足: {config_file.absolute()}")
            return False
        
        # 尝试读取文件内容验证格式
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
            logger.debug(f"📄 识别词配置文件内容长度: {len(content)} 字符")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 验证识别词配置文件失败: {e}")
        return False

def load_identify_mappings() -> dict:
    """
    加载识别词映射规则
    
    Returns:
        dict: 映射规则字典，格式为 {"原始名称 S季度": "目标名称 S季度"}
    """
    mappings = {}
    
    try:
        config_file = get_identify_config_path()
        
        if not config_file.exists():
            logger.warning(f"⚠️ 识别词配置文件不存在，返回空映射: {config_file.absolute()}")
            return mappings
        
        with open(config_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue
                
                # 解析映射规则: "原始名称 S季度 => 目标名称 S季度"
                if ' => ' in line:
                    try:
                        source, target = line.split(' => ', 1)
                        source = source.strip()
                        target = target.strip()
                        
                        if source and target:
                            mappings[source] = target
                            logger.debug(f"📝 加载映射规则 {line_num}: {source} => {target}")
                        else:
                            logger.warning(f"⚠️ 第{line_num}行映射规则格式无效（空值）: {line}")
                    except ValueError:
                        logger.warning(f"⚠️ 第{line_num}行映射规则格式无效: {line}")
                else:
                    logger.warning(f"⚠️ 第{line_num}行不包含映射分隔符 ' => ': {line}")
        
        logger.info(f"✅ 成功加载 {len(mappings)} 条识别词映射规则")
        
    except Exception as e:
        logger.error(f"❌ 加载识别词映射规则失败: {e}")
    
    return mappings

def add_identify_mapping(source: str, target: str) -> bool:
    """
    添加新的识别词映射规则
    
    Args:
        source: 原始标识，格式如 "中餐厅 S09"
        target: 目标标识，格式如 "中餐厅·非洲创业季 S01"
        
    Returns:
        bool: 添加成功返回True，失败返回False
    """
    try:
        config_file = get_identify_config_path()
        
        # 确保配置文件存在
        if not initialize_identify_config():
            return False
        
        # 构建映射规则
        mapping_rule = f"{source} => {target}"
        
        # 检查规则是否已存在
        existing_mappings = load_identify_mappings()
        if source in existing_mappings:
            if existing_mappings[source] == target:
                logger.info(f"✅ 映射规则已存在，无需重复添加: {mapping_rule}")
                return True
            else:
                logger.warning(f"⚠️ 映射规则冲突，原有: {source} => {existing_mappings[source]}，新规则: {mapping_rule}")
        
        # 追加新规则到文件
        with open(config_file, 'a', encoding='utf-8') as f:
            f.write(f"{mapping_rule}\n")
        
        logger.info(f"✅ 识别词映射规则已添加: {mapping_rule}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 添加识别词映射规则失败: {e}")
        return False

def get_identify_stats() -> dict:
    """
    获取识别词配置统计信息
    
    Returns:
        dict: 统计信息，包含文件状态、规则数量等
    """
    stats = {
        'file_exists': False,
        'file_readable': False,
        'file_writable': False,
        'total_rules': 0,
        'file_size': 0,
        'file_path': str(get_identify_config_path().absolute())
    }
    
    try:
        config_file = get_identify_config_path()
        
        if config_file.exists():
            stats['file_exists'] = True
            stats['file_readable'] = os.access(config_file, os.R_OK)
            stats['file_writable'] = os.access(config_file, os.W_OK)
            stats['file_size'] = config_file.stat().st_size
            
            # 统计有效规则数量
            mappings = load_identify_mappings()
            stats['total_rules'] = len(mappings)
        
    except Exception as e:
        logger.error(f"❌ 获取识别词配置统计信息失败: {e}")
    
    return stats