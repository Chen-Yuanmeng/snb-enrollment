import hashlib
import json
from datetime import datetime, timedelta
from sqlalchemy import select
from typing import Any

from .database import SessionLocal
from .models import Student, StudentHistory
from .class_subject_meta import GRADE_CLASS_SUBJECT_OPTIONS
from .constants import NON_EARLY_BIRD_VALID_UNTIL
from .rules_loader import get_grade_rule
from .schemas import QuoteCalculateRequest, QuoteResult, DiscountItem


EARLY_BIRD_STAGE_1 = datetime.fromisoformat("2026-05-15T23:59:59")
EARLY_BIRD_STAGE_2 = datetime.fromisoformat("2026-06-15T23:59:59")


def _rule(grade: str) -> dict:
    rule = get_grade_rule(grade) or {}
    return rule if isinstance(rule, dict) else {}


def _discount_meta_map(grade: str) -> dict[str, dict]:
    discounts = _rule(grade).get("discounts", [])
    mapping: dict[str, dict] = {}
    if not isinstance(discounts, list):
        return mapping
    for item in discounts:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        mapping[name] = item
    return mapping


def _subject_strategy_map(grade: str) -> dict[str, str]:
    groups = _rule(grade).get("class_subject_groups", [])
    mapping: dict[str, str] = {}
    if not isinstance(groups, list):
        return mapping
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    mapping[name] = "default"
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            strategy = str(item.get("pricing_strategy", "default")).strip() or "default"
            if name:
                mapping[name] = strategy
    return mapping


def _strategy_pricing(grade: str, strategy: str) -> dict:
    pricing = _rule(grade).get("pricing", {})
    if not isinstance(pricing, dict):
        return {}
    cfg = pricing.get(strategy, {})
    return cfg if isinstance(cfg, dict) else {}


def _merge_discount_cfg(base: dict, override: dict) -> dict:
    merged = dict(base)
    for k, v in override.items():
        if k == "rule" and isinstance(v, dict) and isinstance(base.get("rule"), dict):
            rule_merged = dict(base.get("rule", {}))
            rule_merged.update(v)
            merged["rule"] = rule_merged
            continue
        merged[k] = v
    return merged


def _strategy_discount_map(grade: str, strategy: str) -> dict[str, dict]:
    rule = _rule(grade)
    presets = rule.get("discount_presets", {})
    pricing_cfg = _strategy_pricing(grade, strategy)

    mapping: dict[str, dict] = {}
    refs = pricing_cfg.get("discount_preset_refs", [])
    if isinstance(refs, list) and isinstance(presets, dict):
        for ref in refs:
            preset_items = presets.get(ref, [])
            if not isinstance(preset_items, list):
                continue
            for item in preset_items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                mapping[name] = item

    overrides = pricing_cfg.get("available_discounts_overrides", [])
    if isinstance(overrides, dict):
        normalized: list[dict] = []
        for name, override in overrides.items():
            if isinstance(override, dict):
                normalized.append({"name": name, **override})
        overrides = normalized

    if isinstance(overrides, list):
        for override in overrides:
            if not isinstance(override, dict):
                continue
            name = str(override.get("name", "")).strip()
            if not name:
                continue
            base = mapping.get(name, {"name": name})
            mapping[name] = _merge_discount_cfg(base, override)

    return mapping


def _discount_cfg_for_subject(grade: str, subject: str) -> dict[str, dict]:
    strategy = _subject_strategy_map(grade).get(subject, "default")
    return _strategy_discount_map(grade, strategy)


def _grade_supports_discount(grade: str, name: str) -> bool:
    pricing = _rule(grade).get("pricing", {})
    if not isinstance(pricing, dict):
        return False
    for strategy in pricing.keys():
        cfg = _strategy_discount_map(grade, str(strategy)).get(name, {})
        if isinstance(cfg, dict) and cfg.get("enabled", True):
            return True
    return False


def _early_bird_grades() -> set[str]:
    return {
        grade
        for grade in GRADE_CLASS_SUBJECT_OPTIONS.keys()
        if _grade_supports_discount(grade, "早鸟")
    }


def _has_discount(req: QuoteCalculateRequest, name: str) -> bool:
    return any(item.name == name for item in req.discounts)


def _stage_end_times(grade: str) -> list[datetime]:
    validity = _rule(grade).get("quote_validity", {})
    validity_params = validity.get("params", {}) if isinstance(validity, dict) else {}
    raw_ends = validity_params.get("early_bird_stage_ends", [])
    stage_ends: list[datetime] = []
    if isinstance(raw_ends, list):
        for raw in raw_ends[:2]:
            if isinstance(raw, str):
                try:
                    stage_ends.append(datetime.fromisoformat(raw))
                except ValueError:
                    continue
    if len(stage_ends) >= 2:
        return stage_ends[:2]
    return [EARLY_BIRD_STAGE_1, EARLY_BIRD_STAGE_2]


def _early_bird_stage(grade: str, now: datetime) -> int:
    stage_ends = _stage_end_times(grade)
    if now <= stage_ends[0]:
        return 1
    if now <= stage_ends[1]:
        return 2
    return 0


def class_subject_units(grade: str, class_subjects: list[str]) -> int:
    del grade
    return len(class_subjects)


def _validate_class_subjects(grade: str, class_subjects: list[str]) -> None:
    rule = get_grade_rule(grade)
    if not rule:
        raise ValueError(f"暂不支持的年级: {grade}")

    options = GRADE_CLASS_SUBJECT_OPTIONS.get(grade)
    if not options:
        raise ValueError(f"暂不支持的年级: {grade}")

    constraints = rule.get("constraints", {}) if isinstance(rule, dict) else {}
    selection_mode = constraints.get("selection_mode")
    max_select = constraints.get("max_select")
    if selection_mode == "single" and len(class_subjects) != 1:
        if grade == "新高一暑期":
            raise ValueError("新高一暑期班型与科目仅支持单选")
        raise ValueError(f"{grade}班型与科目仅支持单选")
    if isinstance(max_select, int) and max_select > 0 and len(class_subjects) > max_select:
        raise ValueError(f"{grade}班型与科目最多可选{max_select}项")

    for item in class_subjects:
        if item not in options:
            raise ValueError(f"无效的班型与科目: {item}")


def _subject_mode(req: QuoteCalculateRequest, subject: str) -> str:
    if req.class_mode != "混合":
        return req.class_mode
    details = req.mode_details or {}
    online = set(details.get("online_subjects", []))
    return "线上" if subject in online else "线下"


def _validate_request(req: QuoteCalculateRequest) -> None:
    _validate_class_subjects(req.grade, req.class_subjects)
    rule = _rule(req.grade)

    allowed_modes = set(rule.get("class_modes", []))
    if req.class_mode not in allowed_modes:
        raise ValueError("当前年级不支持该上课方式")

    discount_names = {item.name for item in req.discounts}
    meta_map = _discount_meta_map(req.grade)
    enabled_discount_names = {
        name
        for name, cfg in meta_map.items()
        if bool(cfg.get("enabled", True))
    }

    for name in discount_names:
        if name not in enabled_discount_names:
            raise ValueError(f"当前年级不支持{name}")

    for name in discount_names:
        exclusive_with = meta_map.get(name, {}).get("exclusive_with", [])
        if not isinstance(exclusive_with, list):
            continue
        for other in exclusive_with:
            if other in discount_names:
                raise ValueError(f"{name}与{other}不能同时选择")

    for item in req.discounts:
        requires_history_student = meta_map.get(item.name, {}).get("requires_history_student", False)
        if requires_history_student and not item.history_student_id:
            raise ValueError(f"{item.name}必须关联老生记录")

    if req.grade not in _early_bird_grades() and any("早鸟" in name for name in discount_names):
        raise ValueError("该年级不支持早鸟优惠")

    for name in discount_names:
        if any(
            _discount_cfg_for_subject(req.grade, subject).get(name, {}).get("enabled", True)
            for subject in req.class_subjects
        ):
            continue
        raise ValueError(f"当前班型不支持{name}")

    constraints = rule.get("constraints", {}) if isinstance(rule, dict) else {}
    forbidden_keywords = constraints.get("forbidden_subject_keywords", [])
    if isinstance(forbidden_keywords, list):
        for keyword in forbidden_keywords:
            if any(str(keyword) in name for name in req.class_subjects):
                if str(keyword) == "新一试":
                    raise ValueError("新高三暑期已移除新一试(视频课)")
                raise ValueError(f"当前年级已移除{keyword}")

    if req.class_mode == "混合":
        mixed_mode = constraints.get("mixed_mode", {}) if isinstance(constraints, dict) else {}
        if not mixed_mode.get("allowed", False):
            raise ValueError("当前年级不支持混合上课方式")
        if not req.mode_details:
            raise ValueError("混合上课方式必须提供mode_details")
        offline_subjects = set(req.mode_details.get("offline_subjects", []))
        online_subjects = set(req.mode_details.get("online_subjects", []))
        chosen = set(req.class_subjects)
        if not offline_subjects and not online_subjects:
            raise ValueError("混合上课方式必须选择线上或线下科目")
        if (offline_subjects | online_subjects) != chosen:
            raise ValueError("混合上课方式的科目拆分需与class_subjects一致")
        if offline_subjects.intersection(online_subjects):
            raise ValueError("同一科目不能同时在线上和线下")


def _calc_base_price(req: QuoteCalculateRequest) -> tuple[float, str]:
    total = 0.0
    terms: list[str] = []
    strategy_map = _subject_strategy_map(req.grade)

    for subject in req.class_subjects:
        strategy = strategy_map.get(subject, "default")
        pricing_cfg = _strategy_pricing(req.grade, strategy)
        if not pricing_cfg:
            raise ValueError(f"{req.grade}缺少计价策略: {strategy}")

        mode = _subject_mode(req, subject)
        price_type = str(pricing_cfg.get("price_type", "per_subject_by_mode"))

        if price_type == "fixed_total_by_mode":
            if mode == "线下":
                amount = float(pricing_cfg.get("offline_total", 0))
                expr = pricing_cfg.get("offline_equation") or str(int(amount) if amount.is_integer() else amount)
            else:
                amount = float(pricing_cfg.get("online_total", 0))
                expr = pricing_cfg.get("online_equation") or str(int(amount) if amount.is_integer() else amount)
            total += amount
            terms.append(str(expr))
            continue

        if price_type == "fixed_total":
            amount = float(pricing_cfg.get("total", 0))
            total += amount
            terms.append(str(int(amount) if amount.is_integer() else amount))
            continue

        if mode == "线下":
            amount = float(pricing_cfg.get("offline_per_subject", 0))
        else:
            amount = float(pricing_cfg.get("online_per_subject", pricing_cfg.get("offline_per_subject", 0)))
        total += amount
        terms.append(str(int(amount) if amount.is_integer() else amount))

    return float(total), "+".join(terms)


def _stage_value(stages: list[dict], now: datetime) -> float | None:
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        raw_start = stage.get("time_start")
        raw_end = stage.get("time_end") or stage.get("end")

        start = None
        end = None
        if isinstance(raw_start, str):
            try:
                start = datetime.fromisoformat(raw_start)
            except ValueError:
                start = None
        if isinstance(raw_end, str):
            try:
                end = datetime.fromisoformat(raw_end)
            except ValueError:
                end = None

        if start and now < start:
            continue
        if end and now > end:
            continue

        if "value" in stage:
            return float(stage.get("value", 0))
        if "amount" in stage:
            return float(stage.get("amount", 0))
        if "amount_per_subject" in stage:
            return float(stage.get("amount_per_subject", 0))
    return None


def _discount_amount_from_cfg(name: str, cfg: dict, raw_amount: float, now: datetime) -> float:
    strategy = str(cfg.get("strategy", ""))
    params = cfg.get("params", {}) if isinstance(cfg.get("params", {}), dict) else {}

    if strategy in {"fixed_amount", "per_subject_amount"}:
        if "value" in cfg:
            return float(cfg.get("value", 0))
        return float(params.get("value", 0))

    if strategy == "from_input":
        min_value = float(params.get("min_value", 0))
        max_value = float(params.get("max_value", raw_amount if raw_amount >= 0 else 0))
        if raw_amount < min_value or raw_amount > max_value:
            if name == "优秀生第四档":
                raise ValueError("优秀生第四档优惠不能超过600")
            raise ValueError(f"{name}金额需在{int(min_value)}到{int(max_value)}之间")
        return raw_amount

    if strategy == "case_input":
        cases = params.get("cases", {})
        if isinstance(cases, dict):
            # Convert keys to integers and find the appropriate case
            int_cases = {int(k): v for k, v in cases.items()}
            if raw_amount in int_cases:
                return float(int_cases[int(raw_amount)])
        if name == "五一报名优惠":
            raise ValueError("五一报名优惠金额不在可选范围内")
        return raw_amount

    if strategy in {"time_staged", "time_staged_per_subject"}:
        stages = params.get("stages", [])
        if isinstance(stages, list):
            value = _stage_value(stages, now)
            if value is None:
                raise ValueError("当前时间不在早鸟优惠窗口")
            return value
        return 0.0

    if raw_amount < 0:
        raise ValueError("优惠金额不能为负")
    return raw_amount


def _calc_discounts(req: QuoteCalculateRequest, now: datetime) -> tuple[float, dict[str, float], list[str]]:
    total_discount = 0.0
    discount_info: dict[str, float] = {}
    non_price_benefits: list[str] = []

    effective_discounts: list[dict[str, float | str | int | None]] = [
        {
            "name": item.name,
            "amount": float(item.amount),
            "history_student_id": item.history_student_id,
        }
        for item in req.discounts
    ]

    stage = _early_bird_stage(req.grade, now)
    if req.grade in _early_bird_grades() and stage > 0 and not _has_discount(req, "早鸟"):
        effective_discounts.append({"name": "早鸟", "amount": 0.0, "history_student_id": None})

    for item in effective_discounts:
        name = str(item["name"])
        raw_amount = float(item["amount"])
        history_student_id = item.get("history_student_id")

        amount = 0.0
        applied_once = False
        for subject in req.class_subjects:
            cfg = _discount_cfg_for_subject(req.grade, subject).get(name, {})
            if not isinstance(cfg, dict) or not cfg.get("enabled", True):
                continue
            strategy = str(cfg.get("strategy", ""))
            apply_scope = cfg.get("apply_scope")
            if not apply_scope:
                apply_scope = "per_subject" if strategy in {"per_subject_amount", "time_staged_per_subject"} else "per_selection"

            if apply_scope == "per_selection" and applied_once:
                continue

            amount += _discount_amount_from_cfg(name, cfg, raw_amount, now)
            applied_once = True

        if amount <= 0 and name != "五一报名优惠":
            continue

        total_discount += amount
        discount_info[name] = discount_info.get(name, 0.0) + amount

        if name in {"老带新", "老生续报"} and history_student_id:
            non_price_benefits.append(f"优惠关联老生ID: {history_student_id}")

    if req.grade in {"新高一暑期", "新高二暑期", "新高三暑期", "初中/小学暑期"}:
        if req.grade == "初中/小学暑期":
            non_price_benefits.append("全勤奖提示: 28天课程每科结课后可返100元")
        elif req.grade == "新高一暑期":
            non_price_benefits.append("全勤奖提示: 28天课程每科结课后可返100元")
        else:
            non_price_benefits.append("全勤奖提示: 每科结课后可返100元（仅提示，不计价）")

    if req.grade in _early_bird_grades():
        if stage == 1:
            non_price_benefits.append("命中早鸟第一阶段")
        elif stage == 2:
            non_price_benefits.append("命中早鸟第二阶段")

    return total_discount, discount_info, non_price_benefits


def _calc_valid_until(req: QuoteCalculateRequest, now: datetime) -> datetime:
    uses_early_bird = req.grade in _early_bird_grades() and _early_bird_stage(req.grade, now) > 0
    uses_early_bird = uses_early_bird or any("早鸟" in item.name for item in req.discounts)
    validity = _rule(req.grade).get("quote_validity", {})
    strategy = validity.get("strategy") if isinstance(validity, dict) else None
    params = validity.get("params", {}) if isinstance(validity, dict) else {}
    if not isinstance(params, dict):
        params = {}

    if strategy == "fixed":
        return datetime.fromisoformat(str(params.get("fixed_until", NON_EARLY_BIRD_VALID_UNTIL)))

    fallback_minutes = int(params.get("fallback_minutes", 30))
    if strategy == "follow_early_bird_stage_or_fixed" and uses_early_bird:
        stage_ends = _stage_end_times(req.grade)
        if now <= stage_ends[0]:
            cutoff = stage_ends[0]
        elif now <= stage_ends[1]:
            cutoff = stage_ends[1]
        else:
            return now + timedelta(minutes=fallback_minutes)

        if (cutoff - now) <= timedelta(minutes=fallback_minutes):
            return now + timedelta(minutes=fallback_minutes)
        return cutoff

    return datetime.fromisoformat(str(params.get("fixed_until", NON_EARLY_BIRD_VALID_UNTIL)))


def _format_price(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _get_name_and_info_from_student_id(student_id: int) -> str:
    default_name = "未知老生"
    default_grade = "年级未知"

    with SessionLocal() as db:
        history_row = db.scalar(select(StudentHistory).where(StudentHistory.id == student_id))
        if history_row is not None:
            student_name = history_row.name or default_name
            student_grade = history_row.grade or default_grade
            return f"{student_name} (ID: {student_id}, {student_grade})"

    return f"{default_name} (ID: {student_id}, {default_grade})"


def _render_discount_info_text(discounts: list[DiscountItem]) -> str:
    if not discounts:
        return ""
    lines = []
    
    for idx, discount in enumerate(discounts):
        name = discount.name
        amount = discount.amount
        if name == "老带新":
            lines.append(f"{idx + 1}. {name}优惠: {_format_price(amount)} (关联老生: {_get_name_and_info_from_student_id(int(amount))})")
            continue
        else:
            lines.append(f"{idx + 1}. {name}: {_format_price(amount)}")

    return "\n".join(lines)


def _render_mixed_mode_details_text(mode_details: dict[str, Any] | None) -> str:
    if not mode_details:
        return ""
    lines = []
    online_subjects = mode_details.get("online_subjects", [])
    offline_subjects = mode_details.get("offline_subjects", [])
    if online_subjects:
        lines.append(f"线上科目: {'、'.join(online_subjects)}")
    if offline_subjects:
        lines.append(f"线下科目: {'、'.join(offline_subjects)}")
    return "\n".join(lines)


def render_quote_text(req: QuoteCalculateRequest, quote: QuoteResult) -> str:
    """
    生成给家长的报价文本，包含报价详情和优惠信息等。

    req: QuoteCalculateRequest - 报价请求数据，包含学生信息、年级、科目、上课方式、优惠等。
    quote: QuoteResult - 计算得到的报价结果，包含价格、优惠信息、有效期等。
    """
    lines = [
        f"学生姓名: {req.student_info.name} 家长电话: {req.student_info.phone}",
        "--------------------------------",
        req.grade,
        f"{'、'.join(req.class_subjects)}",
        f"上课方式: {req.class_mode if req.class_mode != '混合' else ('混合 (' + _render_mixed_mode_details_text(req.mode_details) + ')')}",
        "--------------------------------",
        f"优惠:\n{_render_discount_info_text(req.discounts)}\n" \
        "--------------------------------" if req.discounts else "",
        f"原价: {_format_price(quote.base_price)}",
        f"算式: {quote.pricing_formula}",
        "--------------------------------",
        f"报价: {_format_price(quote.final_price)}",
        f"有效期: {quote.quote_valid_until.strftime('%Y/%m/%d %H:%M:%S 中国标准时间')}",
    ]

    if quote.non_price_benefits:
        lines.append("提示:")
        lines.extend(f"- {item}" for item in quote.non_price_benefits)

    return "\n".join(lines)


def render_quote_text_internal(req: QuoteCalculateRequest, quote: QuoteResult) -> str:
    lines = [
        "【报价通知】",
        f"学生: {req.student_info.name} / {req.student_info.phone}",
        f"操作人: {req.operator_name}   来源: {req.source}",
        f"年级: {req.grade}",
        f"班型与科目: {'、'.join(req.class_subjects)}",
        f"上课方式: {req.class_mode}",
        f"原价: {_format_price(quote.base_price)}",
        f"优惠: {_format_price(quote.discount_total)}",
        f"报价: {_format_price(quote.final_price)}",
        f"算式: {quote.pricing_formula}",
        f"有效期: {quote.quote_valid_until.strftime('%y/%m/%d %H:%M:%S 中国标准时间')}",
    ]

    if req.mode_details:
        mode_details = json.dumps(req.mode_details, ensure_ascii=False, sort_keys=True)
        lines.append(f"混合模式明细: {mode_details}")

    if req.discounts:
        lines.append("手选优惠:")
        lines.extend(
            f"- {item.name}: {_format_price(item.amount)}"
            f"{f' (老生ID:{item.history_student_id})' if item.history_student_id else ''}"
            for item in req.discounts
        )

    if quote.non_price_benefits:
        lines.append("系统提示:")
        lines.extend(f"- {item}" for item in quote.non_price_benefits)

    return "\n".join(lines)


def build_quote(req: QuoteCalculateRequest, now: datetime | None = None) -> QuoteResult:
    current = now or datetime.now()
    _validate_request(req)
    base_price, base_expr = _calc_base_price(req)
    discount_total, discount_info, non_price_benefits = _calc_discounts(req, current)
    final_price = round(base_price - discount_total, 2)
    quote_valid_until = _calc_valid_until(req, current)

    expr_parts = [base_expr]
    for name, amount in discount_info.items():
        expr_parts.append(f"-{name}({int(amount) if amount.is_integer() else amount})")
    formula = f"{' '.join(expr_parts)} = {final_price}"

    snapshot = {
        "grade": req.grade,
        "class_subjects": req.class_subjects,
        "class_mode": req.class_mode,
        "mode_details": req.mode_details,
        "discounts": [item.model_dump() for item in req.discounts],
        "generated_at": current.isoformat(),
    }

    quote = QuoteResult(
        base_price=base_price,
        discount_total=discount_total,
        final_price=final_price,
        pricing_formula=formula,
        quote_valid_until=quote_valid_until,
        non_price_benefits=non_price_benefits,
        discount_info=discount_info,
        pricing_snapshot=snapshot,
        quote_text="",
    )
    quote.quote_text = render_quote_text(req, quote)
    return quote


def build_fingerprint(student_id: int, req: QuoteCalculateRequest, final_price: float) -> str:
    payload = {
        "student_id": student_id,
        "source": req.source,
        "grade": req.grade,
        "class_subjects": sorted(req.class_subjects),
        "class_mode": req.class_mode,
        "mode_details": req.mode_details,
        "discounts": sorted(
            [item.model_dump() for item in req.discounts], key=lambda x: json.dumps(x, sort_keys=True)
        ),
        "final_price": final_price,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
