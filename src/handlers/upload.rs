use axum::{
    extract::{Multipart, State},
    http::StatusCode,
    Json,
};
use serde::Serialize;
use uuid::Uuid;

use crate::{
    models::CreateAudioFile,
    utils::{
        file_validator::{compute_hash, mime_from_extension, validate_file},
        jwt::AuthenticatedUser,
    },
    AppState,
};

#[derive(Serialize)]
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
/// Accepts multipart/form-data with field `file`
/// Returns 200 with UploadResponse or 4xx/5xx with ErrorResponse
pub async fn upload_handler(
    State(state): State<AppState>,
    user: AuthenticatedUser,
    mut multipart: Multipart,
) -> Result<Json<UploadResponse>, (StatusCode, Json<ErrorResponse>)> {
    // Extract the file field from multipart
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

    // Validate file
    validate_file(
        &data,
        &content_type,
        &state.config.allowed_mime_types,
        state.config.max_file_size,
    )
    .map_err(|e| api_error(StatusCode::UNPROCESSABLE_ENTITY, &e.to_string()))?;

    let file_hash = compute_hash(&data);

    // Duplicate check
    if let Ok(Some(existing)) = state
        .db
        .find_duplicate_by_hash(user.user_id, &file_hash)
        .await
    {
        return Ok(Json(UploadResponse {
            file_id: existing.id,
            message: "Duplicate file detected — returning existing record".to_string(),
            status: existing.status.to_string(),
            duplicate: true,
        }));
    }

    // Build MinIO object key: users/{user_id}/{uuid}/{filename}
    let object_id = Uuid::new_v4();
    let minio_key = format!("users/{}/{}/{}", user.user_id, object_id, filename);

    // Upload to MinIO
    state
        .storage
        .upload_file(&minio_key, &data, &content_type)
        .await
        .map_err(|e| {
            tracing::error!("MinIO upload failed: {}", e);
            api_error(StatusCode::INTERNAL_SERVER_ERROR, "Storage upload failed")
        })?;

    // Persist record in DB
    let audio_file = state
        .db
        .create_audio_file(&CreateAudioFile {
            user_id: user.user_id,
            original_name: filename,
            minio_key,
            file_size: data.len() as i64,
            mime_type: content_type,
            file_hash,
        })
        .await
        .map_err(|e| {
            tracing::error!("DB insert failed: {}", e);
            api_error(StatusCode::INTERNAL_SERVER_ERROR, "Database error")
        })?;

    // Enqueue for analysis
    state
        .db
        .enqueue_file(audio_file.id)
        .await
        .map_err(|e| {
            tracing::warn!("Failed to enqueue file {}: {}", audio_file.id, e);
            api_error(StatusCode::INTERNAL_SERVER_ERROR, "Queue error")
        })?;

    tracing::info!(
        "File uploaded: {} by user {}",
        audio_file.id,
        user.user_id
    );

    Ok(Json(UploadResponse {
        file_id: audio_file.id,
        message: "File uploaded successfully and queued for analysis".to_string(),
        status: "pending".to_string(),
        duplicate: false,
    }))
}

fn api_error(status: StatusCode, message: &str) -> (StatusCode, Json<ErrorResponse>) {
    (
        status,
        Json(ErrorResponse {
            error: message.to_string(),
        }),
    )
}