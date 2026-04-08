"""Telegram Bot 模块"""
import logging
import tempfile
import os
from typing import Optional, Dict, Any
import asyncio

from telegram import Update, MenuButtonCommands, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

from app.config import config
from app.vision_analyzer import get_analyzer as get_vision_analyzer
from app.data_manager import get_data_manager
from app.pattern_matcher import get_matcher
from app.result_analyzer import get_analyzer as get_result_analyzer

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 白名单用户ID列表（只允许这些用户使用Bot）
# 获取你的用户ID: 在Telegram中发送 /myid 给 Bot
ALLOWED_USER_IDS = [
    1795326193,  # Bot所有者
]


class ChartMatcherBot:
    """K线模式匹配 Telegram Bot"""
    
    def __init__(self, token: Optional[str] = None, allowed_users: Optional[list] = None):
        """
        初始化Bot
        
        Args:
            token: Telegram Bot Token
            allowed_users: 允许使用的用户ID列表
        """
        self.token = token or config.TELEGRAM_BOT_TOKEN
        if not self.token:
            raise ValueError("Telegram Bot Token is required")
        
        # 设置白名单
        self.allowed_user_ids = set(allowed_users or ALLOWED_USER_IDS)
        if self.allowed_user_ids:
            logger.info(f"Bot restricted to users: {self.allowed_user_ids}")
        else:
            logger.warning("No whitelist set - Bot is open to all users!")
        
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
        
        # 用户默认设置（使用线程安全的字典）
        self._user_defaults_lock = asyncio.Lock()
        self.user_defaults: Dict[int, Dict[str, Any]] = {}
        
        logger.info("ChartMatcherBot initialized")
    
    def _is_authorized(self, user_id: int) -> bool:
        """检查用户是否有权限使用Bot"""
        # 如果没有设置白名单，允许所有人使用
        if not self.allowed_user_ids:
            return True
        return user_id in self.allowed_user_ids
    
    async def _setup_menu(self):
        """设置Bot菜单按钮"""
        try:
            # 设置菜单按钮类型为命令菜单
            await self.application.bot.set_chat_menu_button(
                menu_button=MenuButtonCommands()
            )
            
            # 设置命令列表（会显示在菜单中）
            commands = [
                BotCommand("start", "🚀 开始使用"),
                BotCommand("help", "❓ 使用帮助"),
                BotCommand("myid", "🆔 查看我的ID"),
                BotCommand("status", "📊 当前设置"),
                BotCommand("set_pair", "💱 设置交易对"),
                BotCommand("set_timeframe", "⏱️ 设置周期"),
            ]
            await self.application.bot.set_my_commands(commands)
            logger.info("Bot menu commands set up successfully")
        except Exception as e:
            logger.warning(f"Failed to set up menu: {e}")
    
    def _setup_handlers(self):
        """设置命令处理器"""
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("help", self._cmd_help))
        self.application.add_handler(CommandHandler("myid", self._cmd_myid))
        self.application.add_handler(CommandHandler("set_pair", self._cmd_set_pair))
        self.application.add_handler(CommandHandler("set_timeframe", self._cmd_set_timeframe))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        
        # 图片消息处理器
        self.application.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))
        
        # 回调处理器（用于按钮交互）
        self.application.add_handler(CallbackQueryHandler(self._handle_callback))
        
        # 错误处理器
        self.application.add_error_handler(self._error_handler)
        
        # 设置启动后回调来配置菜单
        self.application.post_init = self._post_init
    
    async def _post_init(self, application: Application):
        """Bot启动后的初始化"""
        await self._setup_menu()
    
    async def _get_user_defaults(self, user_id: int) -> Dict[str, Any]:
        """获取用户默认设置（线程安全）"""
        async with self._user_defaults_lock:
            return self.user_defaults.get(user_id, {}).copy()
    
    async def _set_user_default(self, user_id: int, key: str, value: Any):
        """设置用户默认设置（线程安全）"""
        async with self._user_defaults_lock:
            if user_id not in self.user_defaults:
                self.user_defaults[user_id] = {}
            self.user_defaults[user_id][key] = value
    
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        user_id = update.effective_user.id
        
        # 检查权限
        if not self._is_authorized(user_id):
            await update.message.reply_text("⛔ 你没有权限使用此Bot。")
            return
        
        # 创建快捷按钮
        keyboard = [
            [InlineKeyboardButton("📊 查看设置", callback_data="back_to_status")],
            [InlineKeyboardButton("❓ 使用帮助", callback_data="show_help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_message = (
            "👋 欢迎使用 K线模式匹配工具 Bot！\n\n"
            "我可以帮你分析K线截图，在历史数据中找到相似走势。\n\n"
            "📸 直接发送K线截图，我会自动分析并返回匹配结果。\n\n"
            "⚠️ 免责声明：本工具仅供参考，不构成投资建议。"
        )
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    
    async def _cmd_myid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /myid 命令 - 获取自己的用户ID"""
        user = update.effective_user
        user_id = user.id
        username = user.username or "未设置"
        
        is_authorized = self._is_authorized(user_id)
        status = "✅ 已授权" if is_authorized else "⛔ 未授权"
        
        message = (
            f"👤 你的用户信息\n\n"
            f"用户ID: <code>{user_id}</code>\n"
            f"用户名: @{username}\n"
            f"状态: {status}\n\n"
            f"ℹ️ 将此ID发送给Bot管理员以获取使用权限。"
        )
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        user_id = update.effective_user.id
        
        # 检查权限
        if not self._is_authorized(user_id):
            await update.message.reply_text("⛔ 你没有权限使用此Bot。")
            return
        
        # 创建快捷按钮
        keyboard = [
            [InlineKeyboardButton("📊 查看设置", callback_data="back_to_status")],
            [InlineKeyboardButton("🚀 开始使用", callback_data="back_to_start")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        help_message = (
            "📖 K线模式匹配工具 使用帮助\n\n"
            "1️⃣ 直接发送K线截图\n"
            "   - 支持 JPG/PNG 格式\n"
            "   - 自动识别币种和周期\n"
            "   - 返回历史相似走势分析\n\n"
            "2️⃣ 设置默认参数\n"
            "   点击 📊 查看设置 按钮\n"
            "   选择交易对和时间周期\n\n"
            "3️⃣ 使用菜单\n"
            "   点击左下角 🗂️ 菜单按钮\n"
            "   快速访问所有功能\n\n"
            "⚠️ 注意事项：\n"
            "- 首次分析可能需要较长时间\n"
            "- 分析结果基于历史数据\n"
            "- 请结合其他工具综合判断"
        )
        await update.message.reply_text(help_message, reply_markup=reply_markup)
    
    async def _cmd_set_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /set_pair 命令"""
        user_id = update.effective_user.id
        
        # 检查权限
        if not self._is_authorized(user_id):
            await update.message.reply_text("⛔ 你没有权限使用此Bot。")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ 请提供交易对\n\n"
                "示例: /set_pair BTC/USDT\n"
                "支持: BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT"
            )
            return
        
        pair = context.args[0].upper()
        
        # 验证交易对格式
        if '/' not in pair:
            await update.message.reply_text("❌ 交易对格式错误，应为 XXX/USD 或 XXX/USDT")
            return
        
        # 保存用户设置
        await self._set_user_default(user_id, 'symbol', pair)
        
        await update.message.reply_text(f"✅ 默认交易对已设置为: {pair}")
    
    async def _cmd_set_timeframe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /set_timeframe 命令"""
        user_id = update.effective_user.id
        
        # 检查权限
        if not self._is_authorized(user_id):
            await update.message.reply_text("⛔ 你没有权限使用此Bot。")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ 请提供时间周期\n\n"
                "示例: /set_timeframe 4h\n"
                "支持: 5m, 15m, 30m, 1h, 4h, 1d"
            )
            return
        
        timeframe = context.args[0].lower()
        valid_timeframes = ['5m', '15m', '30m', '1h', '4h', '1d']
        
        if timeframe not in valid_timeframes:
            await update.message.reply_text(
                f"❌ 不支持的时间周期: {timeframe}\n"
                f"支持: {', '.join(valid_timeframes)}"
            )
            return
        
        # 保存用户设置
        await self._set_user_default(user_id, 'timeframe', timeframe)
        
        await update.message.reply_text(f"✅ 默认时间周期已设置为: {timeframe}")
    
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /status 命令"""
        user_id = update.effective_user.id
        
        # 检查权限
        if not self._is_authorized(user_id):
            await update.message.reply_text("⛔ 你没有权限使用此Bot。")
            return
        
        defaults = await self._get_user_defaults(user_id)
        
        symbol = defaults.get('symbol', config.DEFAULT_SYMBOL)
        timeframe = defaults.get('timeframe', config.DEFAULT_TIMEFRAME)
        
        # 创建设置按钮
        keyboard = [
            [InlineKeyboardButton("💱 选择交易对", callback_data="select_pair")],
            [InlineKeyboardButton("⏱️ 选择时间周期", callback_data="select_timeframe")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status_message = (
            "📊 当前设置\n\n"
            f"交易对: {symbol}\n"
            f"时间周期: {timeframe}\n\n"
            "点击下方按钮快速修改设置:"
        )
        await update.message.reply_text(status_message, reply_markup=reply_markup)
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮回调"""
        query = update.callback_query
        user_id = update.effective_user.id
        
        # 检查权限
        if not self._is_authorized(user_id):
            await query.answer("⛔ 你没有权限使用此Bot。", show_alert=True)
            return
        
        await query.answer()  # 确认收到回调
        
        data = query.data
        
        if data == "select_pair":
            # 显示交易对选择按钮
            keyboard = [
                [InlineKeyboardButton("BTC/USDT", callback_data="pair_BTC/USDT")],
                [InlineKeyboardButton("ETH/USDT", callback_data="pair_ETH/USDT")],
                [InlineKeyboardButton("SOL/USDT", callback_data="pair_SOL/USDT")],
                [InlineKeyboardButton("BNB/USDT", callback_data="pair_BNB/USDT")],
                [InlineKeyboardButton("XRP/USDT", callback_data="pair_XRP/USDT")],
                [InlineKeyboardButton("ADA/USDT", callback_data="pair_ADA/USDT")],
                [InlineKeyboardButton("🔙 返回", callback_data="back_to_status")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "💱 选择交易对:\n\n当前支持的币种:",
                reply_markup=reply_markup
            )
        
        elif data == "select_timeframe":
            # 显示时间周期选择按钮
            keyboard = [
                [
                    InlineKeyboardButton("5m", callback_data="tf_5m"),
                    InlineKeyboardButton("15m", callback_data="tf_15m"),
                    InlineKeyboardButton("30m", callback_data="tf_30m"),
                ],
                [
                    InlineKeyboardButton("1h", callback_data="tf_1h"),
                    InlineKeyboardButton("4h", callback_data="tf_4h"),
                    InlineKeyboardButton("1d", callback_data="tf_1d"),
                ],
                [InlineKeyboardButton("🔙 返回", callback_data="back_to_status")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "⏱️ 选择时间周期:\n\n5m/15m/30m 适合短线\n1h/4h 适合中线\n1d 适合长线",
                reply_markup=reply_markup
            )
        
        elif data.startswith("pair_"):
            # 设置交易对
            pair = data.replace("pair_", "")
            await self._set_user_default(user_id, 'symbol', pair)
            await query.edit_message_text(f"✅ 交易对已设置为: {pair}\n\n发送 /status 查看设置")
        
        elif data.startswith("tf_"):
            # 设置时间周期
            tf = data.replace("tf_", "")
            await self._set_user_default(user_id, 'timeframe', tf)
            await query.edit_message_text(f"✅ 时间周期已设置为: {tf}\n\n发送 /status 查看设置")
        
        elif data == "back_to_status":
            # 返回状态页面
            defaults = await self._get_user_defaults(user_id)
            symbol = defaults.get('symbol', config.DEFAULT_SYMBOL)
            timeframe = defaults.get('timeframe', config.DEFAULT_TIMEFRAME)
            
            keyboard = [
                [InlineKeyboardButton("💱 选择交易对", callback_data="select_pair")],
                [InlineKeyboardButton("⏱️ 选择时间周期", callback_data="select_timeframe")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📊 当前设置\n\n"
                f"交易对: {symbol}\n"
                f"时间周期: {timeframe}\n\n"
                f"点击下方按钮快速修改设置:",
                reply_markup=reply_markup
            )
        
        elif data == "show_help":
            # 显示帮助信息
            help_text = (
                "📖 使用帮助\n\n"
                "1️⃣ 直接发送K线截图\n"
                "   - 支持 JPG/PNG 格式\n"
                "   - 自动识别币种和周期\n"
                "   - 返回历史相似走势分析\n\n"
                "2️⃣ 设置默认参数\n"
                "   点击 📊 查看设置 按钮\n"
                "   选择交易对和时间周期\n\n"
                "3️⃣ 使用菜单\n"
                "   点击左下角 🗂️ 菜单按钮\n"
                "   快速访问所有功能\n\n"
                "⚠️ 注意事项：\n"
                "- 首次分析可能需要较长时间\n"
                "- 分析结果基于历史数据\n"
                "- 请结合其他工具综合判断"
            )
            keyboard = [[InlineKeyboardButton("🔙 返回", callback_data="back_to_start")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(help_text, reply_markup=reply_markup)
        
        elif data == "back_to_start":
            # 返回开始页面
            keyboard = [
                [InlineKeyboardButton("📊 查看设置", callback_data="back_to_status")],
                [InlineKeyboardButton("❓ 使用帮助", callback_data="show_help")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            welcome_message = (
                "👋 欢迎使用 K线模式匹配工具 Bot！\n\n"
                "我可以帮你分析K线截图，在历史数据中找到相似走势。\n\n"
                "📸 直接发送K线截图，我会自动分析并返回匹配结果。\n\n"
                "⚠️ 免责声明：本工具仅供参考，不构成投资建议。"
            )
            await query.edit_message_text(welcome_message, reply_markup=reply_markup)
    
    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理用户发送的图片"""
        user_id = update.effective_user.id
        
        # 检查权限
        if not self._is_authorized(user_id):
            await update.message.reply_text("⛔ 你没有权限使用此Bot。")
            return
        
        tmp_path = None
        
        # 发送"正在分析"消息
        processing_msg = await update.message.reply_text(
            "🔄 正在分析图表，请稍候..."
        )
        
        try:
            # 获取用户默认设置
            defaults = await self._get_user_defaults(user_id)
            symbol = defaults.get('symbol', config.DEFAULT_SYMBOL)
            timeframe = defaults.get('timeframe', config.DEFAULT_TIMEFRAME)
            
            # 下载图片
            photo = update.message.photo[-1]  # 获取最大尺寸
            file = await context.bot.get_file(photo.file_id)
            
            # 保存到临时文件
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            
            # 分析图表
            await context.bot.edit_message_text(
                "🔄 正在识别图表特征...",
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id
            )
            
            vision_analyzer = get_vision_analyzer()
            chart_analysis = await vision_analyzer.analyze_chart(image_path=tmp_path)
            
            # 使用Vision识别的结果或用户默认设置
            final_symbol = chart_analysis.get('symbol', 'UNKNOWN')
            if final_symbol == 'UNKNOWN' or not final_symbol:
                final_symbol = symbol
            
            final_timeframe = chart_analysis.get('timeframe', 'UNKNOWN')
            if final_timeframe == 'UNKNOWN' or not final_timeframe:
                final_timeframe = timeframe
            
            final_symbol = final_symbol.upper()
            final_timeframe = final_timeframe.lower()
            
            await context.bot.edit_message_text(
                f"🔄 正在获取 {final_symbol} {final_timeframe} 历史数据...",
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id
            )
            
            # 获取历史数据
            data_manager = get_data_manager()
            success = await data_manager.ensure_data(final_symbol, final_timeframe)
            
            if not success:
                await context.bot.edit_message_text(
                    f"❌ 无法获取 {final_symbol} {final_timeframe} 的历史数据",
                    chat_id=update.effective_chat.id,
                    message_id=processing_msg.message_id
                )
                return
            
            historical_ohlcv = data_manager.get_ohlcv(final_symbol, final_timeframe)
            historical_timestamps = data_manager.get_timestamps(final_symbol, final_timeframe)
            
            if len(historical_ohlcv) == 0:
                await context.bot.edit_message_text(
                    f"❌ 没有找到 {final_symbol} {final_timeframe} 的历史数据",
                    chat_id=update.effective_chat.id,
                    message_id=processing_msg.message_id
                )
                return
            
            await context.bot.edit_message_text(
                "🔄 正在匹配历史模式...",
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id
            )
            
            # 获取查询序列
            normalized_sequence = chart_analysis.get('normalized_price_sequence', [])
            if not normalized_sequence or len(normalized_sequence) < 10:
                query_len = min(50, len(historical_ohlcv) // 10)
                if query_len < 10:
                    query_len = min(10, len(historical_ohlcv) // 2)
                query_closes = historical_ohlcv[-query_len:, 4]
                min_val, max_val = query_closes.min(), query_closes.max()
                if max_val > min_val:
                    normalized_sequence = ((query_closes - min_val) / (max_val - min_val)).tolist()
                else:
                    normalized_sequence = [0.5] * len(query_closes)
            
            import numpy as np
            query_sequence = np.array(normalized_sequence)
            
            # 执行模式匹配
            matcher = get_matcher()
            ema_state = chart_analysis.get('indicators', {}).get('ema_arrangement', 'UNKNOWN')
            
            matches = matcher.find_similar_patterns(
                query_sequence=query_sequence,
                historical_ohlcv=historical_ohlcv,
                historical_timestamps=historical_timestamps,
                window_size=len(query_sequence),
                top_n=5,  # Bot返回前5个
                ema_state=ema_state if ema_state != 'UNKNOWN' else None,
                min_similarity=0.6
            )
            
            # 汇总结果
            result_analyzer = get_result_analyzer()
            prediction = result_analyzer.summarize(matches)
            
            # 格式化结果消息
            result_message = self._format_result(
                final_symbol,
                final_timeframe,
                chart_analysis,
                prediction,
                matches
            )
            
            await context.bot.edit_message_text(
                result_message,
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id,
                parse_mode='HTML'
            )
                
        except Exception as e:
            logger.error(f"Error processing photo: {e}", exc_info=True)
            try:
                await context.bot.edit_message_text(
                    f"❌ 分析失败: {str(e)}\n\n请重试或联系管理员。",
                    chat_id=update.effective_chat.id,
                    message_id=processing_msg.message_id
                )
            except Exception as edit_error:
                logger.error(f"Failed to edit message: {edit_error}")
                await update.message.reply_text(
                    f"❌ 分析失败: {str(e)}\n\n请重试或联系管理员。"
                )
        finally:
            # 清理临时文件
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file: {e}")
    
    def _format_result(
        self,
        symbol: str,
        timeframe: str,
        chart_analysis: dict,
        prediction: Any,
        matches: list
    ) -> str:
        """格式化结果为Telegram消息"""
        # 识别到的形态
        patterns = chart_analysis.get('pattern', {})
        trend = patterns.get('trend', 'UNKNOWN')
        key_patterns = patterns.get('key_patterns', [])
        
        trend_emoji = {
            'uptrend': '📈',
            'downtrend': '📉',
            'sideways': '➡️',
            'reversal_up': '🔼',
            'reversal_down': '🔽'
        }.get(trend, '📊')
        
        # 置信度表情
        confidence_emoji = {
            'high': '🟢',
            'medium': '🟡',
            'low': '⚪'
        }.get(prediction.confidence, '⚪')
        
        lines = [
            f"<b>📊 K线模式匹配结果</b>",
            f"{'━' * 20}",
            f"",
            f"🎯 <b>识别:</b> {symbol} {timeframe}",
            f"{trend_emoji} <b>趋势:</b> {trend}",
        ]
        
        if key_patterns:
            lines.append(f"🔍 <b>形态:</b> {', '.join(key_patterns[:3])}")
        
        lines.extend([
            f"",
            f"<b>🔮 预测摘要</b>",
            f"{confidence_emoji} <b>置信度:</b> {prediction.confidence.upper()}",
            f"📈 <b>上涨概率:</b> {prediction.bullish_probability * 100:.0f}%",
            f"💰 <b>平均收益:</b> {prediction.avg_future_return:+.1f}%",
            f"📊 <b>匹配数:</b> {prediction.total_matches}",
            f"",
            f"<b>📋 Top {min(3, len(matches))} 匹配</b>",
        ])
        
        for i, match in enumerate(matches[:3], 1):
            trend_icon = '📈' if match.future_trend == 'up' else '📉' if match.future_trend == 'down' else '➡️'
            lines.append(
                f"{i}. 相似度 {(match.similarity_score * 100):.0f}% | {match.start_time[:10]}\n"
                f"   后续: {trend_icon} {match.future_return_1x:+.1f}%"
            )
        
        lines.extend([
            f"",
            f"<i>⚠️ 仅供参考，不构成投资建议</i>"
        ])
        
        return '\n'.join(lines)
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """错误处理器"""
        logger.error(f"Update {update} caused error: {context.error}")
        
        # 尝试通知用户
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ 发生错误，请稍后重试。"
                )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
    
    def run(self):
        """启动Bot"""
        logger.info("Starting ChartMatcherBot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


# 主入口
def main():
    """Telegram Bot 主入口"""
    bot = ChartMatcherBot()
    bot.run()


if __name__ == "__main__":
    main()
