"""图表视觉分析模块 - 使用Claude Vision API分析K线截图"""
import anthropic
import base64
import json
import re
from pathlib import Path
from typing import Optional, Union
import logging
from io import BytesIO
from functools import wraps
import time

from app.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 图片大小限制（MB）
MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

# Claude Vision 分析提示词
CHART_ANALYSIS_PROMPT = """
你是一个专业的加密货币K线图分析器。请仔细观察这张K线图截图，提取以下信息并以严格的JSON格式返回，不要返回任何其他内容：

{
  "symbol": "交易对，如 BTC/USDT，如果无法确定写 UNKNOWN",
  "timeframe": "K线周期，如 1m/5m/15m/30m/1h/4h/1d/1w，如果无法确定写 UNKNOWN",
  "candle_count": "截图中大约有多少根K线，整数",
  "pattern": {
    "trend": "整体趋势: uptrend/downtrend/sideways/reversal_up/reversal_down",
    "recent_trend": "最近10-20根K线的趋势: up/down/sideways",
    "volatility": "波动性: low/medium/high",
    "key_patterns": ["识别到的形态，如: double_top, head_shoulders, triangle, wedge, channel, flag, cup_handle, consolidation, breakout, breakdown 等"]
  },
  "indicators": {
    "ema_arrangement": "EMA/MA排列状态: bullish_aligned(多头排列)/bearish_aligned(空头排列)/tangled(缠绕)/crossing(交叉中)",
    "ema_cross_signal": "最近是否有EMA交叉: golden_cross/death_cross/none",
    "price_vs_ema": "价格相对于主要EMA的位置: above_all/below_all/between",
    "volume_pattern": "成交量模式: increasing/decreasing/spike/normal/unknown"
  },
  "price_structure": {
    "recent_high_position": "近期高点在截图中的相对位置(0-1，0=最左，1=最右)",
    "recent_low_position": "近期低点在截图中的相对位置(0-1)",
    "price_range_percent": "截图中价格波动幅度百分比估算",
    "current_position_in_range": "当前价格在整个截图价格区间的位置(0=最低,1=最高)"
  },
  "normalized_price_sequence": [
    "将截图中的K线收盘价走势归一化为0-1之间的序列",
    "采样约30-50个点，均匀分布",
    "例如: [0.2, 0.25, 0.3, 0.28, ...]",
    "这是最关键的数据，请尽可能准确"
  ],
  "confidence": "你对以上分析的置信度: 0-100"
}

注意事项：
1. normalized_price_sequence 是最重要的字段，请仔细观察K线走势，提取尽可能准确的归一化价格序列
2. 如果图表中有明确的EMA/MA线，请仔细观察它们的排列和交叉情况
3. 如果某些信息无法从截图中确定，请如实标注为 UNKNOWN
4. 只返回JSON，不要有任何额外文字
"""


def retry_on_error(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)  # 指数退避
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries} attempts failed")
            raise last_exception
        return wrapper
    return decorator


class ChartVisionAnalyzer:
    """K线图表视觉分析器"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化分析器
        
        Args:
            api_key: Anthropic API密钥，如果不提供则从配置读取
        """
        self.api_key = api_key or config.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key is required")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        logger.info("ChartVisionAnalyzer initialized")
    
    async def analyze_chart(
        self, 
        image_path: Optional[str] = None, 
        image_bytes: Optional[bytes] = None,
        image_base64: Optional[str] = None
    ) -> dict:
        """
        分析K线截图，返回结构化特征数据
        
        Args:
            image_path: 图片文件路径
            image_bytes: 图片二进制数据
            image_base64: base64编码的图片数据
            
        Returns:
            包含图表分析结果的字典
        """
        # 获取图片的base64编码
        try:
            if image_base64:
                base64_data = image_base64
            elif image_bytes:
                # 检查图片大小
                if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                    logger.warning(f"Image size {len(image_bytes)} exceeds limit, compressing...")
                    image_bytes = self._compress_image(image_bytes)
                base64_data = base64.b64encode(image_bytes).decode('utf-8')
            elif image_path:
                base64_data = self._load_image_to_base64(image_path)
            else:
                raise ValueError("必须提供 image_path、image_bytes 或 image_base64 之一")
        except Exception as e:
            logger.error(f"Error preparing image: {e}")
            return self._get_default_result()
        
        # 检测图片格式
        image_format = self._detect_image_format(base64_data)
        
        # 调用API（带重试）
        return await self._call_vision_api(base64_data, image_format)
    
    @retry_on_error(max_retries=3, delay=1.0)
    async def _call_vision_api(self, base64_data: str, image_format: str) -> dict:
        """
        调用Claude Vision API（带重试）
        
        Args:
            base64_data: base64编码的图片
            image_format: 图片格式
            
        Returns:
            分析结果字典
        """
        try:
            logger.info("Calling Claude Vision API...")
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": f"image/{image_format}",
                                    "data": base64_data
                                }
                            },
                            {
                                "type": "text",
                                "text": CHART_ANALYSIS_PROMPT
                            }
                        ]
                    }
                ]
            )
            
            # 解析响应
            content = response.content[0].text
            logger.info("Received response from Claude Vision API")
            
            # 提取JSON
            analysis_result = self._extract_json(content)
            
            # 验证和修正结果
            validated_result = self._validate_analysis(analysis_result)
            
            return validated_result
            
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return self._get_default_result()
        except Exception as e:
            logger.error(f"Error calling Claude Vision API: {e}")
            return self._get_default_result()
    
    def _load_image_to_base64(self, image_path: str) -> str:
        """将图片文件转换为base64编码"""
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        # 检查图片大小
        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            logger.warning(f"Image size {len(image_bytes)} exceeds limit, compressing...")
            image_bytes = self._compress_image(image_bytes)
        
        return base64.b64encode(image_bytes).decode('utf-8')
    
    def _compress_image(self, image_bytes: bytes, max_size: tuple = (1024, 1024)) -> bytes:
        """
        压缩图片
        
        Args:
            image_bytes: 原始图片字节
            max_size: 最大尺寸 (宽, 高)
            
        Returns:
            压缩后的图片字节
        """
        try:
            from PIL import Image
            
            img = Image.open(BytesIO(image_bytes))
            
            # 转换为RGB（如果是RGBA）
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # 调整大小
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # 保存为JPEG
            output = BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            compressed_bytes = output.getvalue()
            
            logger.info(f"Image compressed from {len(image_bytes)} to {len(compressed_bytes)} bytes")
            return compressed_bytes
            
        except ImportError:
            logger.warning("PIL not available, returning original image")
            return image_bytes
        except Exception as e:
            logger.error(f"Error compressing image: {e}")
            return image_bytes
    
    def _detect_image_format(self, base64_data: str) -> str:
        """根据base64头部检测图片格式"""
        header = base64_data[:20]
        if header.startswith('/9j/'):
            return 'jpeg'
        elif header.startswith('iVBORw0KGgo'):
            return 'png'
        elif header.startswith('R0lGOD'):
            return 'gif'
        elif header.startswith('UklGR'):
            return 'webp'
        else:
            return 'png'  # 默认返回png
    
    def _extract_json(self, content: str) -> dict:
        """从响应内容中提取JSON"""
        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取JSON代码块
        json_pattern = r'```(?:json)?\s*([\s\S]*?)```'
        matches = re.findall(json_pattern, content)
        
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue
        
        # 尝试提取花括号内容
        try:
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                return json.loads(content[start:end+1])
        except json.JSONDecodeError:
            pass
        
        logger.warning("Failed to extract JSON from response, using default")
        return self._get_default_result()
    
    def _validate_analysis(self, data: dict) -> dict:
        """验证和修正分析结果"""
        if not isinstance(data, dict):
            logger.warning("Invalid data type, using default")
            return self._get_default_result()
        
        result = data.copy()
        
        # 确保必要字段存在
        required_fields = ['symbol', 'timeframe', 'candle_count', 'pattern', 
                          'indicators', 'price_structure', 'normalized_price_sequence', 'confidence']
        
        for field in required_fields:
            if field not in result:
                if field == 'normalized_price_sequence':
                    result[field] = []
                elif field == 'confidence':
                    result[field] = 0
                elif field in ['pattern', 'indicators', 'price_structure']:
                    result[field] = {}
                else:
                    result[field] = 'UNKNOWN'
        
        # 确保嵌套字段存在
        for nested_field in ['pattern', 'indicators', 'price_structure']:
            if not isinstance(result.get(nested_field), dict):
                result[nested_field] = {}
        
        # 验证 normalized_price_sequence
        seq = result.get('normalized_price_sequence', [])
        if isinstance(seq, list) and len(seq) > 0:
            try:
                seq = [float(x) for x in seq if x is not None]
                seq = [max(0.0, min(1.0, x)) for x in seq]
                result['normalized_price_sequence'] = seq
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid sequence data: {e}")
                result['normalized_price_sequence'] = []
        else:
            result['normalized_price_sequence'] = []
        
        # 验证枚举值
        valid_trends = ['uptrend', 'downtrend', 'sideways', 'reversal_up', 'reversal_down', 'UNKNOWN']
        pattern = result.get('pattern', {})
        if pattern.get('trend') not in valid_trends:
            pattern['trend'] = 'UNKNOWN'
        
        valid_ema_arrangements = ['bullish_aligned', 'bearish_aligned', 'tangled', 'crossing', 'UNKNOWN']
        indicators = result.get('indicators', {})
        if indicators.get('ema_arrangement') not in valid_ema_arrangements:
            indicators['ema_arrangement'] = 'UNKNOWN'
        
        # 确保confidence是整数
        try:
            result['confidence'] = max(0, min(100, int(result.get('confidence', 0))))
        except (ValueError, TypeError):
            result['confidence'] = 0
        
        # 确保candle_count是整数
        try:
            result['candle_count'] = int(result.get('candle_count', 0))
        except (ValueError, TypeError):
            result['candle_count'] = 0
        
        return result
    
    def _get_default_result(self) -> dict:
        """获取默认分析结果"""
        return {
            "symbol": "UNKNOWN",
            "timeframe": "UNKNOWN",
            "candle_count": 0,
            "pattern": {
                "trend": "UNKNOWN",
                "recent_trend": "UNKNOWN",
                "volatility": "UNKNOWN",
                "key_patterns": []
            },
            "indicators": {
                "ema_arrangement": "UNKNOWN",
                "ema_cross_signal": "none",
                "price_vs_ema": "UNKNOWN",
                "volume_pattern": "unknown"
            },
            "price_structure": {
                "recent_high_position": 0.5,
                "recent_low_position": 0.5,
                "price_range_percent": 0,
                "current_position_in_range": 0.5
            },
            "normalized_price_sequence": [],
            "confidence": 0
        }


# 全局分析器实例
_analyzer: Optional[ChartVisionAnalyzer] = None


def get_analyzer() -> ChartVisionAnalyzer:
    """获取全局分析器实例（单例模式）"""
    global _analyzer
    if _analyzer is None:
        _analyzer = ChartVisionAnalyzer()
    return _analyzer
