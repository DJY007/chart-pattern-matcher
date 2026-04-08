"""数据初始化脚本 - 预加载常用交易对的历史数据"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_manager import HistoricalDataManager

# 预加载清单
INIT_PAIRS = [
    ("BTC/USDT", ["1h", "4h", "1d"]),
    ("ETH/USDT", ["1h", "4h", "1d"]),
    ("SOL/USDT", ["1h", "4h", "1d"]),
    ("BNB/USDT", ["1h", "4h", "1d"]),
]


async def init_data():
    """初始化历史数据"""
    print("=" * 60)
    print("K线模式匹配工具 - 数据初始化")
    print("=" * 60)
    print()
    
    data_manager = HistoricalDataManager()
    
    total_tasks = sum(len(timeframes) for _, timeframes in INIT_PAIRS)
    completed = 0
    
    for symbol, timeframes in INIT_PAIRS:
        print(f"\n📊 处理交易对: {symbol}")
        print("-" * 40)
        
        for timeframe in timeframes:
            completed += 1
            print(f"\n[{completed}/{total_tasks}] 获取 {symbol} {timeframe} 数据...")
            
            try:
                success = await data_manager.ensure_data(symbol, timeframe)
                if success:
                    print(f"✅ {symbol} {timeframe} 数据已就绪")
                else:
                    print(f"⚠️ {symbol} {timeframe} 数据获取失败")
            except Exception as e:
                print(f"❌ {symbol} {timeframe} 错误: {e}")
    
    print("\n" + "=" * 60)
    print("数据初始化完成！")
    print("=" * 60)
    
    # 显示数据状态
    print("\n📋 数据缓存状态:")
    status = data_manager.get_data_status()
    for item in status:
        print(f"  {item['symbol']} {item['timeframe']}: {item['record_count']} 条记录")


if __name__ == "__main__":
    asyncio.run(init_data())
