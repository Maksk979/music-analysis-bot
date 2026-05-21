/// HTTP-клиент для микросервиса анализа аудио (Копылов).
///
/// После загрузки файла в MinIO и записи в БД этот клиент
/// отправляет файл на анализ: POST {ANALYZER_SERVICE_URL}/api/v1/analyze
/// Анализатор обрабатывает файл асинхронно и по завершении
/// уведомляет нас через POST /api/notify.

use anyhow::Result;
use reqwest::Client;
use uuid::Uuid;

#[derive(Clone)]
pub struct AnalyzerClient {
    client: Client,
    base_url: String,
}

impl AnalyzerClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            client: Client::builder()
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .expect("Failed to build HTTP client"),
            base_url: base_url.to_string(),
        }
    }

    /// Отправляет файл на анализ.
    /// `file_id` передаётся как form-поле, чтобы анализатор мог
    /// использовать его при отправке уведомления обратно.
    pub async fn submit_file(
        &self,
        file_id: Uuid,
        data: Vec<u8>,
        filename: String,
        mime_type: String,
    ) -> Result<()> {
        let url = format!("{}/api/v1/analyze", self.base_url);

        let file_part = reqwest::multipart::Part::bytes(data)
            .file_name(filename)
            .mime_str(&mime_type)?;

        let form = reqwest::multipart::Form::new()
            .part("file", file_part)
            .text("file_id", file_id.to_string());

        let resp = self
            .client
            .post(&url)
            .multipart(form)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Analyzer returned {}: {}", status, body);
        }

        tracing::info!("File {} submitted to analyzer", file_id);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn client_constructs_with_base_url() {
        let client = AnalyzerClient::new("http://localhost:8001");
        assert_eq!(client.base_url, "http://localhost:8001");
    }

    #[tokio::test]
    async fn submit_returns_error_when_endpoint_unreachable() {
        // Port 1 is reserved and never listens — request must fail.
        let client = AnalyzerClient::new("http://127.0.0.1:1");
        let result = client
            .submit_file(
                Uuid::new_v4(),
                vec![0u8; 10],
                "x.mp3".to_string(),
                "audio/mpeg".to_string(),
            )
            .await;
        assert!(result.is_err());
    }
}
