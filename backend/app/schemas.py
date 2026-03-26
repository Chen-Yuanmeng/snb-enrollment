from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


class DiscountItem(BaseModel):
    name: str
    amount: float = 0
    history_student_id: int | None = None
    note: str | None = None


class StudentInfoInput(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=6, max_length=20)
    gender: int | None = None
    birth_date: str | None = None
    school: str | None = None
    note: str | None = None


class QuoteCalculateRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    student_info: StudentInfoInput
    grade: str
    class_subjects: list[str]
    class_mode: str
    mode_details: dict[str, Any] | None = None
    discounts: list[DiscountItem] = Field(default_factory=list)
    note: str | None = None

    @field_validator("class_subjects")
    @classmethod
    def check_class_subjects(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("class_subjects 不能为空")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            trimmed = item.strip()
            if not trimmed:
                continue
            if trimmed in seen:
                continue
            seen.add(trimmed)
            normalized.append(trimmed)
        if not normalized:
            raise ValueError("class_subjects 不能为空")
        return normalized


class QuoteResult(BaseModel):
    base_price: float
    discount_total: float
    final_price: float
    pricing_formula: str
    quote_valid_until: datetime
    non_price_benefits: list[str]
    discount_info: dict[str, float]
    pricing_snapshot: dict[str, Any]


class EnrollmentCreateRequest(QuoteCalculateRequest):
    front_display_price: float | None = None


class PayRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    note: str | None = None


class BatchPayRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    enrollment_ids: list[int]


class RefundPreviewRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    original_enrollment_id: int
    new_enrollment_payload: QuoteCalculateRequest


class RefundCreateRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    original_enrollment_id: int
    new_enrollment_payload: QuoteCalculateRequest
    review_note: str | None = None


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    grade: str
    class_subjects: list[str]
    class_mode: str
    final_price: float
    status: str
    source: str
    quote_valid_until: datetime
    operator_name: str
    created_at: datetime


class StudentHistoryCreateRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    grade: str | None = Field(default=None, max_length=50)
    phone_suffix: str | None = Field(default=None, max_length=20)
    note: str | None = None

    @field_validator("name", "grade", "phone_suffix", "note")
    @classmethod
    def trim_optional_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class StudentHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    grade: str | None
    phone_suffix: str | None
    note: str | None
    created_at: datetime

