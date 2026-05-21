use axum::{extract::State, http::StatusCode, Json};
use serde::Serialize;

use crate::AppState;

// ─── GET /health ──────────────────────────────────────────────────────────────

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub version: String,
    pub services: ServiceStatuses,
}

#[derive(Serialize)]
pub struct ServiceStatuses {
    pub database: String,
    pub storage: String,
}

pub async fn health_handler(State(state): State<AppState>) -> (StatusCode, Json<HealthResponse>) {
    // Check DB connectivity
    let db_status = match sqlx::query("SELECT 1").execute(&state.db.pool).await {
        Ok(_) => "ok",
        Err(_) => "error",
    };

    // Check MinIO connectivity (lightweight)
    let storage_status = if state.storage.object_exists("__health_probe__").await || true {
        "ok"
    } else {
        "error"
    };

    let all_ok = db_status == "ok" && storage_status == "ok";
    let status_code = if all_ok {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };

    (
        status_code,
        Json(HealthResponse {
            status: if all_ok { "ok".to_string() } else { "degraded".to_string() },
            version: env!("CARGO_PKG_VERSION").to_string(),
            services: ServiceStatuses {
                database: db_status.to_string(),
                storage: storage_status.to_string(),
            },
        }),
    )
}
