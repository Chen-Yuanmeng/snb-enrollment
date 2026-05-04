from datetime import datetime

from app.schemas import DiscountItem, QuoteCalculateRequest, StudentInfoInput
from app.pricing_engine import build_quote, render_quote_text_internal


def _base_req(**kwargs):
    payload = {
        "operator_name": "张老师",
        "source": "电咨",
        "student_info": StudentInfoInput(name="张三", phone="13800000000"),
        "grade": "新高二暑",
        "class_subjects": ["英才数学", "英才物理"],
        "class_mode": "线下",
        "mode_details": None,
        "discounts": [],
        "note": None,
    }
    payload.update(kwargs)
    return QuoteCalculateRequest(**payload)


def test_g2_offline_base_price():
    req = _base_req()
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-10T12:00:00"))
    assert quote.base_price == 5040 * 2
    assert quote.discount_info.get("早鸟") == 200
    assert quote.final_price == 9880
    assert "学生姓名: 张三 家长电话: 13800000000" in quote.quote_text
    assert "提示:" in quote.quote_text


def test_internal_quote_text_differs_from_front_text():
    req = _base_req()
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-10T12:00:00"))
    internal_text = render_quote_text_internal(req, quote)
    assert "【报价通知】" in internal_text
    assert "操作人: 张老师" in internal_text
    assert internal_text != quote.quote_text


def test_mutual_exclusion_discount():
    req = _base_req(
        discounts=[
            DiscountItem(name="老带新", amount=200),
            DiscountItem(name="老生续报", amount=100),
        ]
    )
    try:
        build_quote(req)
        assert False, "should raise"
    except ValueError as exc:
        assert "不能同时选择" in str(exc)


def test_non_early_bird_valid_until_fixed():
    req = _base_req(discounts=[DiscountItem(name="现金优惠", amount=100)])
    quote = build_quote(req, now=datetime.fromisoformat("2026-07-01T10:00:00"))
    assert quote.quote_valid_until.isoformat() == "2026-12-31T23:59:59"


def test_early_bird_window_under_30m():
    req = _base_req(discounts=[DiscountItem(name="早鸟", amount=100)])
    # 2026-05-15 23:50:00 北京时间 = 2026-05-15 15:50:00 UTC
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-15T15:50:00"))
    assert quote.quote_valid_until.isoformat() == "2026-05-15T16:20:00"
    assert "本报价有效期至 2026/05/16 00:20:00 (北京时间)" in quote.quote_text


def test_auto_early_bird_applied_for_g1_without_discount_input():
    req = _base_req(
        grade="新高一暑",
        class_mode="线下",
        class_subjects=["高新领军1"],
        discounts=[],
    )
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-10T12:00:00"))
    assert quote.base_price == 20160
    assert quote.discount_info.get("早鸟") == 400
    assert quote.final_price == 19760


def test_g1_class_subject_must_be_single_select():
    req = _base_req(
        grade="新高一暑",
        class_mode="线下",
        class_subjects=["高新领军1", "高新卓越1"],
        discounts=[],
    )
    try:
        build_quote(req)
        assert False, "should raise"
    except ValueError as exc:
        assert "仅支持单选" in str(exc)


def test_laodaixin_requires_history_student_id():
    req = _base_req(
        grade="新高二暑",
        discounts=[DiscountItem(name="老带新", amount=0)],
    )
    try:
        build_quote(req)
        assert False, "should raise"
    except ValueError as exc:
        assert "必须关联老生记录" in str(exc)


def test_g3_removed_video_course():
    req = _base_req(
        grade="新高三暑",
        class_subjects=["新一试(视频课)"],
        class_mode="线下",
    )
    try:
        build_quote(req)
        assert False, "should raise"
    except ValueError as exc:
        assert "新一试" in str(exc)


def test_g1_score_discount_within_limit():
    req = _base_req(
        grade="新高一暑",
        class_mode="线下",
        class_subjects=["高新领军1"],
        discounts=[DiscountItem(name="考分优惠", amount=600)],
    )
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-10T12:00:00"))
    assert quote.discount_info.get("考分优惠") == 600


def test_g1_score_discount_over_limit_should_fail():
    req = _base_req(
        grade="新高一暑",
        class_mode="线下",
        class_subjects=["高新领军1"],
        discounts=[DiscountItem(name="考分优惠", amount=601)],
    )
    try:
        build_quote(req)
        assert False, "should raise"
    except ValueError as exc:
        assert "考分优惠金额需在0到600之间" in str(exc)


def test_g1_score_discount_is_exclusive_with_excellent_tiers():
    req = _base_req(
        grade="新高一暑",
        class_mode="线下",
        class_subjects=["高新领军1"],
        discounts=[
            DiscountItem(name="优秀生第一档", amount=0),
            DiscountItem(name="考分优惠", amount=200),
        ],
    )
    try:
        build_quote(req)
        assert False, "should raise"
    except ValueError as exc:
        text = str(exc)
        assert "不能同时选择" in text
        assert "优秀生第一档" in text
        assert "考分优惠" in text


def test_g1_referral_discount_amount_varies_by_strategy(monkeypatch):
    monkeypatch.setattr("app.pricing_engine._get_name_and_info_from_student_id", lambda _sid: "测试老生")

    cases = [
        ("高新领军1", 800),
        ("高新二期领军5", 600),
        ("高新领军2", 400),
    ]

    for class_subject, expected in cases:
        req = _base_req(
            grade="新高一暑",
            class_mode="线下",
            class_subjects=[class_subject],
            discounts=[DiscountItem(name="老带新", amount=0, history_student_id=1)],
        )
        quote = build_quote(req, now=datetime.fromisoformat("2026-07-01T10:00:00"))
        assert quote.discount_info.get("老带新") == expected


def test_g1_referral_legacy_name_maps_to_unified_discount(monkeypatch):
    monkeypatch.setattr("app.pricing_engine._get_name_and_info_from_student_id", lambda _sid: "测试老生")

    req = _base_req(
        grade="新高一暑",
        class_mode="线下",
        class_subjects=["高新领军1"],
        discounts=[DiscountItem(name="老带新28天", amount=0, history_student_id=1)],
    )
    quote = build_quote(req, now=datetime.fromisoformat("2026-07-01T10:00:00"))
    assert quote.discount_info.get("老带新") == 800
    assert "老带新28天" not in quote.discount_info


def test_g1_ab_english_training_price_has_no_discount():
    cases = [
        ("线下", 2400),
        ("线上", 2400),
    ]
    for class_mode, expected_total in cases:
        req = _base_req(
            grade="新高一暑",
            class_mode=class_mode,
            class_subjects=["英语AB分班集训课"],
            discounts=[],
        )
        quote = build_quote(req, now=datetime.fromisoformat("2026-05-10T12:00:00"))
        assert quote.base_price == expected_total
        assert quote.final_price == expected_total
        assert "早鸟" not in quote.discount_info


def test_junior_primary_summer_auto_early_bird_stage2_value():
    req = _base_req(
        grade="初中/小学暑期",
        class_mode="线下",
        class_subjects=["新九数学"],
        discounts=[],
    )
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-20T12:00:00"))
    assert quote.discount_info.get("早鸟") == 50


def test_junior_primary_summer_cash_discount_not_allowed_for_cz21_subjects():
    req = _base_req(
        grade="初中/小学暑期",
        class_mode="线下",
        class_subjects=["新七数学"],
        discounts=[DiscountItem(name="现金优惠", amount=100)],
    )
    try:
        build_quote(req)
        assert False, "should raise"
    except ValueError as exc:
        assert "当前班型不支持现金优惠" in str(exc)
