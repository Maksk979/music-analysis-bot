-- Migration: 001_initial_schema.sql

-- Custom ENUM types
CREATE TYPE audio_file_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE queue_status       AS ENUM ('queued', 'processing', 'done', 'failed');

-- ─── Users ────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT  NOT NULL UNIQUE,
    username    TEXT,
    first_name  TEXT    NOT NULL,
    last_name   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);

-- ─── Audio Files ──────────────────────────────────────────────────────────────
CREATE TABLE audio_files (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_name TEXT    NOT NULL,
    minio_key     TEXT    NOT NULL UNIQUE,
    file_size     BIGINT  NOT NULL,
    mime_type     TEXT    NOT NULL,
    file_hash     TEXT    NOT NULL,
    status        audio_file_status NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audio_files_user_id   ON audio_files(user_id);
CREATE INDEX idx_audio_files_file_hash ON audio_files(file_hash);
CREATE INDEX idx_audio_files_status    ON audio_files(status);

-- ─── Audio Features (written by Kopylev's analyser service) ───────────────────
CREATE TABLE audio_features (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audio_file_id       UUID NOT NULL UNIQUE REFERENCES audio_files(id) ON DELETE CASCADE,
    tempo               DOUBLE PRECISION,
    energy              DOUBLE PRECISION,
    danceability        DOUBLE PRECISION,
    valence             DOUBLE PRECISION,
    acousticness        DOUBLE PRECISION,
    instrumentalness    DOUBLE PRECISION,
    speechiness         DOUBLE PRECISION,
    loudness            DOUBLE PRECISION,
    key                 INTEGER,
    mode                INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Recommendations (written by Belyakov's recommender service) ─────────────
CREATE TABLE recommendations (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id       UUID NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    recommended_file_id  UUID NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    similarity_score     DOUBLE PRECISION NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file_id, recommended_file_id)
);

CREATE INDEX idx_recommendations_source ON recommendations(source_file_id);

-- ─── Processing Queue ─────────────────────────────────────────────────────────
CREATE TABLE processing_queue (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audio_file_id UUID NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
    status        queue_status NOT NULL DEFAULT 'queued',
    attempts      INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_processing_queue_status        ON processing_queue(status);
CREATE INDEX idx_processing_queue_audio_file_id ON processing_queue(audio_file_id);
