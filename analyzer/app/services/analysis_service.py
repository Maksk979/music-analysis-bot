"""
Фоновая задача анализа аудиофайла.

После завершения анализа:
1. Сохраняет высокоуровневые метрики в таблицу audio_features (PostgreSQL).
2. Вызывает POST /api/notify на Rust-сервисе, чтобы тот обновил статус
   файла и уведомил клиентов.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import asyncpg
import httpx

from app.models.schemas import AnalysisResult, TaskStatus
from app.core.analyzer import AudioAnalyzer

logger = logging.getLogger(__name__)

analyzer = AudioAnalyzer()

# ─── Config ───────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@postgres:5432/track_analyzer"
)
BOT_SERVICE_URL = os.getenv("BOT_SERVICE_URL", "http://bot:8080")
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "internal-secret")


# ─── Main task ────────────────────────────────────────────────────────────────

async def run_analysis(task_id: str, file_path: Path, task_manager):
    file_id: Optional[str] = None
    try:
        task_data = await task_manager.get_task(task_id)
        file_id = task_data.get('file_id') if task_data else None

        logger.info(f"Запуск анализа задача={task_id} файл={file_path} file_id={file_id}")
        await task_manager.update_task(task_id, TaskStatus.PROCESSING)

        result_dict = await asyncio.to_thread(analyzer.analyze_file, str(file_path))

        result = AnalysisResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            file_info=result_dict.get('file_info'),
            spectral=result_dict.get('spectral'),
            rhythm=result_dict.get('rhythm'),
            harmonic=result_dict.get('harmonic'),
            high_level=result_dict.get('high_level'),
            analysis_metadata=result_dict.get('analysis_metadata'),
        )

        await task_manager.update_task(task_id, TaskStatus.COMPLETED, result=result)
        logger.info(f"Задача {task_id} завершена успешно")

        # ── 1. Save features to PostgreSQL ────────────────────────────────────
        if file_id:
            await _save_features_to_db(file_id, result_dict)

        # ── 2. Notify Rust bot ────────────────────────────────────────────────
        if file_id:
            await _notify_bot(file_id, "completed")

    except Exception as e:
        logger.error(f"Ошибка анализа задача={task_id}: {e}", exc_info=True)
        await task_manager.update_task(task_id, TaskStatus.FAILED, error=str(e))
        if file_id:
            await _notify_bot(file_id, "failed", details=str(e))

    finally:
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Временный файл {file_path} удалён")


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _save_features_to_db(file_id: str, result_dict: dict):
    """Insert/upsert a row into audio_features."""
    hl = result_dict.get('high_level', {})
    rhythm = result_dict.get('rhythm', {})
    harmonic = result_dict.get('harmonic', {})

    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute(
                """
                INSERT INTO audio_features
                    (id, audio_file_id, tempo, energy, danceability, valence,
                     acousticness, instrumentalness, speechiness, loudness,
                     key, mode, created_at)
                VALUES (gen_random_uuid(), $1::uuid, $2, $3, $4, $5,
                        $6, $7, $8, $9, $10, $11, NOW())
                ON CONFLICT (audio_file_id) DO UPDATE SET
                    tempo            = EXCLUDED.tempo,
                    energy           = EXCLUDED.energy,
                    danceability     = EXCLUDED.danceability,
                    valence          = EXCLUDED.valence,
                    acousticness     = EXCLUDED.acousticness,
                    instrumentalness = EXCLUDED.instrumentalness,
                    speechiness      = EXCLUDED.speechiness,
                    loudness         = EXCLUDED.loudness,
                    key              = EXCLUDED.key,
                    mode             = EXCLUDED.mode
                """,
                file_id,
                rhythm.get('tempo'),
                hl.get('energy'),
                hl.get('danceability'),
                hl.get('valence'),
                hl.get('acousticness'),
                hl.get('instrumentalness'),
                hl.get('speechiness'),
                hl.get('loudness'),
                harmonic.get('key_index'),
                1 if harmonic.get('mode') == 'major' else 0,
            )
            logger.info(f"Метрики сохранены в audio_features для file_id={file_id}")
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения метрик в БД для {file_id}: {e}", exc_info=True)


async def _notify_bot(file_id: str, status: str, details: Optional[str] = None):
    """POST /api/notify to the Rust bot service."""
    url = f"{BOT_SERVICE_URL}/api/notify"
    payload = {"file_id": file_id, "status": status, "details": details}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"X-Internal-Secret": INTERNAL_API_SECRET},
            )
        if resp.status_code == 200:
            logger.info(f"Bot notified: file={file_id} status={status}")
        else:
            logger.warning(f"Bot notification returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to notify bot for file={file_id}: {e}")
