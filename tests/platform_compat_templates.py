"""Templates for cross-platform tests.

Copy patterns from this file into concrete `tests/test_*.py` files when
touching platform-sensitive code paths.
"""

from pathlib import Path
from urllib.parse import unquote, urlparse


def template_normalize_file_uri_to_path(file_uri: str) -> Path:
    """Template: normalize file:// URI in a platform-aware way."""
    parsed = urlparse(file_uri)
    path_text = unquote(parsed.path or "")

    # Windows drive URI often looks like /C:/foo/bar.
    if path_text.startswith("/") and len(path_text) >= 3 and path_text[2] == ":":
        path_text = path_text[1:]

    if not path_text and parsed.netloc:
        path_text = unquote(parsed.netloc)
    return Path(path_text)


async def template_subprocess_utf8_assertion(run_callable):
    """Template: verify child process output handles unicode safely.

    Args:
        run_callable: async callable that accepts script/code and returns a
            structured payload or raw text.
    """
    script = "print('🧪 utf8 template check')"
    result = await run_callable(script)
    # Replace with module-specific assertions.
    assert result is not None


def template_path_roundtrip_assertion(tmp_path):
    """Template: verify file path <-> file URI roundtrip on current platform."""
    sample = tmp_path / "示例 folder" / "file name.txt"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("ok", encoding="utf-8")

    normalized = template_normalize_file_uri_to_path(sample.resolve().as_uri())
    assert normalized.exists()
