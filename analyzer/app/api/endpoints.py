import shutil
from pathlib import Path
from fastapi import APIRouter, Form, UploadFile, File, HTTPException, BackgroundTasks, Request
from typing import Optional
from app.models.schemas import AnalysisResponse, StatusResponse, AnalysisResult, TaskStatus, HealthResponse
from app.services.analysis_service import run_analysis
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}
MAX_FILE_SIZE = 50 * 1024 * 1024


def _validate_and_save(file: UploadFile) -> Path:
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported format. Allowed: {ALLOWED_EXTENSIONS}")
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"{uuid.uuid4()}{ext}"


async def _write_file(file: UploadFile, destination: Path) -> None:
    try:
        with open(destination, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    finally:
        file.file.close()


@router.post("/analyze", response_model=AnalysisResponse, status_code=202)
async def analyze_audio(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_id: Optional[str] = Form(None),   # UUID from Rust service
):
    """
    Принимает аудиофайл на анализ.

    `file_id` — UUID файла из Rust БД. Если передан, анализатор после
    завершения сохранит метрики в PostgreSQL и отправит POST /api/notify.
    """
    task_manager = request.app.state.task_manager
    temp_path = _validate_and_save(file)
    await _write_file(file, temp_path)

    task_id = await task_manager.create_task(str(temp_path), file_id=file_id)
    background_tasks.add_task(run_analysis, task_id, temp_path, task_manager)

    return AnalysisResponse(task_id=task_id, status=TaskStatus.PENDING)


@router.get("/status/{task_id}", response_model=StatusResponse)
async def get_status(request: Request, task_id: str):
    task_manager = request.app.state.task_manager
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    progress_map = {
        TaskStatus.PENDING.value:    0.0,
        TaskStatus.PROCESSING.value: 0.5,
        TaskStatus.COMPLETED.value:  1.0,
        TaskStatus.FAILED.value:     1.0,
    }
    return StatusResponse(
        task_id=task_id,
        status=task['status'],
        progress=progress_map.get(task['status']),
        error=task.get('error'),
    )


@router.get("/result/{task_id}", response_model=AnalysisResult)
async def get_result(request: Request, task_id: str):
    task_manager = request.app.state.task_manager
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status = task['status']
    if status == TaskStatus.PENDING.value:
        raise HTTPException(status_code=425, detail="Task is pending")
    if status == TaskStatus.PROCESSING.value:
        raise HTTPException(status_code=425, detail="Task is still processing")
    if status == TaskStatus.FAILED.value:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {task.get('error')}")

    result_data = task.get('result')
    if not result_data:
        raise HTTPException(status_code=500, detail="Result not found")
    return AnalysisResult(**result_data)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse()
