import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.job import BaseSchema


class ErrorListQuery(BaseModel):
    """错误明细的分页参数。默认第 1 页、每页 20 条，最多 100 条。"""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class ErrorListMeta(BaseModel):
    page: int
    page_size: int
    total: int


class JobError(BaseSchema):
    """对外只返回这 7 个字段。内部自增 id 只用于排序，不出现在响应里。"""

    job_id: str
    row_number: Optional[int] = None
    field_name: Optional[str] = None
    error_code: str
    error_message: str
    raw_row: Optional[dict] = None
    created_at: datetime

    @field_validator("raw_row", mode="before")
    @classmethod
    def parse_raw_row(cls, value):
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            if not value:
                return None
            return json.loads(value)
        return value
