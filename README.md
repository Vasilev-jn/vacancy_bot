# Vacancy Bot

Telegram bot that helps users find vacancies on HH.ru, save a profile, and browse cards with full vacancy text.

## Features
- Profile onboarding (/start) with role, work format, locations, salary, experience, skills.
- Vacancy cards with full text, work format, experience, salary, and skill match counters.
- Main menu with quick actions: Resume and Vacancies.
- Postgres storage for user profiles.

## Requirements
- Python 3.10+
- PostgreSQL (optional, but recommended for persistent profiles)

## Setup
1) Create a virtual environment (optional):

```bash
python -m venv .venv
.\.venv\Scripts\activate
```

2) Install dependencies:

```bash
pip install pytelegrambotapi python-dotenv requests psycopg2-binary
```

3) Configure environment:

Copy `.env.example` to `.env` and fill values.

```bash
copy .env.example .env
```

Example `.env`:

```
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
PG_DSN=postgresql://user:password@localhost:5432/vacancy_bot
VACANCY_CACHE_SIZE=15
PER_SOURCE_CACHE=15
VACANCY_CACHE_TTL=600
HH_PAGE_RANGE=4
MATCH_THRESHOLD=0.5
SKILLS_SAMPLE_RATIO=0.5
```

4) Run the bot:

```bash
python main.py
```

## Usage
- `/start` — onboarding or show saved profile.
- `📄 Резюме` — show profile.
- `👀 Вакансии` — show vacancy cards.

## Notes
- HH search is performed only by role. Skills are used for match counters in cards.
- Vacancy details are fetched on demand to show full text and compute skill matches.
- `.env` is ignored by git. Use `.env.example` as a template.

## License
MIT License. See `LICENSE`.
