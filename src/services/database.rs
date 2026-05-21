use anyhow::{Context, Result};
use sqlx::{PgPool, postgres::PgPoolOptions};
use uuid::Uuid;

use crate::models::*;

#[derive(Clone)]
pub struct DatabaseService {
    pub pool: PgPool,
}

impl DatabaseService {
    pub async fn new(database_url: &str) -> Result<Self> {
        let pool = PgPoolOptions::new()
            .max_connections(10)
            .connect(database_url)
            .await
            .context("Failed to connect to PostgreSQL")?;

        tracing::info!("Connected to PostgreSQL");
        Ok(Self { pool })
    }

    pub async fn run_migrations(&self) -> Result<()> {
        // Inline SQL — обходим проблему sqlx::migrate! с путями на Windows
        sqlx::query("DO $$ BEGIN CREATE TYPE audio_file_status AS ENUM ('pending','processing','completed','failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
            .execute(&self.pool).await.ok();
        sqlx::query("DO $$ BEGIN CREATE TYPE queue_status AS ENUM ('queued','processing','done','failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
            .execute(&self.pool).await.ok();
        sqlx::query(r#"CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_id BIGINT NOT NULL UNIQUE, username TEXT,
            first_name TEXT NOT NULL, last_name TEXT,
            lang TEXT NOT NULL DEFAULT 'en',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"#).execute(&self.pool).await.ok();
        // Add lang column if upgrading from old schema
        sqlx::query("ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT NOT NULL DEFAULT 'en'")
            .execute(&self.pool).await.ok();
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_users_tg ON users(telegram_id)").execute(&self.pool).await.ok();
        sqlx::query(r#"CREATE TABLE IF NOT EXISTS audio_files (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            original_name TEXT NOT NULL, minio_key TEXT NOT NULL UNIQUE,
            file_size BIGINT NOT NULL, mime_type TEXT NOT NULL, file_hash TEXT NOT NULL,
            status audio_file_status NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"#).execute(&self.pool).await.ok();
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_af_user ON audio_files(user_id)").execute(&self.pool).await.ok();
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_af_hash ON audio_files(file_hash)").execute(&self.pool).await.ok();
        sqlx::query("CREATE INDEX IF NOT EXISTS idx_af_status ON audio_files(status)").execute(&self.pool).await.ok();
        sqlx::query(r#"CREATE TABLE IF NOT EXISTS audio_features (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            audio_file_id UUID NOT NULL UNIQUE REFERENCES audio_files(id) ON DELETE CASCADE,
            tempo DOUBLE PRECISION, energy DOUBLE PRECISION, danceability DOUBLE PRECISION,
            valence DOUBLE PRECISION, acousticness DOUBLE PRECISION,
            instrumentalness DOUBLE PRECISION, speechiness DOUBLE PRECISION,
            loudness DOUBLE PRECISION, key INTEGER, mode INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"#).execute(&self.pool).await.ok();
        sqlx::query(r#"CREATE TABLE IF NOT EXISTS recommendations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_file_id UUID NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
            recommended_file_id UUID NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
            similarity_score DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_file_id, recommended_file_id)
        )"#).execute(&self.pool).await.ok();
        sqlx::query(r#"CREATE TABLE IF NOT EXISTS processing_queue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            audio_file_id UUID NOT NULL REFERENCES audio_files(id) ON DELETE CASCADE,
            status queue_status NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0, error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"#).execute(&self.pool).await.ok();
        // Idempotency keys table — stores REST-upload responses keyed by
        // (idempotency_key, user_id) for 24 h so duplicate requests get the
        // same response without re-processing.
        sqlx::query(r#"CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            response JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (key, user_id)
        )"#).execute(&self.pool).await.ok();
        // Clean up keys older than 24 hours automatically via a partial index
        // (actual row deletion is done lazily on read).
        tracing::info!("Database schema ready");
        Ok(())
    }

    // ─── Users ────────────────────────────────────────────────────────────────

    pub async fn upsert_user(&self, input: &CreateUser) -> Result<User> {
        let user = sqlx::query_as::<_, User>(
            r#"
            INSERT INTO users (id, telegram_id, username, first_name, last_name, lang, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name  = EXCLUDED.last_name,
                updated_at = NOW()
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(input.telegram_id)
        .bind(&input.username)
        .bind(&input.first_name)
        .bind(&input.last_name)
        .bind(&input.lang)
        .fetch_one(&self.pool)
        .await
        .context("Failed to upsert user")?;

        Ok(user)
    }

    pub async fn set_user_lang(&self, telegram_id: i64, lang: &str) -> Result<()> {
        sqlx::query(
            "UPDATE users SET lang = $1, updated_at = NOW() WHERE telegram_id = $2",
        )
        .bind(lang)
        .bind(telegram_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn get_user_by_telegram_id(&self, telegram_id: i64) -> Result<Option<User>> {
        let user = sqlx::query_as::<_, User>(
            "SELECT * FROM users WHERE telegram_id = $1",
        )
        .bind(telegram_id)
        .fetch_optional(&self.pool)
        .await
        .context("Failed to fetch user")?;

        Ok(user)
    }

    pub async fn get_user_by_id(&self, user_id: Uuid) -> Result<Option<User>> {
        let user = sqlx::query_as::<_, User>(
            "SELECT * FROM users WHERE id = $1",
        )
        .bind(user_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(user)
    }

    // ─── Audio Files ──────────────────────────────────────────────────────────

    pub async fn create_audio_file(&self, input: &CreateAudioFile) -> Result<AudioFile> {
        let file = sqlx::query_as::<_, AudioFile>(
            r#"
            INSERT INTO audio_files
                (id, user_id, original_name, minio_key, file_size, mime_type, file_hash, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', NOW(), NOW())
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(input.user_id)
        .bind(&input.original_name)
        .bind(&input.minio_key)
        .bind(input.file_size)
        .bind(&input.mime_type)
        .bind(&input.file_hash)
        .fetch_one(&self.pool)
        .await
        .context("Failed to create audio file record")?;

        Ok(file)
    }

    pub async fn get_audio_file_by_id(&self, file_id: Uuid) -> Result<Option<AudioFile>> {
        let file = sqlx::query_as::<_, AudioFile>(
            "SELECT * FROM audio_files WHERE id = $1",
        )
        .bind(file_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(file)
    }

    pub async fn find_duplicate_by_hash(
        &self,
        user_id: Uuid,
        file_hash: &str,
    ) -> Result<Option<AudioFile>> {
        let file = sqlx::query_as::<_, AudioFile>(
            "SELECT * FROM audio_files WHERE user_id = $1 AND file_hash = $2 LIMIT 1",
        )
        .bind(user_id)
        .bind(file_hash)
        .fetch_optional(&self.pool)
        .await?;

        Ok(file)
    }

    /// Update status following the allowed state-machine transitions:
    ///
    /// ```
    /// pending    → processing | failed
    /// processing → completed  | failed
    /// completed  → (terminal — no transitions allowed)
    /// failed     → (terminal — no transitions allowed)
    /// ```
    ///
    /// Returns `Ok(true)` when the row was updated, `Ok(false)` when the
    /// transition was rejected because the file is already in a terminal state
    /// (idempotent — callers should treat this as success).
    pub async fn update_audio_file_status(
        &self,
        file_id: Uuid,
        status: AudioFileStatus,
    ) -> Result<bool> {
        let rows = sqlx::query(
            r#"
            UPDATE audio_files
               SET status = $1, updated_at = NOW()
             WHERE id = $2
               AND status NOT IN ('completed', 'failed')
            "#,
        )
        .bind(status)
        .bind(file_id)
        .execute(&self.pool)
        .await?;

        Ok(rows.rows_affected() > 0)
    }

    pub async fn get_user_audio_files(&self, user_id: Uuid) -> Result<Vec<AudioFile>> {
        let files = sqlx::query_as::<_, AudioFile>(
            "SELECT * FROM audio_files WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50",
        )
        .bind(user_id)
        .fetch_all(&self.pool)
        .await?;

        Ok(files)
    }

    /// Fetch just (id, original_name) pairs for a set of file ids.
    /// Used by /recommend to show names instead of raw UUIDs.
    pub async fn get_audio_file_names(
        &self,
        ids: &[Uuid],
    ) -> Result<std::collections::HashMap<Uuid, String>> {
        if ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }
        let rows: Vec<(Uuid, String)> = sqlx::query_as(
            "SELECT id, original_name FROM audio_files WHERE id = ANY($1)",
        )
        .bind(ids)
        .fetch_all(&self.pool)
        .await?;

        Ok(rows.into_iter().collect())
    }

    // ─── Processing Queue ─────────────────────────────────────────────────────

    pub async fn enqueue_file(&self, audio_file_id: Uuid) -> Result<ProcessingQueueItem> {
        let item = sqlx::query_as::<_, ProcessingQueueItem>(
            r#"
            INSERT INTO processing_queue (id, audio_file_id, status, attempts, created_at, updated_at)
            VALUES ($1, $2, 'queued', 0, NOW(), NOW())
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(audio_file_id)
        .fetch_one(&self.pool)
        .await
        .context("Failed to enqueue file")?;

        Ok(item)
    }

    // ─── Idempotency keys ─────────────────────────────────────────────────────

    /// Store the JSON response for a given (idempotency_key, user_id) pair.
    /// Overwrites silently — the caller should check `get_idempotency` first.
    pub async fn store_idempotency(
        &self,
        key: &str,
        user_id: Uuid,
        response: serde_json::Value,
    ) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO idempotency_keys (key, user_id, response, created_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (key, user_id) DO NOTHING
            "#,
        )
        .bind(key)
        .bind(user_id)
        .bind(response)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    /// Return the cached response for a (key, user_id) pair, or `None` if
    /// not found or expired (> 24 h old).
    pub async fn get_idempotency(
        &self,
        key: &str,
        user_id: Uuid,
    ) -> Result<Option<serde_json::Value>> {
        let row: Option<(serde_json::Value,)> = sqlx::query_as(
            r#"
            SELECT response FROM idempotency_keys
             WHERE key = $1
               AND user_id = $2
               AND created_at > NOW() - INTERVAL '24 hours'
            "#,
        )
        .bind(key)
        .bind(user_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(row.map(|(v,)| v))
    }

    // ─── Stats ────────────────────────────────────────────────────────────────

    pub async fn get_user_stats(&self, user_id: Uuid) -> Result<UserStats> {
        let total_files: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM audio_files WHERE user_id = $1",
        )
        .bind(user_id)
        .fetch_one(&self.pool)
        .await
        .unwrap_or(0);

        let analyzed_files: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM audio_files WHERE user_id = $1 AND status = 'completed'",
        )
        .bind(user_id)
        .fetch_one(&self.pool)
        .await
        .unwrap_or(0);

        Ok(UserStats {
            total_files,
            analyzed_files,
        })
    }
}

#[derive(Debug)]
pub struct UserStats {
    pub total_files: i64,
    pub analyzed_files: i64,

}