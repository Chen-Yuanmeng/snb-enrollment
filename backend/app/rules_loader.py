from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _rules_root() -> Path:
    return Path(__file__).resolve().parents[1] / "rules"


def _read_json(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"规则文件必须是对象: {file_path}")
    return data


@lru_cache(maxsize=1)
def get_rules_index() -> dict[str, Any]:
    return _read_json(_rules_root() / "index.json")


@lru_cache(maxsize=1)
def get_accommodation_rule() -> dict[str, Any]:
    return _read_json(_rules_root() / "accommodation.json")


@lru_cache(maxsize=1)
def get_enabled_grade_rules() -> list[dict[str, Any]]:
    index = get_rules_index()
    grades = index.get("grades", [])
    rules: list[dict[str, Any]] = []
    for item in grades:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled", True):
            continue
        file_rel = item.get("file")
        if not file_rel:
            continue
        rule = _read_json(_rules_root() / str(file_rel))
        if rule.get("enabled", True):
            rules.append(rule)
    return rules


@lru_cache(maxsize=1)
def get_grade_rule_map() -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for rule in get_enabled_grade_rules():
        grade = str(rule.get("grade", "")).strip()
        if not grade:
            continue
        mapping[grade] = rule
    return mapping


def get_grade_rule(grade: str) -> dict[str, Any] | None:
    return get_grade_rule_map().get(grade)


def get_grade_class_subject_groups() -> dict[str, list[list[str]]]:
    result: dict[str, list[list[str]]] = {}
    for grade, rule in get_grade_rule_map().items():
        groups = rule.get("class_subject_groups", [])
        if not isinstance(groups, list):
            continue
        normalized: list[list[str]] = []
        for group in groups:
            if not isinstance(group, list):
                continue
            group_names: list[str] = []
            for item in group:
                if isinstance(item, str):
                    name = item.strip()
                    if name:
                        group_names.append(name)
                    continue
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if name:
                        group_names.append(name)
            normalized.append(group_names)
        result[grade] = normalized
    return result


def get_grade_class_modes() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for grade, rule in get_grade_rule_map().items():
        modes = rule.get("class_modes", [])
        if not isinstance(modes, list):
            continue
        result[grade] = [str(item) for item in modes if str(item).strip()]
    return result


def get_grade_class_subject_options() -> dict[str, set[str]]:
    groups = get_grade_class_subject_groups()
    return {
        grade: {item for group in class_groups for item in group}
        for grade, class_groups in groups.items()
    }


def get_rules_meta_payload(sources: list[str], status: dict[str, str]) -> dict[str, Any]:
    groups = get_grade_class_subject_groups()
    modes = get_grade_class_modes()
    index = get_rules_index()

    def _normalize_discount_meta(discount: dict[str, Any]) -> dict[str, Any]:
        raw_exclusive = discount.get("exclusive_with", [])
        exclusive_with = [str(item) for item in raw_exclusive if str(item).strip()] if isinstance(raw_exclusive, list) else []
        return {
            "name": str(discount.get("name", "")).strip(),
            "mode": str(discount.get("mode", "manual")).strip() or "manual",
            "requires_history_student": bool(discount.get("requires_history_student", False)),
            "exclusive_with": exclusive_with,
        }

    def _pricing_discount_names(rule: dict[str, Any]) -> set[str]:
        presets = rule.get("discount_presets", {}) if isinstance(rule, dict) else {}
        pricing = rule.get("pricing", {}) if isinstance(rule, dict) else {}
        names: set[str] = set()
        if not isinstance(presets, dict) or not isinstance(pricing, dict):
            return names

        for cfg in pricing.values():
            if not isinstance(cfg, dict):
                continue

            refs = cfg.get("discount_preset_refs", [])
            if isinstance(refs, list):
                for ref in refs:
                    preset_items = presets.get(ref, [])
                    if not isinstance(preset_items, list):
                        continue
                    for item in preset_items:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name", "")).strip()
                        if name and item.get("enabled", True):
                            names.add(name)

            overrides = cfg.get("available_discounts_overrides", [])
            if isinstance(overrides, dict):
                iterable = [{"name": k, **v} for k, v in overrides.items() if isinstance(v, dict)]
            elif isinstance(overrides, list):
                iterable = [item for item in overrides if isinstance(item, dict)]
            else:
                iterable = []

            for item in iterable:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                if item.get("enabled", True):
                    names.add(name)
                elif name in names:
                    names.remove(name)

        return names

    def _grade_discounts_meta(grade: str) -> list[dict[str, Any]]:
        rule = get_grade_rule(grade) or {}
        explicit_meta = {
            str(item.get("name", "")).strip(): _normalize_discount_meta(item)
            for item in rule.get("discounts", [])
            if isinstance(item, dict) and item.get("enabled", True) and item.get("name")
        }

        for name in sorted(_pricing_discount_names(rule)):
            if name in explicit_meta:
                continue
            explicit_meta[name] = {
                "name": name,
                "mode": "manual",
                "requires_history_student": False,
                "exclusive_with": [],
            }

        return list(explicit_meta.values())

    return {
        "version": index.get("version", "unknown"),
        "timezone": index.get("timezone", "Asia/Shanghai"),
        "grades": list(groups.keys()),
        "grade_options": [
            {
                "grade": grade,
                "class_modes": modes.get(grade, []),
                "class_subject_groups": groups.get(grade, []),
                "discounts": [
                    item
                    for item in _grade_discounts_meta(grade)
                    if item.get("name")
                ],
                "selection_mode": ((get_grade_rule(grade) or {}).get("constraints", {}) or {}).get(
                    "selection_mode", "multiple"
                ),
                "max_select": ((get_grade_rule(grade) or {}).get("constraints", {}) or {}).get(
                    "max_select"
                ),
                "ui_hints": (get_grade_rule(grade) or {}).get("ui_hints", {}),
            }
            for grade in groups.keys()
        ],
        "status": status,
        "sources": sources,
        "notes": "规则由 backend/rules/*.json 维护",
    }
