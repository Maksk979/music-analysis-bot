use anyhow::{Context, Result};
use s3::creds::Credentials;
use s3::{Bucket, Region};

#[derive(Clone)]
pub struct StorageService {
    bucket: Box<Bucket>,
}

impl StorageService {
    pub async fn new(
        endpoint: &str,
        access_key: &str,
        secret_key: &str,
        bucket_name: &str,
        region: &str,
    ) -> Result<Self> {
        let credentials = Credentials::new(
            Some(access_key),
            Some(secret_key),
            None,
            None,
            None,
        )?;

        let region = Region::Custom {
            region: region.to_string(),
            endpoint: endpoint.to_string(),
        };

        let bucket = Bucket::new(bucket_name, region, credentials)
            .context("Failed to create S3 bucket client")?
            .with_path_style(); // MinIO requires path-style

        // Ensure bucket exists
        let service = Self { bucket };
        service.ensure_bucket_exists(bucket_name).await?;

        Ok(service)
    }

    async fn ensure_bucket_exists(&self, bucket_name: &str) -> Result<()> {
        match self.bucket.head_object("/").await {
            Ok(_) => Ok(()),
            Err(_) => {
                // Bucket might not exist, attempt to create via PutBucketPolicy is not
                // available in this crate — typically you create the bucket via MinIO
                // console or mc CLI. Log a warning and continue.
                tracing::warn!(
                    "Bucket '{}' may not exist. Create it via MinIO console or mc CLI.",
                    bucket_name
                );
                Ok(())
            }
        }
    }

    /// Upload bytes to MinIO and return the object key
    pub async fn upload_file(
        &self,
        key: &str,
        data: &[u8],
        content_type: &str,
    ) -> Result<String> {
        self.bucket
            .put_object_with_content_type(key, data, content_type)
            .await
            .with_context(|| format!("Failed to upload file to MinIO: {}", key))?;

        tracing::info!("Uploaded file to MinIO: {}", key);
        Ok(key.to_string())
    }

    /// Download bytes from MinIO
    pub async fn download_file(&self, key: &str) -> Result<Vec<u8>> {
        let response = self
            .bucket
            .get_object(key)
            .await
            .with_context(|| format!("Failed to download file from MinIO: {}", key))?;

        Ok(response.to_vec())
    }

    /// Delete a file from MinIO
    pub async fn delete_file(&self, key: &str) -> Result<()> {
        self.bucket
            .delete_object(key)
            .await
            .with_context(|| format!("Failed to delete file from MinIO: {}", key))?;

        tracing::info!("Deleted file from MinIO: {}", key);
        Ok(())
    }

    /// Generate a presigned URL (valid for `expiry_secs` seconds)
    pub async fn presigned_url(&self, key: &str, expiry_secs: u32) -> Result<String> {
        let url = self
            .bucket
            .presign_get(key, expiry_secs, None)
            .await
            .with_context(|| format!("Failed to generate presigned URL for: {}", key))?;

        Ok(url)
    }

    /// Check if an object exists
    pub async fn object_exists(&self, key: &str) -> bool {
        self.bucket.head_object(key).await.is_ok()
    }
}