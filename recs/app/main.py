# main.py (обновленный)
from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import numpy as np

from .database import get_db, AudioFeatures
from .models import FeaturesIn, RecommendationOut, BatchRecommendationRequest, WeightsUpdateRequest
from .similarity import extract_feature_vector, get_top_similar, compute_similarity
from .redis_cache import cache
from .model_manager import model
from .weighting import weighting
from .normalization import normalizer

app = FastAPI(title="Recommendations Microservice", version="1.0.0")

@app.on_event("startup")
async def startup():
    await cache.init()
    # Попытка загрузить предобученную модель
    try:
        model.load("model_data")
        print("Model loaded from disk")
    except:
        print("No existing model found, will build on first request")

@app.on_event("shutdown")
async def shutdown():
    await cache.close()
    # Сохраняем модель при завершении (опционально)
    try:
        model.save("model_data")
    except:
        pass

async def rebuild_model_background(db: AsyncSession):
    """Фоновая перестройка модели"""
    result = await db.execute(select(AudioFeatures))
    all_features = result.scalars().all()
    if all_features:
        model.build_index(all_features)
        model.save("model_data")
        # Инвалидируем весь кэш после перестройки
        await cache.client.flushall()

@app.post("/admin/rebuild-model")
async def rebuild_model(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Принудительная перестройка индекса и кластеризации"""
    background_tasks.add_task(rebuild_model_background, db)
    return {"status": "model rebuild started"}

@app.post("/admin/invalidate-cache")
async def invalidate_cache(pattern: str = "rec:*"):
    """Инвалидация кэша по паттерну"""
    if cache.client:
        keys = await cache.client.keys(pattern)
        if keys:
            await cache.client.delete(*keys)
    return {"status": "cache invalidated", "keys_deleted": len(keys) if keys else 0}

@app.post("/admin/weights")
async def update_weights(weights: WeightsUpdateRequest):
    """Обновление весов признаков"""
    for feat_name, weight in weights.weights.items():
        weighting.update_weight(feat_name, weight)
    # После изменения весов нужно перестроить модель
    return {"status": "weights updated, please rebuild model with /admin/rebuild-model"}

@app.get("/admin/weights")
async def get_weights():
    """Получить текущие веса"""
    return weighting.weights

@app.get("/health")
async def health():
    return {"status": "ok", "service": "recommendations"}

@app.get("/recommendations/{file_id}", response_model=List[RecommendationOut])
async def get_recommendations(
    file_id: int,
    method: str = Query("cosine", regex="^(cosine|euclidean|pearson)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    use_model: bool = Query(True, description="Использовать индексированную модель (быстрее)")
):
    cache_key = f"rec:{file_id}:{method}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    # Получаем целевой файл
    result = await db.execute(
        select(AudioFeatures).where(AudioFeatures.audio_file_id == file_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="File not found or not analyzed yet")
    
    target_vec = extract_feature_vector(target)
    
    if use_model and model.index is not None and method in ["cosine", "euclidean"]:
        # Используем FAISS индекс
        similar = model.get_similar(target_vec, file_id, method, limit)
        recommendations = [
            RecommendationOut(file_id=fid, similarity_score=score)
            for fid, score in similar
        ]
    else:
        # Линейный поиск (для Pearson или если модель не готова)
        result = await db.execute(select(AudioFeatures))
        all_features = result.scalars().all()
        similar = get_top_similar(target_vec, file_id, all_features, method, limit)
        recommendations = [
            RecommendationOut(file_id=fid, similarity_score=score)
            for fid, score in similar
        ]
    
    await cache.set(cache_key, [r.dict() for r in recommendations], ttl=300)
    return recommendations

@app.post("/similar-by-features", response_model=List[RecommendationOut])
async def similar_by_features(
    features: FeaturesIn,
    method: str = Query("cosine", regex="^(cosine|euclidean|pearson)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    use_model: bool = Query(True)
):
    # Создаем вектор из переданных фичей
    # Для удобства создадим временный объект
    class Dummy:
        pass
    tmp = Dummy()
    for k, v in features.dict().items():
        setattr(tmp, k, v)
    target_vec = extract_feature_vector(tmp)
    
    if use_model and model.index is not None and method in ["cosine", "euclidean"]:
        similar = model.get_similar(target_vec, target_id=-1, method=method, limit=limit)
        return [
            RecommendationOut(file_id=fid, similarity_score=score)
            for fid, score in similar
        ]
    else:
        result = await db.execute(select(AudioFeatures))
        all_features = result.scalars().all()
        scores = []
        for feats in all_features:
            vec = extract_feature_vector(feats)
            score = compute_similarity(target_vec, vec, method)
            scores.append((feats.audio_file_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        top_scores = scores[:limit]
        return [
            RecommendationOut(file_id=fid, similarity_score=score)
            for fid, score in top_scores
        ]

@app.post("/batch-recommendations")
async def batch_recommendations(
    request: BatchRecommendationRequest,
    db: AsyncSession = Depends(get_db)
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
        if model.index is not None and request.method in ["cosine", "euclidean"]:
            similar = model.get_similar(target_vec, file_id, request.method, request.limit)
        else:
            similar = get_top_similar(target_vec, file_id, all_features, request.method, request.limit)
        response[file_id] = [
            {"file_id": fid, "similarity_score": score}
            for fid, score in similar
        ]
    return response

@app.get("/features/{file_id}", response_model=FeaturesIn)
async def get_features(file_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AudioFeatures).where(AudioFeatures.audio_file_id == file_id)
    )
    features = result.scalar_one_or_none()
    if not features:
        raise HTTPException(status_code=404, detail="Features not found")
    return FeaturesIn(
        tempo=features.tempo,
        energy=features.energy,
        danceability=features.danceability,
        valence=features.valence,
        acousticness=features.acousticness,
        instrumentalness=features.instrumentalness,
        speechiness=features.speechiness,
        loudness=features.loudness,
        key=features.key,
        mode=features.mode
    )