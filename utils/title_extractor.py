import re
from bs4 import BeautifulSoup

def extract_show_title_from_h1(soup) -> str:
    """从页面h1标签中提取节目标题（中英文字符）
    
    Args:
        soup: BeautifulSoup解析后的页面对象
        
    Returns:
        str: 节目标题，如果没有找到则返回空字符串
    """
    # 查找所有h1标签
    h1_tags = soup.find_all('h1')
    
    for h1 in h1_tags:
        if h1.get_text():
            text = h1.get_text().strip()
            
            # 提取中英文字符（包括数字、空格、常见标点）
            # 匹配中文字符、英文字母、数字、空格和常见标点符号
            chinese_english_pattern = r'[\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9\s\-_：:（）()【】\[\]《》<>""''.,!！？?]+'
            
            matches = re.findall(chinese_english_pattern, text)
            if matches:
                # 取最长的匹配结果作为节目标题
                title = max(matches, key=len).strip()
                
                # 过滤掉过短或明显不是标题的内容
                if len(title) >= 2 and not title.isdigit():
                    # 清理标题，移除首尾的标点符号
                    title = re.sub(r'^[\s\-_：:（）()【】\[\]《》<>""''.,!！？?]+|[\s\-_：:（）()【】\[\]《》<>""''.,!！？?]+$', '', title)
                    if title:
                        return title
    
    return ''