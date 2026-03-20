use anyhow::Result;
use chrono::{Duration, Utc};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, TokenData, Validation};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Claims {
    pub sub: String,       // user UUID
    pub telegram_id: i64,
    pub exp: usize,        // expiry timestamp
    pub iat: usize,        // issued-at timestamp
}

pub struct JwtService {
    secret: String,
    expiry_hours: u64,
}

impl JwtService {
    pub fn new(secret: &str, expiry_hours: u64) -> Self {
        Self {
            secret: secret.to_string(),
            expiry_hours,
        }
    }

    pub fn generate_token(&self, user_id: Uuid, telegram_id: i64) -> Result<String> {
        let now = Utc::now();
        let expiry = now + Duration::hours(self.expiry_hours as i64);

        let claims = Claims {
            sub: user_id.to_string(),
            telegram_id,
            exp: expiry.timestamp() as usize,
            iat: now.timestamp() as usize,
        };

        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(self.secret.as_bytes()),
        )?;

        Ok(token)
    }

    pub fn verify_token(&self, token: &str) -> Result<TokenData<Claims>> {
        let token_data = decode::<Claims>(
            token,
            &DecodingKey::from_secret(self.secret.as_bytes()),
            &Validation::default(),
        )?;
        Ok(token_data)
    }

    pub fn extract_user_id(&self, token: &str) -> Result<Uuid> {
        let token_data = self.verify_token(token)?;
        let user_id = Uuid::parse_str(&token_data.claims.sub)?;
        Ok(user_id)
    }
}

/// Axum extractor — reads Bearer token from Authorization header
use axum::{
    async_trait,
    extract::FromRequestParts,
    http::{request::Parts, StatusCode},
};
use std::sync::Arc;

pub struct AuthenticatedUser {
    pub user_id: Uuid,
    pub telegram_id: i64,
}

#[async_trait]
impl<S> FromRequestParts<S> for AuthenticatedUser
where
    S: Send + Sync,
    Arc<JwtService>: axum::extract::FromRef<S>,
{
    type Rejection = (StatusCode, &'static str);

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        use axum::extract::FromRef;

        let jwt_service = Arc::<JwtService>::from_ref(state);

        let auth_header = parts
            .headers
            .get("Authorization")
            .and_then(|v| v.to_str().ok())
            .ok_or((StatusCode::UNAUTHORIZED, "Missing Authorization header"))?;

        let token = auth_header
            .strip_prefix("Bearer ")
            .ok_or((StatusCode::UNAUTHORIZED, "Invalid Authorization format"))?;

        let token_data = jwt_service
            .verify_token(token)
            .map_err(|_| (StatusCode::UNAUTHORIZED, "Invalid or expired token"))?;

        let user_id = Uuid::parse_str(&token_data.claims.sub)
            .map_err(|_| (StatusCode::UNAUTHORIZED, "Invalid user ID in token"))?;

        Ok(AuthenticatedUser {
            user_id,
            telegram_id: token_data.claims.telegram_id,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_and_verify_token() {
        let service = JwtService::new("test_secret_key_long_enough", 24);
        let user_id = Uuid::new_v4();
        let telegram_id = 123456789i64;

        let token = service.generate_token(user_id, telegram_id).unwrap();
        let token_data = service.verify_token(&token).unwrap();

        assert_eq!(token_data.claims.sub, user_id.to_string());
        assert_eq!(token_data.claims.telegram_id, telegram_id);
    }

    #[test]
    fn test_invalid_token_rejected() {
        let service = JwtService::new("test_secret_key_long_enough", 24);
        let result = service.verify_token("invalid.token.here");
        assert!(result.is_err());
    }

    #[test]
    fn test_wrong_secret_rejected() {
        let service1 = JwtService::new("secret_one_long_enough_xxx", 24);
        let service2 = JwtService::new("secret_two_long_enough_yyy", 24);

        let user_id = Uuid::new_v4();
        let token = service1.generate_token(user_id, 42).unwrap();
        let result = service2.verify_token(&token);
        assert!(result.is_err());
    }
}
