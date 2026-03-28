from typing import Any

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.models import Student


def search_students(db: Session, keyword: str) -> list[dict[str, Any]]:
    stmt = (
        select(Student)
        .where(or_(Student.name.ilike(f"%{keyword}%"), Student.phone.ilike(f"%{keyword}%")))
        .order_by(desc(Student.id))
        .limit(30)
    )
    students = db.scalars(stmt).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "phone": s.phone,
            "grade": s.grade,
        }
        for s in students
    ]
