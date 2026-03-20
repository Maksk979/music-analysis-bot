import os
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List

from app.models.schemas import (
    AnalysisResponse, StatusResponse, AnalysisResult,
    TaskStatus, HealthResponse
)
from app.services.task_manager import TaskManager
from app.core.analyzer import AudioAnalyzer
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

task_manager = TaskManager()
analyzer = AudioAnalyzer()

ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}
MAX_FILE_SIZE = 50 * 1024 * 1024

def validate_audio_file(file: UploadFile) -> Path:
    """Проверяет расширение и создаёт путь для временного сохранения."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file format. Allowed: {ALLOWED_EXTENSIONS}")

    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)

    import uuid
    temp_path = temp_dir / f"{uuid.uuid4()}{ext}"
    return temp_path

async def save_upload_file(file: UploadFile, destination: Path) -> None:
    """Асинхронно сохраняет загруженный файл."""
    try:
        with open(destination, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

def run_analysis(task_id: str, file_path: Path):
    """Фоновая задача для анализа аудио."""
    try:
        logger.info(f"Запуск анализа для задачи {task_id}, файл {file_path}")
        task_manager.update_task(task_id, TaskStatus.PROCESSING)

        result_dict = analyzer.analyze_file(str(file_path))

        result = AnalysisResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            file_info=result_dict.get('file_info'),
            spectral=result_dict.get('spectral'),
            rhythm=result_dict.get('rhythm'),
            harmonic=result_dict.get('harmonic'),
            high_level=result_dict.get('high_level'),
            analysis_metadata=result_dict.get('analysis_metadata')
        )

        task_manager.update_task(task_id, TaskStatus.COMPLETED, result=result)
        logger.info(f"Задача {task_id} завершена успешно")

    except Exception as e:
        logger.error(f"Ошибка при анализе задачи {task_id}: {e}")
        task_manager.update_task(task_id, TaskStatus.FAILED, error=str(e))
    finally:
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Временный файл {file_path} удалён")

@router.post("/analyze", response_model=AnalysisResponse, status_code=202)
async def analyze_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Загружает аудиофайл и запускает его анализ в фоновом режиме.
    Возвращает ID задачи для отслеживания статуса.
    """

    temp_path = validate_audio_file(file)
    await save_upload_file(file, temp_path)

    task_id = task_manager.create_task()

    background_tasks.add_task(run_analysis, task_id, temp_path)

    return AnalysisResponse(task_id=task_id, status=TaskStatus.PENDING)

@router.get("/status/{task_id}", response_model=StatusResponse)
async def get_status(task_id: str):
    """Возвращает статус обработки задачи."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    progress = None
    if task['status'] == TaskStatus.PENDING:
        progress = 0.0
    elif task['status'] == TaskStatus.PROCESSING:
        progress = 0.5
    elif task['status'] == TaskStatus.COMPLETED:
        progress = 1.0

    return StatusResponse(
        task_id=task_id,
        status=task['status'],
        progress=progress,
        error=task.get('error')
    )

@router.get("/result/{task_id}", response_model=AnalysisResult)
async def get_result(task_id: str):
    """Возвращает результат анализа, если задача завершена."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task['status'] == TaskStatus.PENDING:
        raise HTTPException(status_code=425, detail="Task is pending")  
    elif task['status'] == TaskStatus.PROCESSING:
        raise HTTPException(status_code=425, detail="Task is still processing")
    elif task['status'] == TaskStatus.FAILED:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {task.get('error')}")

    return task['result']

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Проверка работоспособности сервиса."""
    return HealthResponse()