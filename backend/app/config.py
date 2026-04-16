import os

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()


class AppConfig(BaseModel):
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/snb_enrollment",
    )
    operators: list[str] = ["雷老师", "赵老师", "陈昱萌", "李燕子", "陈鹏举", "秦彬洋", "田奕博", "陈曦", "吴思苇", "赵毅存", "任悠然", "利利", "游老师", "测试"]
    sources: list[str] = ["大号", "小号1", "小号2", "小号3", "赵老师", "测试"]
    api_prefix: str = "/api/v1"
    reset_db_on_startup: bool = os.getenv("RESET_DB_ON_STARTUP", "0") == "1"
    reset_db_confirm: bool = os.getenv("RESET_DB_CONFIRM", "") == "YES"


config = AppConfig()
