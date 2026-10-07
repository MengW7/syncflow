from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import get_job_service
from app.api.responses import ok
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
