# K线模式匹配工具

一个加密货币K线图模式匹配工具。用户上传一张K线截图（带EMA/MA等指标），系统自动识别图表特征，在历史数据中找到相似走势，并统计后续涨跌概率，帮助预测接下来的行情。

## 功能特性

- 📸 **智能图表识别**: 使用 Claude Vision API 自动识别K线图特征
- 🔍 **历史模式匹配**: 基于 DTW 算法在历史数据中查找相似走势
- 📊 **多维度分析**: 综合价格形态、EMA排列、成交量、波动率等多个维度
- 📈 **预测统计**: 统计历史相似走势的后续涨跌概率和收益率
- 🌐 **Web界面**: 美观的React前端，支持拖拽上传和实时可视化
- 🤖 **Telegram Bot**: 支持通过 Telegram 直接分析K线截图

## 技术栈

- **后端**: Python 3.11+, FastAPI
- **前端**: React + TypeScript + Tailwind CSS + Vite
- **数据库**: SQLite（存储历史K线数据缓存）
- **核心依赖**:
  - `ccxt` — 从 Binance 拉取历史K线数据
  - `numpy`, `scipy` — 数学计算、DTW相似度
  - `anthropic` — 调用 Claude API 做图表视觉分析
  - `recharts` — 前端图表可视化

## 快速开始

### 1. 安装依赖

```bash
# 克隆项目
cd chart-pattern-matcher

# 安装Python依赖
pip install -r requirements.txt

# 安装前端依赖（可选，如需修改前端）
cd frontend
npm install
npm run build
cd ..
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入API密钥
```

必需配置:
- `ANTHROPIC_API_KEY` - Claude API密钥
- `TELEGRAM_BOT_TOKEN` - Telegram Bot Token（可选）

### 3. 初始化历史数据

```bash
python scripts/init_data.py
```

### 4. 启动Web服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 http://localhost:8000 使用Web界面

### 5. 启动Telegram Bot（可选）

```bash
python -m app.telegram_bot
```

## 使用说明

### Web界面

1. 打开浏览器访问 http://localhost:8000
2. 拖拽或点击上传K线截图
3. 选择交易对和时间周期（可选）
4. 点击"开始匹配"按钮
5. 查看匹配结果和预测分析

### Telegram Bot

1. 在Telegram中搜索你的Bot
2. 发送 `/start` 查看帮助
3. 直接发送K线截图
4. Bot会自动分析并返回结果

## API接口

### 分析图表

```http
POST /api/analyze
Content-Type: multipart/form-data

file: <图片文件>
symbol: BTC/USDT (可选)
timeframe: 4h (可选)
top_n: 10 (可选)
min_similarity: 0.6 (可选)
```

返回示例:
```json
{
  "chart_analysis": { ... },
  "query_info": {
    "symbol": "BTC/USDT",
    "timeframe": "4h",
    "sequence_length": 40
  },
  "matches": [ ... ],
  "prediction": {
    "bullish_probability": 0.72,
    "avg_future_return": 8.3,
    "confidence": "high",
    "suggestion": "..."
  },
  "chart_data": { ... },
  "disclaimer": "..."
}
```

### 健康检查

```http
GET /api/health
```

### 数据状态

```http
GET /api/data/status
```

## 项目结构

```
chart-pattern-matcher/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 主应用
│   ├── config.py               # 配置管理
│   ├── vision_analyzer.py      # Claude Vision 图表分析
│   ├── data_manager.py         # 历史数据管理
│   ├── pattern_matcher.py      # 核心匹配引擎
│   ├── result_analyzer.py      # 结果汇总分析
│   └── telegram_bot.py         # Telegram Bot
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # 主组件
│   │   ├── main.tsx            # 入口
│   │   └── index.css           # 样式
│   ├── dist/                   # 构建输出
│   └── package.json
├── scripts/
│   ├── init_data.py            # 初始化历史数据
│   └── benchmark.py            # 性能测试
├── tests/
│   ├── test_pattern_matcher.py
│   ├── test_vision_analyzer.py
│   └── test_data_manager.py
├── data/                       # SQLite数据库
├── requirements.txt
├── .env.example
└── README.md
```

## 匹配算法说明

### 多维度加权相似度

1. **价格形态相似度 (50%)**: 使用 DTW 算法计算归一化价格序列的相似度
2. **EMA排列相似度 (20%)**: 比较 EMA7/25/99 的排列状态
3. **成交量模式相似度 (15%)**: 比较成交量序列的相似度
4. **波动率相似度 (10%)**: 比较价格波动的标准差
5. **趋势方向相似度 (5%)**: 使用线性回归判断趋势方向

### 综合评分

```
总相似度 = 价格相似度 × 0.50
         + EMA相似度 × 0.20
         + 成交量相似度 × 0.15
         + 波动率相似度 × 0.10
         + 趋势相似度 × 0.05
```

## 测试

```bash
# 运行所有测试
python -m unittest discover tests/

# 运行单个测试文件
python -m unittest tests.test_pattern_matcher
python -m unittest tests.test_vision_analyzer
python -m unittest tests.test_data_manager
```

## 性能优化

- **粗筛过滤**: 使用皮尔逊相关系数快速过滤不相似的窗口
- **降采样**: 对长序列进行降采样后再匹配
- **EMA缓存**: 预计算整个历史数据的EMA值
- **去重叠**: 移除时间重叠的匹配结果

## 注意事项

1. **DTW计算较慢**: 历史数据量大时，滑动窗口DTW计算可能耗时较长
2. **Vision识别精度**: Claude Vision提取的归一化价格序列是近似值
3. **免责声明**: 历史模式不代表未来表现，本工具仅供参考
4. **数据更新**: 系统会自动检查并增量更新历史数据

## 许可证

MIT License

## 免责声明

⚠️ **本工具仅供参考，不构成投资建议。加密货币交易风险极高，请谨慎决策。**
