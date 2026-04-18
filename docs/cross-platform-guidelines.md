# Cross-Platform Guidelines

This project must run consistently on Windows, Linux, and macOS.

## Scope

Apply these rules to:

- Runtime/tool execution paths
- File/path and URI handling
- Shell/process calls
- Logging and error reporting
- New tests and bugfixes

## Non-Negotiable Rules

1. Always force UTF-8 for child Python execution.
2. Never rely on OS default encodings (`gbk`, locale-dependent behavior, etc.).
3. Use `pathlib.Path` for path operations; avoid hardcoded separators.
4. Treat `file://` URIs as first-class input and normalize per platform.
5. Prefer platform-agnostic Python APIs over shell-specific behavior.
6. Never swallow exceptions; include exception type + message in tool errors.

## Process/Command Execution

For Python child processes:

- Prefer `sys.executable` over hardcoded `python`.
- Use `-X utf8`.
- Pass env:
  - `PYTHONUTF8=1`
  - `PYTHONIOENCODING=utf-8`

For shell commands:

- Explicitly branch by platform when behavior differs.
- Keep a fallback path for environments with limited event-loop/process support.
- Enforce timeout and return structured output (`ok`, `exit_code`, `stdout`, `stderr`).

## Path and URI Handling

- Build paths with `Path(...)`.
- Normalize `file://` URIs using `urllib.parse.urlparse` + `unquote`.
- On Windows, strip leading slash for drive-letter paths (`/C:/...` -> `C:/...`) when needed.
- Avoid assumptions about case sensitivity and path root style.

## Logging Standard

- Default logs should be signal-first, not transport noise.
- Keep framework/network/sqlite internals at `WARNING` unless debugging those subsystems.
- Emit actionable app logs for tool lifecycle:
  - start
  - done (with short result preview)
  - failed (with traceback)

## Testing Gate (Required)

Every platform-sensitive change must include at least one of:

- A guardrail test that prevents regressions in cross-platform behavior.
- A template-based test instantiated for the changed module.

Current baseline gate lives in:

- `tests/test_platform_guardrails.py`

Template file for new modules:

- `tests/platform_compat_templates.py`

## PR Checklist

Before merge, confirm:

1. No hardcoded platform-only path assumptions were introduced.
2. Child process encoding is explicit where subprocesses are used.
3. Errors remain diagnosable (no empty error strings).
4. Guardrail/template tests were added or updated.
5. `pytest` passes for touched platform-sensitive tests.
