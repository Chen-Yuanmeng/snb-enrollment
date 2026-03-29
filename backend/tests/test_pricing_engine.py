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
    assert "张三 / 13800000000" in quote.quote_text
    assert "提示:" in quote.quote_text


def test_internal_quote_text_differs_from_front_text():
    req = _base_req()
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-10T12:00:00"))
    internal_text = render_quote_text_internal(req, quote)
    assert "【报价通知-内部】" in internal_text
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
    quote = build_quote(req, now=datetime.fromisoformat("2026-05-15T23:50:00"))
    assert quote.quote_valid_until.isoformat() == "2026-05-16T00:20:00"


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
