from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送欢迎消息和指令列表"""
    welcome_msg = """
👋 欢迎使用 Misaka 弹幕系统机器人！
仅授权用户可使用以下指令，直接发送指令即可操作：

【📥 媒体导入】
/search [关键词] - 搜索媒体（如：/search 火影忍者）
/auto - 自动导入媒体（支持关键词搜索和平台ID导入）

【其他】
/help  - 查看帮助信息
/cancel - 取消当前操作
    """
    await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardRemove())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """重复发送帮助信息"""
    await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消当前对话流程"""
    context.user_data.clear()
    await update.message.reply_text("✅ 已取消当前操作", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END