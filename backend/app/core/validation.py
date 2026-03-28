from app.config import config
from app.errors import raise_biz_error


def ensure_operator(name: str) -> None:
    if name not in config.operators:
        raise_biz_error(40002, "操作员未选择或无效")


def ensure_source(name: str) -> None:
    if name not in config.sources:
        raise_biz_error(40007, "来源未选择或无效")
