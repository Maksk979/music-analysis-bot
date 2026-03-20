use anyhow::Result;
use std::env;

#[derive(Debug, Clone)]
pub struct Config {
    pub telegram_bot_token: String,
    pub database_url: String,
    pub minio_endpoint: String,
    pub minio_access_key: String,
    pub minio_secret_key: String,
    pub minio_bucket: String,
    pub minio_region: String,
    pub jwt_secret: String,
    pub jwt_expiry_hours: u64,
    pub server_host: String,
    pub server_port: u16,
    pub analyzer_service_url: String,
    pub recommender_service_url: String,
    pub max_file_size: usize,
    pub allowed_mime_types: Vec<String>,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        dotenv::dotenv().ok();
        Ok(Config {
            telegram_bot_token: env::var("TELEGRAM_BOT_TOKEN").expect("TELEGRAM_BOT_TOKEN must be set"),
            database_url: env::var("DATABASE_URL").expect("DATABASE_URL must be set"),
            minio_endpoint: env::var("MINIO_ENDPOINT").unwrap_or_else(|_| "http://localhost:9000".to_string()),
            minio_access_key: env::var("MINIO_ACCESS_KEY").unwrap_or_else(|_| "minioadmin".to_string()),
            minio_secret_key: env::var("MINIO_SECRET_KEY").unwrap_or_else(|_| "minioadmin".to_string()),
            minio_bucket: env::var("MINIO_BUCKET").unwrap_or_else(|_| "audio-files".to_string()),
            minio_region: env::var("MINIO_REGION").unwrap_or_else(|_| "us-east-1".to_string()),
            jwt_secret: env::var("JWT_SECRET").expect("JWT_SECRET must be set"),
            jwt_expiry_hours: env::var("JWT_EXPIRY_HOURS").unwrap_or_else(|_| "24".to_string()).parse().unwrap_or(24),
            server_host: env::var("SERVER_HOST").unwrap_or_else(|_| "0.0.0.0".to_string()),
            server_port: env::var("SERVER_PORT").unwrap_or_else(|_| "8080".to_string()).parse().unwrap_or(8080),
            analyzer_service_url: env::var("ANALYZER_SERVICE_URL").unwrap_or_else(|_| "http://localhost:8001".to_string()),
            recommender_service_url: env::var("RECOMMENDER_SERVICE_URL").unwrap_or_else(|_| "http://localhost:8002".to_string()),
            max_file_size: env::var("MAX_FILE_SIZE").unwrap_or_else(|_| "52428800".to_string()).parse().unwrap_or(52428800),
            allowed_mime_types: env::var("ALLOWED_MIME_TYPES")
                .unwrap_or_else(|_| "audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/x-m4a".to_string())
                .split(',').map(|s| s.trim().to_string()).collect(),
        })
    }
}