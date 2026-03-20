from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.endpoints import router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="Track Analyzer Microservice",
    description="Анализ аудиофайлов и извлечение акустических характеристик",
    version="0.1.0"
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
