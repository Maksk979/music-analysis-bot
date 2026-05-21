mod config;
mod handlers;
mod models;
mod services;
mod utils;

use std::sync::Arc;

use axum::{
    routing::{get, post},
    Router,
};
use teloxide::{
    dispatching::{UpdateFilterExt, UpdateHandler},
    dptree,
    prelude::*,
    types::{CallbackQuery, Update},
};
use tower_http::{cors::CorsLayer, trace::TraceLayer};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use crate::config::Config;
use services::{analyzer::AnalyzerClient, database::DatabaseService, storage::StorageService};
use utils::jwt::JwtService;

/// Shared application state — cloned into every handler
#[derive(Clone)]
pub struct AppState {
    pub db: DatabaseService,
    pub storage: StorageService,
    pub jwt: Arc<JwtService>,
    pub config: Arc<Config>,
    pub analyzer: AnalyzerClient,
}

impl axum::extract::FromRef<AppState> for Arc<JwtService> {
    fn from_ref(state: &AppState) -> Self {
        state.jwt.clone()
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialise tracing
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "info,sqlx=warn".to_string()),
        ))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = Arc::new(Config::from_env()?);
    tracing::info!("Configuration loaded");

    // Database
    let db = DatabaseService::new(&config.database_url).await?;
    db.run_migrations().await?;

    // MinIO / S3 storage
    let storage = StorageService::new(
        &config.minio_endpoint,
        &config.minio_access_key,
        &config.minio_secret_key,
        &config.minio_bucket,
        &config.minio_region,
    )
    .await?;

    // JWT
    let jwt = Arc::new(JwtService::new(&config.jwt_secret, config.jwt_expiry_hours));

    let analyzer = AnalyzerClient::new(&config.analyzer_service_url);

    let state = AppState {
        db,
        storage,
        jwt,
        config: config.clone(),
        analyzer,
    };

    // Run Axum REST API and Telegram bot concurrently
    tokio::try_join!(
        run_api_server(state.clone()),
        run_telegram_bot(state),
    )?;

    Ok(())
}

// в”Ђв”Ђв”Ђ REST API server в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async fn run_api_server(state: AppState) -> anyhow::Result<()> {
    let router = Router::new()
        .route("/health", get(handlers::health::health_handler))
        .route("/api/upload", post(handlers::upload::upload_handler))
        .route("/api/notify", post(handlers::webhook_notify::notify_handler))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state.clone());

    let addr = format!(
        "{}:{}",
        state.config.server_host, state.config.server_port
    );
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    tracing::info!("REST API listening on {}", addr);

    axum::serve(listener, router).await?;
    Ok(())
}

// в”Ђв”Ђв”Ђ Telegram bot в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async fn run_telegram_bot(state: AppState) -> anyhow::Result<()> {
    let bot = Bot::new(&state.config.telegram_bot_token);

    tracing::info!("Starting Telegram bot (long-polling)");

    Dispatcher::builder(bot, build_handler())
        .dependencies(dptree::deps![state])
        .enable_ctrlc_handler()
        .build()
        .dispatch()
        .await;

    Ok(())
}

fn build_handler() -> UpdateHandler<Box<dyn std::error::Error + Send + Sync>> {
    use handlers::bot_commands::{handle_audio_message, handle_callback, handle_command, Command};

    let command_branch = Update::filter_message()
        .filter_command::<Command>()
        .endpoint(|bot: Bot, msg: Message, cmd: Command, state: AppState| async move {
            handle_command(bot, msg, cmd, state)
                .await
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)
        });

    let audio_branch = Update::filter_message()
        .branch(
            dptree::filter(|msg: Message| {
                msg.audio().is_some() || msg.document().is_some()
            })
            .endpoint(|bot: Bot, msg: Message, state: AppState| async move {
                handle_audio_message(bot, msg, state)
                    .await
                    .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)
            }),
        );

    // Handles inline keyboard button presses (language selection)
    let callback_branch = Update::filter_callback_query()
        .endpoint(|bot: Bot, q: CallbackQuery, state: AppState| async move {
            handle_callback(bot, q, state)
                .await
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)
        });

    dptree::entry()
        .branch(command_branch)
        .branch(audio_branch)
        .branch(callback_branch)
}
