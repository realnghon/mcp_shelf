# MCP Shelf

面向 MCP 优先场景的统一 capability registry 与调试平台。  
统一管理 builtin、local plugin、remote MCP server，并提供 capability 校验、测试、健康检查与网页调试视图。

## 为什么做这个

- 用统一 schema/registry 管理 `builtin` / `plugin` / `mcp_server` capability
- 对外主打 MCP 服务，对内保留本地运行与调试能力
- 在同一个货架里查看 capability 定义、测试结果、健康状态与运行配置

## 功能

- 统一 capability 货架：builtin、plugin、MCP server 一起展示
- Capability 校验：检查 schema 与 MCP 连接配置是否完整
- Capability 测试：执行工具并记录 `last_test_status` / `capability_tests`
- MCP 健康检查：展示 connectivity / discovery 状态与历史
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
