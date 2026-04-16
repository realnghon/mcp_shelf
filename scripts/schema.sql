-- MCP Shelf Schema v0.1.0

CREATE TABLE IF NOT EXISTS capabilities (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                -- mcp | tool | skill
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  description TEXT,
  category TEXT,
  tags TEXT NOT NULL DEFAULT '[]',   -- JSON string
  version TEXT NOT NULL DEFAULT '0.1.0',
  visibility TEXT NOT NULL DEFAULT 'public',
  status TEXT NOT NULL DEFAULT 'active',
  owner_id TEXT,
  type TEXT NOT NULL DEFAULT 'tool',
  source_type TEXT NOT NULL DEFAULT 'custom',
  source_id TEXT,
  input_schema TEXT NOT NULL DEFAULT '{}',
  output_schema TEXT NOT NULL DEFAULT '{}',
  config_schema TEXT NOT NULL DEFAULT '{}',
  connection_config TEXT NOT NULL DEFAULT '{}',
  schema_status TEXT,
  last_test_status TEXT,
  last_tested_at TEXT,
  last_latency_ms INTEGER,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_capabilities_kind ON capabilities(kind);
CREATE INDEX IF NOT EXISTS idx_capabilities_status ON capabilities(status);

CREATE TABLE IF NOT EXISTS capability_versions (
  id TEXT PRIMARY KEY,
  capability_id TEXT NOT NULL,
  version TEXT NOT NULL,
  snapshot TEXT NOT NULL,
  changelog TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(capability_id, version),
  FOREIGN KEY(capability_id) REFERENCES capabilities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS capability_tests (
  id TEXT PRIMARY KEY,
  capability_id TEXT NOT NULL,
  status TEXT NOT NULL,
  latency_ms INTEGER,
  request_payload TEXT NOT NULL DEFAULT '{}',
  response_payload TEXT NOT NULL DEFAULT '{}',
  error_message TEXT,
  tested_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(capability_id) REFERENCES capabilities(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_capability_tests_capability_id ON capability_tests(capability_id, tested_at DESC);

CREATE TABLE IF NOT EXISTS bindings (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  model_key TEXT NOT NULL,
  system_prompt TEXT,
  max_steps INTEGER NOT NULL DEFAULT 8,
  temperature REAL,
  allow_shell INTEGER NOT NULL DEFAULT 0,
  owner_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'private',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS binding_capabilities (
  id TEXT PRIMARY KEY,
  binding_id TEXT NOT NULL,
  capability_id TEXT NOT NULL,
  is_enabled INTEGER NOT NULL DEFAULT 1,
  mount_order INTEGER NOT NULL DEFAULT 0,
  runtime_overrides TEXT NOT NULL DEFAULT '{}',
  UNIQUE(binding_id, capability_id),
  FOREIGN KEY(binding_id) REFERENCES bindings(id) ON DELETE CASCADE,
  FOREIGN KEY(capability_id) REFERENCES capabilities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runtime_sessions (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL UNIQUE,
  binding_id TEXT,
  title TEXT,
  actor_id TEXT,
  session_status TEXT NOT NULL DEFAULT 'idle',
  model_key TEXT NOT NULL,
  runtime_config TEXT NOT NULL DEFAULT '{}',
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(binding_id) REFERENCES bindings(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS runtime_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,                  -- user | assistant | tool | system
  content TEXT,
  tool_name TEXT,
  tool_call_id TEXT,
  tool_args TEXT,
  tool_result TEXT,
  message_index INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES runtime_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_runtime_messages_session ON runtime_messages(session_id, message_index);

CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY,
  actor_id TEXT,
  action TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);

CREATE TABLE IF NOT EXISTS health_checks (
  id TEXT PRIMARY KEY,
  capability_id TEXT NOT NULL,
  status TEXT NOT NULL,               -- ok | degraded | failed
  latency_ms INTEGER,
  detail TEXT,
  checked_at TEXT NOT NULL,
  FOREIGN KEY(capability_id) REFERENCES capabilities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS llm_configs (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,                -- openai | anthropic | custom
  name TEXT NOT NULL,                    -- display name
  api_key TEXT,                          -- encrypted or plain API key
  base_url TEXT,                         -- custom endpoint
  default_model TEXT,                    -- e.g. gpt-4.1
  is_default INTEGER NOT NULL DEFAULT 0, -- is this the default provider?
  extra_config TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
