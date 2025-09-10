import os
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

def convert_emby_series_name(series_name: str, parent_index_number: int, config_file: str = "app/config/identify.txt") -> Optional[Dict[str, any]]:
    """
    根据Emby通知中的SeriesName和ParentIndexNumber进行名称转换
    
    Args:
        series_name: Emby中的剧集名称，如"中餐厅"
        parent_index_number: Emby中的季度编号，如9
        config_file: 配置文件路径
        
    Returns:
        转换结果字典，包含title和season_number，如果没有匹配则返回None
        {
            "title": "中餐厅·非洲创业季",
            "season_number": 1
        }
    """
    if not series_name or parent_index_number is None:
        return None
        
    # 生成待匹配词：支持S9和S09两种格式
    match_patterns = [
        f"{series_name} S{parent_index_number}",  # 如：中餐厅 S9
        f"{series_name} S{parent_index_number:02d}"  # 如：中餐厅 S09
    ]
    
    logger.debug(f"🔍 生成匹配模式: {match_patterns}")
    
    try:
        if not os.path.exists(config_file):
            logger.warning(f"⚠️ 配置文件不存在: {config_file}")
            return None
            
        with open(config_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # 跳过空行和注释行
            if not line or line.startswith('#'):
                continue
                
            # 解析映射规则：原始名称 S季度 => 转换后名称 S季度
            if ' => ' not in line:
                logger.warning(f"⚠️ 配置文件第{line_num}行格式错误，跳过: {line}")
                continue
                
            try:
                # 分割左右两部分
                left_part, right_part = line.split(' => ', 1)
                left_part = left_part.strip()
                right_part = right_part.strip()
                
                # 检查是否匹配左侧模式
                for match_pattern in match_patterns:
                    if match_pattern == left_part:
                        logger.info(f"✅ 找到匹配规则: {match_pattern} => {right_part}")
                        
                        # 解析转换结果
                        result = _parse_converted_result(right_part)
                        if result:
                            logger.info(f"🔄 名称转换成功: {series_name} S{parent_index_number} -> {result}")
                            return result
                        else:
                            logger.warning(f"⚠️ 转换结果解析失败: {right_part}")
                            
            except Exception as e:
                logger.warning(f"⚠️ 配置文件第{line_num}行解析错误，跳过: {line} ({e})")
                
        logger.debug(f"🔍 未找到匹配规则: {match_patterns}")
        return None
        
    except Exception as e:
        logger.error(f"❌ 读取配置文件失败: {e}")
        return None

def _parse_converted_result(converted_result: str) -> Optional[Dict[str, any]]:
    """
    解析转换结果，提取series_name和season_number
    
    Args:
        converted_result: 转换后的结果，如"中餐厅·非洲创业季 S01"
        
    Returns:
        解析结果字典或None
    """
    import re
    
    # 匹配格式：标题 S数字
    pattern = r'^(.+?)\s+S(\d+)$'
    match = re.match(pattern, converted_result.strip())
    
    if match:
        series_name = match.group(1).strip()
        season_number = int(match.group(2))
        
        return {
            "series_name": series_name,
            "season_number": season_number
        }
    else:
        logger.warning(f"⚠️ 无法解析转换结果格式: {converted_result}")
        return None