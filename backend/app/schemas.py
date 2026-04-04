from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


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
    quote_text: str


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


class AccommodationCreateRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    related_enrollment_id: int
    hotel: str = Field(min_length=1, max_length=50)
    room_type: str = Field(min_length=1, max_length=50)
    other_room_type_name: str | None = Field(default=None, max_length=100)
    duration_days: int
    gender: str = Field(min_length=1, max_length=10)
    nightly_price: float | None = None
    note: str | None = None

    @field_validator("hotel", "room_type", "other_room_type_name", "gender", "note")
    @classmethod
    def trim_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class AccommodationStatusUpdateRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    status: Literal["confirmed", "cancelled"]
    note: str | None = None

    @field_validator("note")
    @classmethod
    def trim_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class AccommodationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    related_enrollment_id: int
    hotel: str
    room_type: str
    other_room_type_name: str | None
    duration_days: int
    duration_label: str
    gender: str
    nightly_price: float
    total_price: float
    quote_text: str
    status: str
    source: str
    operator_name: str
    note: str | None
    created_at: datetime
    updated_at: datetime


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


class AdjustmentConfirmPaymentRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    note: str | None = None


class RefundConfirmRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    note: str | None = None


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
    note: str | None = None


class StudentHistoryCreateRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    grade: str | None = Field(default=None, max_length=50)
    phone_suffix: str | None = Field(default=None, max_length=20)
    can_renew_discount: bool
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
    can_renew_discount: bool
    note: str | None
    created_at: datetime


class NotificationSendRequest(BaseModel):
    operator_name: str = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=50)
    type: Literal["quotation", "payment", "adjustment", "refund", "accommodation"]
    text: str = Field(min_length=1, max_length=4000)


class MessageTaskOut(BaseModel):
    id: int
    message_type: str
    webhook_url: str
    text: str
    status: str
    retry_count: int
    next_retry_at: datetime | None
    last_error: str | None
    remote_msg_id: str | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
