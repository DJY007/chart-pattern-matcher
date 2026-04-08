"""模式匹配引擎测试"""
import unittest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pattern_matcher import PatternMatcher, MatchResult


class TestPatternMatcher(unittest.TestCase):
    """测试模式匹配引擎"""
    
    def setUp(self):
        """测试前准备"""
        self.matcher = PatternMatcher()
    
    def test_normalize(self):
        """测试归一化函数"""
        # 正常序列
        seq = np.array([1, 2, 3, 4, 5])
        normalized = self.matcher._normalize(seq)
        self.assertAlmostEqual(normalized.min(), 0)
        self.assertAlmostEqual(normalized.max(), 1)
        
        # 常数序列
        const_seq = np.array([5, 5, 5, 5])
        const_normalized = self.matcher._normalize(const_seq)
        self.assertTrue(np.all(const_normalized == 0))
    
    def test_price_similarity_identical(self):
        """测试相同序列的相似度"""
        seq = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        similarity = self.matcher._calc_price_similarity(seq, seq)
        self.assertGreater(similarity, 0.9)  # 相同序列相似度应接近1
    
    def test_price_similarity_different(self):
        """测试不同序列的相似度"""
        seq1 = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
        seq2 = np.array([0.6, 0.7, 0.8, 0.9, 1.0])
        similarity = self.matcher._calc_price_similarity(seq1, seq2)
        self.assertLess(similarity, 0.5)  # 完全不同的序列相似度应较低
    
    def test_ema_state(self):
        """测试EMA状态计算"""
        # 多头排列
        bullish_closes = np.array([100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120])
        state = self.matcher._calc_ema_state(bullish_closes)
        self.assertEqual(state, 'bullish_aligned')
        
        # 空头排列
        bearish_closes = np.array([120, 118, 116, 114, 112, 110, 108, 106, 104, 102, 100])
        state = self.matcher._calc_ema_state(bearish_closes)
        self.assertEqual(state, 'bearish_aligned')
    
    def test_ema_similarity(self):
        """测试EMA相似度计算"""
        # 相同状态
        sim = self.matcher._calc_ema_similarity('bullish_aligned', 'bullish_aligned')
        self.assertEqual(sim, 1.0)
        
        # 不同状态
        sim = self.matcher._calc_ema_similarity('bullish_aligned', 'bearish_aligned')
        self.assertEqual(sim, 0.0)
        
        # 部分匹配
        sim = self.matcher._calc_ema_similarity('bullish_aligned', 'crossing')
        self.assertEqual(sim, 0.5)
    
    def test_remove_overlapping(self):
        """测试去重叠功能"""
        # 创建测试数据
        matches = [
            MatchResult(
                start_index=0, end_index=10,
                start_time="2023-01-01", end_time="2023-01-10",
                similarity_score=0.9, price_similarity=0.9, ema_similarity=0.9,
                volume_similarity=0.9, volatility_similarity=0.9, trend_similarity=0.9,
                future_return_1x=5.0, future_return_half=2.5,
                future_max_drawdown=-2.0, future_max_gain=8.0, future_trend='up'
            ),
            MatchResult(
                start_index=5, end_index=15,  # 与第一个重叠
                start_time="2023-01-05", end_time="2023-01-15",
                similarity_score=0.8, price_similarity=0.8, ema_similarity=0.8,
                volume_similarity=0.8, volatility_similarity=0.8, trend_similarity=0.8,
                future_return_1x=3.0, future_return_half=1.5,
                future_max_drawdown=-1.0, future_max_gain=5.0, future_trend='up'
            ),
            MatchResult(
                start_index=100, end_index=110,  # 不重叠
                start_time="2023-04-01", end_time="2023-04-10",
                similarity_score=0.85, price_similarity=0.85, ema_similarity=0.85,
                volume_similarity=0.85, volatility_similarity=0.85, trend_similarity=0.85,
                future_return_1x=4.0, future_return_half=2.0,
                future_max_drawdown=-1.5, future_max_gain=6.0, future_trend='up'
            ),
        ]
        
        filtered = self.matcher._remove_overlapping(matches, min_gap=5)
        
        # 应该保留第一个和第三个（第二个与第一个重叠）
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0].start_index, 0)
        self.assertEqual(filtered[1].start_index, 100)


if __name__ == '__main__':
    unittest.main()
