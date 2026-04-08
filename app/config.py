"""配置管理模块"""
import os
from dotenv import load_dotenv
from pathlib import Path

# 加载环境变量
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


class Config:
    """应用配置类"""
    
    # API Keys
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")
    
    # 默认设置
    DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTC/USDT")
    DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "4h")
    
    # 数据库路径
    DB_PATH = os.getenv("DB_PATH", "data/klines.db")
    
    # 支持的时间周期
    TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h', '1d']
    
    # 历史数据深度（天）
    HISTORY_DEPTH = {
        '5m': 90,
        '15m': 180,
        '30m': 365,
        '1h': 730,
        '4h': 1095,
        '1d': 1825
    }
    
    # 模式匹配默认参数
    DEFAULT_TOP_N = 10
    DEFAULT_MIN_SIMILARITY = 0.6
    
    # 模式匹配权重
    MATCHER_WEIGHTS = {
        'price': 0.50,
        'ema': 0.20,
        'volume': 0.15,
        'volatility': 0.10,
        'trend': 0.05
    }


# 全局配置实例
config = Config()
