"""结果分析模块 - 汇总匹配结果，生成预测摘要"""
from dataclasses import dataclass
from typing import List
import logging

from app.pattern_matcher import MatchResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PredictionSummary:
    """预测摘要数据类"""
    total_matches: int
    avg_similarity: float
    
    # 后续走势统计
    bullish_count: int          # 后续上涨的匹配数
    bearish_count: int          # 后续下跌的匹配数
    neutral_count: int          # 后续横盘的匹配数
    bullish_probability: float  # 上涨概率
    
    avg_future_return: float    # 平均后续收益率
    median_future_return: float # 中位数后续收益率
    avg_max_gain: float         # 平均最大涨幅
    avg_max_drawdown: float     # 平均最大回撤
    
    confidence: str             # low/medium/high
    suggestion: str             # 简要建议文字


class ResultAnalyzer:
    """结果分析器"""
    
    def summarize(self, matches: List[MatchResult]) -> PredictionSummary:
        """
        汇总所有匹配结果，生成预测摘要
        
        Args:
            matches: 匹配结果列表
            
        Returns:
            预测摘要
        """
        if not matches:
            return PredictionSummary(
                total_matches=0,
                avg_similarity=0.0,
                bullish_count=0,
                bearish_count=0,
                neutral_count=0,
                bullish_probability=0.0,
                avg_future_return=0.0,
                median_future_return=0.0,
                avg_max_gain=0.0,
                avg_max_drawdown=0.0,
                confidence='low',
                suggestion='未找到足够的匹配数据，无法进行预测。'
            )
        
        total = len(matches)
        
        # 统计涨跌
        bullish_count = sum(1 for m in matches if m.future_trend == 'up')
        bearish_count = sum(1 for m in matches if m.future_trend == 'down')
        neutral_count = sum(1 for m in matches if m.future_trend == 'sideways')
        
        # 计算上涨概率
        bullish_probability = bullish_count / total if total > 0 else 0
        
        # 计算平均相似度
        avg_similarity = sum(m.similarity_score for m in matches) / total
        
        # 计算收益率统计
        returns = [m.future_return_1x for m in matches]
        avg_future_return = sum(returns) / total
        
        # 计算中位数
        sorted_returns = sorted(returns)
        mid = total // 2
        if total % 2 == 0:
            median_future_return = (sorted_returns[mid-1] + sorted_returns[mid]) / 2
        else:
            median_future_return = sorted_returns[mid]
        
        # 计算平均最大涨幅和回撤
        avg_max_gain = sum(m.future_max_gain for m in matches) / total
        avg_max_drawdown = sum(m.future_max_drawdown for m in matches) / total
        
        # 判断置信度
        confidence = self._calculate_confidence(total, bullish_probability, avg_similarity)
        
        # 生成建议
        suggestion = self._generate_suggestion(
            confidence,
            bullish_probability,
            avg_future_return,
            avg_max_gain,
            avg_max_drawdown
        )
        
        return PredictionSummary(
            total_matches=total,
            avg_similarity=round(avg_similarity, 4),
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            neutral_count=neutral_count,
            bullish_probability=round(bullish_probability, 2),
            avg_future_return=round(avg_future_return, 2),
            median_future_return=round(median_future_return, 2),
            avg_max_gain=round(avg_max_gain, 2),
            avg_max_drawdown=round(avg_max_drawdown, 2),
            confidence=confidence,
            suggestion=suggestion
        )
    
    def _calculate_confidence(
        self, 
        total_matches: int, 
        bullish_probability: float,
        avg_similarity: float
    ) -> str:
        """
        计算置信度
        
        Args:
            total_matches: 匹配数量
            bullish_probability: 上涨概率
            avg_similarity: 平均相似度
            
        Returns:
            置信度等级 (low/medium/high)
        """
        # 计算涨跌一致性（偏离50%的程度）
        consistency = abs(bullish_probability - 0.5) * 2  # 0-1范围
        
        if total_matches >= 5 and consistency >= 0.4 and avg_similarity >= 0.75:
            return 'high'
        elif total_matches >= 3 and consistency >= 0.2 and avg_similarity >= 0.65:
            return 'medium'
        else:
            return 'low'
    
    def _generate_suggestion(
        self,
        confidence: str,
        bullish_probability: float,
        avg_future_return: float,
        avg_max_gain: float,
        avg_max_drawdown: float
    ) -> str:
        """
        生成建议文字
        
        Args:
            confidence: 置信度
            bullish_probability: 上涨概率
            avg_future_return: 平均后续收益率
            avg_max_gain: 平均最大涨幅
            avg_max_drawdown: 平均最大回撤
            
        Returns:
            建议文字
        """
        if confidence == 'low':
            return '匹配数据不足或一致性较低，建议谨慎参考，结合其他分析工具综合判断。'
        
        # 判断方向
        if bullish_probability > 0.6:
            direction = '上涨'
            direction_emoji = '📈'
        elif bullish_probability < 0.4:
            direction = '下跌'
            direction_emoji = '📉'
        else:
            direction = '横盘震荡'
            direction_emoji = '➡️'
        
        # 构建建议
        parts = [f'{direction_emoji} 历史相似走势中{bullish_probability*100:.0f}%后续{direction}，']
        
        if avg_future_return > 0:
            parts.append(f'平均收益+{avg_future_return:.1f}%，')
        else:
            parts.append(f'平均收益{avg_future_return:.1f}%，')
        
        parts.append(f'平均最大涨幅可达+{avg_max_gain:.1f}%，')
        parts.append(f'但需注意最大回撤可达{avg_max_drawdown:.1f}%。')
        
        if confidence == 'high':
            parts.append('整体信号较强，但仍需结合市场情况综合判断。')
        else:
            parts.append('信号中等，建议结合其他指标确认。')
        
        return ''.join(parts)


# 全局分析器实例
_analyzer: ResultAnalyzer = None


def get_analyzer() -> ResultAnalyzer:
    """获取全局分析器实例（单例模式）"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ResultAnalyzer()
    return _analyzer
