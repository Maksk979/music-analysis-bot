# Track Analyzer Bot

Telegram-бот для анализа аудиотреков и подбора рекомендаций похожей музыки.
Учебный проект по ПИУС (Мельников Л. А., Копылов М. А., Беляков А. К.).

## Архитектура

Распределённая система из трёх микросервисов, общая БД и хранилище:

```
┌─────────────┐        ┌──────────────┐       ┌──────────┐
│  Telegram   │◀──────▶│   Rust Bot   │──────▶│  MinIO   │
│    User     │        │  (teloxide)  │       │   (S3)   │
└─────────────┘        │   REST API   │       └──────────┘
                       │   (axum)     │
┌─────────────┐        └──────┬───────┘       ┌──────────┐
│ REST Client │──────▶        │     ◀────────▶│PostgreSQL│
└─────────────┘               │               └──────────┘
                              ▼
              ┌───────────────┴────────────────┐
              │                                │
       ┌──────▼──────┐                 ┌───────▼──────┐
       │  Analyzer   │                 │   Recs       │
       │  (Python)   │                 │   (Python)   │
       │  librosa    │                 │   FAISS      │
       └─────────────┘                 └──────────────┘
              │                                │
              └────────► Redis ◀───────────────┘
```

**Состав:**

| Сервис   | Технология              | Порт  | Ответственный | Папка       |
|----------|-------------------------|-------|---------------|-------------|
| bot      | Rust (teloxide, axum)   | 8080  | Мельников     | `./`        |
| analyzer | Python (FastAPI, librosa) | 8001 | Копылов       | `analyzer/` |
| recs     | Python (FastAPI, FAISS) | 8002  | Беляков       | `recs/`     |
| postgres | PostgreSQL 16           | 5432  | —             | контейнер   |
| minio    | MinIO (S3)              | 9000, 9001 | —        | контейнер   |
| redis    | Redis 7                 | 6379  | —             | контейнер   |

## Поток данных

1. Пользователь отправляет аудиофайл в Telegram **или** делает `POST /api/upload` с JWT.
2. **bot** валидирует файл (MIME + magic-bytes + размер), считает SHA-256, проверяет дубликаты, кладёт в MinIO, пишет в `audio_files` со статусом `pending`.
3. **bot** делает fire-and-forget `POST analyzer:8001/api/v1/analyze` с файлом и `file_id`.
4. **analyzer** в фоне через librosa извлекает 10 акустических признаков (темп, энергия, танцевальность и т.д.) и записывает их в `audio_features`.
5. **analyzer** уведомляет **bot** через `POST bot:8080/api/notify` с заголовком `X-Internal-Secret`. **bot** атомарно меняет статус файла на `completed`.
6. Пользователь шлёт `/recommend` → **bot** запрашивает `GET recs:8002/recommendations/{file_id}`.
7. **recs** вычисляет косинусное сходство (через FAISS-индекс) и возвращает топ-10 похожих треков.
8. **bot** разрешает UUID-ы в имена файлов и отправляет красивый список пользователю.

## Реализованные механизмы надёжности

| Механизм                     | Где                                       | Назначение                                                    |
|------------------------------|-------------------------------------------|---------------------------------------------------------------|
| **Idempotency Key**          | `src/handlers/upload.rs`                  | Повторный `POST /api/upload` с тем же ключом не дублирует файл |
| **Receiver-Side Protection** | `src/handlers/webhook_notify.rs`          | Проверка `X-Internal-Secret` + state-machine guard в SQL      |
| **State Machine**            | `audio_file_status` ENUM + атомарный UPDATE | Запрет обратных переходов из `completed/failed`              |
| **Deduplication (SHA-256)**  | `src/utils/file_validator.rs`             | Поиск дубликата по хешу контента до загрузки                  |
| **Unique Business Keys**     | `UNIQUE` constraints в схеме              | `users.telegram_id`, `audio_files.minio_key`, и т.д.          |
| **Redis-кеш**                | `recs/app/redis_cache.py`                 | TTL=5 мин на ответы `/recommendations`                        |
| **Fire-and-forget submission** | `tokio::spawn` в `upload.rs` / `bot_commands.rs` | Анализатор работает асинхронно, бот не блокируется    |
| **Magic-byte валидация**     | `is_mp3 / is_wav / is_ogg / is_m4a / is_flac` | Защита от подмены расширения вредоносным файлом         |

## Структура репозитория

```
.
├── src/                         # Rust-бот (Мельников)
│   ├── main.rs                  # Точка входа: запускает axum + teloxide параллельно
│   ├── config/mod.rs            # Чтение env
│   ├── handlers/
│   │   ├── bot_commands.rs      # /start /help /analyze /recommend /history /stats + загрузка аудио и ZIP
│   │   ├── upload.rs            # POST /api/upload (с Idempotency Key)
│   │   ├── webhook_notify.rs    # POST /api/notify (с защитой получателя)
│   │   └── health.rs            # GET /health
│   ├── services/
│   │   ├── database.rs          # CRUD + миграции inline
│   │   ├── storage.rs           # Клиент MinIO/S3
│   │   └── analyzer.rs          # HTTP-клиент к analyzer
│   ├── models/mod.rs            # Структуры данных + sqlx ENUM
│   ├── utils/
│   │   ├── file_validator.rs    # MIME + magic-bytes + SHA-256
│   │   ├── jwt.rs               # JWT для REST + axum extractor
│   │   └── zip_handlers.rs      # Распаковка ZIP-архивов
│   └── bin/seed.rs              # Утилита для наполнения БД тестовыми данными
├── analyzer/                    # Python-анализатор (Копылов)
│   ├── app/
│   │   ├── main.py              # FastAPI + Redis lifespan
│   │   ├── api/endpoints.py     # POST /api/v1/analyze, GET /status/{id}, GET /result/{id}
│   │   ├── services/            # task_manager (Redis), analysis_service (DB save + notify)
│   │   └── core/                # librosa: spectral / rhythm / harmonic feature extractors
│   ├── tests/test_high_level_metrics.py
│   └── Dockerfile
├── recs/                        # Python-рекомендации (Беляков)
│   ├── app/
│   │   ├── main.py              # FastAPI + /recommendations/{id}
│   │   ├── similarity.py        # cosine / euclidean / pearson
│   │   ├── model_manager.py     # FAISS-индекс
│   │   ├── normalization.py     # MinMax + handle_missing
│   │   ├── weighting.py         # Веса признаков
│   │   ├── redis_cache.py       # 5-минутный TTL на ответы
│   │   └── database.py          # asyncpg-модель AudioFeatures
│   ├── tests/test_similarity.py
│   └── Dockerfile
├── migrations/                  # SQL-миграции (запускаются inline из database.rs)
├── docker-compose.yml           # Полный стек
├── Dockerfile                   # Многостейджевая сборка Rust-бота
├── .githooks/pre-commit         # fmt + clippy + tests перед коммитом
├── rustfmt.toml                 # Конфиг форматтера
├── clippy.toml                  # Конфиг линтера
└── .env                         # Локальная конфигурация (НЕ коммитится)
```

## Быстрый старт

### Требования

- **Docker Desktop** (Windows / macOS / Linux) — поднимает все 6 контейнеров.
- (Для разработки Rust-бота вне Docker) Rust 1.75+, Cargo.
- (Для разработки Python-сервисов) Python 3.11+, pip.

### Запуск через Docker (рекомендуется)

```bash
git clone https://github.com/Maksk979/music-analysis-bot.git
cd music-analysis-bot
git checkout feature/melnikov

# Заполни .env по примеру ниже
docker compose up -d

# Логи всех сервисов
docker compose logs -f

# Остановка
docker compose down

# Полный сброс (включая данные!)
docker compose down -v
```

### Пример `.env`

```ini
# Telegram
TELEGRAM_BOT_TOKEN=<токен от @BotFather>

# PostgreSQL
DATABASE_URL=postgresql://postgres:password@localhost:5432/track_analyzer

# MinIO / S3
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=audio-files
MINIO_REGION=us-east-1

# JWT
JWT_SECRET=<любая длинная случайная строка>
JWT_EXPIRY_HOURS=24

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8080

# Соседние микросервисы
ANALYZER_SERVICE_URL=http://localhost:8001
RECOMMENDER_SERVICE_URL=http://localhost:8002

# Лимиты
MAX_FILE_SIZE=52428800
ALLOWED_MIME_TYPES=audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/x-m4a

# Общий секрет между микросервисами (для /api/notify)
INTERNAL_API_SECRET=internal-secret
```

### Проверка работоспособности

```bash
curl http://localhost:8080/health
# {"status":"ok","version":"0.1.0","services":{"database":"ok","storage":"ok"}}

curl http://localhost:8001/api/v1/health
curl http://localhost:8002/health
```

## REST API

### `POST /api/upload`

Загрузка аудиофайла. Поддерживается **идемпотентность** через заголовок `X-Idempotency-Key`.

```bash
curl -X POST http://localhost:8080/api/upload \
  -H "Authorization: Bearer <JWT>" \
  -H "X-Idempotency-Key: 0e4f1a2b-..." \
  -F "file=@track.mp3"
```

Повторный запрос с тем же `X-Idempotency-Key` вернёт идентичный ответ без повторной обработки (TTL 24 часа).

### `POST /api/notify`

Внутренний webhook от analyzer / recs. Требует заголовок `X-Internal-Secret`.

```bash
curl -X POST http://localhost:8080/api/notify \
  -H "Content-Type: application/json" \
  -H "X-Internal-Secret: internal-secret" \
  -d '{"file_id": "...", "status": "completed"}'
```

### `GET /health`

Возвращает `200 OK` если бот, БД и MinIO живы; иначе `503`.

## Команды бота

| Команда      | Назначение                                              |
|--------------|---------------------------------------------------------|
| `/start`     | Регистрация, выбор языка (RU/EN), выдача JWT-токена     |
| `/help`      | Справка                                                 |
| `/analyze`   | Подсказка отправить аудиофайл                           |
| `/recommend` | Топ-10 похожих треков на последний проанализированный   |
| `/history`   | Последние 10 загруженных треков и их статус             |
| `/stats`     | Сводная статистика по пользователю                      |

Просто отправь боту mp3 / wav / ogg / m4a / flac или ZIP-архив с ними — он сам подхватит.

## Разработка

### Rust-бот

```bash
# Сборка
cargo build

# Запуск тестов
cargo test

# Линтер
cargo clippy --all-targets -- -D warnings

# Форматирование
cargo fmt --all

# Запуск локально (требует поднятых postgres / minio / redis)
docker compose up -d postgres minio minio-init redis
cargo run --bin bot
```

### Python-сервисы

```bash
# Analyzer
cd analyzer
python -m venv .venv && . .venv/bin/activate  # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest

# Recs
cd ../recs
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest
```

### Git-хуки

Один раз после клонирования установи путь к хукам — пре-коммит хук будет запускать `cargo fmt`, `cargo clippy` и `cargo test` перед каждым коммитом:

```bash
git config core.hooksPath .githooks
```

(На Windows для PowerShell-варианта запускается `.githooks/pre-commit.ps1` вручную: `pwsh .githooks/pre-commit.ps1`.)

### Линтеры

| Сервис   | Команда                                       |
|----------|-----------------------------------------------|
| bot      | `cargo clippy --all-targets -- -D warnings`   |
| bot      | `cargo fmt --all -- --check`                  |
| analyzer | `cd analyzer && pytest`                       |
| recs     | `cd recs && pytest`                           |

## Тестирование

### Что покрыто unit-тестами (bot)

- `utils/file_validator.rs` — MIME-нормализация, magic-bytes для MP3/WAV/OGG/M4A/FLAC, SHA-256, отказ для пустых/больших/неверных файлов.
- `utils/jwt.rs` — генерация и валидация JWT, отказ на неправильном секрете, проверка истечения.
- `utils/zip_handlers.rs` — распаковка ZIP с фильтрацией только аудио, обработка невалидных архивов.
- `services/analyzer.rs` — конструктор клиента, обработка недоступного эндпоинта.
- `models/mod.rs` — round-trip `Lang`, `Display` для `AudioFileStatus`.

### Что покрыто unit-тестами (recs)

- `similarity.py` — косинус, евклид, корреляция Пирсона, обработка вырожденных случаев.
- `normalization.py` — масштабирование, заполнение пропущенных значений медианой / нулём.
- `weighting.py` — применение весов, обновление весов, отказ для неизвестных признаков.

### Что покрыто unit-тестами (analyzer)

- `core/analyzer.py::_compute_high_level_metrics` — energy / valence / danceability / loudness / speechiness в допустимых диапазонах.
- `models/schemas.py` — Pydantic-схемы (TaskStatus, HighLevelMetrics, AnalysisResponse, FileInfo).

### Интеграционное тестирование

Для проверки полного контура поднимите весь стек через `docker compose up -d` и:

```bash
# 1. Получить JWT через /start в Telegram
# 2. Загрузить файл через REST
curl -X POST http://localhost:8080/api/upload \
  -H "Authorization: Bearer <JWT>" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -F "file=@./samples/track.mp3"

# 3. Дождаться completed
curl -X GET http://localhost:8080/health

# 4. Получить рекомендации
curl http://localhost:8002/recommendations/<file_id>
```

## Соответствие техническому заданию

| Пункт ТЗ                                    | Статус |
|---------------------------------------------|--------|
| **Лаба 1**                                  |        |
| POST /api/upload → MinIO                    | ✅     |
| GET /health → 200                           | ✅     |
| Валидация типов файлов                      | ✅     |
| JWT-токены                                  | ✅     |
| Unit-тестирование                           | ✅     |
| Документация (этот README)                  | ✅     |
| **Лаба 2**                                  |        |
| 1.5 Модульная архитектура                   | ✅     |
| 1.6 Команды /start /help /analyze /recommend /history /stats | ✅ |
| 1.7 Приём + валидация + ZIP + webhook + дубли по хешу + magic-bytes + прогресс-бар + временное хранилище + очередь | ✅ |
| 1.8 Pool соединений, CRUD, миграции         | ✅     |
| **Лаба 3** (Копылов + Беляков)              |        |
| 3.2 Извлечение признаков (10 фич)           | ✅     |
| 3.3 MFCC + спектральный + ритмический + гармонический анализ | ✅ |
| 3.4 REST API анализатора                    | ✅     |
| 3.5 Нормализация                            | ✅     |
| 3.6 Косинус / евклид / Пирсон               | ✅     |
| 3.7 Взвешивание признаков                   | ✅     |
| 3.8 FAISS-индекс + кластеризация (KMeans)   | ✅     |
| 3.9 API рекомендаций (по ID, по фичам, batch) | ✅   |
| 3.10 Redis-кеш                              | ✅     |
| **Лаба 4**                                  |        |
| 4.1 Unit-тесты Rust + pytest для Python     | ✅     |
| 4.6 Документация                            | ✅     |
| 4.7 Dockerfile + docker-compose             | ✅     |

## Лицензия

Учебный проект, лицензия не определена.

## Авторы

- **Мельников Л. А.** — Rust-бот + REST API + REST-аутентификация (`feature/melnikov`)
- **Копылов М. А.** — Python-анализатор (`feature/kopylov` → `analyzer/`)
- **Беляков А. К.** — Python-рекомендации (`feature/belyakov` → `recs/`)
