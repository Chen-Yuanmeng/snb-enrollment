from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .api.routers.enrollments import list_enrollments
from .api.routers.students_history import list_students_history
from .config import config
from .database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if config.reset_db_on_startup:
        if not config.reset_db_confirm:
            raise RuntimeError(
                "检测到 RESET_DB_ON_STARTUP=1，但未确认。请设置 RESET_DB_CONFIRM=YES 后再启动。"
            )
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="山那边内部报名系统", version="0.1.0", lifespan=lifespan)

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

app.include_router(api_router)


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


if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
