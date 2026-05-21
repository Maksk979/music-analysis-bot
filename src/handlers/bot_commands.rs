use teloxide::{
    prelude::*,
    types::{InlineKeyboardButton, InlineKeyboardMarkup, Message},
    utils::command::BotCommands,
};
use uuid::Uuid;

use crate::{
    models::CreateUser,
    utils::file_validator::{compute_hash, mime_from_extension, validate_file},
    utils::zip_handlers::extract_audio_from_zip,
    AppState,
};

// ─── Language ─────────────────────────────────────────────────────────────────

#[derive(Clone, PartialEq)]
pub enum Lang { Ru, En }

impl Lang {
    pub fn from_str(s: &str) -> Self {
        if s == "ru" { Lang::Ru } else { Lang::En }
    }
    pub fn as_str(&self) -> &'static str {
        match self { Lang::Ru => "ru", Lang::En => "en" }
    }
}

// ─── All user-facing strings (plain text only, NO Markdown) ───────────────────

fn txt_choose_lang() -> &'static str {
    "🌍 Choose language / Выберите язык:"
}

fn txt_welcome(lang: &Lang, name: &str, token: &str) -> String {
    match lang {
        Lang::Ru => format!(
            "👋 Привет, {}!\n\n\
             🎵 Я умею анализировать аудиофайлы и советовать похожую музыку.\n\n\
             📤 Отправь мне MP3, WAV, OGG или M4A файл.\n\n\
             🔑 Твой API токен:\n{}\n\n\
             Используй /help для списка команд.",
            name, token
        ),
        Lang::En => format!(
            "👋 Welcome, {}!\n\n\
             🎵 I can analyze your audio files and suggest similar music.\n\n\
             📤 Send me an MP3, WAV, OGG, or M4A file to get started.\n\n\
             🔑 Your API token:\n{}\n\n\
             Use /help for a list of commands.",
            name, token
        ),
    }
}

fn txt_help(lang: &Lang) -> &'static str {
    match lang {
        Lang::Ru =>
            "Track Analyzer Bot — Команды:\n\n\
             /start — Регистрация и получение токена\n\
             /analyze — Анализ аудиофайла\n\
             /recommend — Рекомендации по последнему треку\n\
             /history — Последние 10 треков\n\
             /stats — Статистика\n\n\
             Форматы: MP3, WAV, OGG, M4A\n\
             Макс. размер: 50 МБ\n\n\
             Просто отправь файл — я определю его сам!",
        Lang::En =>
            "Track Analyzer Bot — Commands:\n\n\
             /start — Register and get your token\n\
             /analyze — Analyze an audio file\n\
             /recommend — Recommendations for your last track\n\
             /history — Your last 10 tracks\n\
             /stats — Usage statistics\n\n\
             Formats: MP3, WAV, OGG, M4A\n\
             Max size: 50 MB\n\n\
             Just send a file — I will detect it automatically!",
    }
}

fn txt_not_registered(lang: &Lang) -> &'static str {
    match lang {
        Lang::Ru => "Сначала используй /start для регистрации.",
        Lang::En => "Use /start to register first.",
    }
}

fn txt_no_tracks(lang: &Lang) -> &'static str {
    match lang {
        Lang::Ru => "Треков нет. Отправь мне аудиофайл!",
        Lang::En => "No tracks yet. Send me an audio file!",
    }
}

fn txt_history_header(lang: &Lang) -> &'static str {
    match lang {
        Lang::Ru => "Последние треки:\n",
        Lang::En => "Your last tracks:\n",
    }
}

fn txt_downloading(lang: &Lang) -> &'static str {
    match lang {
        Lang::Ru => "Скачиваю файл...",
        Lang::En => "Downloading your file...",
    }
}

fn txt_uploading(lang: &Lang) -> &'static str {
    match lang {
        Lang::Ru => "Загружаю в хранилище...",
        Lang::En => "Uploading to storage...",
    }
}

fn txt_saving(lang: &Lang) -> &'static str {
    match lang {
        Lang::Ru => "Сохраняю в базу данных...",
        Lang::En => "Saving to database...",
    }
}

fn txt_upload_ok(lang: &Lang, name: &str, kb: f64, id: &str) -> String {
    match lang {
        Lang::Ru => format!(
            "Файл загружен!\n\nИмя: {}\nРазмер: {:.0} КБ\nID: {}\n\nТрек в очереди на анализ. Проверь /history.",
            name, kb, id
        ),
        Lang::En => format!(
            "File uploaded!\n\nName: {}\nSize: {:.0} KB\nID: {}\n\nTrack queued for analysis. Check /history.",
            name, kb, id
        ),
    }
}

// ─── Commands ─────────────────────────────────────────────────────────────────

#[derive(BotCommands, Clone)]
#[command(rename_rule = "lowercase", description = "Track Analyzer Bot:")]
pub enum Command {
    #[command(description = "Start / Начать")]
    Start,
    #[command(description = "Help / Помощь")]
    Help,
    #[command(description = "Analyze / Анализ")]
    Analyze,
    #[command(description = "Recommendations / Рекомендации")]
    Recommend,
    #[command(description = "History / История")]
    History,
    #[command(description = "Statistics / Статистика")]
    Stats,
}

pub async fn handle_command(
    bot: Bot,
    msg: Message,
    cmd: Command,
    state: AppState,
) -> ResponseResult<()> {
    match cmd {
        Command::Start    => cmd_start(bot, msg, state).await,
        Command::Help     => cmd_help(bot, msg, state).await,
        Command::Analyze  => cmd_analyze_prompt(bot, msg, state).await,
        Command::Recommend => cmd_recommend(bot, msg, state).await,
        Command::History  => cmd_history(bot, msg, state).await,
        Command::Stats    => cmd_stats(bot, msg, state).await,
    }
}

// ─── Language selection callback ──────────────────────────────────────────────

pub async fn handle_callback(
    bot: Bot,
    q: CallbackQuery,
    state: AppState,
) -> ResponseResult<()> {
    let data = match q.data.as_deref() {
        Some(d) if d.starts_with("lang:") => d.to_string(),
        _ => { bot.answer_callback_query(q.id).await?; return Ok(()); }
    };

    let lang_code = data.trim_start_matches("lang:").to_string();
    let tg_id = q.from.id.0 as i64;

    state.db.set_user_lang(tg_id, &lang_code).await.ok();

    if let Ok(Some(user)) = state.db.get_user_by_telegram_id(tg_id).await {
        let lang = Lang::from_str(&lang_code);
        let token = state.jwt.generate_token(user.id, user.telegram_id).unwrap_or_default();
        let welcome = txt_welcome(&lang, &user.first_name, &token);

        if let Some(msg) = q.message {
            bot.edit_message_text(msg.chat.id, msg.id, welcome).await?;
        }
    }

    bot.answer_callback_query(q.id).await?;
    Ok(())
}

// ─── /start ───────────────────────────────────────────────────────────────────

async fn cmd_start(bot: Bot, msg: Message, state: AppState) -> ResponseResult<()> {
    let from = match msg.from() {
        Some(f) => f,
        None => { bot.send_message(msg.chat.id, "Cannot identify user.").await?; return Ok(()); }
    };

    state.db.upsert_user(&CreateUser {
        telegram_id: from.id.0 as i64,
        username:    from.username.clone(),
        first_name:  from.first_name.clone(),
        last_name:   from.last_name.clone(),
        lang:        "en".to_string(),
    }).await.ok();

    let keyboard = InlineKeyboardMarkup::new(vec![vec![
        InlineKeyboardButton::callback("🇷🇺 Русский", "lang:ru"),
        InlineKeyboardButton::callback("🇬🇧 English", "lang:en"),
    ]]);

    bot.send_message(msg.chat.id, txt_choose_lang())
        .reply_markup(keyboard)
        .await?;

    Ok(())
}

// ─── /help ────────────────────────────────────────────────────────────────────

async fn cmd_help(bot: Bot, msg: Message, state: AppState) -> ResponseResult<()> {
    let lang = user_lang(&state, &msg).await;
    bot.send_message(msg.chat.id, txt_help(&lang)).await?;
    Ok(())
}

// ─── /analyze ─────────────────────────────────────────────────────────────────

async fn cmd_analyze_prompt(bot: Bot, msg: Message, state: AppState) -> ResponseResult<()> {
    let lang = user_lang(&state, &msg).await;
    let text = match lang {
        Lang::Ru => "Отправь аудиофайл (MP3, WAV, OGG, M4A) и я его проанализирую!",
        Lang::En => "Send me an audio file (MP3, WAV, OGG, M4A) and I will analyze it!",
    };
    bot.send_message(msg.chat.id, text).await?;
    Ok(())
}

// ─── Handle incoming audio / document ────────────────────────────────────────

pub async fn handle_audio_message(
    bot: Bot,
    msg: Message,
    state: AppState,
) -> ResponseResult<()> {
    let from = match msg.from() { Some(f) => f, None => return Ok(()) };
    let lang = user_lang(&state, &msg).await;

    let (file_id, filename, mime_hint) = if let Some(audio) = msg.audio() {
        (
            audio.file.id.clone(),
            audio.file_name.clone().unwrap_or_else(|| "track.mp3".to_string()),
            audio.mime_type.as_ref().map(|m| m.to_string()),
        )
    } else if let Some(doc) = msg.document() {
        (
            doc.file.id.clone(),
            doc.file_name.clone().unwrap_or_else(|| "file".to_string()),
            doc.mime_type.as_ref().map(|m| m.to_string()),
        )
    } else {
        return Ok(());
    };

    let progress_msg = bot.send_message(msg.chat.id, txt_downloading(&lang)).await?;

    let file_info = bot.get_file(&file_id).await?;
    let file_url = format!(
        "https://api.telegram.org/file/bot{}/{}",
        state.config.telegram_bot_token, file_info.path
    );

    let bytes = match reqwest::get(&file_url).await {
        Ok(r) => match r.bytes().await {
            Ok(b) => b.to_vec(),
            Err(_) => {
                bot.edit_message_text(msg.chat.id, progress_msg.id,
                    if lang == Lang::Ru { "Ошибка чтения файла." } else { "Failed to read file." }).await?;
                return Ok(());
            }
        },
        Err(_) => {
            bot.edit_message_text(msg.chat.id, progress_msg.id,
                if lang == Lang::Ru { "Ошибка загрузки." } else { "Download error." }).await?;
            return Ok(());
        }
    };

    let content_type = mime_hint.unwrap_or_else(|| mime_from_extension(&filename).to_string());

    // ── ZIP-архив: извлекаем все аудиофайлы и обрабатываем каждый ─────────────
    let is_zip = content_type == "application/zip"
        || content_type == "application/x-zip-compressed"
        || filename.to_lowercase().ends_with(".zip");
 
    if is_zip {
        return handle_zip_message(bot, msg.chat.id, progress_msg.id, &from, &lang, bytes, &state).await;
    }
 

    if let Err(e) = validate_file(&bytes, &content_type, &state.config.allowed_mime_types, state.config.max_file_size) {
        bot.edit_message_text(msg.chat.id, progress_msg.id, e.to_string()).await?;
        return Ok(());
    }

    bot.edit_message_text(msg.chat.id, progress_msg.id, txt_uploading(&lang)).await?;

    let user = match state.db.upsert_user(&CreateUser {
        telegram_id: from.id.0 as i64,
        username:    from.username.clone(),
        first_name:  from.first_name.clone(),
        last_name:   from.last_name.clone(),
        lang:        lang.as_str().to_string(),
    }).await {
        Ok(u) => u,
        Err(_) => {
            bot.edit_message_text(msg.chat.id, progress_msg.id, "Internal error.").await?;
            return Ok(());
        }
    };

    let file_hash = compute_hash(&bytes);

    if let Ok(Some(existing)) = state.db.find_duplicate_by_hash(user.id, &file_hash).await {
        let text = match lang {
            Lang::Ru => format!("Этот файл уже загружен!\nID: {}\nСтатус: {}", existing.id, existing.status),
            Lang::En => format!("Duplicate file!\nID: {}\nStatus: {}", existing.id, existing.status),
        };
        bot.edit_message_text(msg.chat.id, progress_msg.id, text).await?;
        return Ok(());
    }

    let minio_key = format!("users/{}/{}/{}", user.id, Uuid::new_v4(), filename);

    if let Err(_) = state.storage.upload_file(&minio_key, &bytes, &content_type).await {
        bot.edit_message_text(msg.chat.id, progress_msg.id,
            if lang == Lang::Ru { "Ошибка хранилища." } else { "Storage error." }).await?;
        return Ok(());
    }

    bot.edit_message_text(msg.chat.id, progress_msg.id, txt_saving(&lang)).await?;

    let audio_file = match state.db.create_audio_file(&crate::models::CreateAudioFile {
        user_id:       user.id,
        original_name: filename,
        minio_key,
        file_size:     bytes.len() as i64,
        mime_type:     content_type,
        file_hash,
    }).await {
        Ok(f) => f,
        Err(_) => {
            bot.edit_message_text(msg.chat.id, progress_msg.id, "Database error.").await?;
            return Ok(());
        }
    };

    let _ = state.db.enqueue_file(audio_file.id).await;

    // Submit to analyzer (fire-and-forget)
    {
        let analyzer = state.analyzer.clone();
        let fid = audio_file.id;
        let b = bytes.clone();
        let fn_ = audio_file.original_name.clone();
        let mt = audio_file.mime_type.clone();
        tokio::spawn(async move {
            if let Err(e) = analyzer.submit_file(fid, b, fn_, mt).await {
                tracing::warn!("Analyzer submission failed for {}: {}", fid, e);
            }
        });
    }

    let success = txt_upload_ok(
        &lang,
        &audio_file.original_name,
        audio_file.file_size as f64 / 1024.0,
        &audio_file.id.to_string(),
    );
    bot.edit_message_text(msg.chat.id, progress_msg.id, success).await?;

    Ok(())
}

// ─── ZIP batch upload (п. 1.7 ТЗ) ────────────────────────────────────────────
 
async fn handle_zip_message(
    bot: Bot,
    chat_id: teloxide::types::ChatId,
    progress_id: teloxide::types::MessageId,
    from: &teloxide::types::User,
    lang: &Lang,
    zip_bytes: Vec<u8>,
    state: &AppState,
) -> ResponseResult<()> {
    let extracted = match extract_audio_from_zip(&zip_bytes) {
        Ok(files) => files,
        Err(e) => {
            let text = match lang {
                Lang::Ru => format!("Не удалось распаковать архив: {}", e),
                Lang::En => format!("Failed to unpack archive: {}", e),
            };
            bot.edit_message_text(chat_id, progress_id, text).await?;
            return Ok(());
        }
    };
 
    let total = extracted.len();
    let header = match lang {
        Lang::Ru => format!("Найдено {} аудиофайл(ов) в архиве. Загружаю...", total),
        Lang::En => format!("Found {} audio file(s) in archive. Uploading...", total),
    };
    bot.edit_message_text(chat_id, progress_id, header).await?;
 
    let user = match state.db.upsert_user(&CreateUser {
        telegram_id: from.id.0 as i64,
        username:    from.username.clone(),
        first_name:  from.first_name.clone(),
        last_name:   from.last_name.clone(),
        lang:        lang.as_str().to_string(),
    }).await {
        Ok(u) => u,
        Err(_) => {
            bot.edit_message_text(chat_id, progress_id, "Internal error.").await?;
            return Ok(());
        }
    };
 
    let mut saved = 0usize;
    let mut skipped = 0usize;
    let mut errors = 0usize;
 
    for (idx, file) in extracted.into_iter().enumerate() {
        // Прогресс-бар
        let bar_done = (idx + 1) * 10 / total;
        let bar = format!(
            "[{}{}] {}/{}",
            "█".repeat(bar_done),
            "░".repeat(10 - bar_done),
            idx + 1,
            total
        );
        let progress_text = match lang {
            Lang::Ru => format!("Обрабатываю: {}\n{}", file.name, bar),
            Lang::En => format!("Processing: {}\n{}", file.name, bar),
        };
        bot.edit_message_text(chat_id, progress_id, progress_text).await.ok();
 
        if let Err(_) = validate_file(
            &file.data,
            &file.mime_type,
            &state.config.allowed_mime_types,
            state.config.max_file_size,
        ) {
            errors += 1;
            continue;
        }
 
        let file_hash = compute_hash(&file.data);
        if let Ok(Some(_)) = state.db.find_duplicate_by_hash(user.id, &file_hash).await {
            skipped += 1;
            continue;
        }
 
        let minio_key = format!("users/{}/{}/{}", user.id, Uuid::new_v4(), file.name);
 
        if state.storage.upload_file(&minio_key, &file.data, &file.mime_type).await.is_err() {
            errors += 1;
            continue;
        }
 
        let audio_file = match state.db.create_audio_file(&crate::models::CreateAudioFile {
            user_id:       user.id,
            original_name: file.name,
            minio_key,
            file_size:     file.data.len() as i64,
            mime_type:     file.mime_type,
            file_hash,
        }).await {
            Ok(f) => f,
            Err(_) => { errors += 1; continue; }
        };
 
        let _ = state.db.enqueue_file(audio_file.id).await;

        // Submit to analyzer (fire-and-forget)
        {
            let analyzer = state.analyzer.clone();
            let fid = audio_file.id;
            let b = file.data.clone();
            let fn_ = audio_file.original_name.clone();
            let mt = audio_file.mime_type.clone();
            tokio::spawn(async move {
                if let Err(e) = analyzer.submit_file(fid, b, fn_, mt).await {
                    tracing::warn!("Analyzer submission failed for {}: {}", fid, e);
                }
            });
        }

        saved += 1;
    }
 
    let summary = match lang {
        Lang::Ru => format!(
            "Архив обработан!\n\nЗагружено: {}\nПропущено (дубли): {}\nОшибки: {}\n\nПроверь /history.",
            saved, skipped, errors
        ),
        Lang::En => format!(
            "Archive processed!\n\nUploaded: {}\nSkipped (duplicates): {}\nErrors: {}\n\nCheck /history.",
            saved, skipped, errors
        ),
    };
    bot.edit_message_text(chat_id, progress_id, summary).await?;
 
    Ok(())
}
 

// ─── /history ─────────────────────────────────────────────────────────────────

async fn cmd_history(bot: Bot, msg: Message, state: AppState) -> ResponseResult<()> {
    let from = match msg.from() { Some(f) => f, None => return Ok(()) };
    let lang = user_lang(&state, &msg).await;

    let user = match state.db.get_user_by_telegram_id(from.id.0 as i64).await {
        Ok(Some(u)) => u,
        _ => { bot.send_message(msg.chat.id, txt_not_registered(&lang)).await?; return Ok(()); }
    };

    let files = state.db.get_user_audio_files(user.id).await.unwrap_or_default();

    if files.is_empty() {
        bot.send_message(msg.chat.id, txt_no_tracks(&lang)).await?;
        return Ok(());
    }

    let mut lines = vec![txt_history_header(&lang).to_string()];
    for (i, f) in files.iter().take(10).enumerate() {
        lines.push(format!(
            "{}. {} | {} | {:.0} KB",
            i + 1, f.original_name, f.status, f.file_size as f64 / 1024.0
        ));
    }

    bot.send_message(msg.chat.id, lines.join("\n")).await?;
    Ok(())
}

// ─── /recommend ───────────────────────────────────────────────────────────────

async fn cmd_recommend(bot: Bot, msg: Message, state: AppState) -> ResponseResult<()> {
    let from = match msg.from() { Some(f) => f, None => return Ok(()) };
    let lang = user_lang(&state, &msg).await;

    let user = match state.db.get_user_by_telegram_id(from.id.0 as i64).await {
        Ok(Some(u)) => u,
        _ => { bot.send_message(msg.chat.id, txt_not_registered(&lang)).await?; return Ok(()); }
    };

    let files = state.db.get_user_audio_files(user.id).await.unwrap_or_default();
    let latest = files.into_iter().find(|f| f.status == crate::models::AudioFileStatus::Completed);

    let file = match latest {
        Some(f) => f,
        None => {
            let t = match lang {
                Lang::Ru => "Нет проанализированных треков. Загрузи файл и дождись анализа.",
                Lang::En => "No analyzed tracks yet. Upload a file and wait for analysis to complete.",
            };
            bot.send_message(msg.chat.id, t).await?;
            return Ok(());
        }
    };

    let url = format!("{}/recommendations/{}", state.config.recommender_service_url, file.id);

    #[derive(serde::Deserialize)]
    struct RecItem {
        file_id: String,
        #[allow(dead_code)]
        similarity_score: f64,
    }

    let recs: Vec<RecItem> = match reqwest::get(&url).await {
        Ok(r) if r.status().is_success() => r.json().await.unwrap_or_default(),
        _ => {
            let t = match lang {
                Lang::Ru => "Сервис рекомендаций недоступен. Попробуй позже.",
                Lang::En => "Recommender service unavailable. Try again later.",
            };
            bot.send_message(msg.chat.id, t).await?;
            return Ok(());
        }
    };

    if recs.is_empty() {
        let t = match lang {
            Lang::Ru => "Похожих треков пока нет — загрузи ещё несколько файлов.",
            Lang::En => "No similar tracks yet — upload a few more files.",
        };
        bot.send_message(msg.chat.id, t).await?;
        return Ok(());
    }

    let ids: Vec<Uuid> = recs.iter()
        .filter_map(|r| Uuid::parse_str(&r.file_id).ok())
        .collect();
    let names = state.db.get_audio_file_names(&ids).await.unwrap_or_default();

    let header = match lang {
        Lang::Ru => format!("🎵 Похожие на «{}»:\n", file.original_name),
        Lang::En => format!("🎵 Similar to \"{}\":\n", file.original_name),
    };

    let mut lines = vec![header];
    for (i, r) in recs.iter().enumerate() {
        let name = Uuid::parse_str(&r.file_id)
            .ok()
            .and_then(|u| names.get(&u).cloned())
            .unwrap_or_else(|| r.file_id.clone());
        lines.push(format!("{}. {}", i + 1, name));
    }

    bot.send_message(msg.chat.id, lines.join("\n")).await?;
    Ok(())
}

// ─── /stats ───────────────────────────────────────────────────────────────────

async fn cmd_stats(bot: Bot, msg: Message, state: AppState) -> ResponseResult<()> {
    let from = match msg.from() { Some(f) => f, None => return Ok(()) };
    let lang = user_lang(&state, &msg).await;

    let user = match state.db.get_user_by_telegram_id(from.id.0 as i64).await {
        Ok(Some(u)) => u,
        _ => { bot.send_message(msg.chat.id, txt_not_registered(&lang)).await?; return Ok(()); }
    };

    let stats = state.db.get_user_stats(user.id).await.unwrap_or_else(|_|
        crate::services::database::UserStats { total_files: 0, analyzed_files: 0 }
    );

    let text = match lang {
        Lang::Ru => format!(
            "Статистика\n\nЗагружено: {}\nПроанализировано: {}\nОжидают: {}",
            stats.total_files, stats.analyzed_files, stats.total_files - stats.analyzed_files
        ),
        Lang::En => format!(
            "Statistics\n\nTotal uploads: {}\nAnalyzed: {}\nPending: {}",
            stats.total_files, stats.analyzed_files, stats.total_files - stats.analyzed_files
        ),
    };

    bot.send_message(msg.chat.id, text).await?;
    Ok(())
}

// ─── Helper ───────────────────────────────────────────────────────────────────

async fn user_lang(state: &AppState, msg: &Message) -> Lang {
    if let Some(from) = msg.from() {
        if let Ok(Some(user)) = state.db.get_user_by_telegram_id(from.id.0 as i64).await {
            return Lang::from_str(&user.lang);
        }
    }
    Lang::En
}