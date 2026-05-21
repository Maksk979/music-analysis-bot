import json
import uuid
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import logging
import redis.asyncio as redis

from app.models.schemas import TaskStatus, AnalysisResult

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, redis_client: redis.Redis, expiration_minutes: int = 60):
        self.redis = redis_client
        self.tasks_key = "tasks"
        self.expiration_seconds = expiration_minutes * 60

    async def create_task(self, file_path: str, file_id: Optional[str] = None) -> str:
        """Создаёт задачу. file_id — UUID файла из Rust БД (для /api/notify)."""
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        task_data = {
            'status': TaskStatus.PENDING.value,
            'file_path': file_path,
            'file_id': file_id,       # UUID from the Rust service
            'result': None,
            'error': None,
            'created_at': now,
            'updated_at': now,
        }
        await self.redis.hset(self.tasks_key, task_id, json.dumps(task_data))
        logger.info(f"Создана задача {task_id}, файл: {file_path}, file_id: {file_id}")
        return task_id

    async def update_task(self, task_id: str, status: TaskStatus,
                          result: Optional[AnalysisResult] = None,
                          error: Optional[str] = None):
        task_json = await self.redis.hget(self.tasks_key, task_id)
        if task_json:
            task_data = json.loads(task_json)
            task_data['status'] = status.value
            task_data['updated_at'] = datetime.now().isoformat()
            if result:
                task_data['result'] = result.dict() if hasattr(result, 'dict') else result
            if error:
                task_data['error'] = error
            await self.redis.hset(self.tasks_key, task_id, json.dumps(task_data))

    async def get_task(self, task_id: str) -> Optional[Dict]:
        task_json = await self.redis.hget(self.tasks_key, task_id)
        if task_json:
            return json.loads(task_json)
        return None

    async def get_result(self, task_id: str) -> Optional[AnalysisResult]:
        task_data = await self.get_task(task_id)
        if task_data and task_data.get('status') == TaskStatus.COMPLETED.value:
            res = task_data.get('result')
            if res:
                return AnalysisResult(**res)
        return None

    async def get_all_tasks(self) -> Dict[str, Dict]:
        all_tasks = await self.redis.hgetall(self.tasks_key)
        return {tid: json.loads(data) for tid, data in all_tasks.items()}

    async def get_resumable_tasks(self) -> List[tuple]:
        all_tasks = await self.get_all_tasks()
        to_resume = []
        for task_id, task_data in all_tasks.items():
            status = task_data.get('status')
            if status in (TaskStatus.PENDING.value, TaskStatus.PROCESSING.value):
                file_path = task_data.get('file_path')
                if file_path and Path(file_path).exists():
                    to_resume.append((task_id, Path(file_path)))
                else:
                    await self.update_task(task_id, TaskStatus.FAILED,
                                           error="File lost after server restart")
        return to_resume
