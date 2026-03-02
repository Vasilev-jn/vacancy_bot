try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - handled at runtime
    psycopg2 = None

from app.config import Settings


def postgres_enabled(settings: Settings) -> bool:
    return bool(settings.pg_dsn and psycopg2)


def init_db(settings: Settings) -> None:
    if not postgres_enabled(settings):
        return

    with psycopg2.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    tg_id BIGINT PRIMARY KEY,
                    profile JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )


def save_profile_db(settings: Settings, tg_id: int, profile: dict) -> bool:
    if not postgres_enabled(settings):
        return False

    with psycopg2.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO profiles (tg_id, profile, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (tg_id)
                DO UPDATE SET profile = EXCLUDED.profile, updated_at = NOW();
                """,
                (tg_id, psycopg2.extras.Json(profile)),
            )
    return True


def load_profile_db(settings: Settings, tg_id: int) -> dict | None:
    if not postgres_enabled(settings):
        return None

    with psycopg2.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT profile FROM profiles WHERE tg_id = %s;", (tg_id,))
            row = cur.fetchone()
            if not row:
                return None
            return row[0]


def list_profile_ids_db(settings: Settings) -> list[int]:
    if not postgres_enabled(settings):
        return []

    with psycopg2.connect(settings.pg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tg_id FROM profiles;")
            rows = cur.fetchall()
    return [int(row[0]) for row in rows]
