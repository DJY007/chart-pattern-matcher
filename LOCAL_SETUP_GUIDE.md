# K线模式匹配工具 - MacBook 本地运行指南

## 📋 前置要求

### 1. 安装 Homebrew（如果还没有）
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. 安装 Python 3.11+
```bash
brew install python@3.11
```

验证安装：
```bash
python3 --version  # 应显示 3.11.x 或更高
```

### 3. 安装 Node.js 18+（用于前端开发）
```bash
brew install node
```

验证安装：
```bash
node --version  # 应显示 v18.x 或更高
npm --version
```

---

## 📥 步骤 1: 下载项目文件

### 方式 A: 直接下载（推荐）
1. 将项目文件夹从服务器下载到本地
2. 解压到你喜欢的位置，例如 `~/Projects/chart-pattern-matcher`

### 方式 B: 使用 Git（如果有Git仓库）
```bash
cd ~/Projects
git clone <你的仓库地址> chart-pattern-matcher
cd chart-pattern-matcher
```

---

## 🔧 步骤 2: 创建 Python 虚拟环境

```bash
cd ~/Projects/chart-pattern-matcher  # 进入项目目录

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 验证（命令行前应该显示 (venv)）
which python  # 应显示 .../chart-pattern-matcher/venv/bin/python
```

---

## 📦 步骤 3: 安装 Python 依赖

确保虚拟环境已激活（看到命令行前的 `(venv)`）

```bash
# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

⚠️ **注意**: 安装可能需要几分钟，请耐心等待。

---

## 🔑 步骤 4: 配置 API 密钥

### 4.1 创建环境变量文件

```bash
cp .env.example .env
```

### 4.2 编辑 .env 文件

```bash
# 使用你喜欢的编辑器
nano .env
# 或
vim .env
# 或
open -e .env  # 用 TextEdit 打开
```

### 4.3 填入你的 API 密钥

```env
# 必需：Anthropic API Key（用于图像分析）
# 获取地址：https://console.anthropic.com/
ANTHROPIC_API_KEY=sk-ant-你的密钥

# 可选：Telegram Bot Token（如需使用 Telegram Bot）
# 获取方式：在 Telegram 中搜索 @BotFather，创建新 Bot
TELEGRAM_BOT_TOKEN=你的TelegramBotToken

# 可选：Binance API（公开数据不需要）
BINANCE_API_KEY=
BINANCE_SECRET=

# 默认设置
DEFAULT_SYMBOL=BTC/USDT
DEFAULT_TIMEFRAME=4h
```

---

## 🗄️ 步骤 5: 初始化历史数据

```bash
# 确保虚拟环境已激活
source venv/bin/activate

# 运行数据初始化脚本
python scripts/init_data.py
```

这将下载以下数据（可能需要几分钟）：
- BTC/USDT: 1h, 4h, 1d
- ETH/USDT: 1h, 4h, 1d
- SOL/USDT: 1h, 4h, 1d
- BNB/USDT: 1h, 4h, 1d

---

## 🚀 步骤 6: 启动后端服务

### 方式 A: 使用 uvicorn（推荐开发模式）

```bash
# 确保虚拟环境已激活
source venv/bin/activate

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

参数说明：
- `--host 0.0.0.0`: 允许外部访问
- `--port 8000`: 服务端口
- `--reload`: 代码修改后自动重启（开发模式）

### 方式 B: 使用 Python 直接运行

```bash
source venv/bin/activate
python -m app.main
```

---

## 🌐 步骤 7: 访问 Web 界面

后端启动后，打开浏览器访问：

```
http://localhost:8000
```

或 API 文档：

```
http://localhost:8000/docs
```

---

## 🤖 步骤 8: 启动 Telegram Bot（可选）

在**新的终端窗口**中：

```bash
cd ~/Projects/chart-pattern-matcher
source venv/bin/activate
python -m app.telegram_bot
```

---

## 🔄 日常使用流程

### 启动服务（每次开机后）

```bash
# 1. 进入项目目录
cd ~/Projects/chart-pattern-matcher

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 停止服务

按 `Ctrl + C` 停止服务

### 退出虚拟环境

```bash
deactivate
```

---

## 🧪 运行测试

```bash
source venv/bin/activate

# 运行所有测试
python -m unittest discover tests/

# 运行单个测试文件
python -m unittest tests.test_pattern_matcher
python -m unittest tests.test_vision_analyzer
python -m unittest tests.test_data_manager
```

---

## 📊 性能测试

```bash
source venv/bin/activate
python scripts/benchmark.py
```

---

## 🛠️ 故障排除

### 问题 1: pip 安装失败

```bash
# 尝试升级 pip
pip install --upgrade pip setuptools wheel

# 重新安装
pip install -r requirements.txt
```

### 问题 2: 权限错误

```bash
# 使用 --user 选项
pip install --user -r requirements.txt
```

### 问题 3: 端口被占用

```bash
# 查找占用 8000 端口的进程
lsof -i :8000

# 杀死进程
kill -9 <PID>

# 或使用其他端口启动
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 问题 4: 数据下载失败

```bash
# 检查网络连接
ping binance.com

# 删除数据库重新下载
rm data/klines.db
python scripts/init_data.py
```

### 问题 5: Anthropic API 错误

- 检查 `.env` 文件中的 `ANTHROPIC_API_KEY` 是否正确
- 确认账户有可用额度
- 检查网络是否能访问 anthropic API

---

## 📁 项目结构说明

```
chart-pattern-matcher/
├── venv/                       # Python 虚拟环境（自动生成）
├── app/                        # 后端代码
│   ├── main.py                 # FastAPI 主应用
│   ├── vision_analyzer.py      # Claude Vision 图像分析
│   ├── data_manager.py         # 历史数据管理
│   ├── pattern_matcher.py      # 核心匹配引擎
│   ├── result_analyzer.py      # 结果分析
│   ├── telegram_bot.py         # Telegram Bot
│   └── config.py               # 配置管理
├── frontend/dist/              # 前端构建文件
├── scripts/
│   ├── init_data.py            # 初始化历史数据
│   └── benchmark.py            # 性能测试
├── tests/                      # 单元测试
├── data/
│   └── klines.db               # SQLite 数据库（自动生成）
├── requirements.txt            # Python 依赖
├── .env                        # 环境变量（你需要创建）
└── .env.example                # 环境变量模板
```

---

## 💡 开发提示

### 修改后端代码

使用 `--reload` 参数后，修改 `.py` 文件会自动重启服务

### 修改前端代码

如果需要修改前端：

```bash
cd frontend
npm install
npm run dev      # 开发模式
npm run build    # 构建生产版本
```

### 查看日志

```bash
# 实时查看日志
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
```

---

## 📞 需要帮助？

1. 查看 API 文档：`http://localhost:8000/docs`
2. 检查日志输出
3. 运行测试确认安装正确：`python -m unittest discover tests/`

---

## ⚠️ 免责声明

本工具仅供参考，不构成投资建议。加密货币交易风险极高，请谨慎决策。
