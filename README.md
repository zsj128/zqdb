# 智能法律咨询助手

基于 **RAG（检索增强生成）** 技术的智能法律咨询系统，提供法律条文检索、案例分析与 AI 智能问答能力。

## ✨ 功能特性

- 📜 **法律条文检索**：关键词精准检索法条，按条文分块展示
- 🤖 **AI 智能问答**：基于知识库检索 + 大模型生成，支持流式输出
- ⚖️ **案例分析**：展示指导性案例的案情、裁判要点与裁判结果
- 🔍 **混合检索**：向量语义 + Jieba 关键词 + RRF 融合排序，检索精度更高
- 🧠 **CoT 思维链**：结论 + 法律分析，自动标注法条引用 `【引用：《XX法》第X条】`
- 👥 **多用户隔离**：每用户独立知识库，数据互不干扰
- 🛡 **服务容错**：超时 / 重试 / 熔断 / 兜底，LLM 不可用时降级返回法条原文
- 🔐 **管理员后台**：查看数据库、按用户/表/行删除数据
- 📊 **运行监控**：请求数、缓存命中率、降级率、熔断状态

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Element Plus + Axios |
| 后端 | FastAPI + Uvicorn |
| 向量数据库 | ChromaDB |
| 嵌入模型 | sentence-transformers（paraphrase-multilingual-MiniLM-L12-v2） |
| 分词 | Jieba |
| 大模型 | 通义千问（OpenAI 兼容接口，可替换） |
| 关系数据库 | MySQL |
| 部署 | Docker + Docker Compose |

## 📁 目录结构

```
zqdb/
├── backend/            # FastAPI 后端（模块化拆分）
│   ├── main.py         # 应用装配中心
│   ├── routes.py       # 路由定义
│   ├── kb_store.py     # 知识库存储（ChromaDB 用户隔离）
│   ├── retrieval.py    # 混合检索（Jieba + 向量 + RRF）
│   ├── llm_service.py  # LLM 调用 + 容错
│   ├── prompt_builder.py # CoT Prompt 构建
│   └── ...
├── frontend/           # Vue 3 前端
│   ├── src/            # 源码
│   └── package.json
├── models/             # 嵌入模型（需自行下载，见下文）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 🚀 快速开始

### 环境要求

- Docker 与 Docker Compose（推荐）
- 或 Python 3.10+ 与 Node.js 18+

### 方式一：Docker 部署（推荐）

**1. 克隆项目**

```bash
git clone https://github.com/zsj128/zqdb.git
cd zqdb
```

**2. 下载嵌入模型**（约 470MB）

> 模型需放置到 `models/paraphrase-multilingual-MiniLM-L12-v2/` 目录（Docker 构建时会打包进镜像）。

```bash
pip install -U huggingface_hub
huggingface-cli download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --local-dir models/paraphrase-multilingual-MiniLM-L12-v2
```

**3. 构建并启动**

```bash
docker compose up -d --build
```

**4. 访问**

浏览器打开 http://localhost:8000

### 方式二：本地运行

**1. 安装后端依赖**

```bash
pip install -r requirements.txt
```

**2. 安装前端依赖**

```bash
cd frontend
npm install
```

**3. 配置 MySQL**

确保本地 MySQL 运行中，并在 `backend/database.py` 或环境变量中配置连接参数（`DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME`）。

**4. 启动后端**

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**5. 启动前端（开发模式）**

```bash
cd frontend
npm run dev
```

## 📖 使用说明

### 1. 登录 / 注册

首次使用需注册账号。系统内置管理员账号：

| 账号 | 密码 |
|------|------|
| `admin` | `Aa@123456` |

### 2. 配置大模型

登录后进入「知识库管理」→「LLM 配置」，填写 API Key（通义千问/OpenAI 兼容接口）、模型名称（默认 `qwen-plus`）和 Base URL。

### 3. 导入数据

在「知识库管理」→「数据导入」中：

- **插入单个文件 / 整个文件夹**：上传法律文件（.docx/.pdf）与案例
- 法律文件按「第X条」自动分块，案例整篇存储
- 数据会保存到当前用户目录（`~/.law_ai/`），下次登录自动恢复

### 4. 开始提问

进入「AI 问答」，输入法律问题即可获得基于知识库的回答，回答会标注引用的法条来源。

## ⚙️ 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `DB_HOST` | MySQL 主机 | `localhost` |
| `DB_PORT` | MySQL 端口 | `3306` |
| `DB_USER` | MySQL 用户 | `root` |
| `DB_PASSWORD` | MySQL 密码 | - |
| `DB_NAME` | 数据库名 | `zqdb_db` |
| `LAW_AI_HOME` | 用户数据根目录 | `~/.law_ai` |
| `EMBED_MODEL_PATH` | 嵌入模型路径 | 自动查找 |
