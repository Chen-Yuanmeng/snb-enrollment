from typing import Any

from app.config import config
from app.errors import raise_biz_error
from app.rules_loader import get_accommodation_rule, get_grade_rule
from app.rules_meta import RULES_META


def list_operators() -> list[dict[str, str]]:
    return [{"name": item} for item in config.operators]


def list_sources() -> list[dict[str, str]]:
    return [{"name": item} for item in config.sources]


def get_rules_meta() -> dict[str, Any]:
    return RULES_META


def get_rule_by_grade(grade: str) -> dict[str, Any]:
    rule = get_grade_rule(grade)
    if not rule:
        raise_biz_error(40401, "年级规则不存在", status_code=404)
    return rule


def get_accommodation_meta() -> dict[str, Any]:
    return get_accommodation_rule()
