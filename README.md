# vacancy_bot

Telegram bot that collects a user profile, fetches relevant vacancies from HH.ru, ranks them by profile match, and stores the profile in PostgreSQL when persistence is enabled.

## What the bot does

- Onboards the user through Telegram chat and stores the desired role, work format, locations, budget, experience, skills, stop words, and blacklisted companies.
- Fetches matching HH.ru vacancies and shows them as Telegram cards with links and matching metadata.
- Filters results by budget, stop words, company blacklist, and skill match ratio.
- Supports automatic push delivery for new matching vacancies.

## External APIs and data sources

- HH.ru API client for vacancy search, normalization, and detail enrichment
- Telegram Bot API via `pyTelegramBotAPI`

## Profile storage

- PostgreSQL persistence is enabled when `PG_DSN` is configured.
- If PostgreSQL is not configured, the bot still works with in-memory profile storage for the current process.

## Matching logic

- The bot builds a search query from the desired role or the first non-empty skill.
- Skills are normalized, deduplicated, and sampled deterministically per vacancy.
- A vacancy passes when it satisfies the minimum budget filter, does not hit stop words or blacklisted companies, and reaches the configured match threshold.

## Architecture

- `app/bot.py` - bot bootstrap, polling, and auto-push thread
- `app/config.py` - environment loading and project settings
- `app/db.py` - PostgreSQL persistence helpers
- `app/handlers.py` - Telegram commands, callbacks, onboarding, and menu flow
- `app/keyboards.py` - reply and inline keyboard builders
- `app/state.py` - in-memory runtime state
- `app/services/` - profile logic, vacancy orchestration, and matching
- `app/clients/` - external source clients and parsers
- `tests/` - focused unit tests for matching, parsing, and config loading

## Data flow

1. User starts onboarding in Telegram and fills the profile step by step.
2. The profile is cached in memory and optionally persisted to PostgreSQL.
3. Vacancy sources are queried using the derived search query and source-specific clients.
4. Matching and filtering rules produce the shortlist shown to the user.
5. Seen vacancies are tracked to reduce duplicates in manual and auto-push delivery.

## How to run

```bash
git clone https://github.com/Vasilev-jn/vacancy_bot.git
cd vacancy_bot
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python main.py
```

## Environment variables

- `BOT_TOKEN` - Telegram bot token
- `TELEGRAM_PROXY_URL` - optional HTTP/SOCKS proxy for Telegram API only, for example `socks5h://127.0.0.1:1080`
- `PG_DSN` - PostgreSQL DSN for profile persistence
- `HH_BASE_URL`, `HH_USER_AGENT` - HH.ru client configuration. HH vacancy requests use `User-Agent`; a token is not required.
- `REQUEST_TIMEOUT`, `FETCH_ATTEMPTS` - HTTP behavior
- `VACANCY_CACHE_SIZE`, `PER_SOURCE_CACHE`, `VACANCY_CACHE_TTL`, `MAX_SEEN_PER_USER` - caching behavior
- `MATCH_THRESHOLD`, `SKILLS_SAMPLE_RATIO`, `HH_PAGE_RANGE` - search and matching behavior
- `AUTO_PUSH_ENABLED`, `AUTO_PUSH_INTERVAL_SECONDS`, `AUTO_PUSH_MAX_PER_CYCLE` - auto-push behavior

## Tests

```bash
pytest
```

Current test coverage includes:

- skill normalization and matching logic
- vacancy source HTML parsing
- environment/config loading

## Limitations

- Source schemas can change without notice, especially for HTML-based parsers.
- PostgreSQL persistence stores only the user profile, not full vacancy history.
- Matching is heuristic and keyword-based, so it can miss context or synonyms.

## Possible improvements

- split Telegram handlers into smaller handler modules
- add persistent storage for seen vacancies and delivery history
- add structured logging and request tracing
- add more focused tests around source integration and onboarding flow

## License

MIT. See `LICENSE`.
