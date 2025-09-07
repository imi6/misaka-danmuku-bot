# 自动导入所有处理器模块，供bot.py统一注册
from .general import start, help_command, cancel
from .import_media import (
    search_media, search_media_input, process_search_media,
    import_auto, import_auto_keyword_input, import_auto_id_input,
    # import_auto_season_input, import_auto_episode_input  # 已移除
)

# 导出所有需要注册的处理器（便于bot.py导入）
__all__ = [
    "start", "help_command", "cancel",
    "search_media", "search_media_input", "process_search_media",
    "import_auto", "import_auto_keyword_input", "import_auto_id_input",
    # "import_auto_season_input", "import_auto_episode_input"  # 已移除
]