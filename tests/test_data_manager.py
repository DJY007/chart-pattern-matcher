"""历史数据管理测试"""
import unittest
import sys
import os
import tempfile
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_manager import HistoricalDataManager


class TestDataManager(unittest.TestCase):
    """测试历史数据管理器"""
    
    def setUp(self):
        """测试前准备"""
        # 使用临时数据库
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        self.data_manager = HistoricalDataManager(db_path=self.temp_db.name)
    
    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)
    
    def test_init_db(self):
        """测试数据库初始化"""
        # 验证表是否创建
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        self.assertIn('klines', tables)
        self.assertIn('data_meta', tables)
        
        conn.close()
    
    def test_store_and_retrieve(self):
        """测试数据存储和检索"""
        # 模拟K线数据
        test_data = [
            [1609459200000, 29000.0, 29500.0, 28800.0, 29300.0, 100.5],
            [1609545600000, 29300.0, 29800.0, 29100.0, 29600.0, 150.2],
            [1609632000000, 29600.0, 30100.0, 29400.0, 29900.0, 200.8],
        ]
        
        # 存储数据
        self.data_manager._store_data("BTC/USDT", "1h", test_data)
        
        # 检索收盘价
        closes = self.data_manager.get_close_prices("BTC/USDT", "1h")
        
        self.assertEqual(len(closes), 3)
        self.assertAlmostEqual(closes[0], 29300.0)
        self.assertAlmostEqual(closes[1], 29600.0)
        self.assertAlmostEqual(closes[2], 29900.0)
    
    def test_get_ohlcv(self):
        """测试获取完整OHLCV数据"""
        # 模拟K线数据
        test_data = [
            [1609459200000, 29000.0, 29500.0, 28800.0, 29300.0, 100.5],
            [1609545600000, 29300.0, 29800.0, 29100.0, 29600.0, 150.2],
        ]
        
        self.data_manager._store_data("BTC/USDT", "1h", test_data)
        
        # 获取完整数据
        ohlcv = self.data_manager.get_ohlcv("BTC/USDT", "1h")
        
        self.assertEqual(ohlcv.shape, (2, 6))
        self.assertAlmostEqual(ohlcv[0, 4], 29300.0)  # close
        self.assertAlmostEqual(ohlcv[0, 5], 100.5)    # volume


if __name__ == '__main__':
    unittest.main()
