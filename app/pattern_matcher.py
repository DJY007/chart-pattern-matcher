"""模式匹配引擎 - 核心模块，使用DTW和多维度相似度进行模式匹配"""
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime
import logging
from scipy import stats
from functools import lru_cache

# 尝试导入dtaidistance，如果失败则使用自定义DTW实现
try:
    from dtaidistance import dtw
    DTAIDISTANCE_AVAILABLE = True
except ImportError:
    DTAIDISTANCE_AVAILABLE = False
    logging.warning("dtaidistance not available, using custom DTW implementation")

from app.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """匹配结果数据类"""
    start_index: int              # 匹配片段在历史数据中的起始索引
    end_index: int                # 匹配片段结束索引
    start_time: str               # 起始时间（人类可读）
    end_time: str                 # 结束时间
    similarity_score: float       # 综合相似度 0-1
    price_similarity: float       # 价格形态相似度
    ema_similarity: float         # EMA相似度
    volume_similarity: float      # 成交量相似度
    volatility_similarity: float  # 波动率相似度
    trend_similarity: float       # 趋势相似度
    
    # 后续走势统计
    future_return_1x: float       # 匹配段后续等长区间的收益率
    future_return_half: float     # 后续半段的收益率
    future_max_drawdown: float    # 后续最大回撤
    future_max_gain: float        # 后续最大涨幅
    future_trend: str             # up/down/sideways


class PatternMatcher:
    """K线模式匹配器"""
    
    def __init__(self, weights: dict = None):
        """
        初始化匹配器
        
        Args:
            weights: 各维度权重字典
        """
        self.weights = weights or config.MATCHER_WEIGHTS
        logger.info(f"PatternMatcher initialized with weights: {self.weights}")
    
    def find_similar_patterns(
        self,
        query_sequence: np.ndarray,
        historical_ohlcv: np.ndarray,
        historical_timestamps: np.ndarray,
        window_size: int = None,
        step: int = None,
        top_n: int = 10,
        ema_state: str = None,
        volume_pattern: str = None,
        min_similarity: float = 0.6
    ) -> List[MatchResult]:
        """
        查找相似的模式
        
        Args:
            query_sequence: 归一化的查询价格序列
            historical_ohlcv: 历史OHLCV数据，shape=(N, 6)
            historical_timestamps: 历史时间戳数组
            window_size: 滑动窗口大小，默认等于查询序列长度
            step: 滑动步长，默认=window_size//4
            top_n: 返回前N个最相似的结果
            ema_state: 查询图表的EMA状态
            volume_pattern: 查询图表的成交量模式
            min_similarity: 最低相似度阈值
            
        Returns:
            匹配结果列表
        """
        if len(query_sequence) == 0:
            logger.warning("Empty query sequence")
            return []
        
        if len(historical_ohlcv) == 0:
            logger.warning("Empty historical data")
            return []
        
        # 确定窗口大小
        if window_size is None:
            window_size = len(query_sequence)
        
        if step is None:
            step = max(1, window_size // 4)
        
        # 确保窗口大小合理
        if window_size > len(historical_ohlcv):
            logger.warning(f"Window size {window_size} larger than historical data {len(historical_ohlcv)}")
            window_size = len(historical_ohlcv) // 2
        
        # 对查询序列做归一化
        query_normalized = self._normalize(query_sequence)
        
        # 预计算查询序列的EMA状态（如果需要）
        query_ema_state = ema_state
        
        # 预计算整个历史数据的EMA
        historical_closes = historical_ohlcv[:, 4]
        ema7 = self._ema(historical_closes, 7)
        ema25 = self._ema(historical_closes, 25)
        ema99 = self._ema(historical_closes, 99)
        
        # 预计算查询序列的趋势斜率
        query_trend_slope = self._calc_trend_slope(query_normalized)
        
        # 滑动窗口匹配
        results = []
        max_windows = min(10000, (len(historical_ohlcv) - window_size) // step + 1)
        
        logger.info(f"Scanning up to {max_windows} windows with size {window_size}, step {step}")
        
        for i in range(0, len(historical_ohlcv) - window_size, step):
            # 限制最大窗口数，避免性能问题
            if len(results) >= max_windows:
                break
            
            # 提取窗口数据
            window_ohlcv = historical_ohlcv[i:i+window_size]
            window_closes = window_ohlcv[:, 4]
            window_volumes = window_ohlcv[:, 5]
            
            # 归一化窗口价格序列
            window_normalized = self._normalize(window_closes)
            
            # 快速粗筛：使用皮尔逊相关系数
            if len(query_normalized) == len(window_normalized):
                try:
                    corr, _ = stats.pearsonr(query_normalized, window_normalized)
                    if corr < 0.3:  # 相关系数太低，跳过详细计算
                        continue
                except:
                    pass
            
            # 计算各维度相似度
            # 1. 价格形态相似度（使用DTW）
            price_sim = self._calc_price_similarity(query_normalized, window_normalized)
            
            # 快速过滤：如果价格相似度太低，跳过其他计算
            if price_sim < min_similarity * 0.7:
                continue
            
            # 2. EMA排列相似度
            if query_ema_state:
                window_ema_state = self._calc_ema_state_from_precomputed(
                    ema7[i:i+window_size],
                    ema25[i:i+window_size],
                    ema99[i:i+window_size]
                )
                ema_sim = self._calc_ema_similarity(query_ema_state, window_ema_state)
            else:
                ema_sim = 0.5  # 默认中等相似度
            
            # 3. 成交量模式相似度
            volume_sim = self._calc_volume_similarity(
                historical_ohlcv[-window_size:, 5] if len(historical_ohlcv) >= window_size else historical_ohlcv[:, 5],
                window_volumes
            )
            
            # 4. 波动率相似度
            volatility_sim = self._calc_volatility_similarity(query_normalized, window_normalized)
            
            # 5. 趋势方向相似度（使用预计算的斜率）
            window_trend_slope = self._calc_trend_slope(window_normalized)
            trend_sim = self._calc_trend_similarity_from_slopes(query_trend_slope, window_trend_slope)
            
            # 加权计算综合相似度
            total_sim = (
                price_sim * self.weights['price'] +
                ema_sim * self.weights['ema'] +
                volume_sim * self.weights['volume'] +
                volatility_sim * self.weights['volatility'] +
                trend_sim * self.weights['trend']
            )
            
            # 如果综合相似度达到阈值，添加到结果
            if total_sim >= min_similarity:
                # 计算后续走势统计
                future_stats = self._calc_future_stats(
                    historical_closes, i + window_size, window_size
                )
                
                # 格式化时间
                start_time = datetime.fromtimestamp(historical_timestamps[i] / 1000)
                end_idx = min(i + window_size - 1, len(historical_timestamps) - 1)
                end_time = datetime.fromtimestamp(historical_timestamps[end_idx] / 1000)
                
                result = MatchResult(
                    start_index=i,
                    end_index=i + window_size,
                    start_time=start_time.strftime('%Y-%m-%d %H:%M'),
                    end_time=end_time.strftime('%Y-%m-%d %H:%M'),
                    similarity_score=round(total_sim, 4),
                    price_similarity=round(price_sim, 4),
                    ema_similarity=round(ema_sim, 4),
                    volume_similarity=round(volume_sim, 4),
                    volatility_similarity=round(volatility_sim, 4),
                    trend_similarity=round(trend_sim, 4),
                    future_return_1x=future_stats['return_1x'],
                    future_return_half=future_stats['return_half'],
                    future_max_drawdown=future_stats['max_drawdown'],
                    future_max_gain=future_stats['max_gain'],
                    future_trend=future_stats['trend']
                )
                results.append(result)
        
        logger.info(f"Found {len(results)} matches above threshold {min_similarity}")
        
        # 按相似度降序排序
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # 去除重叠窗口
        results = self._remove_overlapping(results, window_size // 2)
        
        # 取Top N
        results = results[:top_n]
        
        return results
    
    def _normalize(self, seq: np.ndarray) -> np.ndarray:
        """
        Min-max归一化到[0,1]
        
        Args:
            seq: 输入序列
            
        Returns:
            归一化后的序列
        """
        min_val, max_val = seq.min(), seq.max()
        if max_val == min_val:
            return np.zeros_like(seq)
        return (seq - min_val) / (max_val - min_val)
    
    def _calc_price_similarity(self, query: np.ndarray, candidate: np.ndarray) -> float:
        """
        计算价格形态相似度（使用DTW）
        
        Args:
            query: 查询序列（已归一化）
            candidate: 候选序列（已归一化）
            
        Returns:
            相似度分数 0-1
        """
        try:
            if DTAIDISTANCE_AVAILABLE:
                # 使用dtaidistance库，启用快速模式
                distance = dtw.distance_fast(query.astype(np.double), candidate.astype(np.double))
            else:
                # 使用自定义DTW实现
                distance = self._dtw_distance(query, candidate)
            
            # 转换为相似度
            similarity = 1 / (1 + distance)
            return min(1.0, max(0.0, similarity))
        except Exception as e:
            logger.warning(f"DTW calculation failed: {e}")
            # 降级为皮尔逊相关系数
            if len(query) == len(candidate):
                try:
                    corr, _ = stats.pearsonr(query, candidate)
                    return max(0, (corr + 1) / 2)  # 转换到0-1范围
                except:
                    pass
            return 0.5
    
    def _dtw_distance(self, s1: np.ndarray, s2: np.ndarray) -> float:
        """
        自定义DTW距离计算（当dtaidistance不可用时使用）
        
        Args:
            s1: 序列1
            s2: 序列2
            
        Returns:
            DTW距离
        """
        n, m = len(s1), len(s2)
        if n == 0 or m == 0:
            return float('inf')
        
        # 使用一维数组优化内存
        prev_row = np.full(m + 1, np.inf)
        curr_row = np.full(m + 1, np.inf)
        prev_row[0] = 0
        
        for i in range(1, n + 1):
            curr_row[0] = np.inf
            for j in range(1, m + 1):
                cost = abs(s1[i-1] - s2[j-1])
                curr_row[j] = cost + min(
                    prev_row[j],      # 插入
                    curr_row[j-1],    # 删除
                    prev_row[j-1]     # 匹配
                )
            prev_row, curr_row = curr_row, prev_row
        
        return prev_row[m]
    
    def _calc_ema_state(self, closes: np.ndarray) -> str:
        """
        计算EMA排列状态
        
        Args:
            closes: 收盘价序列
            
        Returns:
            EMA状态字符串
        """
        ema7 = self._ema(closes, 7)
        ema25 = self._ema(closes, 25)
        ema99 = self._ema(closes, 99)
        
        return self._calc_ema_state_from_precomputed(ema7, ema25, ema99)
    
    def _calc_ema_state_from_precomputed(
        self, 
        ema7: np.ndarray, 
        ema25: np.ndarray, 
        ema99: np.ndarray
    ) -> str:
        """
        从预计算的EMA值判断排列状态
        
        Args:
            ema7: EMA7序列
            ema25: EMA25序列
            ema99: EMA99序列
            
        Returns:
            EMA状态字符串
        """
        # 确保有足够的数据
        valid_len = min(len(ema7), len(ema25), len(ema99))
        if valid_len < 3:
            return 'UNKNOWN'
        
        # 取最后3根K线判断
        e7 = ema7[-3:]
        e25 = ema25[-3:]
        e99 = ema99[-3:]
        
        # 检查是否有交叉
        cross_detected = False
        for i in range(1, len(e7)):
            if (e7[i-1] <= e25[i-1] and e7[i] > e25[i]) or \
               (e7[i-1] >= e25[i-1] and e7[i] < e25[i]):
                cross_detected = True
                break
        
        if cross_detected:
            return 'crossing'
        
        # 判断排列状态
        if e7[-1] > e25[-1] > e99[-1]:
            return 'bullish_aligned'
        elif e7[-1] < e25[-1] < e99[-1]:
            return 'bearish_aligned'
        else:
            return 'tangled'
    
    def _calc_ema_similarity(self, query_state: str, candidate_state: str) -> float:
        """
        计算EMA状态相似度
        
        Args:
            query_state: 查询状态
            candidate_state: 候选状态
            
        Returns:
            相似度分数
        """
        if query_state == candidate_state:
            return 1.0
        
        if query_state == 'UNKNOWN' or candidate_state == 'UNKNOWN':
            return 0.5
        
        # 定义部分匹配规则
        partial_matches = {
            ('bullish_aligned', 'crossing'): 0.5,
            ('bearish_aligned', 'crossing'): 0.5,
            ('tangled', 'crossing'): 0.7,
            ('bullish_aligned', 'tangled'): 0.3,
            ('bearish_aligned', 'tangled'): 0.3,
        }
        
        key = tuple(sorted([query_state, candidate_state]))
        return partial_matches.get(key, 0.0)
    
    def _calc_volume_similarity(
        self, 
        query_vol: np.ndarray, 
        candidate_vol: np.ndarray
    ) -> float:
        """
        计算成交量模式相似度
        
        Args:
            query_vol: 查询成交量序列
            candidate_vol: 候选成交量序列
            
        Returns:
            相似度分数
        """
        if len(query_vol) < 2 or len(candidate_vol) < 2:
            return 0.5
        
        try:
            # 归一化成交量
            query_norm = self._normalize(query_vol)
            candidate_norm = self._normalize(candidate_vol)
            
            # 计算相关系数
            min_len = min(len(query_norm), len(candidate_norm))
            corr, _ = stats.pearsonr(query_norm[:min_len], candidate_norm[:min_len])
            return max(0, (corr + 1) / 2)
        except:
            return 0.5
    
    def _calc_volatility_similarity(
        self, 
        query_prices: np.ndarray, 
        candidate_prices: np.ndarray
    ) -> float:
        """
        计算波动率相似度
        
        Args:
            query_prices: 查询序列
            candidate_prices: 候选序列
            
        Returns:
            相似度分数
        """
        # 计算收益率序列
        if len(query_prices) < 2 or len(candidate_prices) < 2:
            return 0.5
        
        try:
            query_returns = np.diff(query_prices) / query_prices[:-1]
            candidate_returns = np.diff(candidate_prices) / candidate_prices[:-1]
            
            # 计算波动率（标准差）
            vol1 = np.std(query_returns)
            vol2 = np.std(candidate_returns)
            
            if max(vol1, vol2) < 1e-10:
                return 1.0
            
            similarity = 1 - abs(vol1 - vol2) / max(vol1, vol2, 1e-10)
            return max(0, min(1, similarity))
        except:
            return 0.5
    
    def _calc_trend_slope(self, seq: np.ndarray) -> float:
        """
        计算序列的趋势斜率
        
        Args:
            seq: 输入序列
            
        Returns:
            斜率值
        """
        if len(seq) < 2:
            return 0.0
        try:
            x = np.arange(len(seq))
            slope, _, _, _, _ = stats.linregress(x, seq)
            return slope
        except:
            return 0.0
    
    def _calc_trend_similarity_from_slopes(self, slope1: float, slope2: float) -> float:
        """
        从斜率计算趋势方向相似度
        
        Args:
            slope1: 斜率1
            slope2: 斜率2
            
        Returns:
            相似度分数
        """
        # 判断方向是否一致
        if (slope1 > 0 and slope2 > 0) or (slope1 < 0 and slope2 < 0):
            return 1.0
        elif abs(slope1) < 0.01 and abs(slope2) < 0.01:  # 都接近水平
            return 1.0
        else:
            return 0.0
    
    def _calc_trend_similarity(
        self, 
        query: np.ndarray, 
        candidate: np.ndarray
    ) -> float:
        """
        计算趋势方向相似度
        
        Args:
            query: 查询序列
            candidate: 候选序列
            
        Returns:
            相似度分数
        """
        slope1 = self._calc_trend_slope(query)
        slope2 = self._calc_trend_slope(candidate)
        return self._calc_trend_similarity_from_slopes(slope1, slope2)
    
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """
        计算EMA
        
        Args:
            data: 输入数据
            period: EMA周期
            
        Returns:
            EMA序列
        """
        if len(data) == 0:
            return np.array([])
        
        if len(data) < period:
            # 数据不足时，使用简单平均作为初始值
            ema = np.zeros_like(data, dtype=float)
            ema[0] = data[0]
            alpha = 2 / (period + 1)
            for i in range(1, len(data)):
                ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
            return ema
        
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data, dtype=float)
        # 使用SMA作为初始值
        ema[0] = np.mean(data[:period])
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        
        return ema
    
    def _remove_overlapping(
        self, 
        results: List[MatchResult], 
        min_gap: int
    ) -> List[MatchResult]:
        """
        去除重叠的匹配窗口
        
        Args:
            results: 匹配结果列表（已按相似度降序排序）
            min_gap: 最小间隔
            
        Returns:
            去重后的结果列表
        """
        if not results:
            return []
        
        filtered = [results[0]]
        
        for result in results[1:]:
            # 检查是否与已选窗口重叠
            overlap = False
            for selected in filtered:
                # 检查两个区间是否重叠
                # 区间1: [result.start_index, result.end_index]
                # 区间2: [selected.start_index, selected.end_index]
                if not (result.end_index <= selected.start_index + min_gap or 
                        result.start_index >= selected.end_index - min_gap):
                    overlap = True
                    break
            
            if not overlap:
                filtered.append(result)
        
        return filtered
    
    def _calc_future_stats(
        self, 
        historical_closes: np.ndarray, 
        match_end_index: int, 
        window_size: int
    ) -> dict:
        """
        计算匹配片段之后的走势统计
        
        Args:
            historical_closes: 历史收盘价序列
            match_end_index: 匹配段结束索引
            window_size: 窗口大小
            
        Returns:
            统计信息字典
        """
        # 检查是否有足够的数据
        if match_end_index >= len(historical_closes) or match_end_index < 1:
            return {
                'return_1x': 0.0,
                'return_half': 0.0,
                'max_drawdown': 0.0,
                'max_gain': 0.0,
                'trend': 'unknown'
            }
        
        # 获取匹配结束时的价格
        match_end_price = historical_closes[match_end_index - 1]
        
        # 获取后续数据
        future_end_1x = min(match_end_index + window_size, len(historical_closes))
        future_end_half = min(match_end_index + window_size // 2, len(historical_closes))
        
        future_1x = historical_closes[match_end_index:future_end_1x]
        future_half = historical_closes[match_end_index:future_end_half]
        
        if len(future_1x) == 0:
            return {
                'return_1x': 0.0,
                'return_half': 0.0,
                'max_drawdown': 0.0,
                'max_gain': 0.0,
                'trend': 'unknown'
            }
        
        # 计算收益率
        final_price = future_1x[-1]
        return_1x = (final_price - match_end_price) / match_end_price
        
        if len(future_half) > 0:
            return_half = (future_half[-1] - match_end_price) / match_end_price
        else:
            return_half = 0.0
        
        # 计算最大回撤和最大涨幅
        running_max = np.maximum.accumulate(future_1x)
        gains = (future_1x - match_end_price) / match_end_price
        
        drawdowns = (future_1x - running_max) / running_max
        
        max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0.0
        max_gain = np.max(gains) if len(gains) > 0 else 0.0
        
        # 判断趋势
        if return_1x > 0.02:
            trend = 'up'
        elif return_1x < -0.02:
            trend = 'down'
        else:
            trend = 'sideways'
        
        return {
            'return_1x': round(return_1x * 100, 2),  # 转换为百分比
            'return_half': round(return_half * 100, 2),
            'max_drawdown': round(max_drawdown * 100, 2),
            'max_gain': round(max_gain * 100, 2),
            'trend': trend
        }


# 全局匹配器实例
_matcher: Optional[PatternMatcher] = None


def get_matcher() -> PatternMatcher:
    """获取全局匹配器实例（单例模式）"""
    global _matcher
    if _matcher is None:
        _matcher = PatternMatcher()
    return _matcher
