"""图表视觉分析测试"""
import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.vision_analyzer import ChartVisionAnalyzer


class TestVisionAnalyzer(unittest.TestCase):
    """测试图表视觉分析器"""
    
    def setUp(self):
        """测试前准备"""
        # 使用模拟API密钥进行测试
        self.analyzer = ChartVisionAnalyzer(api_key="test-key")
    
    def test_validate_analysis_complete(self):
        """测试完整数据的验证"""
        data = {
            "symbol": "BTC/USDT",
            "timeframe": "4h",
            "candle_count": 50,
            "pattern": {
                "trend": "uptrend",
                "recent_trend": "up",
                "volatility": "medium",
                "key_patterns": ["channel"]
            },
            "indicators": {
                "ema_arrangement": "bullish_aligned",
                "ema_cross_signal": "none",
                "price_vs_ema": "above_all",
                "volume_pattern": "normal"
            },
            "price_structure": {
                "recent_high_position": 0.8,
                "recent_low_position": 0.2,
                "price_range_percent": 10.5,
                "current_position_in_range": 0.7
            },
            "normalized_price_sequence": [0.2, 0.3, 0.4, 0.5, 0.6],
            "confidence": 85
        }
        
        result = self.analyzer._validate_analysis(data)
        
        self.assertEqual(result["symbol"], "BTC/USDT")
        self.assertEqual(result["timeframe"], "4h")
        self.assertEqual(len(result["normalized_price_sequence"]), 5)
        self.assertEqual(result["confidence"], 85)
    
    def test_validate_analysis_missing_fields(self):
        """测试缺失字段的验证"""
        data = {
            "symbol": "BTC/USDT"
            # 缺少其他字段
        }
        
        result = self.analyzer._validate_analysis(data)
        
        # 应该填充默认值
        self.assertIn("pattern", result)
        self.assertIn("indicators", result)
        self.assertIn("normalized_price_sequence", result)
        self.assertIsInstance(result["normalized_price_sequence"], list)
    
    def test_validate_analysis_invalid_sequence(self):
        """测试无效序列的验证"""
        data = {
            "normalized_price_sequence": ["invalid", "data"]
        }
        
        result = self.analyzer._validate_analysis(data)
        
        # 无效序列应该被清空
        self.assertEqual(result["normalized_price_sequence"], [])
    
    def test_extract_json_direct(self):
        """测试直接JSON提取"""
        json_str = '{"symbol": "BTC/USDT", "confidence": 90}'
        result = self.analyzer._extract_json(json_str)
        
        self.assertEqual(result["symbol"], "BTC/USDT")
        self.assertEqual(result["confidence"], 90)
    
    def test_extract_json_with_code_block(self):
        """测试代码块中的JSON提取"""
        content = '```json\n{"symbol": "ETH/USDT", "confidence": 75}\n```'
        result = self.analyzer._extract_json(content)
        
        self.assertEqual(result["symbol"], "ETH/USDT")
        self.assertEqual(result["confidence"], 75)


if __name__ == '__main__':
    unittest.main()
