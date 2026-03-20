from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import numpy as np

from .database import get_db, AudioFeatures
from .models import FeaturesIn, RecommendationOut, BatchRecommendationRequest
from .similarity import extract_feature_vector, get_top_similar
from .redis_cache import cache

app = FastAPI(title="Recommendations Microservice", version="1.0.0")

@app.on_event("startup")
async def startup():
    await cache.init()

@app.on_event("shutdown")
async def shutdown():
    await cache.close()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "recommendations"}

@app.get("/recommendations/{file_id}", response_model=List[RecommendationOut])
async def get_recommendations(
    file_id: int,
    method: str = Query("cosine", regex="^(cosine|euclidean|pearson)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    # Пытаемся получить из кэша
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
    
    # Получаем все остальные файлы
    result = await db.execute(select(AudioFeatures))
    all_features = result.scalars().all()
    
    # Вычисляем схожесть
    target_vec = extract_feature_vector(target)
    similar = get_top_similar(target_vec, all_features, method, limit)
    
    # Формируем ответ
    recommendations = []
    for similar_id, score in similar:
        # Можно догрузить фичи, но для простоты пока так
        recommendations.append(RecommendationOut(
            file_id=similar_id,
            similarity_score=score
        ))
    
    # Кэшируем на 5 минут
    await cache.set(cache_key, [r.dict() for r in recommendations], ttl=300)
    
    return recommendations

@app.post("/similar-by-features", response_model=List[RecommendationOut])
async def similar_by_features(
    features: FeaturesIn,
    method: str = Query("cosine", regex="^(cosine|euclidean|pearson)$"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    # Создаем вектор из переданных фичей
    target_vec = np.array([[
        features.tempo,
        features.energy,
        features.danceability,
        features.valence,
        features.acousticness,
        features.instrumentalness,
        features.speechiness,
        features.loudness,
        features.key,
        features.mode
    ]])
    
    # Получаем все фичи из БД
    result = await db.execute(select(AudioFeatures))
    all_features = result.scalars().all()
    
    # Вычисляем схожесть
    scores = []
    for feats in all_features:
        vec = extract_feature_vector(feats)
        from .similarity import compute_similarity
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
    
    # Для простоты возвращаем словарь file_id -> рекомендации
    response = {}
    
    for file_id in request.file_ids:
        target = next((f for f in all_features if f.audio_file_id == file_id), None)
        if not target:
            response[file_id] = {"error": "Not found"}
            continue
        
        target_vec = extract_feature_vector(target)
        similar = get_top_similar(target_vec, all_features, request.method, request.limit)
        
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