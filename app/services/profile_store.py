import logging

from app import state
from app.config import Settings
from app.db import list_profile_ids_db, load_profile_db, save_profile_db

logger = logging.getLogger(__name__)


def get_profile_for_user(tg_id: int, settings: Settings) -> dict | None:
    profile = state.profiles.get(tg_id)
    if profile:
        return profile
    profile = load_profile_db(settings, tg_id)
    if profile:
        state.profiles[tg_id] = profile
    return profile


def persist_profile(tg_id: int, profile: dict, settings: Settings) -> None:
    state.profiles[tg_id] = profile
    save_profile_db(settings, tg_id, profile)
    state.vacancy_cache.pop(tg_id, None)
    state.seen_vacancies.pop(tg_id, None)


def list_tracked_user_ids(settings: Settings) -> list[int]:
    ids = {int(uid) for uid in state.profiles.keys()}
    try:
        ids.update(list_profile_ids_db(settings))
    except Exception as exc:  # pragma: no cover - defensive runtime path
        logger.warning("Failed to load profile ids for auto-push: %s", exc)
    return sorted(ids)
