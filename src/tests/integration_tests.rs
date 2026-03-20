/// Integration tests for the REST API.
/// Run with: cargo test --test integration_tests
/// Requires a running PostgreSQL + MinIO (use docker-compose up postgres minio minio-init).

use std::sync::Arc;

use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use tower::ServiceExt; // for `oneshot`

// These tests build a real AppState with test credentials loaded from .env.test
// They are intentionally skipped in CI unless TEST_INTEGRATION=1 is set.

#[cfg(test)]
mod health {
    use super::*;

    #[tokio::test]
    async fn health_returns_200() {
        let app = build_test_app().await;
        let response = app
            .oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }
}

#[cfg(test)]
mod upload {
    use axum::http::header;
    use bytes::Bytes;

    use super::*;

    #[tokio::test]
    async fn upload_rejects_missing_auth() {
        let app = build_test_app().await;

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/upload")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn upload_rejects_invalid_token() {
        let app = build_test_app().await;

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/upload")
                    .header(header::AUTHORIZATION, "Bearer not.a.real.token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn upload_rejects_wrong_mime_type() {
        if std::env::var("TEST_INTEGRATION").is_err() {
            return; // skip unless explicitly enabled
        }

        let app = build_test_app().await;
        let (token, _user_id) = create_test_user_token(&app).await;

        // Build a minimal multipart body with a .txt file
        let boundary = "testboundary12345";
        let body = format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.txt\"\r\nContent-Type: text/plain\r\n\r\nhello world\r\n--{boundary}--\r\n",
            boundary = boundary
        );

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/upload")
                    .header(header::AUTHORIZATION, format!("Bearer {}", token))
                    .header(
                        header::CONTENT_TYPE,
                        format!("multipart/form-data; boundary={}", boundary),
                    )
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async fn build_test_app() -> axum::Router {
    dotenv::from_filename(".env.test").ok();
    dotenv::dotenv().ok();

    use crate::track_analyzer_bot::{
        config::Config,
        handlers,
        services::{database::DatabaseService, storage::StorageService},
        utils::jwt::JwtService,
        AppState,
    };

    let config = Arc::new(Config::from_env().expect("Config"));
    let db = DatabaseService::new(&config.database_url).await.expect("DB");
    db.run_migrations().await.expect("Migrations");
    let storage = StorageService::new(
        &config.minio_endpoint,
        &config.minio_access_key,
        &config.minio_secret_key,
        &config.minio_bucket,
        &config.minio_region,
    )
    .await
    .expect("Storage");
    let jwt = Arc::new(JwtService::new(&config.jwt_secret, config.jwt_expiry_hours));

    let state = AppState { db, storage, jwt, config };

    axum::Router::new()
        .route("/health", axum::routing::get(handlers::health::health_handler))
        .route("/api/upload", axum::routing::post(handlers::upload::upload_handler))
        .with_state(state)
}

async fn create_test_user_token(_app: &axum::Router) -> (String, uuid::Uuid) {
    // In a real test: POST /start or call db.upsert_user directly
    // For now return a dummy pair; extend as needed
    (String::new(), uuid::Uuid::new_v4())
}
