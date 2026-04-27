import logging
import threading
import time

import telebot
from telebot import apihelper

from app.config import Settings, get_settings
from app.db import init_db
from app.handlers import register_handlers
from app.keyboards import build_vacancy_kb
from app.services.profile_store import get_profile_for_user, list_tracked_user_ids
from app.services.vacancies import build_vacancy_text, fetch_vacancies, filter_new_vacancies, mark_vacancy_seen

logger = logging.getLogger(__name__)


def configure_telegram_proxy(settings: Settings) -> None:
    if settings.telegram_proxy_url:
        apihelper.proxy = {
            "http": settings.telegram_proxy_url,
            "https": settings.telegram_proxy_url,
        }
        logger.info("Telegram proxy enabled")
    else:
        apihelper.proxy = None


def create_bot(settings: Settings) -> telebot.TeleBot:
    settings.validate()
    configure_telegram_proxy(settings)
    return telebot.TeleBot(settings.bot_token, parse_mode="HTML")


def send_auto_push_batch(bot: telebot.TeleBot, settings: Settings, tg_id: int) -> int:
    profile = get_profile_for_user(tg_id, settings)
    if not profile:
        return 0
    vacancies = fetch_vacancies(profile, settings, tg_id=tg_id)
    vacancies = filter_new_vacancies(tg_id, vacancies)
    if not vacancies:
        return 0
    sent = 0
    for vacancy in vacancies:
        if sent >= settings.auto_push_max_per_cycle:
            break
        mark_vacancy_seen(tg_id, vacancy, settings)
        try:
            bot.send_message(tg_id, build_vacancy_text(vacancy), reply_markup=build_vacancy_kb(vacancy))
        except Exception as exc:  # pragma: no cover - runtime network path
            logger.warning("Auto-push send failed for %s: %s", tg_id, exc)
            break
        sent += 1
    return sent


def auto_push_loop(bot: telebot.TeleBot, settings: Settings) -> None:
    if not settings.auto_push_enabled:
        logger.info("Auto-push disabled")
        return
    logger.info("Auto-push started, interval=%ss", settings.auto_push_interval_seconds)
    while True:
        try:
            for tg_id in list_tracked_user_ids(settings):
                send_auto_push_batch(bot, settings, tg_id)
        except Exception as exc:  # pragma: no cover - runtime network path
            logger.warning("Auto-push loop error: %s", exc)
        time.sleep(settings.auto_push_interval_seconds)


def start_auto_push_thread(bot: telebot.TeleBot, settings: Settings):
    if not settings.auto_push_enabled:
        return None
    worker = threading.Thread(target=auto_push_loop, args=(bot, settings), name="auto-push-loop", daemon=True)
    worker.start()
    return worker


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    init_db(settings)
    bot = create_bot(settings)
    register_handlers(bot, settings)
    start_auto_push_thread(bot, settings)
    logger.info("Bot started")
    bot.infinity_polling(skip_pending=True)
