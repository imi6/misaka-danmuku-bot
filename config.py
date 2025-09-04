import os
from dotenv import load_dotenv
from typing import List

# 加载.env文件中的环境变量
load_dotenv()

# ------------------------------
# Telegram 机器人配置
# ------------------------------
# 机器人令牌（必填）
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ 请在.env文件中配置TELEGRAM_BOT_TOKEN（从@BotFather获取）")

# 允许访问的用户ID白名单（必填，转为整数列表）
ALLOWED_USER_IDS_STR: str = os.getenv("ALLOWED_USER_IDS", "")
if not ALLOWED_USER_IDS_STR:
    raise ValueError("❌ 请在.env文件中配置ALLOWED_USER_IDS（从@userinfobot获取）")

# 解析用户ID："123,456" → [123, 456]
ALLOWED_USER_IDS: List[int] = []
for id_str in ALLOWED_USER_IDS_STR.split(","):
    id_str = id_str.strip()
    if id_str.isdigit():
        ALLOWED_USER_IDS.append(int(id_str))
if not ALLOWED_USER_IDS:
    raise ValueError("❌ ALLOWED_USER_IDS格式错误，需填写纯数字（多个用逗号分隔）")

# ------------------------------
# Misaka Danmaku API 配置
# ------------------------------
# API基础地址（必填）
DANMAKU_API_BASE_URL: str = os.getenv("DANMAKU_API_BASE_URL", "")
if not DANMAKU_API_BASE_URL:
    raise ValueError("❌ 请在.env文件中配置DANMAKU_API_BASE_URL")

# API鉴权密钥（必填）
DANMAKU_API_KEY: str = os.getenv("DANMAKU_API_KEY", "")
if not DANMAKU_API_KEY:
    raise ValueError("❌ 请在.env文件中配置DANMAKU_API_KEY（从弹幕系统获取）")

# ------------------------------
# 代理配置（可选）
# ------------------------------
# SOCKS代理配置（可选，格式：socks5://127.0.0.1:1080）
SOCKS_PROXY_URL: str = os.getenv("SOCKS_PROXY_URL", "")

# HTTP代理配置（可选，格式：http://127.0.0.1:8080）
HTTP_PROXY_URL: str = os.getenv("HTTP_PROXY_URL", "")

# ------------------------------
# 通用配置
# ------------------------------
# API请求超时时间（默认60秒）
API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", 60))
if API_TIMEOUT <= 0:
    API_TIMEOUT = 60

# Telegram连接超时时间（默认30秒）
TELEGRAM_CONNECT_TIMEOUT: float = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", 30.0))
if TELEGRAM_CONNECT_TIMEOUT <= 0:
    TELEGRAM_CONNECT_TIMEOUT = 30.0

# Telegram读取超时时间（默认30秒）
TELEGRAM_READ_TIMEOUT: float = float(os.getenv("TELEGRAM_READ_TIMEOUT", 30.0))
if TELEGRAM_READ_TIMEOUT <= 0:
    TELEGRAM_READ_TIMEOUT = 30.0

# Telegram连接池超时时间（默认60秒）
TELEGRAM_POOL_TIMEOUT: float = float(os.getenv("TELEGRAM_POOL_TIMEOUT", 60.0))
if TELEGRAM_POOL_TIMEOUT <= 0:
    TELEGRAM_POOL_TIMEOUT = 60.0

# Telegram连接池大小（默认20个连接）
TELEGRAM_CONNECTION_POOL_SIZE: int = int(os.getenv("TELEGRAM_CONNECTION_POOL_SIZE", 20))
if TELEGRAM_CONNECTION_POOL_SIZE <= 0:
    TELEGRAM_CONNECTION_POOL_SIZE = 20

# 日志级别（默认INFO）
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
if LOG_LEVEL not in VALID_LOG_LEVELS:
    LOG_LEVEL = "INFO"

# API请求头（固定JSON格式）
DANMAKU_API_HEADERS: dict = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
}