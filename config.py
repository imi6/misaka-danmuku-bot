import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    """Telegram Bot 配置"""
    bot_token: str
    allowed_user_ids: List[int]
    connect_timeout: float = 30.0
    read_timeout: float = 30.0
    pool_timeout: float = 60.0
    connection_pool_size: int = 20
    
    def __post_init__(self):
        if not self.bot_token:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN 不能为空")
        if not self.allowed_user_ids:
            raise ValueError("❌ ALLOWED_USER_IDS 不能为空")
        
        # 验证超时配置
        if self.connect_timeout <= 0:
            logger.warning("⚠️ connect_timeout 必须大于0，使用默认值30.0")
            self.connect_timeout = 30.0
        if self.read_timeout <= 0:
            logger.warning("⚠️ read_timeout 必须大于0，使用默认值30.0")
            self.read_timeout = 30.0
        if self.pool_timeout <= 0:
            logger.warning("⚠️ pool_timeout 必须大于0，使用默认值60.0")
            self.pool_timeout = 60.0
        if self.connection_pool_size <= 0:
            logger.warning("⚠️ connection_pool_size 必须大于0，使用默认值20")
            self.connection_pool_size = 20


@dataclass
class DanmakuAPIConfig:
    """弹幕API配置"""
    base_url: str
    api_key: str
    timeout: int = 60
    headers: Dict[str, str] = field(default_factory=lambda: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    })
    
    def __post_init__(self):
        if not self.base_url:
            raise ValueError("❌ DANMAKU_API_BASE_URL 不能为空")
        if not self.api_key:
            raise ValueError("❌ DANMAKU_API_KEY 不能为空")
        
        # 验证超时配置
        if self.timeout <= 0:
            logger.warning("⚠️ API timeout 必须大于0，使用默认值60")
            self.timeout = 60
        
        # 确保URL格式正确
        if not self.base_url.startswith(('http://', 'https://')):
            raise ValueError("❌ DANMAKU_API_BASE_URL 必须以 http:// 或 https:// 开头")
        
        # 移除末尾的斜杠
        self.base_url = self.base_url.rstrip('/')


@dataclass
class ProxyConfig:
    """代理配置"""
    socks_url: Optional[str] = None
    http_url: Optional[str] = None
    
    def __post_init__(self):
        # 验证代理URL格式
        if self.socks_url and not self.socks_url.startswith('socks'):
            logger.warning("⚠️ SOCKS代理URL格式可能不正确，应以socks开头")
        if self.http_url and not self.http_url.startswith('http'):
            logger.warning("⚠️ HTTP代理URL格式可能不正确，应以http开头")
    
    @property
    def enabled(self) -> bool:
        """检查代理是否启用"""
        return bool(self.socks_url or self.http_url)
    
    @property
    def url(self) -> Optional[str]:
        """获取代理URL（优先返回SOCKS代理）"""
        return self.socks_url or self.http_url


@dataclass
class AppConfig:
    """应用程序配置"""
    log_level: str = "INFO"
    debug: bool = False
    environment: str = "production"
    api_timeout: int = 60
    
    def __post_init__(self):
        # 验证日志级别
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.log_level = self.log_level.upper()
        if self.log_level not in valid_levels:
            logger.warning(f"⚠️ 无效的日志级别 '{self.log_level}'，使用默认值 'INFO'")
            self.log_level = "INFO"
        
        # 设置调试模式
        if self.environment.lower() in ['dev', 'development', 'debug']:
            self.debug = True
            if self.log_level == "INFO":
                self.log_level = "DEBUG"


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self._telegram: Optional[TelegramConfig] = None
        self._danmaku_api: Optional[DanmakuAPIConfig] = None
        self._proxy: Optional[ProxyConfig] = None
        self._app: Optional[AppConfig] = None
        self._load_config()
    
    def _parse_user_ids(self, user_ids_str: str) -> List[int]:
        """解析用户ID字符串"""
        if not user_ids_str:
            return []
        
        user_ids = []
        for id_str in user_ids_str.split(","):
            id_str = id_str.strip()
            if id_str.isdigit():
                user_ids.append(int(id_str))
            else:
                logger.warning(f"⚠️ 忽略无效的用户ID: {id_str}")
        
        return user_ids
    
    def _load_config(self):
        """加载配置"""
        try:
            # 加载Telegram配置
            telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            user_ids_str = os.getenv("ALLOWED_USER_IDS", "")
            user_ids = self._parse_user_ids(user_ids_str)
            
            self._telegram = TelegramConfig(
                bot_token=telegram_token,
                allowed_user_ids=user_ids,
                connect_timeout=float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", 30.0)),
                read_timeout=float(os.getenv("TELEGRAM_READ_TIMEOUT", 30.0)),
                pool_timeout=float(os.getenv("TELEGRAM_POOL_TIMEOUT", 60.0)),
                connection_pool_size=int(os.getenv("TELEGRAM_CONNECTION_POOL_SIZE", 20))
            )
            
            # 加载弹幕API配置
            self._danmaku_api = DanmakuAPIConfig(
                base_url=os.getenv("DANMAKU_API_BASE_URL", ""),
                api_key=os.getenv("DANMAKU_API_KEY", ""),
                timeout=int(os.getenv("API_TIMEOUT", 60))
            )
            
            # 加载代理配置
            self._proxy = ProxyConfig(
                socks_url=os.getenv("SOCKS_PROXY_URL") or None,
                http_url=os.getenv("HTTP_PROXY_URL") or None
            )
            
            # 加载应用配置
            self._app = AppConfig(
                log_level=os.getenv("LOG_LEVEL", "INFO"),
                debug=os.getenv("DEBUG", "false").lower() in ['true', '1', 'yes'],
                environment=os.getenv("ENVIRONMENT", "production"),
                api_timeout=int(os.getenv("API_TIMEOUT", 60))
            )
            
            logger.info("✅ 配置加载成功")
            
        except Exception as e:
            logger.error(f"❌ 配置加载失败: {e}")
            raise
    
    @property
    def telegram(self) -> TelegramConfig:
        """获取Telegram配置"""
        if self._telegram is None:
            raise RuntimeError("Telegram配置未初始化")
        return self._telegram
    
    @property
    def danmaku_api(self) -> DanmakuAPIConfig:
        """获取弹幕API配置"""
        if self._danmaku_api is None:
            raise RuntimeError("弹幕API配置未初始化")
        return self._danmaku_api
    
    @property
    def proxy(self) -> ProxyConfig:
        """获取代理配置"""
        if self._proxy is None:
            raise RuntimeError("代理配置未初始化")
        return self._proxy
    
    @property
    def app(self) -> AppConfig:
        """获取应用配置"""
        if self._app is None:
            raise RuntimeError("应用配置未初始化")
        return self._app
    
    def reload(self):
        """重新加载配置"""
        load_dotenv(override=True)
        self._load_config()
        logger.info("🔄 配置已重新加载")
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要（隐藏敏感信息）"""
        return {
            "telegram": {
                "bot_token": "***" + self.telegram.bot_token[-4:] if self.telegram.bot_token else "未配置",
                "allowed_users_count": len(self.telegram.allowed_user_ids),
                "timeouts": {
                    "connect": self.telegram.connect_timeout,
                    "read": self.telegram.read_timeout,
                    "pool": self.telegram.pool_timeout
                },
                "pool_size": self.telegram.connection_pool_size
            },
            "danmaku_api": {
                "base_url": self.danmaku_api.base_url,
                "api_key": "***" + self.danmaku_api.api_key[-4:] if self.danmaku_api.api_key else "未配置",
                "timeout": self.danmaku_api.timeout
            },
            "proxy": {
                "socks_enabled": bool(self.proxy.socks_url),
                "http_enabled": bool(self.proxy.http_url)
            },
            "app": {
                "log_level": self.app.log_level,
                "debug": self.app.debug,
                "environment": self.app.environment
            }
        }


# 创建全局配置实例
config = ConfigManager()

# 向后兼容的变量（保持现有代码正常工作）
TELEGRAM_BOT_TOKEN = config.telegram.bot_token
ALLOWED_USER_IDS = config.telegram.allowed_user_ids
DANMAKU_API_BASE_URL = config.danmaku_api.base_url
DANMAKU_API_KEY = config.danmaku_api.api_key
DANMAKU_API_HEADERS = config.danmaku_api.headers
API_TIMEOUT = config.danmaku_api.timeout
SOCKS_PROXY_URL = config.proxy.socks_url or ""
HTTP_PROXY_URL = config.proxy.http_url or ""
TELEGRAM_CONNECT_TIMEOUT = config.telegram.connect_timeout
TELEGRAM_READ_TIMEOUT = config.telegram.read_timeout
TELEGRAM_POOL_TIMEOUT = config.telegram.pool_timeout
TELEGRAM_CONNECTION_POOL_SIZE = config.telegram.connection_pool_size
LOG_LEVEL = config.app.log_level