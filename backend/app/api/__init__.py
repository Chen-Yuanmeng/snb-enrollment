from fastapi import APIRouter

from .routers.enrollments import router as enrollments_router
from .routers.logs import router as logs_router
from .routers.quotes import router as quotes_router
from .routers.refunds import router as refunds_router
from .routers.rules import router as rules_router
from .routers.students import router as students_router
from .routers.students_history import router as students_history_router
from .routers.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(rules_router)
api_router.include_router(students_router)
api_router.include_router(students_history_router)
api_router.include_router(quotes_router)
api_router.include_router(enrollments_router)
api_router.include_router(refunds_router)
api_router.include_router(logs_router)
