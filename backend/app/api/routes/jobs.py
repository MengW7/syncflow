from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import get_job_service
from app.api.responses import ok
from app.models.job import JobListQuery
from app.services.job_service import JobService

router = APIRouter()


@router.post("/jobs")
def create_job(
    file: UploadFile = File(...),
    name: Optional[str] = Form(default=None),
    service: JobService = Depends(get_job_service),
) -> JSONResponse:
    created = service.create_job(file, name)
    return JSONResponse(status_code=201, content=ok(created.model_dump(mode="json")))


@router.get("/jobs")
def list_jobs(
    query: Annotated[JobListQuery, Query()],
    service: JobService = Depends(get_job_service),
) -> JSONResponse:
    status = query.status.value if query.status else None
    items, meta = service.list_jobs(page=query.page, page_size=query.page_size, status=status)
    return JSONResponse(
        status_code=200,
        content=ok([item.model_dump(mode="json") for item in items], meta.model_dump()),
    )


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JSONResponse:
    detail = service.get_job(job_id)
    return JSONResponse(status_code=200, content=ok(detail.model_dump(mode="json")))
