from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import config
from .constants import STATUS_PAID, STATUS_QUOTED, STATUS_REFUNDED, STATUS_REFUND_REQUESTED
from .database import Base, engine, get_db
from .errors import raise_biz_error
from .models import Enrollment, OperationLog, Refund, Student, StudentHistory
from .pricing_engine import build_fingerprint, build_quote, class_subject_units
from .rules_loader import get_grade_rule
from .rules_meta import RULES_META
from .schemas import (
    ApiResponse,
    BatchPayRequest,
    DiscountItem,
    EnrollmentCreateRequest,
    EnrollmentOut,
    PayRequest,
    QuoteCalculateRequest,
    RefundCreateRequest,
    RefundPreviewRequest,
    StudentHistoryCreateRequest,
    StudentHistoryOut,
)

app = FastAPI(title="山那边内部报名系统", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://127.0.0.1:5555",
        "http://localhost:5555",
    ],
    allow_origin_regex=r"https?://([a-zA-Z0-9-]+\.)*trycloudflare\.com|https?://.+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = Path(__file__).resolve().parents[2] / "frontend"


@app.exception_handler(HTTPException)
def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        payload = exc.detail
    else:
        code = 50000 if exc.status_code >= 500 else 40001
        if exc.status_code == 404:
            code = 40401
        payload = {
            "code": code,
            "message": str(exc.detail),
            "data": None,
        }
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(Exception)
def handle_exception(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "code": 50000,
            "message": str(exc),
            "data": None,
        },
    )


@app.on_event("startup")
def on_startup() -> None:
    if config.reset_db_on_startup:
        if not config.reset_db_confirm:
            raise RuntimeError(
                "检测到 RESET_DB_ON_STARTUP=1，但未确认。请设置 RESET_DB_CONFIRM=YES 后再启动。"
            )
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _log(
    db: Session,
    operator_name: str,
    source: str,
    action_type: str,
    target_type: str,
    target_id: int | None,
    result_status: str,
    message: str | None = None,
    request_summary: dict | None = None,
) -> None:
    log = OperationLog(
        operator_name=operator_name,
        source=source,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        result_status=result_status,
        message=message,
        request_summary=request_summary,
    )
    db.add(log)


def _ensure_operator(name: str) -> None:
    if name not in config.operators:
        raise_biz_error(40002, "操作员未选择或无效")


def _ensure_source(name: str) -> None:
    if name not in config.sources:
        raise_biz_error(40007, "来源未选择或无效")


def _archive_student_grade(enrollment_grade: str) -> str:
    if enrollment_grade in {"道法押题", "五一中考", "新高一暑"}:
        return "2029届"
    if enrollment_grade == "新高二暑":
        return "2028届"
    if enrollment_grade == "新高三暑":
        return "2027届"
    if enrollment_grade == "初中/小学暑期":
        return "初中/小学"
    return enrollment_grade


def _history_grade_candidates(input_grade: str) -> set[str]:
    trimmed = (input_grade or "").strip()
    if not trimmed:
        return set()

    canonical = _archive_student_grade(trimmed)
    aliases: dict[str, set[str]] = {
        "2029届": {"2029届", "道法押题", "五一中考", "新高一暑"},
        "2028届": {"2028届", "新高二暑"},
        "2027届": {"2027届", "新高三暑"},
        "初中/小学": {"初中/小学", "初中/小学暑期"},
    }
    return aliases.get(canonical, {trimmed})


def _get_or_create_student(db: Session, req: EnrollmentCreateRequest | QuoteCalculateRequest) -> Student:
    stmt = select(Student).where(Student.phone == req.student_info.phone)
    student = db.scalar(stmt)
    if student:
        return student

    student = Student(
        name=req.student_info.name,
        phone=req.student_info.phone,
        gender=req.student_info.gender,
        school=req.student_info.school,
        grade=_archive_student_grade(req.grade),
        note=req.student_info.note,
    )
    db.add(student)
    db.flush()
    return student


def _inject_auto_discounts(db: Session, payload: QuoteCalculateRequest) -> QuoteCalculateRequest:
    if payload.grade != "新高一暑":
        return payload

    if any(item.name == "五一报名优惠" for item in payload.discounts):
        return payload

    student = db.scalar(select(Student).where(Student.phone == payload.student_info.phone))
    if not student:
        return payload

    wuyi_stmt = (
        select(Enrollment)
        .where(
            Enrollment.student_id == student.id,
            Enrollment.grade == "五一中考",
            Enrollment.status.in_([STATUS_PAID, STATUS_REFUND_REQUESTED, STATUS_REFUNDED]),
            Enrollment.valid.is_(True),
        )
        .order_by(desc(Enrollment.id))
    )
    latest = db.scalar(wuyi_stmt)
    if not latest:
        return payload

    subject_count = class_subject_units(payload.grade, latest.class_subjects or [])
    if subject_count <= 0:
        return payload

    extra = DiscountItem(name="五一报名优惠", amount=float(subject_count))
    return payload.model_copy(update={"discounts": [*payload.discounts, extra]})


@app.get("/health", response_model=ApiResponse)
def health(db: Session = Depends(get_db)) -> ApiResponse:
    try:
        db.execute(select(1))
    except SQLAlchemyError:
        return ApiResponse(code=50000, message="database disconnected", data=None)
    return ApiResponse(data={"status": "ok"})


@app.get(f"{config.api_prefix}/operators", response_model=ApiResponse)
def get_operators() -> ApiResponse:
    return ApiResponse(data=[{"name": item} for item in config.operators])


@app.get(f"{config.api_prefix}/sources", response_model=ApiResponse)
def get_sources() -> ApiResponse:
    return ApiResponse(data=[{"name": item} for item in config.sources])


@app.get(f"{config.api_prefix}/rules/meta", response_model=ApiResponse)
def get_rules_meta() -> ApiResponse:
    return ApiResponse(data=RULES_META)


@app.get(f"{config.api_prefix}/rules/grade/{{grade}}", response_model=ApiResponse)
def get_rule_by_grade(grade: str) -> ApiResponse:
    rule = get_grade_rule(grade)
    if not rule:
        raise_biz_error(40401, "年级规则不存在", status_code=404)
    return ApiResponse(data=rule)


@app.get(f"{config.api_prefix}/students/search", response_model=ApiResponse)
def search_students(keyword: str = Query(...), db: Session = Depends(get_db)) -> ApiResponse:
    stmt = (
        select(Student)
        .where(or_(Student.name.ilike(f"%{keyword}%"), Student.phone.ilike(f"%{keyword}%")))
        .order_by(desc(Student.id))
        .limit(30)
    )
    students = db.scalars(stmt).all()
    data = [
        {
            "id": s.id,
            "name": s.name,
            "phone": s.phone,
            "grade": s.grade,
        }
        for s in students
    ]
    return ApiResponse(data=data)


@app.get(f"{config.api_prefix}/students-history/search/renewal", response_model=ApiResponse)
def search_students_history_for_renewal(
    name: str = Query(...),
    grade: str = Query(...),
    db: Session = Depends(get_db),
) -> ApiResponse:
    trimmed_name = name.strip()
    trimmed_grade = grade.strip()
    if not trimmed_name or not trimmed_grade:
        raise_biz_error(40001, "老生姓名和年级不能为空")
    grade_candidates = _history_grade_candidates(trimmed_grade)

    stmt = (
        select(StudentHistory)
        .where(
            StudentHistory.name == trimmed_name,
            StudentHistory.grade.in_(grade_candidates),
        )
        .order_by(desc(StudentHistory.id))
        .limit(30)
    )
    rows = db.scalars(stmt).all()
    data = [
        {
            "id": row.id,
            "name": row.name,
            "grade": row.grade,
            "phone_suffix": row.phone_suffix,
        }
        for row in rows
    ]
    return ApiResponse(data=data)


@app.get(f"{config.api_prefix}/students-history/search/referral", response_model=ApiResponse)
def search_students_history_for_referral(
    name: str = Query(...),
    db: Session = Depends(get_db),
) -> ApiResponse:
    trimmed_name = name.strip()
    if not trimmed_name:
        raise_biz_error(40001, "老生姓名不能为空")

    stmt = (
        select(StudentHistory)
        .where(StudentHistory.name.ilike(f"%{trimmed_name}%"))
        .order_by(desc(StudentHistory.id))
        .limit(30)
    )
    rows = db.scalars(stmt).all()
    data = [
        {
            "id": row.id,
            "name": row.name,
            "grade": row.grade,
            "phone_suffix": row.phone_suffix,
        }
        for row in rows
    ]
    return ApiResponse(data=data)


@app.get(f"{config.api_prefix}/students-history", response_model=ApiResponse)
def list_students_history(
    keyword: str | None = None,
    grade: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ApiResponse:
    stmt = select(StudentHistory)
    if keyword:
        trimmed = keyword.strip()
        if trimmed:
            stmt = stmt.where(
                or_(
                    StudentHistory.name.ilike(f"%{trimmed}%"),
                    StudentHistory.grade.ilike(f"%{trimmed}%"),
                    StudentHistory.phone_suffix.ilike(f"%{trimmed}%"),
                )
            )
    if grade:
        candidates = _history_grade_candidates(grade)
        stmt = stmt.where(StudentHistory.grade.in_(candidates))

    rows = db.scalars(stmt.order_by(desc(StudentHistory.id)).limit(limit)).all()
    data = [StudentHistoryOut.model_validate(row).model_dump() for row in rows]
    return ApiResponse(data=data)


@app.post(f"{config.api_prefix}/students-history", response_model=ApiResponse)
def create_student_history(payload: StudentHistoryCreateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    _ensure_operator(payload.operator_name)
    _ensure_source(payload.source)

    if not payload.name:
        raise_biz_error(40001, "老生姓名不能为空")

    row = StudentHistory(
        name=payload.name,
        grade=payload.grade,
        phone_suffix=payload.phone_suffix,
        note=payload.note,
    )
    db.add(row)
    db.flush()

    _log(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="create_student_history",
        target_type="student_history",
        target_id=row.id,
        result_status="success",
        request_summary={
            "name": row.name,
            "grade": row.grade,
            "phone_suffix": row.phone_suffix,
        },
    )

    db.commit()
    return ApiResponse(data=StudentHistoryOut.model_validate(row).model_dump())


@app.post(f"{config.api_prefix}/quotes/calculate", response_model=ApiResponse)
def calculate_quote(payload: QuoteCalculateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    _ensure_operator(payload.operator_name)
    _ensure_source(payload.source)
    try:
        effective_payload = _inject_auto_discounts(db, payload)
        quote = build_quote(effective_payload)
    except ValueError as exc:
        raise_biz_error(40001, str(exc))
    return ApiResponse(data=quote.model_dump())


@app.post(f"{config.api_prefix}/enrollments", response_model=ApiResponse)
def create_enrollment(payload: EnrollmentCreateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    _ensure_operator(payload.operator_name)
    _ensure_source(payload.source)
    try:
        effective_payload = _inject_auto_discounts(db, payload)
        quote = build_quote(effective_payload)
        student = _get_or_create_student(db, payload)
        fingerprint = build_fingerprint(student.id, effective_payload, quote.final_price)

        dup_stmt = select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.grade == payload.grade,
            Enrollment.quote_fingerprint == fingerprint,
            Enrollment.final_price == quote.final_price,
            Enrollment.valid.is_(True),
        )
        duplicate = db.scalar(dup_stmt)
        if duplicate:
            raise_biz_error(40003, "重复提交")

        row = Enrollment(
            student_id=student.id,
            grade=effective_payload.grade,
            class_subjects=effective_payload.class_subjects,
            class_mode=effective_payload.class_mode,
            mode_details=effective_payload.mode_details,
            base_price=quote.base_price,
            discount_total=quote.discount_total,
            final_price=quote.final_price,
            discount_info=quote.discount_info,
            non_price_benefits={"notes": quote.non_price_benefits},
            pricing_formula=quote.pricing_formula,
            pricing_snapshot=quote.pricing_snapshot,
            quote_valid_until=quote.quote_valid_until,
            quote_fingerprint=fingerprint,
            status=STATUS_QUOTED,
            valid=True,
            operator_name=effective_payload.operator_name,
            source=effective_payload.source,
            note=effective_payload.note,
        )
        db.add(row)
        db.flush()

        _log(
            db,
            operator_name=payload.operator_name,
            source=payload.source,
            action_type="create_enrollment",
            target_type="enrollment",
            target_id=row.id,
            result_status="success",
            request_summary={
                "student_id": student.id,
                "grade": effective_payload.grade,
                "class_subjects": effective_payload.class_subjects,
                "source": payload.source,
            },
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise_biz_error(40001, str(exc))
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise_biz_error(50000, str(exc), status_code=500)

    return ApiResponse(data={"enrollment_id": row.id, "status": row.status})


@app.get(f"{config.api_prefix}/enrollments", response_model=ApiResponse)
def list_enrollments(
    status: str | None = None,
    student_id: int | None = None,
    grade: str | None = None,
    valid: bool | None = None,
    source: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    stmt = select(Enrollment, Student.name.label("student_name"), Student.phone.label("student_phone")).join(
        Student, Enrollment.student_id == Student.id
    )
    if status:
        stmt = stmt.where(Enrollment.status == status)
    if student_id:
        stmt = stmt.where(Enrollment.student_id == student_id)
    if grade:
        stmt = stmt.where(Enrollment.grade == grade)
    if valid is not None:
        stmt = stmt.where(Enrollment.valid.is_(valid))
    if source:
        stmt = stmt.where(Enrollment.source == source)
    if keyword:
        trimmed = keyword.strip()
        if trimmed:
            filters = [Student.name.ilike(f"%{trimmed}%")]
            if trimmed.isdigit():
                filters.append(Enrollment.id == int(trimmed))
            stmt = stmt.where(or_(*filters))

    rows = db.execute(stmt.order_by(desc(Enrollment.id)).limit(200)).all()
    data = []
    for enrollment, student_name, student_phone in rows:
        item = EnrollmentOut.model_validate(enrollment).model_dump()
        item["student_name"] = student_name or ""
        item["student_phone"] = student_phone or ""
        item["discount_info"] = enrollment.discount_info or {}
        item["base_price"] = float(enrollment.base_price)
        item["discount_total"] = float(enrollment.discount_total)
        data.append(item)
    return ApiResponse(data=data)


@app.get(f"{config.api_prefix}/enrollments/{{enrollment_id}}", response_model=ApiResponse)
def get_enrollment(enrollment_id: int, db: Session = Depends(get_db)) -> ApiResponse:
    row = db.get(Enrollment, enrollment_id)
    if not row:
        raise_biz_error(40401, "记录不存在", status_code=404)
    return ApiResponse(
        data={
            "id": row.id,
            "student_id": row.student_id,
            "grade": row.grade,
            "class_subjects": row.class_subjects,
            "class_mode": row.class_mode,
            "base_price": float(row.base_price),
            "discount_total": float(row.discount_total),
            "final_price": float(row.final_price),
            "discount_info": row.discount_info,
            "non_price_benefits": row.non_price_benefits,
            "pricing_formula": row.pricing_formula,
            "pricing_snapshot": row.pricing_snapshot,
            "quote_valid_until": row.quote_valid_until,
            "status": row.status,
            "operator_name": row.operator_name,
            "source": row.source,
            "created_at": row.created_at,
        }
    )


@app.post(f"{config.api_prefix}/enrollments/{{enrollment_id}}/pay", response_model=ApiResponse)
def pay_enrollment(enrollment_id: int, payload: PayRequest, db: Session = Depends(get_db)) -> ApiResponse:
    _ensure_operator(payload.operator_name)
    _ensure_source(payload.source)
    row = db.get(Enrollment, enrollment_id)
    if not row:
        raise_biz_error(40401, "记录不存在", status_code=404)
    if row.status != STATUS_QUOTED:
        raise_biz_error(40005, "状态流转非法")

    row.status = STATUS_PAID
    row.updated_at = datetime.utcnow()
    row.note = payload.note or row.note

    _log(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="pay_enrollment",
        target_type="enrollment",
        target_id=row.id,
        result_status="success",
    )
    db.commit()
    return ApiResponse(data={"enrollment_id": row.id, "status": row.status})


@app.post(f"{config.api_prefix}/enrollments/pay-batch", response_model=ApiResponse)
def pay_batch(payload: BatchPayRequest, db: Session = Depends(get_db)) -> ApiResponse:
    _ensure_operator(payload.operator_name)
    _ensure_source(payload.source)
    results: list[dict] = []

    for enrollment_id in payload.enrollment_ids:
        row = db.get(Enrollment, enrollment_id)
        if not row:
            results.append({"enrollment_id": enrollment_id, "ok": False, "reason": "not found"})
            continue
        if row.status != STATUS_QUOTED:
            results.append({"enrollment_id": enrollment_id, "ok": False, "reason": "invalid status"})
            continue
        row.status = STATUS_PAID
        row.updated_at = datetime.utcnow()
        results.append({"enrollment_id": enrollment_id, "ok": True})

        _log(
            db,
            operator_name=payload.operator_name,
            source=payload.source,
            action_type="pay_enrollment_batch",
            target_type="enrollment",
            target_id=row.id,
            result_status="success",
        )

    db.commit()
    return ApiResponse(data=results)


@app.post(f"{config.api_prefix}/refunds/preview", response_model=ApiResponse)
def preview_refund(payload: RefundPreviewRequest, db: Session = Depends(get_db)) -> ApiResponse:
    _ensure_operator(payload.operator_name)
    _ensure_source(payload.source)
    if payload.new_enrollment_payload.source != payload.source:
        raise_biz_error(40001, "退费请求中的source不一致")
    old = db.get(Enrollment, payload.original_enrollment_id)
    if not old:
        raise_biz_error(40401, "原报名记录不存在", status_code=404)

    try:
        effective_payload = _inject_auto_discounts(db, payload.new_enrollment_payload)
        quote = build_quote(effective_payload)
    except ValueError as exc:
        raise_biz_error(40001, str(exc))
    old_price = float(old.final_price)
    new_price = quote.final_price
    refund_amount = round(old_price - new_price, 2)

    auto_rejected = refund_amount <= 0
    reject_reason = (
        "差额小于等于0，需人工先全退原报名再新建"
        if auto_rejected
        else None
    )

    return ApiResponse(
        data={
            "old_price": old_price,
            "new_price": new_price,
            "refund_amount": refund_amount,
            "auto_rejected": auto_rejected,
            "reject_reason": reject_reason,
        }
    )


@app.post(f"{config.api_prefix}/refunds", response_model=ApiResponse)
def create_refund(payload: RefundCreateRequest, db: Session = Depends(get_db)) -> ApiResponse:
    _ensure_operator(payload.operator_name)
    _ensure_source(payload.source)
    if payload.new_enrollment_payload.source != payload.source:
        raise_biz_error(40001, "退费请求中的source不一致")
    old = db.get(Enrollment, payload.original_enrollment_id)
    if not old:
        raise_biz_error(40401, "原报名记录不存在", status_code=404)
    if old.status != STATUS_PAID:
        raise_biz_error(40005, "仅已缴费状态可申请退费")

    try:
        effective_payload = _inject_auto_discounts(db, payload.new_enrollment_payload)
        quote = build_quote(effective_payload)
    except ValueError as exc:
        raise_biz_error(40001, str(exc))
    old_price = float(old.final_price)
    new_price = quote.final_price
    refund_amount = round(old_price - new_price, 2)

    old.status = STATUS_REFUND_REQUESTED

    auto_rejected = refund_amount <= 0
    reject_reason = None

    if auto_rejected:
        reject_reason = "差额小于等于0，需人工先全退原报名再新建"
    else:
        old.status = STATUS_REFUNDED

    refund = Refund(
        original_enrollment_id=old.id,
        recalculated_enrollment_id=None,
        refund_class_subjects=effective_payload.class_subjects,
        old_price=old_price,
        new_price=new_price,
        refund_amount=refund_amount,
        auto_rejected=auto_rejected,
        reject_reason=reject_reason,
        review_required=True,
        review_operator_name=payload.operator_name,
        review_note=payload.review_note,
        operator_name=payload.operator_name,
        source=payload.source,
    )
    db.add(refund)
    db.flush()

    _log(
        db,
        operator_name=payload.operator_name,
        source=payload.source,
        action_type="create_refund",
        target_type="refund",
        target_id=refund.id,
        result_status="auto_rejected" if auto_rejected else "success",
        message=reject_reason,
    )
    db.commit()

    if auto_rejected:
        raise_biz_error(40006, reject_reason or "退费金额小于等于0（自动拒绝）")

    return ApiResponse(data={"refund_id": refund.id, "refund_amount": refund_amount})


@app.get(f"{config.api_prefix}/logs", response_model=ApiResponse)
def list_logs(
    operator_name: str | None = None,
    source: str | None = None,
    action_type: str | None = None,
    target_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> ApiResponse:
    stmt = select(OperationLog)
    if operator_name:
        stmt = stmt.where(OperationLog.operator_name == operator_name)
    if source:
        stmt = stmt.where(OperationLog.source == source)
    if action_type:
        stmt = stmt.where(OperationLog.action_type == action_type)
    if target_type:
        stmt = stmt.where(OperationLog.target_type == target_type)

    stmt = stmt.order_by(desc(OperationLog.id)).offset((page - 1) * page_size).limit(page_size)
    rows = db.scalars(stmt).all()

    data = [
        {
            "id": row.id,
            "operator_name": row.operator_name,
            "source": row.source,
            "action_type": row.action_type,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "result_status": row.result_status,
            "message": row.message,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return ApiResponse(data=data)


if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
