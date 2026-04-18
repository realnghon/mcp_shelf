import logging
import sys

from app.core.config import settings


def setup_logging():
    root_level = logging.INFO
    logging.basicConfig(
        level=root_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    app_level = logging.DEBUG if settings.debug else logging.INFO
    logging.getLogger("app").setLevel(app_level)

    # Keep framework and SDK internals quiet so runtime/tool logs stay readable.
    for noisy in (
        "aiosqlite",
        "httpcore",
        "httpx",
        "openai",
        "sse_starlette",
        "uvicorn.access",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
