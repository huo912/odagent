# OmniDev Agent — 全栈代码自动生成系统

基于 **CrewAI** 的多 Agent 协作系统，输入一份需求（支持 **Word 文档**），自动完成需求分析、软件架构设计、数据库设计、全栈代码生成与测试计划，并**落地为完整的工程**（Spring Boot 后端 + Vue3/Element Plus 前端 + MySQL 数据库脚本），同时提供**可视化控制台**实时查看每个 Agent 的进度与 Token 使用量。

## ✨ 核心能力

| 能力                 | 说明                                                                    |
| -------------------- | ----------------------------------------------------------------------- |
| 📄 **Word 需求输入** | 支持上传 `.docx` 需求文档，自动解析段落、标题、表格                     |
| 🧠 **多 Agent 协作** | 需求分析师 → 软件架构师 → 数据库架构师 → 全栈工程师 → 测试工程师        |
| 🖥️ **技术栈**        | 前端 Vue3 + Vite + Element Plus；后端 Java 17 + Spring Boot 3.x + MySQL |
| 📦 **完整工程输出**  | 自动落地为 `backend/`、`frontend/`、`sql/`、`docs/` 目录                |
| 🗄️ **数据库脚本**    | 输出完整 MySQL 建表 SQL（含索引、初始化数据）                           |
| 📊 **可视化控制台**  | 实时查看每个 Agent 的进度、耗时、Token 使用量（SSE 推送）               |

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                   可视化控制台 (Vue3 + Element Plus)      │
│        上传需求 / 查看进度 / 查看 Token / 浏览工程        │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────┐
│              FastAPI 可视化服务 (端口 8000)               │
│   /api/run  /api/status  /api/events  /api/outputs       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                    CrewAI 多 Agent 编排                   │
│  需求分析师 → 架构师 → 数据库分析师 → 全栈工程师 → 测试    │
└──────────────────────────┬──────────────────────────────┘
                           │ 输出
┌──────────────────────────▼──────────────────────────────┐
│   output/  (设计文档)  +  generated_project/ (完整工程)   │
│   ├── backend/   Spring Boot 后端                        │
│   ├── frontend/  Vue3 + Element Plus 前端                │
│   ├── sql/       MySQL 数据库脚本                        │
│   └── docs/      设计文档                                │
└─────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 环境初始化

```bash
# Windows
setup.bat

# 或手动执行
python -m venv .venv
.venv\Scripts\python -m pip install -e odagent
cd web && npm install
```

### 2. 配置 LLM

编辑 `odagent/.env`：

```env
OPENAI_API_KEY=sk-xxx
# 可选：LLM_TIMEOUT_SECONDS=120
```

### 3. 启动可视化控制台

```bash
# Windows
start.bat
```

- 后端服务：http://localhost:8000
- 前端控制台：http://localhost:5173

### 4. 使用

1. 打开前端控制台 http://localhost:5173
2. 上传 **Word 需求文档**（.docx）或直接输入需求文本
3. 点击「开始生成」
4. 实时查看每个 Agent 的进度、耗时与 Token 使用量
5. 生成完成后，浏览设计文档与落地工程结构

## 🖥️ 命令行方式

```bash
# 输入需求文本
.venv\Scripts\python -m odagent.main --text "开发一个图书管理系统..."

# 输入 Word 需求文档
.venv\Scripts\python -m odagent.main --file "需求文档.docx"

# 指定输出目录
.venv\Scripts\python -m odagent.main --file "需求文档.docx" --output ./my_project
```

## 📁 工程结构

```
odagent/
├── odagent/                  # Python 后端包
│   ├── src/odagent/
│   │   ├── main.py           # CLI 入口
│   │   ├── server.py         # FastAPI 可视化服务
│   │   ├── crew.py           # 多 Agent 编排
│   │   ├── docx_parser.py    # Word 文档解析
│   │   ├── tracker.py        # 进度/Token 追踪器
│   │   ├── project_writer.py # 工程落地
│   │   ├── agents/           # 各 Agent 定义
│   │   └── config/           # Agent 配置
│   └── output/               # 生成的设计文档
├── web/                      # Vue3 + Element Plus 前端
│   └── src/App.vue           # 可视化控制台
├── setup.bat                 # 环境初始化
└── start.bat                 # 一键启动
```

## 🔌 API 接口

| 方法 | 路径                  | 说明                            |
| ---- | --------------------- | ------------------------------- |
| POST | `/api/run`            | 上传需求文档/文本，启动生成任务 |
| GET  | `/api/status`         | 获取当前进度快照                |
| GET  | `/api/events`         | SSE 实时推送进度                |
| GET  | `/api/outputs`        | 列出生成的设计文档              |
| GET  | `/api/outputs/{name}` | 读取文档内容                    |
| GET  | `/api/project/tree`   | 查看落地工程目录树              |
| GET  | `/api/project/file`   | 读取工程文件内容                |

## 🧠 Agent 角色

| Agent          | 职责                               |
| -------------- | ---------------------------------- |
| 需求分析师     | 拆解需求，输出 PRD、验收标准、风险 |
| 软件架构师     | 设计系统架构、模块划分、技术选型   |
| 数据库架构师   | 设计数据模型、表结构、索引、SQL    |
| 资深全栈工程师 | 生成 Vue3 + Spring Boot 完整代码   |
| 资深测试工程师 | 制定测试计划与测试用例             |
