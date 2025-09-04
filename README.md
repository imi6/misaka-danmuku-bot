# Misaka Danmaku Bot

Telegram 机器人指令与 Misaka Danmaku API 的对接

## 快速部署

### 使用 Docker Compose（推荐）

1. 创建 `docker-compose.yml` 文件：

```yaml
version: "3.8"

services:
  # Telegram弹幕机器人服务
  misaka-danmaku-bot:
    image: ghcr.io/your-username/misaka-danmuku-bot:latest
    container_name: misaka-danmaku-bot
    restart: unless-stopped
    network_mode: host

    # 环境变量配置
    environment:
      # Telegram机器人必填配置
      - TELEGRAM_BOT_TOKEN=机器人token，botfather获取
      - ALLOWED_USER_IDS=用户id，多个用逗号分隔，get My Id 获取

      # Misaka Danmaku API必填配置
      - DANMAKU_API_BASE_URL=http://127.0.0.1:7668/api/control
      - DANMAKU_API_KEY=外部apikey

      # 代理配置（可选）
      - HTTP_PROXY=http://127.0.0.1:2083
      - HTTPS_PROXY=http://127.0.0.1:2083
      - NO_PROXY=localhost,127.0.0.1

      # 其他可选配置
      - API_TIMEOUT=60
      - LOG_LEVEL=INFO
```

2. 启动服务：

```bash
docker-compose up -d
```

### 环境变量说明

#### 必填配置

- `TELEGRAM_BOT_TOKEN`: Telegram 机器人 Token
- `ALLOWED_USER_IDS`: 允许使用机器人的用户 ID（多个用户用逗号分隔）
- `DANMAKU_API_BASE_URL`: Misaka Danmaku API 基础地址
- `DANMAKU_API_KEY`: Misaka Danmaku API 密钥

#### 可选配置

- `HTTP_PROXY`: HTTP 代理地址
- `HTTPS_PROXY`: HTTPS 代理地址
- `NO_PROXY`: 不使用代理的地址列表
- `API_TIMEOUT`: API 请求超时时间（秒，默认 60）
- `LOG_LEVEL`: 日志级别（INFO/DEBUG/WARNING/ERROR，默认 INFO）

### 本地开发

1. 克隆项目：

```bash
git clone https://github.com/your-username/misaka-danmuku-bot.git
cd misaka-danmuku-bot
```

2. 复制配置文件：

```bash
cp .env.example .env
```

3. 编辑 `.env` 文件，填入必要的配置

4. 安装依赖并运行：

```bash
pip install -r requirements.txt
python bot.py
```

## 功能特性

- 🤖 Telegram 机器人集成
- 🎯 媒体搜索和导入
- 🔄 自动导入功能
- 🌐 代理支持
- 📊 详细日志记录
- 🔥 热重载开发支持

## 许可证

MIT License
