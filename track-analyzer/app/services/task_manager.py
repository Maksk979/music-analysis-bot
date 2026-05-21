import uuid
from typing import Dict, Optional
from datetime import datetime, timedelta
import threading
import logging

from app.models.schemas import TaskStatus, AnalysisResult

logger = logging.getLogger(__name__)

class TaskManager:
    """Простое in-memory хранилище для статусов задач и результатов."""

    def __init__(self, expiration_minutes: int = 60):
        self.tasks: Dict[str, Dict] = {}
        self.expiration = timedelta(minutes=expiration_minutes)
        self._lock = threading.Lock()

    def create_task(self) -> str:
        """Создаёт новую задачу и возвращает её ID."""
        task_id = str(uuid.uuid4())
        with self._lock:
            self.tasks[task_id] = {
                'status': TaskStatus.PENDING,
                'result': None,
                'error': None,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
        logger.info(f"Создана задача {task_id}")
        return task_id

    def update_task(self, task_id: str, status: TaskStatus,
                    result: Optional[AnalysisResult] = None,
                    error: Optional[str] = None):
        """Обновляет статус задачи и, возможно, результат."""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id]['status'] = status
                self.tasks[task_id]['updated_at'] = datetime.now()
                if result:
                    self.tasks[task_id]['result'] = result
                if error:
                    self.tasks[task_id]['error'] = error

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Возвращает информацию о задаче."""
        with self._lock:
            return self.tasks.get(task_id)

    def get_result(self, task_id: str) -> Optional[AnalysisResult]:
        """Возвращает результат задачи, если он готов."""
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task['status'] == TaskStatus.COMPLETED:
                return task['result']
            return None

    def cleanup_old_tasks(self):
        """Удаляет старые задачи."""
        now = datetime.now()
        with self._lock:
            to_delete = [tid for tid, task in self.tasks.items()
                         if now - task['created_at'] > self.expiration]
            for tid in to_delete:
                del self.tasks[tid]
            if to_delete:
                logger.info(f"Удалено {len(to_delete)} устаревших задач")