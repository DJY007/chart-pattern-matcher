"""FastAPI主应用"""
import os
import sys
import logging
from typing import Optional
from datetime import datetime
import re

import numpy as np
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
import uvicorn

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config
from app.vision_analyzer import get_analyzer as get_vision_analyzer
from app.data_manager import get_data_manager
from app.pattern_matcher import get_matcher
from app.result_analyzer import get_analyzer as get_result_analyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 常量配置
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT']
ALLOWED_TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h', '1d']

# 创建FastAPI应用
app = FastAPI(
    title="K线模式匹配工具",
    description="加密货币K线图模式匹配工具 - 上传K线截图，在历史数据中找到相似走势",
    version="1.0.0"
)

# 允许跨域（开发阶段）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务（前端）
frontend_dist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
frontend_assets_path = os.path.join(frontend_dist_path, "assets")
if os.path.exists(frontend_dist_path):
    # 挂载 assets 目录
    if os.path.exists(frontend_assets_path):
        app.mount("/assets", StaticFiles(directory=frontend_assets_path), name="assets")
    logger.info(f"Mounted static files from {frontend_dist_path}")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误"""
    return JSONResponse(
        status_code=422,
        content={"detail": "请求参数验证失败", "errors": exc.errors()}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """处理通用异常"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"}
    )


def validate_symbol(symbol: str) -> bool:
    """验证交易对格式"""
    if not symbol:
        return False
    # 支持自定义格式 XXX/YYY
    pattern = r'^[A-Z0-9]+\/[A-Z0-9]+$'
    return bool(re.match(pattern, symbol.upper()))


def validate_timeframe(timeframe: str) -> bool:
    """验证时间周期"""
    return timeframe in ALLOWED_TIMEFRAMES


@app.get("/")
async def root():
    """根路径，返回前端页面"""
    index_path = os.path.join(frontend_dist_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
        # 如果前端文件不存在，返回API信息
        return {
            "name": "K线模式匹配工具",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
            "warning": "Frontend files not found"
        }


@app.get("/api/health")
async def health():
    """健康检查接口"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/api/data/status")
async def data_status():
    """查看已缓存的历史数据状态"""
    try:
        data_manager = get_data_manager()
        status = data_manager.get_data_status()
        symbols = data_manager.get_available_symbols()
        
        return {
            "status": "ok",
            "cached_symbols": symbols,
            "data_details": status
        }
    except Exception as e:
        logger.error(f"Error getting data status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze_chart(
    file: UploadFile = File(..., description="K线截图文件 (JPG/PNG, 最大10MB)"),
    symbol: Optional[str] = Query(default=None, description="交易对，如不指定则自动识别"),
    timeframe: Optional[str] = Query(default=None, description="时间周期，如不指定则自动识别"),
    top_n: int = Query(default=10, ge=3, le=50, description="返回前N个匹配结果"),
    min_similarity: float = Query(default=0.6, ge=0.3, le=0.95, description="最低相似度阈值")
):
    """
    主接口: 上传K线截图，返回匹配结果
    """
    logger.info(f"Received analyze request: symbol={symbol}, timeframe={timeframe}, top_n={top_n}")
    
    # 验证文件
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="请上传图片文件 (JPG/PNG)")
    
    try:
        # 1. 读取上传文件（限制大小）
        image_bytes = await file.read()
        
        if len(image_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"图片大小超过限制 (最大 {MAX_FILE_SIZE // 1024 // 1024}MB)")
        
        logger.info(f"Received image: {file.filename}, size={len(image_bytes)} bytes")
        
        # 2. 使用Claude Vision分析图表
        logger.info("Analyzing chart with Vision API...")
        vision_analyzer = get_vision_analyzer()
        chart_analysis = await vision_analyzer.analyze_chart(image_bytes=image_bytes)
        logger.info(f"Chart analysis completed: confidence={chart_analysis.get('confidence', 0)}")
        
        # 3. 确定交易对和时间周期
        final_symbol = symbol or chart_analysis.get('symbol', config.DEFAULT_SYMBOL)
        final_timeframe = timeframe or chart_analysis.get('timeframe', config.DEFAULT_TIMEFRAME)
        
        # 验证并清理输入
        if final_symbol == 'UNKNOWN' or not final_symbol:
            final_symbol = config.DEFAULT_SYMBOL
        
        if final_timeframe == 'UNKNOWN' or not final_timeframe:
            final_timeframe = config.DEFAULT_TIMEFRAME
        
        # 验证symbol格式
        if not validate_symbol(final_symbol):
            logger.warning(f"Invalid symbol format: {final_symbol}, using default")
            final_symbol = config.DEFAULT_SYMBOL
        
        # 验证timeframe
        if not validate_timeframe(final_timeframe):
            logger.warning(f"Invalid timeframe: {final_timeframe}, using default")
            final_timeframe = config.DEFAULT_TIMEFRAME
        
        final_symbol = final_symbol.upper()
        final_timeframe = final_timeframe.lower()
        
        logger.info(f"Using symbol={final_symbol}, timeframe={final_timeframe}")
        
        # 4. 确保历史数据已缓存
        logger.info("Ensuring historical data...")
        data_manager = get_data_manager()
        success = await data_manager.ensure_data(final_symbol, final_timeframe)
        
        if not success:
            raise HTTPException(status_code=500, detail=f"无法获取 {final_symbol} {final_timeframe} 的历史数据")
        
        # 5. 获取历史数据
        historical_ohlcv = data_manager.get_ohlcv(final_symbol, final_timeframe)
        historical_timestamps = data_manager.get_timestamps(final_symbol, final_timeframe)
        
        if len(historical_ohlcv) == 0:
            raise HTTPException(status_code=404, detail=f"No historical data found for {final_symbol} {final_timeframe}")
        
        logger.info(f"Retrieved {len(historical_ohlcv)} historical records")
        
        # 6. 获取查询序列
        normalized_sequence = chart_analysis.get('normalized_price_sequence', [])
        
        # 如果Vision没有提供序列，使用历史数据最后一段作为查询
        if not normalized_sequence or len(normalized_sequence) < 10:
            logger.warning("No normalized sequence from Vision, using last 50 candles as query")
            query_len = min(50, len(historical_ohlcv) // 10)
            if query_len < 10:
                query_len = min(10, len(historical_ohlcv) // 2)
            query_closes = historical_ohlcv[-query_len:, 4]
            # 归一化
            min_val, max_val = query_closes.min(), query_closes.max()
            if max_val > min_val:
                normalized_sequence = ((query_closes - min_val) / (max_val - min_val)).tolist()
            else:
                normalized_sequence = [0.5] * len(query_closes)
        
        query_sequence = np.array(normalized_sequence)
        
        # 确保序列长度合理
        if len(query_sequence) < 10:
            raise HTTPException(status_code=400, detail="查询序列太短，无法进行分析")
        
        # 7. 执行模式匹配
        logger.info("Finding similar patterns...")
        matcher = get_matcher()
        
        # 获取EMA状态
        ema_state = chart_analysis.get('indicators', {}).get('ema_arrangement', 'UNKNOWN')
        volume_pattern = chart_analysis.get('indicators', {}).get('volume_pattern', 'unknown')
        
        matches = matcher.find_similar_patterns(
            query_sequence=query_sequence,
            historical_ohlcv=historical_ohlcv,
            historical_timestamps=historical_timestamps,
            window_size=len(query_sequence),
            top_n=top_n,
            ema_state=ema_state if ema_state != 'UNKNOWN' else None,
            volume_pattern=volume_pattern if volume_pattern != 'unknown' else None,
            min_similarity=min_similarity
        )
        
        logger.info(f"Found {len(matches)} matches")
        
        # 8. 汇总分析结果
        result_analyzer = get_result_analyzer()
        prediction = result_analyzer.summarize(matches)
        
        # 9. 组装返回数据
        matches_data = []
        for i, match in enumerate(matches, 1):
            matches_data.append({
                "rank": i,
                "similarity": match.similarity_score,
                "price_similarity": match.price_similarity,
                "ema_similarity": match.ema_similarity,
                "period": f"{match.start_time} ~ {match.end_time}",
                "future_return": match.future_return_1x,
                "future_trend": match.future_trend,
                "max_drawdown": match.future_max_drawdown,
                "max_gain": match.future_max_gain
            })
        
        # 准备图表对比数据
        best_match_normalized = []
        best_match_future = []
        if matches:
            best_match = matches[0]
            # 获取最佳匹配的归一化序列
            best_ohlcv = historical_ohlcv[best_match.start_index:best_match.end_index]
            if len(best_ohlcv) > 0:
                best_closes = best_ohlcv[:, 4]
                min_val, max_val = best_closes.min(), best_closes.max()
                if max_val > min_val:
                    best_match_normalized = ((best_closes - min_val) / (max_val - min_val)).tolist()
                else:
                    best_match_normalized = [0.5] * len(best_closes)
            
            # 获取最佳匹配的后续走势
            future_start = best_match.end_index
            future_end = min(future_start + len(query_sequence), len(historical_ohlcv))
            if future_start < len(historical_ohlcv):
                future_closes = historical_ohlcv[future_start:future_end, 4]
                if len(future_closes) > 0:
                    # 相对于匹配结束时的价格计算收益率
                    base_price = historical_ohlcv[future_start - 1, 4]
                    best_match_future = [0.0]  # 起点为0%
                    for price in future_closes[1:]:
                        ret = (price - base_price) / base_price * 100
                        best_match_future.append(ret)
        
        response = {
            "chart_analysis": chart_analysis,
            "query_info": {
                "symbol": final_symbol,
                "timeframe": final_timeframe,
                "sequence_length": len(query_sequence)
            },
            "matches": matches_data,
            "prediction": {
                "total_matches": prediction.total_matches,
                "avg_similarity": prediction.avg_similarity,
                "bullish_probability": prediction.bullish_probability,
                "bullish_count": prediction.bullish_count,
                "bearish_count": prediction.bearish_count,
                "neutral_count": prediction.neutral_count,
                "avg_future_return": prediction.avg_future_return,
                "median_future_return": prediction.median_future_return,
                "avg_max_gain": prediction.avg_max_gain,
                "avg_max_drawdown": prediction.avg_max_drawdown,
                "confidence": prediction.confidence,
                "suggestion": prediction.suggestion
            },
            "chart_data": {
                "query_normalized": normalized_sequence,
                "best_match_normalized": best_match_normalized,
                "best_match_future": best_match_future
            },
            "disclaimer": "⚠️ 本工具仅供参考，不构成投资建议。历史模式不代表未来表现，请谨慎决策。"
        }
        
        logger.info("Analysis completed successfully")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in analyze_chart: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@app.get("/api/symbols")
async def get_symbols():
    """获取已缓存的交易对列表"""
    try:
        data_manager = get_data_manager()
        symbols = data_manager.get_available_symbols()
        return {
            "symbols": symbols,
            "default_symbol": config.DEFAULT_SYMBOL,
            "supported_timeframes": ALLOWED_TIMEFRAMES
        }
    except Exception as e:
        logger.error(f"Error getting symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # 启动服务
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
