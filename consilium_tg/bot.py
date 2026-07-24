from __future__ import annotations

import logging

from telegram.ext import Application

from consilium_tg import handlers
from consilium_tg.access import AccessStore
from consilium_tg.config import load_settings
from consilium_tg.store import BotStore

_log = logging.getLogger(__name__)


def _build_service():
    try:
        from consilium_chat.council_service import CouncilService

        return CouncilService.build()
    except Exception:  # noqa: BLE001 - a missing proxy/key must not block app creation
        return None


async def _on_error(update, context) -> None:  # pragma: no cover - PTB error hook
    _log.error("handler error", exc_info=context.error)


def build_application(*, settings=None, service=None, store=None, access=None):
    settings = settings or load_settings()
    store = store or BotStore(settings.db_path, default_sensitivity=settings.default_sensitivity)
    access = access or AccessStore(settings.access_path, owner_id=settings.owner_id)
    if service is None:
        service = _build_service()
    app = Application.builder().token(settings.bot_token).concurrent_updates(True).build()
    app.bot_data.update(
        {"settings": settings, "store": store, "service": service, "access": access}
    )
    handlers.register(app)
    app.add_error_handler(_on_error)
    return app


def run(app=None) -> None:  # pragma: no cover - starts the polling loop
    (app or build_application()).run_polling()
