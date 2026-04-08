"""匹配性能测试脚本"""
import asyncio
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_manager import get_data_manager
from app.pattern_matcher import get_matcher


async def benchmark_matching():
    """测试模式匹配性能"""
    print("=" * 60)
    print("模式匹配性能测试")
    print("=" * 60)
    
    # 确保数据已加载
    data_manager = get_data_manager()
    await data_manager.ensure_data("BTC/USDT", "1h")
    
    # 获取历史数据
    ohlcv = data_manager.get_ohlcv("BTC/USDT", "1h")
    timestamps = data_manager.get_timestamps("BTC/USDT", "1h")
    
    print(f"\n历史数据: {len(ohlcv)} 条记录")
    
    # 创建测试查询序列（使用最近50根K线）
    query_len = 50
    query_closes = ohlcv[-query_len:, 4]
    min_val, max_val = query_closes.min(), query_closes.max()
    query_sequence = (query_closes - min_val) / (max_val - min_val)
    
    # 测试不同参数
    test_cases = [
        {"top_n": 5, "min_similarity": 0.7},
        {"top_n": 10, "min_similarity": 0.6},
        {"top_n": 20, "min_similarity": 0.5},
    ]
    
    matcher = get_matcher()
    
    for case in test_cases:
        print(f"\n测试参数: top_n={case['top_n']}, min_similarity={case['min_similarity']}")
        
        start_time = time.time()
        
        matches = matcher.find_similar_patterns(
            query_sequence=query_sequence,
            historical_ohlcv=ohlcv[:-query_len],  # 排除查询段
            historical_timestamps=timestamps[:-query_len],
            window_size=query_len,
            top_n=case['top_n'],
            min_similarity=case['min_similarity']
        )
        
        elapsed = time.time() - start_time
        
        print(f"  匹配数量: {len(matches)}")
        print(f"  耗时: {elapsed:.2f} 秒")
        print(f"  平均相似度: {np.mean([m.similarity_score for m in matches]):.4f}" if matches else "  无匹配结果")
    
    print("\n" + "=" * 60)
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(benchmark_matching())
