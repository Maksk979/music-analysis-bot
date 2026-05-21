from contextlib import asynccontextmanager
import asyncio
import os

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.endpoints import router, run_analysis
from app.services.task_manager import TaskManager
from app.models.schemas import TaskStatus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    await redis_client.ping()
    logger.info("Connected to Redis")

    task_manager = TaskManager(redis_client)
    app.state.task_manager = task_manager

    # Resume tasks that were interrupted by a restart
    resumable = await task_manager.get_resumable_tasks()
    for task_id, file_path in resumable:
        logger.info(f"Возобновляем задачу {task_id}, файл {file_path}")
        await task_manager.update_task(task_id, TaskStatus.PROCESSING)
        asyncio.create_task(run_analysis(task_id, file_path, task_manager))

    yield

    await redis_client.close()


app = FastAPI(
    title="Track Analyzer Microservice",
    description="Анализ аудиофайлов и извлечение акустических характеристик",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Track Analyzer API", "docs": "/docs"}
