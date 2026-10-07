from typing import Any, Optional


def ok(data: Any, meta: Optional[dict] = None) -> dict:
    """标准成功响应格式"""
    return {
        "data": data,
        "meta": meta or {},
    }


def fail(code: str, message: str, details: Optional[list] = None) -> dict:
    """标准失败响应格式"""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        }
    }