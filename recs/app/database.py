"""
Подключение к PostgreSQL для сервиса рекомендаций.

ВАЖНО: audio_file_id хранится как TEXT (UUID-строка), чтобы
соответствовать типу UUID в таблице audio_files Rust-сервиса.
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, Float, Integer, select
from sqlalchemy.dialects.postgresql import UUID
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@postgres:5432/track_analyzer"
)
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class AudioFeatures(Base):
    __tablename__ = "audio_features"

    # Real PostgreSQL UUID type — Rust's audio_files.id is UUID, so the FK
    # column here must be UUID too; otherwise asyncpg binds params as VARCHAR
    # and PostgreSQL refuses the `uuid = varchar` comparison.
    id             = Column(UUID(as_uuid=False), primary_key=True)
    audio_file_id  = Column(UUID(as_uuid=False))
    tempo          = Column(Float)
    energy         = Column(Float)
    danceability   = Column(Float)
    valence        = Column(Float)
    acousticness   = Column(Float)
    instrumentalness = Column(Float)
    speechiness    = Column(Float)
    loudness       = Column(Float)
    key            = Column(Integer)
    mode           = Column(Integer)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
