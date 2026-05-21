use axum::{
    extract::{Multipart, State},
    http::{HeaderMap, StatusCode},
    Json,
};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::{
    models::CreateAudioFile,
    utils::{
        file_validator::{compute_hash, mime_from_extension, validate_file},
        jwt::AuthenticatedUser,
    },
    AppState,
};

#[derive(Serialize, Deserialize, Clone)]
pub struct UploadResponse {
    pub file_id: Uuid,
    pub message: String,
    pub status: String,
    pub duplicate: bool,
}

#[derive(Serialize)]
pub struct ErrorResponse {
    pub error: String,
}

/// POST /api/upload
///
/// Accepts multipart/form-data with field `file`.
///
/// Idempotency key
/// ───────────────
/// Clients MAY send the header `X-Idempotency-Key: <uuid>`.
/// If the same key is seen again within 24 h for the same user, the cached
/// response is returned without re-processing (HTTP 200, `duplicate: false`
/// preserved from the first response).
pub async fn upload_handler(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    headers: HeaderMap,
    mut multipart: Multipart,
) -> Result<Json<UploadResponse>, (StatusCode, Json<ErrorResponse>)> {
    // ── Idempotency key check ─────────────────────────────────────────────────
    let idempotency_key = headers
        .get("X-Idempotency-Key")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());

    if let Some(ref key) = idempotency_key {
        if let Ok(Some(cached)) = state.db.get_idempotency(key, user.user_id).await {
            tracing::info!(
                "Idempotency hit for key={} user={}",
                key,
                user.user_id
            );
            let resp: UploadResponse = serde_json::from_value(cached)
                .map_err(|_| api_error(StatusCode::INTERNAL_SERVER_ERROR, "Cached response corrupt"))?;
            return Ok(Json(resp));
        }
    }

    // ── Read multipart file ───────────────────────────────────────────────────
    let field = multipart
        .next_field()
        .await
        .map_err(|e| api_error(StatusCode::BAD_REQUEST, &e.to_string()))?
        .ok_or_else(|| api_error(StatusCode::BAD_REQUEST, "No file field in request"))?;

    let filename = field
        .file_name()
        .unwrap_or("unknown")
        .to_string();

    let content_type = field
        .content_type()
        .map(|ct| ct.to_string())
        .unwrap_or_else(|| mime_from_extension(&filename).to_string());

    let data = field
        .bytes()
        .await
        .map_err(|e| api_error(StatusCode::BAD_REQUEST, &format!("Failed to read file: {}", e)))?
        .to_vec();

    // ── Validate ──────────────────────────────────────────────────────────────
    validate_file(
        &data,
        &content_type,
        &state.config.allowed_mime_types,
        state.config.max_file_size,
    )
    .map_err(|e| api_error(StatusCode::UNPROCESSABLE_ENTITY, &e.to_string()))?;

    let file_hash = compute_hash(&data);

    // ── Duplicate check ───────────────────────────────────────────────────────
    if let Ok(Some(existing)) = state
        .db
        .find_duplicate_by_hash(user.user_id, &file_hash)
        .await
    {
        let resp = UploadResponse {
            file_id: existing.id,
            message: "Duplicate file detected — returning existing record".to_string(),
            status: existing.status.to_string(),
            duplicate: true,
        };
        maybe_store_idempotency(&state, &idempotency_key, user.user_id, &resp).await;
        return Ok(Json(resp));
    }

    // ── Upload to MinIO ───────────────────────────────────────────────────────
    let object_id = Uuid::new_v4();
    let minio_key = format!("users/{}/{}/{}", user.user_id, object_id, filename);

    state
        .storage
        .upload_file(&minio_key, &data, &content_type)
        .await
        .map_err(|e| {
            tracing::error!("MinIO upload failed: {}", e);
            api_error(StatusCode::INTERNAL_SERVER_ERROR, "Storage upload failed")
        })?;

    // ── Persist in DB ─────────────────────────────────────────────────────────
    let audio_file = state
        .db
        .create_audio_file(&CreateAudioFile {
            user_id: user.user_id,
            original_name: filename.clone(),
            minio_key,
            file_size: data.len() as i64,
            mime_type: content_type.clone(),
            file_hash,
        })
        .await
        .map_err(|e| {
            tracing::error!("DB insert failed: {}", e);
            api_error(StatusCode::INTERNAL_SERVER_ERROR, "Database error")
        })?;

    // ── Enqueue ───────────────────────────────────────────────────────────────
    state
        .db
        .enqueue_file(audio_file.id)
        .await
        .map_err(|e| {
            tracing::warn!("Failed to enqueue file {}: {}", audio_file.id, e);
            api_error(StatusCode::INTERNAL_SERVER_ERROR, "Queue error")
        })?;

    tracing::info!("File uploaded: {} by user {}", audio_file.id, user.user_id);

    // ── Submit to analyzer (fire-and-forget background task) ─────────────────
    {
        let analyzer = state.analyzer.clone();
        let file_id = audio_file.id;
        let bytes = data;
        let fname = filename.clone();
        let mime = content_type.clone();
        tokio::spawn(async move {
            if let Err(e) = analyzer.submit_file(file_id, bytes, fname, mime).await {
                tracing::warn!("Analyzer submission failed for {}: {}", file_id, e);
            }
        });
    }

    // ── Build + cache response ────────────────────────────────────────────────
    let resp = UploadResponse {
        file_id: audio_file.id,
        message: "File uploaded successfully and queued for analysis".to_string(),
        status: "pending".to_string(),
        duplicate: false,
    };

    maybe_store_idempotency(&state, &idempotency_key, user.user_id, &resp).await;

    Ok(Json(resp))
}

// ── Helpers ───────────────────────────────────────────────────────────────────

fn api_error(status: StatusCode, message: &str) -> (StatusCode, Json<ErrorResponse>) {
    (status, Json(ErrorResponse { error: message.to_string() }))
}

/// Persist the response under the idempotency key if one was provided.
/// Failures are non-fatal — we just log them.
async fn maybe_store_idempotency(
    state: &AppState,
    key: &Option<String>,
    user_id: Uuid,
    resp: &UploadResponse,
) {
    if let Some(k) = key {
        let val = match serde_json::to_value(resp) {
            Ok(v) => v,
            Err(e) => {
                tracing::warn!("Failed to serialize idempotency response: {}", e);
                return;
            }
        };
        if let Err(e) = state.db.store_idempotency(k, user_id, val).await {
            tracing::warn!("Failed to store idempotency key {}: {}", k, e);
        }
    }
}
