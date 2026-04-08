"""历史数据管理模块 - 从Binance获取并缓存历史K线数据"""
import ccxt
import sqlite3
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import asyncio
import logging
from pathlib import Path
import contextlib

from app.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConnection:
    """数据库连接上下文管理器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
    
    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
            self.conn.close()
        return False


class HistoricalDataManager:
    """历史K线数据管理器"""
    
    # 支持的时间周期
    TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h', '1d']
    
    # 默认拉取的历史深度（天）
    HISTORY_DEPTH = {
        '5m': 90,
        '15m': 180,
        '30m': 365,
        '1h': 730,
        '4h': 1095,
        '1d': 1825
    }
    
    def __init__(self, db_path: str = None):
        """
        初始化数据管理器
        
        Args:
            db_path: SQLite数据库路径
        """
        self.db_path = db_path or config.DB_PATH
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'
            },
            'timeout': 30000,  # 30秒超时
        })
        
        # 确保数据目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_db()
        logger.info(f"HistoricalDataManager initialized with db: {self.db_path}")
    
    def _init_db(self):
        """初始化数据库表结构"""
        with DatabaseConnection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建K线数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS klines (
                    symbol TEXT,
                    timeframe TEXT,
                    timestamp INTEGER,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                )
            ''')
            
            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_klines_lookup 
                ON klines(symbol, timeframe, timestamp)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_klines_symbol_timeframe
                ON klines(symbol, timeframe)
            ''')
            
            # 创建数据元信息表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS data_meta (
                    symbol TEXT,
                    timeframe TEXT,
                    last_update INTEGER,
                    record_count INTEGER,
                    PRIMARY KEY (symbol, timeframe)
                )
            ''')
            
            logger.info("Database initialized")
    
    async def ensure_data(self, symbol: str, timeframe: str) -> bool:
        """
        确保指定交易对和周期的历史数据已缓存且最新
        
        Args:
            symbol: 交易对，如 "BTC/USDT"
            timeframe: 时间周期，如 "1h"
            
        Returns:
            是否成功
        """
        if timeframe not in self.TIMEFRAMES:
            logger.warning(f"Unsupported timeframe: {timeframe}")
            return False
        
        try:
            # 检查数据库中最新数据
            with DatabaseConnection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT MAX(timestamp) FROM klines 
                    WHERE symbol = ? AND timeframe = ?
                ''', (symbol, timeframe))
                
                result = cursor.fetchone()
                latest_timestamp = result[0] if result[0] else 0
            
            # 计算需要拉取的时间范围
            now = datetime.now()
            depth_days = self.HISTORY_DEPTH.get(timeframe, 365)
            start_date = now - timedelta(days=depth_days)
            start_timestamp = int(start_date.timestamp() * 1000)
            
            # 如果数据缺失或过时，则拉取
            one_hour_ago = int(now.timestamp() * 1000) - 3600000
            if latest_timestamp < one_hour_ago:
                logger.info(f"Fetching data for {symbol} {timeframe}...")
                await self._fetch_and_store(symbol, timeframe, start_timestamp)
            else:
                logger.info(f"Data for {symbol} {timeframe} is up to date")
            
            return True
            
        except Exception as e:
            logger.error(f"Error ensuring data for {symbol} {timeframe}: {e}")
            return False
    
    async def _fetch_and_store(self, symbol: str, timeframe: str, since: int):
        """
        从Binance拉取数据并存储
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            since: 起始时间戳（毫秒）
        """
        all_ohlcv = []
        current_since = since
        max_retries = 3
        retry_count = 0
        
        # ccxt每次最多返回1000根K线，需要循环拉取
        while retry_count < max_retries:
            try:
                logger.info(f"Fetching {symbol} {timeframe} from {datetime.fromtimestamp(current_since/1000)}")
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=1000)
                
                if not ohlcv or len(ohlcv) == 0:
                    break
                
                all_ohlcv.extend(ohlcv)
                
                # 更新since为最后一条数据的时间戳+1
                last_timestamp = ohlcv[-1][0]
                if last_timestamp <= current_since:
                    break
                
                current_since = last_timestamp + 1
                
                # 如果已经拉取到最新数据，停止
                if last_timestamp > int(datetime.now().timestamp() * 1000) - 60000:
                    break
                
                # 重置重试计数
                retry_count = 0
                
                # 避免请求过快
                await asyncio.sleep(0.5)
                
            except ccxt.NetworkError as e:
                retry_count += 1
                logger.warning(f"Network error fetching data (retry {retry_count}/{max_retries}): {e}")
                await asyncio.sleep(2 ** retry_count)  # 指数退避
            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error fetching data: {e}")
                break
            except Exception as e:
                logger.error(f"Error fetching data: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    break
                await asyncio.sleep(1)
        
        if all_ohlcv:
            # 存储到数据库
            self._store_data_batch(symbol, timeframe, all_ohlcv)
            logger.info(f"Stored {len(all_ohlcv)} records for {symbol} {timeframe}")
    
    def _store_data(self, symbol: str, timeframe: str, ohlcv: List[List]):
        """
        存储K线数据到数据库（单条插入，保留用于兼容）
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            ohlcv: K线数据列表
        """
        self._store_data_batch(symbol, timeframe, ohlcv)
    
    def _store_data_batch(self, symbol: str, timeframe: str, ohlcv: List[List]):
        """
        批量存储K线数据到数据库
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            ohlcv: K线数据列表
        """
        if not ohlcv:
            return
        
        with DatabaseConnection(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 批量插入数据
            data_to_insert = [
                (symbol, timeframe, candle[0], candle[1], candle[2], 
                 candle[3], candle[4], candle[5])
                for candle in ohlcv
            ]
            
            cursor.executemany('''
                INSERT OR IGNORE INTO klines 
                (symbol, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)
            
            # 更新元信息
            cursor.execute('''
                INSERT OR REPLACE INTO data_meta (symbol, timeframe, last_update, record_count)
                VALUES (?, ?, ?, (SELECT COUNT(*) FROM klines WHERE symbol = ? AND timeframe = ?))
            ''', (symbol, timeframe, int(datetime.now().timestamp() * 1000), symbol, timeframe))
            
            logger.info(f"Batch inserted {len(ohlcv)} records for {symbol} {timeframe}")
    
    def get_close_prices(self, symbol: str, timeframe: str) -> np.ndarray:
        """
        获取指定交易对和周期的所有收盘价序列
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            
        Returns:
            收盘价数组
        """
        with DatabaseConnection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT close FROM klines 
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp ASC
            ''', (symbol, timeframe))
            
            results = cursor.fetchall()
            
        return np.array([r[0] for r in results])
    
    def get_ohlcv(
        self, 
        symbol: str, 
        timeframe: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None
    ) -> np.ndarray:
        """
        获取完整OHLCV数据
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            start_ts: 起始时间戳（可选）
            end_ts: 结束时间戳（可选）
            
        Returns:
            shape=(N, 6) 的数组，列: [timestamp, open, high, low, close, volume]
        """
        with DatabaseConnection(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT timestamp, open, high, low, close, volume 
                FROM klines 
                WHERE symbol = ? AND timeframe = ?
            '''
            params = [symbol, timeframe]
            
            if start_ts:
                query += ' AND timestamp >= ?'
                params.append(start_ts)
            if end_ts:
                query += ' AND timestamp <= ?'
                params.append(end_ts)
            
            query += ' ORDER BY timestamp ASC'
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        return np.array(results)
    
    def get_timestamps(self, symbol: str, timeframe: str) -> np.ndarray:
        """
        获取时间戳序列
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            
        Returns:
            时间戳数组
        """
        with DatabaseConnection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp FROM klines 
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp ASC
            ''', (symbol, timeframe))
            
            results = cursor.fetchall()
            
        return np.array([r[0] for r in results])
    
    def get_data_status(self) -> List[dict]:
        """
        获取数据缓存状态
        
        Returns:
            数据状态列表
        """
        with DatabaseConnection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT symbol, timeframe, last_update, record_count 
                FROM data_meta
                ORDER BY symbol, timeframe
            ''')
            
            results = cursor.fetchall()
            
        status = []
        for row in results:
            try:
                last_update = datetime.fromtimestamp(row[2] / 1000).isoformat()
            except (ValueError, OSError):
                last_update = None
            
            status.append({
                'symbol': row[0],
                'timeframe': row[1],
                'last_update': last_update,
                'record_count': row[3]
            })
        
        return status
    
    def get_available_symbols(self) -> List[str]:
        """
        获取已缓存的交易对列表
        
        Returns:
            交易对列表
        """
        with DatabaseConnection(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT DISTINCT symbol FROM data_meta')
            results = cursor.fetchall()
            
        return [r[0] for r in results]


# 全局数据管理器实例
_data_manager: Optional[HistoricalDataManager] = None


def get_data_manager() -> HistoricalDataManager:
    """获取全局数据管理器实例（单例模式）"""
    global _data_manager
    if _data_manager is None:
        _data_manager = HistoricalDataManager()
    return _data_manager
