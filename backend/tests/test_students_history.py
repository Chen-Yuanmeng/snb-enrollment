from app.main import list_students_history
from app.models import StudentHistory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


def _make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return testing_session()


def _seed_history(db):
    rows = [
        StudentHistory(name="张三", grade="新高二暑", phone_suffix="0001", note="a"),
        StudentHistory(name="李四", grade="新高二暑", phone_suffix="0002", note="b"),
        StudentHistory(name="王五", grade="新高三暑", phone_suffix="0003", note="c"),
        StudentHistory(name="赵六", grade="新高一暑", phone_suffix="0004", note="d"),
        StudentHistory(name="钱七", grade="新高二暑", phone_suffix="0005", note="e"),
    ]
    db.add_all(rows)
    db.commit()


def test_students_history_pagination_and_total():
    db = _make_session()
    try:
        _seed_history(db)
        result = list_students_history(page=1, page_size=2, db=db)
        assert result.total == 5
        assert result.page == 1
        assert result.page_size == 2
        assert len(result.data) == 2
        assert result.data[0]["id"] > result.data[1]["id"]

        page2 = list_students_history(page=2, page_size=2, db=db)
        assert page2.total == 5
        assert page2.page == 2
        assert len(page2.data) == 2

        page3 = list_students_history(page=3, page_size=2, db=db)
        assert page3.total == 5
        assert page3.page == 3
        assert len(page3.data) == 1
    finally:
        db.close()


def test_students_history_filter_and_limit_compatibility():
    db = _make_session()
    try:
        _seed_history(db)
        result = list_students_history(grade="新高二暑", page=1, page_size=20, db=db)
        assert result.total == 3
        assert len(result.data) == 3

        compat = list_students_history(page=3, page_size=1, limit=2, db=db)
        assert compat.page == 1
        assert compat.page_size == 2
        assert len(compat.data) == 2
    finally:
        db.close()
