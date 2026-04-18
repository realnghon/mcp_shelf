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

## 最近更新（2026-04-18）

- 新增 MCP 向导式能力表单：
  - 只保留主流程必填字段（`Name`、`Transport`、连接入口）
  - `stdio` 必填 `command`；`streamable_http/sse` 必填 `URL`
  - 提供 `stdio` 与 `streamable HTTP` 一键示例填充
  - 高级 JSON 字段收纳到 `Advanced Settings`
- 聊天页会话体验优化：
  - 不再强制先点 `New Chat`
  - 首次点击 `Send` 自动创建会话并发送
  - 切换顶部 Binding 会提示进入新聊天上下文，避免误用旧上下文
- MCP 运行链路增强：
  - `mcp_server` 支持 `stdio`（`command/args/env/cwd`）与 `streamable_http/sse`
  - Capability Test 对 MCP 能力可直接调用 `get_mcp_tools`
  - Healthcheck 增加 `stdio` MCP 工具发现检查
- OpenAI-compatible (`custom`) 兼容修复：
  - `base_url` 自动规范到 `/v1`（若未包含）
  - 修复 Settings 中 provider 编辑保存不生效（支持更新 `provider` 字段）
  - 流式无 chunk 时自动回退 `ainvoke`，降低会话中断概率

## MCP 表单必填说明

- `Transport=stdio`：
  - 必填：`Command`
  - 选填：`Args`、`Environment Variables`、`Timeout`
- `Transport=streamable_http` 或 `sse`：
  - 必填：`URL`
  - 选填：`Headers`、`Timeout`

> 建议：OpenAI-compatible provider 的 Base URL 填写根地址或 `/v1` 都可以，系统会统一处理为 `/v1` 路径。

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
