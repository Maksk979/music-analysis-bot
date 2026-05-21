/// Webhook-уведомления / статусные коллбэки от внутренних сервисов (п. 1.7 ТЗ).
///
/// POST /api/notify
/// ─────────────────
/// Вызывается анализатором (Копылов) или сервисом рекомендаций (Беляков) когда
/// статус файла изменился.
///
/// Защита на стороне получателя
/// ─────────────────────────────
/// 1. Проверка секрета `X-Internal-Secret` — только внутренние сервисы могут
///    вызывать этот эндпоинт.
/// 2. State machine guard — переход принимается только если он разрешён:
///    pending → processing | failed
///    processing → completed | failed
///    completed / failed → любой запрос отклоняется (возвращает 200 идемпотентно).
///    Это гарантирует что повторный вызов с тем же статусом не сломает данные.

use axum::{extract::State, http::{HeaderMap, StatusCode}, Json};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::{models::AudioFileStatus, AppState};

// ─── Request / Response ───────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct NotifyRequest {
    pub file_id: Uuid,
    pub status: String,
    pub details: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct NotifyResponse {
    pub accepted: bool,
    pub message: String,
}

// ─── Handler ──────────────────────────────────────────────────────────────────

pub async fn notify_handler(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<NotifyRequest>,
) -> Result<Json<NotifyResponse>, (StatusCode, Json<NotifyResponse>)> {
    // ── 1. Authenticate internal caller ───────────────────────────────────────
    let provided_secret = headers
        .get("X-Internal-Secret")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if provided_secret != state.config.internal_api_secret {
        return Err((
            StatusCode::UNAUTHORIZED,
            Json(NotifyResponse {
                accepted: false,
                message: "Invalid or missing X-Internal-Secret".to_string(),
            }),
        ));
    }

    // ── 2. Parse requested status ─────────────────────────────────────────────
    let new_status = match payload.status.as_str() {
        "completed"  => AudioFileStatus::Completed,
        "failed"     => AudioFileStatus::Failed,
        "processing" => AudioFileStatus::Processing,
        other => {
            return Err((
                StatusCode::BAD_REQUEST,
                Json(NotifyResponse {
                    accepted: false,
                    message: format!("Unknown status: '{}'", other),
                }),
            ));
        }
    };

    // ── 3. Apply state-machine guard ──────────────────────────────────────────
    // `update_audio_file_status` returns Ok(false) when the file is already
    // in a terminal state — we treat that as idempotent success.
    match state.db.update_audio_file_status(payload.file_id, new_status).await {
        Ok(true) => {
            tracing::info!(
                "Status updated: file={} → {}",
                payload.file_id,
                payload.status
            );
        }
        Ok(false) => {
            tracing::info!(
                "Ignored duplicate/illegal transition for file={} requested={}",
                payload.file_id,
                payload.status
            );
            return Ok(Json(NotifyResponse {
                accepted: false,
                message: "File already in terminal state — no update applied (idempotent)".to_string(),
            }));
        }
        Err(e) => {
            tracing::warn!("DB update failed for file {}: {}", payload.file_id, e);
        }
    }

    // ── 4. Forward to external webhook if configured ──────────────────────────
    let audio_file = state
        .db
        .get_audio_file_by_id(payload.file_id)
        .await
        .ok()
        .flatten();

    let webhook_url = audio_file.and_then(|_| state.config.webhook_notify_url.clone());

    match webhook_url {
        None => Ok(Json(NotifyResponse {
            accepted: true,
            message: "Status updated in DB (no external webhook configured)".to_string(),
        })),
        Some(url) => {
            let body = serde_json::json!({
                "file_id": payload.file_id,
                "status":  payload.status,
                "details": payload.details,
            });

            match reqwest::Client::new()
                .post(&url)
                .json(&body)
                .timeout(std::time::Duration::from_secs(5))
                .send()
                .await
            {
                Ok(resp) if resp.status().is_success() => {
                    tracing::info!("Webhook delivered for file {}", payload.file_id);
                    Ok(Json(NotifyResponse {
                        accepted: true,
                        message: format!("Status updated and webhook delivered to {}", url),
                    }))
                }
                Ok(resp) => {
                    tracing::warn!(
                        "Webhook for file {} returned HTTP {}",
                        payload.file_id,
                        resp.status()
                    );
                    Ok(Json(NotifyResponse {
                        accepted: true,
                        message: format!("Status updated; webhook returned {}", resp.status()),
                    }))
                }
                Err(e) => {
                    tracing::error!("Webhook delivery error for file {}: {}", payload.file_id, e);
                    Ok(Json(NotifyResponse {
                        accepted: true,
                        message: format!("Status updated; webhook delivery failed: {}", e),
                    }))
                }
            }
        }
    }
}
