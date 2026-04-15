# MCP Shelf

MCP / Tool / Skill 货架 + 绑定配置 + 测试台

一个轻量级的 AI Agent 能力管理平台。注册 MCP Server、本地 Tool、Skill，组合成 Binding 配置，在 Playground 里用多轮对话验证能力是否可被模型发现和调用。

## 这不是聊天产品

MCP Shelf 的核心是三层：

| 层 | 功能 |
|---|------|
| **Registry** | 管理 MCP、Tool、Skill 条目，支持分类、搜索、健康检查、版本管理 |
| **Binding** | 把若干能力组合成一个可复用的 Agent 配置（模型、提示词、工具集） |
| **Playground** | 用最小聊天页验证这组能力是否可被模型发现和调用，支持多轮对话 |

## 架构

```
┌──────────────────────────────────────────────┐
│                 Browser                      │
│         Jinja2 + HTMX + SSE                  │
└──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│                    FastAPI App                           │
│   Web Pages  │  JSON API (CRUD/Runtime)  │  SSE Stream  │
│─────────────────────────────────────────────────────────│
│   RegistryService  BindingService  SessionService       │
│   MCPService       AgentService    AuditService         │
│─────────────────────────────────────────────────────────│
│                LangGraph Runtime                        │
│  load_binding → build_tools → call_model → execute_tool │
│                              → finalize / fail          │
└──────────────────────────────────────────────────────────┘
           │                                 │
           ▼                                 ▼
┌───────────────────────┐      ┌──────────────────────────┐
│       SQLite          │      │       File Store         │
│  capabilities         │      │  marketplace/*.json      │
│  bindings             │      │  examples/*.json         │
│  sessions / messages  │      │  exports/*.zip           │
│  audit_logs           │      │  seeds/*.yaml            │
│  health_checks        │      └──────────────────────────┘
│  llm_configs          │
│  _meta (migration)    │
│  langgraph checkpoint │
└───────────────────────┘
           │
           ▼
┌──────────────────────────┐
│    External MCP Servers  │
│   HTTP / streamable_http │
└──────────────────────────┘
```

技术栈选型理由：

- **SQLite** — 零外部服务依赖，单机部署和纯文件一样轻；LangGraph 官方提供 SQLite checkpointer
- **File Store** — 货架模板、导入导出包、市场数据天然适合文件化分发
- **FastAPI + Jinja2** — 服务端渲染为主，API 和页面同进程；FastAPI 原生支持 Jinja2
- **LangGraph** — Agent 运行时和会话状态管理，支持 checkpoint 恢复中断执行
- **langchain-mcp-adapters** — 通过 `MultiServerMCPClient` 接远程 MCP Server，支持 HTTP 和自定义认证

## 快速开始

### 安装

```bash
git clone https://github.com/your-org/mcp-shelf.git
cd mcp-shelf
pip install -e .
```

### 配置

```bash
cp .env.example .env
```

编辑 `.env`，至少填入一个 LLM API Key：

```ini
OPENAI_API_KEY=sk-...
# 或
ANTHROPIC_API_KEY=sk-ant-...
```

也可以启动后在 **Settings** 页面配置，页面配置优先于 `.env`。

### 启动

```bash
mcp-shelf
# 或
python -m uvicorn app.main:app --port 8000
```

访问 http://localhost:8000

### 种子数据

首次启动后可以导入市场模板数据：

```bash
python scripts/seed_marketplace.py
```

## 功能

### Registry — 能力管理

- 注册 MCP Server / Tool / Skill 三种能力
- 分类、标签、搜索、筛选
- 激活/停用
- 健康检查（MCP 自动探测连通性）
- 版本快照与回溯
- 连通性验证接口 `/api/capabilities/validate`

### Binding — 绑定配置

- 选择模型（OpenAI / Anthropic / 自定义 OpenAI 兼容端点）
- 编写 System Prompt
- 挂载/卸载能力，设定顺序和运行时覆盖参数
- 一键克隆

### Playground — 测试台

- 选择 Binding 开始新会话
- 多轮对话，消息持久化
- SSE 实时流式输出
- 工具调用轨迹可视化（tool_call / tool_result）
- 会话状态追踪（idle / running / error）

### Settings — LLM 配置

- 前端页面配置 API Key、Base URL、默认模型
- 支持连接测试
- 配置优先级：**页面配置 > .env 文件**
- 多 Provider 管理（OpenAI / Anthropic / Custom）

### 备份与恢复

- 一键备份：SQLite 数据库 + Marketplace 模板 + 元信息 → zip
- 一键恢复：上传 zip 覆盖当前数据
- 升级版本前备份，升级后恢复，零数据丢失

### 数据库迁移

- `_meta` 表记录 schema 版本
- 启动时自动检测并应用增量迁移
- 新版本加表或改字段只需追加 migration

## 项目结构

```
mcp-shelf/
├─ app/
│  ├─ main.py                  # FastAPI 入口
│  ├─ core/
│  │  ├─ config.py             # pydantic-settings 配置
│  │  ├─ db.py                 # SQLite 连接 + 迁移入口
│  │  ├─ migrations.py         # 版本化迁移系统
│  │  ├─ paths.py              # File Store 路径管理
│  │  ├─ logging.py
│  │  └─ templates.py
│  ├─ schemas/                 # Pydantic 请求/响应模型
│  │  ├─ capability.py
│  │  ├─ binding.py
│  │  ├─ session.py
│  │  ├─ llm_config.py
│  │  └─ common.py
│  ├─ repositories/            # SQLite 数据访问层
│  │  ├─ capability_repo.py
│  │  ├─ binding_repo.py
│  │  ├─ session_repo.py
│  │  ├─ audit_repo.py
│  │  ├─ health_repo.py
│  │  └─ llm_config_repo.py
│  ├─ services/                # 业务逻辑层
│  │  ├─ registry_service.py
│  │  ├─ binding_service.py
│  │  ├─ session_service.py
│  │  ├─ agent_service.py      # LangGraph 编排 + 多轮对话
│  │  ├─ mcp_service.py
│  │  ├─ healthcheck_service.py
│  │  ├─ audit_service.py
│  │  └─ llm_config_service.py # DB > .env 优先级解析
│  ├─ runtime/                 # LangGraph 运行时
│  │  ├─ state.py              # AgentState 定义
│  │  ├─ graph.py              # 图构建 + 条件边
│  │  ├─ checkpoint.py         # 内存/SQLite checkpointer
│  │  ├─ nodes/
│  │  │  ├─ load_binding.py
│  │  │  ├─ build_tools.py
│  │  │  ├─ call_model.py
│  │  │  ├─ execute_tool.py
│  │  │  ├─ finalize.py
│  │  │  └─ fail.py
│  │  └─ adapters/
│  │     ├─ models.py          # OpenAI/Anthropic 模型适配
│  │     ├─ mcp.py             # MultiServerMCPClient 适配
│  │     ├─ local_tools.py     # 内置 echo/calculator
│  │     └─ skills.py
│  ├─ routers/                 # API 路由
│  │  ├─ pages.py              # HTML 页面
│  │  ├─ capabilities.py
│  │  ├─ bindings.py
│  │  ├─ sessions.py
│  │  ├─ runtime.py            # SSE 流式输出
│  │  ├─ llm_configs.py
│  │  ├─ import_export.py
│  │  ├─ backup.py             # 一键备份/恢复
│  │  ├─ health.py
│  │  └─ audit.py
│  ├─ templates/               # Jinja2 模板
│  │  ├─ base.html
│  │  ├─ index.html
│  │  ├─ capabilities/
│  │  ├─ bindings/
│  │  ├─ sessions/
│  │  └─ settings.html
│  └─ static/
├─ data/
│  ├─ marketplace/             # 货架模板（版本化）
│  │  ├─ capabilities/
│  │  └─ bindings/
│  ├─ exports/
│  └─ seeds/
├─ scripts/
│  ├─ schema.sql               # 完整建表语句
│  ├─ init_db.py
│  └─ seed_marketplace.py
├─ tests/
├─ pyproject.toml
└─ .env.example
```

## API

### 能力管理

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/capabilities` | 列表（支持 kind/status/category/search/分页） |
| POST | `/api/capabilities` | 创建 |
| GET | `/api/capabilities/{id}` | 详情 |
| PUT | `/api/capabilities/{id}` | 更新 |
| DELETE | `/api/capabilities/{id}` | 删除 |
| POST | `/api/capabilities/{id}/activate` | 激活 |
| POST | `/api/capabilities/{id}/deactivate` | 停用 |
| POST | `/api/capabilities/{id}/healthcheck` | 健康检查 |
| GET | `/api/capabilities/{id}/versions` | 版本列表 |
| POST | `/api/capabilities/{id}/versions` | 创建版本快照 |
| POST | `/api/capabilities/validate` | 验证 MCP 连通性 |

### 绑定管理

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/bindings` | 列表 |
| POST | `/api/bindings` | 创建 |
| GET | `/api/bindings/{id}` | 详情（含挂载能力） |
| PUT | `/api/bindings/{id}` | 更新 |
| DELETE | `/api/bindings/{id}` | 删除 |
| POST | `/api/bindings/{id}/capabilities` | 挂载能力 |
| DELETE | `/api/bindings/{id}/capabilities/{cap_id}` | 卸载能力 |
| POST | `/api/bindings/{id}/clone` | 克隆 |

### 会话与运行时

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/sessions` | 创建会话 |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/sessions/{id}` | 会话详情 |
| GET | `/api/sessions/{id}/messages` | 消息历史 |
| POST | `/api/sessions/{id}/messages` | 追加消息 |
| POST | `/api/sessions/{id}/run` | 同步执行 |
| GET | `/api/sessions/{id}/stream` | SSE 流式执行 |
| POST | `/api/sessions/{id}/stop` | 停止执行 |
| GET | `/api/sessions/{id}/trace` | 完整轨迹 |

### LLM 配置

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/llm-configs` | 列表（API Key 脱敏） |
| POST | `/api/llm-configs` | 创建 |
| PUT | `/api/llm-configs/{id}` | 更新 |
| DELETE | `/api/llm-configs/{id}` | 删除 |
| POST | `/api/llm-configs/test` | 连接测试 |

### 导入导出 / 市场

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/marketplace/capabilities` | 市场能力模板 |
| GET | `/api/marketplace/bindings` | 市场绑定模板 |
| POST | `/api/import/capability` | 导入能力 |
| POST | `/api/import/binding` | 导入绑定 |
| POST | `/api/import/bundle` | 导入 Bundle zip |
| GET | `/api/export/capability/{id}` | 导出能力 |
| GET | `/api/export/binding/{id}` | 导出绑定 |

### 备份恢复 / 审计 / 健康

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/backup` | 一键备份（zip） |
| POST | `/api/restore` | 一键恢复 |
| GET | `/api/audit` | 审计日志 |
| GET | `/api/health/summary` | 健康摘要 |

## 运行模式

| 模式 | 业务库 | Checkpoint | 适用场景 |
|------|--------|------------|---------|
| demo | SQLite | 内存 | 本地快速试跑 |
| lite | SQLite | SQLite | 单机长期运行（**默认**） |
| future-prod | PostgreSQL | 可选 | 后续升级路径，不改动业务层 |

## Marketplace 文件格式

能力模板 `data/marketplace/capabilities/xxx.json`：

```json
{
  "kind": "mcp",
  "name": "Internal Search",
  "slug": "internal-search",
  "description": "Search internal documents",
  "category": "search",
  "tags": ["docs", "search"],
  "connection_config": {
    "transport": "http",
    "endpoint_url": "http://localhost:8000/mcp",
    "headers_template": { "Authorization": "Bearer {{api_key}}" }
  }
}
```

绑定模板 `data/marketplace/bindings/xxx.json`：

```json
{
  "name": "Docs Basic",
  "model_key": "openai:gpt-4.1",
  "system_prompt": "You are a careful internal test agent.",
  "max_steps": 6,
  "capabilities": [
    { "slug": "internal-search", "is_enabled": true, "runtime_overrides": {} }
  ]
}
```

## LangGraph 运行时

```
START
  ↓
load_binding    ← 从 DB 加载 Binding 配置和挂载能力
  ↓
build_tools     ← 组装本地工具 + MCP 远程工具
  ↓
call_model      ← 调用 LLM（带 tools binding）
  ├─ 有 tool_call → execute_tool → call_model（循环）
  ├─ 有 final answer → finalize
  └─ 出错 / 超步数 → fail
```

- 每轮对话都从 DB 加载完整消息历史，支持多轮上下文
- 消息持久化到 `runtime_messages` 表
- SSE 事件：`token` / `tool_call` / `tool_result` / `done` / `error`

## 升级指南

1. 在 Settings 页面点击 **Backup All Data** 下载备份 zip
2. `git pull` 更新代码
3. `pip install -e .` 安装新依赖
4. 重启服务 — 数据库迁移自动执行
5. 如有问题，在 Settings 页面点击 **Restore from Backup** 恢复

## 开发

```bash
pip install -e ".[dev]"

# 代码检查
ruff check app/

# 运行测试
pytest

# 开发模式启动（自动重载）
python -m uvicorn app.main:app --reload
```

## License

MIT
