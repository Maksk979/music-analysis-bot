use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq)]
pub enum Lang { En, Ru }

impl Lang {
    pub fn from_str(s: &str) -> Self {
        if s == "ru" { Lang::Ru } else { Lang::En }
    }
    pub fn as_str(&self) -> &'static str {
        match self { Lang::Ru => "ru", Lang::En => "en" }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct User {
    pub id: Uuid,
    pub telegram_id: i64,
    pub username: Option<String>,
    pub first_name: String,
    pub last_name: Option<String>,
    pub lang: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug)]
pub struct CreateUser {
    pub telegram_id: i64,
    pub username: Option<String>,
    pub first_name: String,
    pub last_name: Option<String>,
    pub lang: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct AudioFile {
    pub id: Uuid,
    pub user_id: Uuid,
    pub original_name: String,
    pub minio_key: String,
    pub file_size: i64,
    pub mime_type: String,
    pub file_hash: String,
    pub status: AudioFileStatus,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::Type, PartialEq)]
#[sqlx(type_name = "audio_file_status", rename_all = "snake_case")]
pub enum AudioFileStatus { Pending, Processing, Completed, Failed }

impl std::fmt::Display for AudioFileStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AudioFileStatus::Pending    => write!(f, "pending"),
            AudioFileStatus::Processing => write!(f, "processing"),
            AudioFileStatus::Completed  => write!(f, "completed"),
            AudioFileStatus::Failed     => write!(f, "failed"),
        }
    }
}

#[derive(Debug)]
pub struct CreateAudioFile {
    pub user_id: Uuid,
    pub original_name: String,
    pub minio_key: String,
    pub file_size: i64,
    pub mime_type: String,
    pub file_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct AudioFeatures {
    pub id: Uuid,
    pub audio_file_id: Uuid,
    pub tempo: Option<f64>,
    pub energy: Option<f64>,
    pub danceability: Option<f64>,
    pub valence: Option<f64>,
    pub acousticness: Option<f64>,
    pub instrumentalness: Option<f64>,
    pub speechiness: Option<f64>,
    pub loudness: Option<f64>,
    pub key: Option<i32>,
    pub mode: Option<i32>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Recommendation {
    pub id: Uuid,
    pub source_file_id: Uuid,
    pub recommended_file_id: Uuid,
    pub similarity_score: f64,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct ProcessingQueueItem {
    pub id: Uuid,
    pub audio_file_id: Uuid,
    pub status: QueueStatus,
    pub attempts: i32,
    pub error_message: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::Type)]
#[sqlx(type_name = "queue_status", rename_all = "snake_case")]
pub enum QueueStatus { Queued, Processing, Done, Failed }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lang_round_trip() {
        assert_eq!(Lang::from_str("ru"), Lang::Ru);
        assert_eq!(Lang::from_str("en"), Lang::En);
        assert_eq!(Lang::from_str("unknown"), Lang::En);
        assert_eq!(Lang::Ru.as_str(), "ru");
        assert_eq!(Lang::En.as_str(), "en");
    }

    #[test]
    fn audio_file_status_display() {
        assert_eq!(AudioFileStatus::Pending.to_string(), "pending");
        assert_eq!(AudioFileStatus::Processing.to_string(), "processing");
        assert_eq!(AudioFileStatus::Completed.to_string(), "completed");
        assert_eq!(AudioFileStatus::Failed.to_string(), "failed");
    }
}