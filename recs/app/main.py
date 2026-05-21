"""
Сервис рекомендаций (Беляков).

Ключевые исправления по сравнению с оригиналом:
- file_id — UUID-строка (не int), чтобы соответствовать Rust-схеме
- После формирования рекомендаций они сохраняются в таблицу recommendations
"""
import os
import uuid
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .database import get_db, AudioFeatures
from .models import FeaturesIn, RecommendationOut, BatchRecommendationRequest, WeightsUpdateRequest
from .similarity import extract_feature_vector, get_top_similar, compute_similarity
from .redis_cache import cache
from .model_manager import model
from .weighting import weighting
from .normalization import normalizer

app = FastAPI(title="Recommendations Microservice", version="1.0.0")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@postgres:5432/track_analyzer"
)


# ─── Startup / shutdown ───────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await cache.init()
    try:
        model.load("model_data")
        print("Model loaded from disk")
    except Exception:
        print("No existing model found, will build on first request")


@app.on_event("shutdown")
async def shutdown():
    await cache.close()
    try:
        model.save("model_data")
    except Exception:
        pass


# ─── Background tasks ─────────────────────────────────────────────────────────

async def rebuild_model_background(db: AsyncSession):
    result = await db.execute(select(AudioFeatures))
    all_features = result.scalars().all()
    if all_features:
        model.build_index(all_features)
        model.save("model_data")
        if cache.client:
            await cache.client.flushall()


async def _save_recommendations_to_db(source_file_id: str, similar: List[tuple]):
    """Persist recommendations into the recommendations table."""
    import asyncpg
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            for rec_file_id, score in similar:
                await conn.execute(
                    """
                    INSERT INTO recommendations
                        (id, source_file_id, recommended_file_id, similarity_score, created_at)
                    VALUES ($1::uuid, $2::uuid, $3::uuid, $4, NOW())
                    ON CONFLICT (source_file_id, recommended_file_id) DO UPDATE
                        SET similarity_score = EXCLUDED.similarity_score
                    """,
                    str(uuid.uuid4()),
                    source_file_id,
                    rec_file_id,
                    score,
                )
        finally:
            await conn.close()
    except Exception as e:
        print(f"[recs] Failed to save recommendations for {source_file_id}: {e}")


# ─── Admin endpoints ──────────────────────────────────────────────────────────

@app.post("/admin/rebuild-model")
async def rebuild_model(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    background_tasks.add_task(rebuild_model_background, db)
    return {"status": "model rebuild started"}


@app.post("/admin/invalidate-cache")
async def invalidate_cache(pattern: str = "rec:*"):
    keys = []
    if cache.client:
        keys = await cache.client.keys(pattern)
        if keys:
            await cache.client.delete(*keys)
    return {"status": "cache invalidated", "keys_deleted": len(keys)}


@app.post("/admin/weights")
async def update_weights(weights: WeightsUpdateRequest):
    for feat_name, weight in weights.weights.items():
        weighting.update_weight(feat_name, weight)
    return {"status": "weights updated, please rebuild model with /admin/rebuild-model"}


@app.get("/admin/weights")
async def get_weights():
    return weighting.weights


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "recommendations"}


# ─── Recommendations by file_id ───────────────────────────────────────────────

@app.get("/recommendations/{file_id}", response_model=List[RecommendationOut])
async def get_recommendations(
    file_id: str,                           # UUID string
    background_tasks: BackgroundTasks,
    method: str = Query("cosine", regex="^(cosine|euclidean|pearson)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    use_model: bool = Query(True),
):
    cache_key = f"rec:{file_id}:{method}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(AudioFeatures).where(AudioFeatures.audio_file_id == file_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="File not found or not analyzed yet")

    target_vec = extract_feature_vector(target)

    if use_model and model.index is not None and method in ("cosine", "euclidean"):
        similar = model.get_similar(target_vec, file_id, method, limit)
    else:
        result2 = await db.execute(select(AudioFeatures))
        all_features = result2.scalars().all()
        similar = get_top_similar(target_vec, file_id, all_features, method, limit)

    recommendations = [RecommendationOut(file_id=fid, similarity_score=score)
                       for fid, score in similar]

    await cache.set(cache_key, [r.dict() for r in recommendations], ttl=300)

    # Persist to recommendations table in the background
    background_tasks.add_task(_save_recommendations_to_db, file_id, similar)

    return recommendations


# ─── Similar by features ──────────────────────────────────────────────────────

@app.post("/similar-by-features", response_model=List[RecommendationOut])
async def similar_by_features(
    features: FeaturesIn,
    method: str = Query("cosine", regex="^(cosine|euclidean|pearson)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    use_model: bool = Query(True),
):
    class _Dummy:
        pass

    tmp = _Dummy()
    for k, v in features.dict().items():
        setattr(tmp, k, v)
    target_vec = extract_feature_vector(tmp)

    if use_model and model.index is not None and method in ("cosine", "euclidean"):
        similar = model.get_similar(target_vec, target_id="", method=method, limit=limit)
        return [RecommendationOut(file_id=fid, similarity_score=score)
                for fid, score in similar]

    result = await db.execute(select(AudioFeatures))
    all_features = result.scalars().all()
    scores = []
    for feats in all_features:
        vec = extract_feature_vector(feats)
        scores.append((feats.audio_file_id, compute_similarity(target_vec, vec, method)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [RecommendationOut(file_id=fid, similarity_score=score)
            for fid, score in scores[:limit]]


# ─── Batch recommendations ────────────────────────────────────────────────────

@app.post("/batch-recommendations")
async def batch_recommendations(
    request: BatchRecommendationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AudioFeatures))
    all_features = result.scalars().all()
    response = {}
    for file_id in request.file_ids:
        target = next((f for f in all_features if f.audio_file_id == file_id), None)
        if not target:
            response[file_id] = {"error": "Not found"}
            continue
        target_vec = extract_feature_vector(target)
        if model.index is not None and request.method in ("cosine", "euclidean"):
            similar = model.get_similar(target_vec, file_id, request.method, request.limit)
        else:
            similar = get_top_similar(target_vec, file_id, all_features, request.method, request.limit)
        response[file_id] = [{"file_id": fid, "similarity_score": score}
                              for fid, score in similar]
        background_tasks.add_task(_save_recommendations_to_db, file_id, similar)
    return response


# ─── Features endpoint ────────────────────────────────────────────────────────

@app.get("/features/{file_id}", response_model=FeaturesIn)
async def get_features(file_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AudioFeatures).where(AudioFeatures.audio_file_id == file_id)
    )
    features = result.scalar_one_or_none()
    if not features:
        raise HTTPException(status_code=404, detail="Features not found")
    return FeaturesIn(
        tempo=features.tempo or 0.0,
        energy=features.energy or 0.0,
        danceability=features.danceability or 0.0,
        valence=features.valence or 0.0,
        acousticness=features.acousticness or 0.0,
        instrumentalness=features.instrumentalness or 0.0,
        speechiness=features.speechiness or 0.0,
        loudness=features.loudness or 0.0,
        key=features.key or 0,
        mode=features.mode or 0,
    )
