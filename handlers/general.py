from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送欢迎消息和指令列表"""
    welcome_msg = """
👋 欢迎使用 Misaka 弹幕系统机器人！
仅授权用户可使用以下指令，直接发送指令即可操作：

【📥 媒体导入】
/search [关键词] - 搜索媒体（如：/search 火影忍者）
/auto - 自动导入媒体（支持关键词搜索和平台ID导入）
/url - URL导入媒体（支持关键词搜索和URL导入）

【🔑 Token管理】
/tokens - 管理API访问令牌

【其他】
/help  - 查看帮助信息
/cancel - 取消当前操作

💡 提示：点击下方按钮快速使用常用功能！
    """
    
    # 创建自定义键盘，提供快捷按钮
    keyboard = [
        [KeyboardButton("/search"), KeyboardButton("/auto")],
        [KeyboardButton("/url"), KeyboardButton("/tokens")],
        [KeyboardButton("/help"), KeyboardButton("/cancel")]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="选择功能或直接输入命令..."
    )
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送帮助信息并显示自定义键盘"""
    help_msg = """
👋 欢迎使用 Misaka 弹幕系统机器人！
仅授权用户可使用以下指令，直接发送指令即可操作：

【📥 媒体导入】
/search [关键词] - 搜索媒体（如：/search 火影忍者）
/auto - 自动导入媒体（支持关键词搜索和平台ID导入）
/url - URL导入媒体（支持关键词搜索和URL导入）

【🔑 Token管理】
/tokens - 管理API访问令牌

【其他】
/help  - 查看帮助信息
/cancel - 取消当前操作

💡 提示：点击下方按钮快速使用常用功能！
    """
    
    # 创建自定义键盘，提供快捷按钮
    keyboard = [
        [KeyboardButton("🔍 /search"), KeyboardButton("🤖 /auto")],
        [KeyboardButton("❓ /help"), KeyboardButton("❌ /cancel")]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="选择功能或直接输入命令..."
    )
    
    await update.message.reply_text(help_msg, reply_markup=reply_markup)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消当前对话流程"""
    context.user_data.clear()
    await update.message.reply_text("✅ 已取消当前操作", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END