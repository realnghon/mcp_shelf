# Phase 1 Handoff

## 当前状态

Phase 1 已完成，目标闭环已经打通：
- builtin calculator 以 manifest 形式进入 unified registry
- capability definition validation 已接入 API，并可回写 `schema_status`
- capability tool tester 已接入 API，并可回写 `capability_tests` 与 `last_test_*`
- capability list/detail 页面已展示 unified registry 关键字段
- MCP health/discovery 状态已可记录与展示

## 本次交付范围

### 1. Unified registry 基础字段
- `app/schemas/capability.py`
- `app/repositories/capability_repo.py`
- `app/core/migrations.py`
- `scripts/schema.sql`

新增并打通字段：
- `type`
- `source_type`
- `source_id`
- `input_schema`
- `output_schema`
- `config_schema`
- `schema_status`
- `last_test_status`
- `last_tested_at`
- `last_latency_ms`

### 2. Builtin manifest registry
- `data/builtin/capabilities/calculator.tool.json`
- `app/runtime/adapters/builtin_catalog.py`
- `app/services/registry_service.py`
- `app/runtime/adapters/local_tools.py`

现状：
- builtin calculator 可通过 `builtin:calculator` 进入统一 registry
- 页面可查看 builtin capability 详情

### 3. Capability validation
- `app/services/capability_validation_service.py`
- `app/routers/capabilities.py`

现状：
- `POST /api/capabilities/validate`
- 可校验基础字段、schema object、MCP `endpoint_url`
- 对持久化 capability 会回写 `schema_status`

### 4. Capability testing
- `app/repositories/capability_test_repo.py`
- `app/services/capability_test_service.py`
- `app/routers/capabilities.py`

现状：
- `POST /api/capabilities/{cap_id}/test`
- `GET /api/capabilities/{cap_id}/tests`
- 非 builtin capability 会写入 `capability_tests`
- 同时回写：
  - `last_test_status`
  - `last_tested_at`
  - `last_latency_ms`

### 5. MCP health/discovery
- `app/repositories/health_repo.py`
- `app/services/healthcheck_service.py`
- `app/routers/health.py`

现状：
- `POST /api/capabilities/{cap_id}/healthcheck`
- `GET /api/health/summary`
- `GET /api/health/capabilities/{capability_id}`
- 现在会记录 `discovery_status`
  - `available`
  - `degraded`
  - `unavailable`
  - `not_applicable`

### 6. Capability 页面
- `app/routers/pages.py`
- `app/templates/capabilities/list.html`
- `app/templates/capabilities/detail.html`

现状：
- list 页面展示 unified registry 视角
- detail 页面展示：
  - Basic Info
  - Schema Status
  - Latest Test
  - Test History
  - Connection Config
  - Health History

## 测试结果

最后一次验证通过：
- `python -m pytest -q`
- 结果：`17 passed`

最后一次 Phase 1 定向静态检查通过：
- `python -m pyright app/repositories/health_repo.py app/services/healthcheck_service.py app/services/capability_test_service.py app/services/capability_validation_service.py app/routers/capabilities.py app/routers/pages.py tests`
- 结果：`0 errors, 0 warnings, 0 informations`

## 当前已知非阻塞项

这些不是 Phase 1 阻塞项，但后续可以继续处理：
- 全仓 `python -m pyright app tests` 仍有历史 typing debt
- 主要集中在：
  - `app/services/agent_service.py`
  - `app/runtime/nodes/call_model.py`
  - `app/runtime/adapters/mcp.py`
  - `app/runtime/checkpoint.py`
  - 部分 repository 的旧 Optional typing

## 下次直接继续做什么

优先顺序建议如下：

### 方案 A：进入 Phase 2（推荐）
1. 重新梳理顶层对象边界：Plugin / MCP Server / Capability / Agent Preset
2. 把 `skill` 从顶层 capability 语义里继续下沉到 `workflow/prompt`
3. 把 runtime 装配链拆成更清晰的：
   - source loader
   - capability resolver
   - preset assembler
   - session runtime
4. 统一 plugin 与 mcp server 的挂载/发现模型

### 方案 B：先清历史类型债务
1. 修 `app/runtime/adapters/mcp.py` 的类型签名与 async 用法
2. 修 `app/runtime/nodes/call_model.py` 的 model/tool typing
3. 修 `app/services/agent_service.py` 的 `AgentState` 类型流
4. 跑通全仓 `pyright app tests`

### 方案 C：继续补产品闭环
1. capability form 增加 unified registry 全字段编辑能力
2. 为 builtin test 提供可编辑默认请求载荷
3. 在列表页增加 schema/test/health 的筛选与排序
4. 给 MCP discovery 增加更真实的 discovery 探测，而不只是 connectivity

## 发布前注意事项

当前代码里没有发现实际密钥或本机路径泄漏到本次变更文件中。
为了后续发布安全：
- 不要提交 `.env`
- 不要提交数据库文件
- 不要提交 `.claude/`
- 不要提交任何本地缓存或测试临时文件

## 推荐起点

下次如果要无缝继续，直接先读：
1. `docs/handoffs/phase1-handoff.md`
2. `README.md`
3. `app/routers/capabilities.py`
4. `app/services/capability_validation_service.py`
5. `app/services/capability_test_service.py`
6. `app/services/healthcheck_service.py`
