from enum import Enum
from typing import Any, List, Optional


class ErrorCode(str, Enum):
    """全局统一业务错误码定义"""
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_FILE_EXTENSION = "INVALID_FILE_EXTENSION"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    QUEUE_ENQUEUE_FAILED = "QUEUE_ENQUEUE_FAILED"  # 内部用，写入 last_error_code


class AppError(Exception):
    """业务异常基类"""
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        details: Optional[List[Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or []


class JobNotFound(AppError):
    def __init__(self, message: str = "任务不存在", details: Optional[List[Any]] = None):
        super().__init__(
            code=ErrorCode.JOB_NOT_FOUND,
            message=message,
            http_status=404,
            details=details,
        )


class InvalidFileExtension(AppError):
    def __init__(self, message: str = "不支持的文件格式", details: Optional[List[Any]] = None):
        super().__init__(
            code=ErrorCode.INVALID_FILE_EXTENSION,
            message=message,
            http_status=400,
            details=details,
        )


class FileTooLarge(AppError):
    def __init__(self, message: str = "文件大小超出限制", details: Optional[List[Any]] = None):
        super().__init__(
            code=ErrorCode.FILE_TOO_LARGE,
            message=message,
            http_status=413,
            details=details,
        )


class InvalidRequest(AppError):
    def __init__(self, message: str = "请求参数错误", details: Optional[List[Any]] = None):
        super().__init__(
            code=ErrorCode.INVALID_REQUEST,
            message=message,
            http_status=400,
            details=details,
        )