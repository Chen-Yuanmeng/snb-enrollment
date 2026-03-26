from fastapi import HTTPException


def raise_biz_error(code: int, message: str, status_code: int = 400) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "data": None,
        },
    )
