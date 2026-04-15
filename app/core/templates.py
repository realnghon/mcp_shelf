from fastapi.templating import Jinja2Templates
from pathlib import Path

_templates: Jinja2Templates | None = None


def get_templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        template_dir = Path(__file__).parent.parent / "templates"
        _templates = Jinja2Templates(directory=str(template_dir))
    return _templates
