import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, select
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/track_analyzer")
# Заменяем postgresql на postgresql+asyncpg для асинхронной работы
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(ASYNC_DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class AudioFeatures(Base):
    __tablename__ = "audio_features"

    id = Column(Integer, primary_key=True)
    audio_file_id = Column(Integer, ForeignKey("audio_files.id"))
    tempo = Column(Float)
    energy = Column(Float)
    danceability = Column(Float)
    valence = Column(Float)
    acousticness = Column(Float)
    instrumentalness = Column(Float)
    speechiness = Column(Float)
    loudness = Column(Float)
    key = Column(Integer)
    mode = Column(Integer)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session