/// Seeder — заполняет БД тестовыми данными через фабрики.
///
/// Запуск:
///   cargo run --bin seed                                   # дефолт: 10 юзеров, 5 файлов
///   cargo run --bin seed -- --users 50 --files-per-user 10
///   cargo run --bin seed -- --clean                        # очистить БД перед заполнением
///   cargo run --bin seed -- --users 5 --files-per-user 3 --clean

use std::env;

use fake::{
    faker::{
        internet::en::Username,
        name::en::{FirstName, LastName},
    },
    Fake,
};
use rand::{seq::SliceRandom, Rng};
use sqlx::{postgres::PgPoolOptions, PgPool};
use uuid::Uuid;

// ─── CLI аргументы ────────────────────────────────────────────────────────────

struct Args {
    users: usize,
    files_per_user: usize,
    clean: bool,
}

impl Args {
    fn parse() -> Self {
        let args: Vec<String> = env::args().collect();
        let mut users = 10usize;
        let mut files_per_user = 5usize;
        let mut clean = false;

        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--users" => {
                    i += 1;
                    users = args[i].parse().expect("--users must be a number");
                }
                "--files-per-user" => {
                    i += 1;
                    files_per_user = args[i].parse().expect("--files-per-user must be a number");
                }
                "--clean" => clean = true,
                _ => {}
            }
            i += 1;
        }

        Args { users, files_per_user, clean }
    }
}

// ─── UserFactory ──────────────────────────────────────────────────────────────

struct UserFactory;

impl UserFactory {
    async fn create(pool: &PgPool, telegram_id: i64) -> Uuid {
        let id: Uuid = Uuid::new_v4();
        let first_name: String = FirstName().fake();
        let last_name: String  = LastName().fake();
        let username: String   = Username().fake();
        let lang = if rand::random::<bool>() { "ru" } else { "en" };

        sqlx::query(
            r#"INSERT INTO users
               (id, telegram_id, username, first_name, last_name, lang, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
               ON CONFLICT (telegram_id) DO NOTHING"#,
        )
        .bind(id)
        .bind(telegram_id)
        .bind(&username)
        .bind(&first_name)
        .bind(&last_name)
        .bind(lang)
        .execute(pool)
        .await
        .expect("Failed to insert user");

        println!(
            "  👤 {} {} (@{}) [{}] tg_id={}",
            first_name, last_name, username, lang, telegram_id
        );
        id
    }

    async fn create_many(pool: &PgPool, count: usize) -> Vec<Uuid> {
        let mut ids = Vec::with_capacity(count);
        let base: i64 = 9_000_000_000;
        for i in 0..count {
            ids.push(Self::create(pool, base + i as i64).await);
        }
        ids
    }
}

// ─── AudioFileFactory ─────────────────────────────────────────────────────────

struct AudioFileFactory;

impl AudioFileFactory {
    async fn create(pool: &PgPool, user_id: Uuid) -> Uuid {
        let mut rng = rand::thread_rng();
        let id = Uuid::new_v4();

        let genres = ["Rock","Pop","Jazz","Classical","Hip-Hop","Electronic","Metal","R&B","Country","Folk","Reggae","Blues"];
        let genre = genres.choose(&mut rng).copied().unwrap();
        let artist: String = FirstName().fake();
        let ext = ["mp3", "wav", "ogg", "m4a"].choose(&mut rng).copied().unwrap();
        let filename   = format!("{} - {} Track {}.{}", artist, genre, rng.gen_range(1u8..=20), ext);
        let mime_type  = match ext { "mp3" => "audio/mpeg", "wav" => "audio/wav", "ogg" => "audio/ogg", _ => "audio/x-m4a" };
        let file_size: i64 = rng.gen_range(512_000..50_000_000);
        let minio_key  = format!("users/{}/{}/{}", user_id, id, filename);
        let file_hash  = format!("{:032x}", rng.gen::<u128>());
        let status = ["pending", "processing", "completed", "failed"]
            .choose_weighted(&mut rng, |s| match *s {
                "completed" => 60u32, "pending" => 20, "processing" => 10, _ => 10,
            })
            .copied()
            .unwrap();

        sqlx::query(
            r#"INSERT INTO audio_files
               (id, user_id, original_name, minio_key, file_size, mime_type,
                file_hash, status, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8::audio_file_status, NOW(), NOW())"#,
        )
        .bind(id).bind(user_id).bind(&filename).bind(&minio_key)
        .bind(file_size).bind(mime_type).bind(&file_hash).bind(status)
        .execute(pool).await.expect("Failed to insert audio_file");

        println!(
            "    🎵 {} | {:.1}MB | {}",
            filename, file_size as f64 / 1_000_000.0, status
        );

        if status == "completed" {
            AudioFeaturesFactory::create(pool, id).await;
        }
        if status == "pending" || status == "processing" {
            QueueFactory::create(pool, id, status).await;
        }

        id
    }

    async fn create_many(pool: &PgPool, user_id: Uuid, count: usize) -> Vec<Uuid> {
        let mut ids = Vec::with_capacity(count);
        for _ in 0..count {
            ids.push(Self::create(pool, user_id).await);
        }
        ids
    }
}

// ─── AudioFeaturesFactory ─────────────────────────────────────────────────────

struct AudioFeaturesFactory;

impl AudioFeaturesFactory {
    async fn create(pool: &PgPool, audio_file_id: Uuid) {
        let mut rng = rand::thread_rng();

        let tempo:            f64 = rng.gen_range(60.0..200.0);
        let energy:           f64 = rng.gen_range(0.0..1.0);
        let danceability:     f64 = rng.gen_range(0.0..1.0);
        let valence:          f64 = rng.gen_range(0.0..1.0);
        let acousticness:     f64 = rng.gen_range(0.0..1.0);
        let instrumentalness: f64 = rng.gen_range(0.0..1.0);
        let speechiness:      f64 = rng.gen_range(0.0..0.5);
        let loudness:         f64 = rng.gen_range(-60.0..-3.0);
        let key:              i32 = rng.gen_range(0..12);
        let mode:             i32 = rng.gen_range(0..2);

        sqlx::query(
            r#"INSERT INTO audio_features
               (id, audio_file_id, tempo, energy, danceability, valence,
                acousticness, instrumentalness, speechiness, loudness, key, mode, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW())
               ON CONFLICT (audio_file_id) DO NOTHING"#,
        )
        .bind(Uuid::new_v4()).bind(audio_file_id)
        .bind(tempo).bind(energy).bind(danceability).bind(valence)
        .bind(acousticness).bind(instrumentalness).bind(speechiness).bind(loudness)
        .bind(key).bind(mode)
        .execute(pool).await.expect("Failed to insert audio_features");

        println!(
            "      📊 tempo={:.0}bpm energy={:.2} dance={:.2} key={} {}",
            tempo, energy, danceability, key,
            if mode == 1 { "major" } else { "minor" }
        );
    }
}

// ─── QueueFactory ─────────────────────────────────────────────────────────────

struct QueueFactory;

impl QueueFactory {
    async fn create(pool: &PgPool, audio_file_id: Uuid, status: &str) {
        let mut rng = rand::thread_rng();
        let attempts: i32 = if status == "processing" { rng.gen_range(1..3) } else { 0 };
        let queue_status = if status == "processing" { "processing" } else { "queued" };

        sqlx::query(
            r#"INSERT INTO processing_queue
               (id, audio_file_id, status, attempts, created_at, updated_at)
               VALUES ($1, $2, $3::queue_status, $4, NOW(), NOW())"#,
        )
        .bind(Uuid::new_v4()).bind(audio_file_id).bind(queue_status).bind(attempts)
        .execute(pool).await.expect("Failed to insert queue item");
    }
}

// ─── RecommendationFactory ────────────────────────────────────────────────────

struct RecommendationFactory;

impl RecommendationFactory {
    async fn create_between(pool: &PgPool, file_ids: &[Uuid]) {
        if file_ids.len() < 2 { return; }

        let mut rng = rand::thread_rng();
        let mut count = 0u32;

        for i in 0..file_ids.len() {
            let max_recs = 3.min(file_ids.len() - 1);
            let rec_count = rng.gen_range(1..=max_recs);
            let mut used = vec![i];

            for _ in 0..rec_count {
                let candidates: Vec<usize> = (0..file_ids.len())
                    .filter(|j| !used.contains(j))
                    .collect();
                if candidates.is_empty() { break; }

                let j = *candidates.choose(&mut rng).unwrap();
                used.push(j);

                let similarity: f64 = rng.gen_range(0.5..1.0);

                sqlx::query(
                    r#"INSERT INTO recommendations
                       (id, source_file_id, recommended_file_id, similarity_score, created_at)
                       VALUES ($1,$2,$3,$4,NOW())
                       ON CONFLICT (source_file_id, recommended_file_id) DO NOTHING"#,
                )
                .bind(Uuid::new_v4()).bind(file_ids[i]).bind(file_ids[j]).bind(similarity)
                .execute(pool).await.expect("Failed to insert recommendation");

                count += 1;
            }
        }
        println!("  🔗 Created {} recommendations", count);
    }
}

// ─── Clean ────────────────────────────────────────────────────────────────────

async fn clean_db(pool: &PgPool) {
    println!("🧹 Cleaning database...");
    for table in &["recommendations","processing_queue","audio_features","audio_files","users"] {
        sqlx::query(&format!("DELETE FROM {}", table))
            .execute(pool).await
            .unwrap_or_else(|e| panic!("Failed to clean {}: {}", table, e));
        println!("  ✓ {}", table);
    }
    println!();
}

// ─── Stats ────────────────────────────────────────────────────────────────────

async fn print_stats(pool: &PgPool) {
    println!("\n📊 Database stats:");
    for (table, label) in &[
        ("users",            "👤 Users"),
        ("audio_files",      "🎵 Audio files"),
        ("audio_features",   "📊 Features"),
        ("processing_queue", "⏳ Queue"),
        ("recommendations",  "🔗 Recommendations"),
    ] {
        let n: i64 = sqlx::query_scalar(&format!("SELECT COUNT(*) FROM {}", table))
            .fetch_one(pool).await.unwrap_or(0);
        println!("  {}: {}", label, n);
    }

    println!("\n  Files by status:");
    if let Ok(rows) = sqlx::query_as::<_, (String, i64)>(
        "SELECT status::text, COUNT(*) FROM audio_files GROUP BY status ORDER BY status",
    ).fetch_all(pool).await {
        for (status, count) in rows {
            let icon = match status.as_str() {
                "completed" => "✅", "pending" => "⏳", "processing" => "🔄", _ => "❌",
            };
            println!("    {} {}: {}", icon, status, count);
        }
    }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    dotenv::dotenv().ok();
    let args = Args::parse();

    println!("🌱 Track Analyzer — Seeder");
    println!("   users:          {}", args.users);
    println!("   files per user: {}", args.files_per_user);
    println!("   clean first:    {}\n", args.clean);

    let database_url = env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let pool = PgPoolOptions::new().max_connections(5).connect(&database_url).await?;
    println!("✅ Connected\n");

    if args.clean { clean_db(&pool).await; }

    println!("👥 Creating {} users...", args.users);
    let user_ids = UserFactory::create_many(&pool, args.users).await;

    println!("\n🎵 Creating files ({} per user)...", args.files_per_user);
    let mut all_completed: Vec<Uuid> = Vec::new();

    for user_id in &user_ids {
        AudioFileFactory::create_many(&pool, *user_id, args.files_per_user).await;

        let completed: Vec<Uuid> = sqlx::query_scalar(
            "SELECT id FROM audio_files WHERE user_id = $1 AND status = 'completed'",
        )
        .bind(user_id)
        .fetch_all(&pool).await.unwrap_or_default();

        all_completed.extend(completed);
    }

    println!("\n🔗 Building recommendations ({} completed tracks)...", all_completed.len());
    RecommendationFactory::create_between(&pool, &all_completed).await;

    print_stats(&pool).await;
    println!("\n✅ Done!");
    Ok(())
}