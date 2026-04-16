# MCP Shelf

MCP / Tool / Skill 的轻量管理与调试平台。  
用来快速组装 Agent 能力（Binding），并在网页里验证对话、工具调用和流式输出。

## 为什么做这个

- 把分散的能力配置集中管理：`mcp` / `tool` / `skill`
- 支持可复用 Binding（模型、提示词、挂载能力）
- 提供聊天测试台，直接观察 tool call / tool result / streaming

## 功能

- 能力货架：新增、编辑、启停、分类
- Binding 管理：挂载能力、顺序控制、运行时覆盖参数
- 聊天测试台：多轮会话、SSE 流式输出、工具调用可视化
- LLM 配置：支持 OpenAI / Anthropic / OpenAI-compatible
- 数据安全：本地 SQLite，`.env` 与数据库配置分离

## 技术栈

- FastAPI + Jinja2
- LangChain / LangGraph
- SQLite（`aiosqlite`）
- SSE（`sse-starlette`）

## 快速开始

```bash
git clone https://github.com/realnghon/mcp_shelf.git
cd mcp_shelf
pip install -e .
cp .env.example .env
```

编辑 `.env`（至少配置一个 provider）：

```env
OPENAI_API_KEY=your_key
# 或
ANTHROPIC_API_KEY=your_key
```

启动：

```bash
mcp-shelf
# 或
python -m uvicorn app.main:app --reload --port 8000
```

打开：`http://localhost:8000`

## 初始化市场模板（可选）

```bash
python scripts/seed_marketplace.py
```

会导入示例能力与示例 Binding（包括内置工具与 skill 模板）。

## 开发

```bash
pip install -e ".[dev]"
ruff check app
pytest
```

## 项目结构

```text
app/
  routers/        # 页面与 API
  services/       # 业务逻辑
  repositories/   # SQLite 数据访问
  runtime/        # Agent loop、模型/工具适配
  templates/      # 前端页面
  static/         # 静态资源
data/
  marketplace/    # 示例能力与绑定
scripts/
  init_db.py
  seed_marketplace.py
```

## 常见问题

`GET /favicon.ico 404` 是问题吗？  
不是。浏览器默认行为。项目已提供 `/static/favicon.svg`，强刷后即可。

## License

MIT
