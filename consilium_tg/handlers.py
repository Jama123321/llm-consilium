from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from consilium_chat.context import build_prompt
from consilium_tg import render
from council.errors import AllMembersFailed, NoEligibleMember, PrivacyRefusal

_SERVICE_ERRORS = (NoEligibleMember, AllMembersFailed, PrivacyRefusal)
_MODES = ["", "vote", "judge", "debate", "peer-rank"]
_SIZES = [None, 3, 4, 5]


def kb(layout) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=data) for (text, data) in row] for row in layout]
    )


def _deps(context):
    d = context.bot_data
    return d["store"], d["access"], d["service"], d["settings"]


async def _ensure_allowed(update, context) -> bool:
    _store, access, _service, _settings = _deps(context)
    user = update.effective_user
    if access.is_allowed(user.id):
        return True
    owner = access.owner_id()
    if owner is None:
        await update.message.reply_text("This bot is locked — the owner is not configured.")
        return False
    access.request_access(user.id, user.username or user.full_name)
    await context.bot.send_message(
        owner,
        f"Access request from {user.full_name} (id {user.id}).",
        reply_markup=kb([[("Approve", f"appr:{user.id}"), ("Deny", f"deny:{user.id}")]]),
    )
    await update.message.reply_text("Access requested — waiting for the owner's approval.")
    return False


async def start(update, context) -> None:
    _store, access, _service, _settings = _deps(context)
    if access.is_allowed(update.effective_user.id):
        await update.message.reply_text(
            "Consilium bot — a free-LLM council. Send a message to consult it. "
            "/settings to configure this session, /council for a full council, "
            "/sessions to switch conversations, /help for more."
        )
    else:
        await _ensure_allowed(update, context)


async def help_cmd(update, context) -> None:
    await update.message.reply_text(
        "Ask the free-LLM council.\n"
        "• plain text → ask/council per /settings\n"
        "• /ask <q> or /council <q> — one-off override\n"
        "• /settings — tool, sensitivity (tier), mode, council model roster, size, footer "
        "(per session, changeable mid-conversation)\n"
        "• /sessions — switch/new/rename/delete · /new — fresh session\n\n"
        "Privacy: your messages transit Telegram's servers. The privacy gate still limits which "
        "LLMs see the prompt (default: sensitive → Tier-A only)."
    )


async def new_session(update, context) -> None:
    if not await _ensure_allowed(update, context):
        return
    store, *_ = _deps(context)
    store.create_session(update.effective_chat.id)
    await update.message.reply_text("Started a fresh session (previous ones kept — /sessions).")


async def sessions_cmd(update, context) -> None:
    if not await _ensure_allowed(update, context):
        return
    store, *_ = _deps(context)
    rows = store.list_sessions(update.effective_chat.id)
    await update.message.reply_text("Sessions:", reply_markup=kb(render.sessions_layout(rows)))


async def settings_cmd(update, context) -> None:
    if not await _ensure_allowed(update, context):
        return
    store, *_ = _deps(context)
    sid = store.active_session(update.effective_chat.id)
    await update.message.reply_text(
        "Settings (this session):",
        reply_markup=kb(render.settings_layout(store.get_settings(sid))),
    )


async def ask_cmd(update, context) -> None:
    await _run_message(update, context, tool_override="ask", text=" ".join(context.args))


async def council_cmd(update, context) -> None:
    await _run_message(update, context, tool_override="council", text=" ".join(context.args))


async def on_text(update, context) -> None:
    await _run_message(update, context, tool_override=None, text=update.message.text)


async def _run_message(update, context, *, tool_override, text) -> None:
    if not await _ensure_allowed(update, context):
        return
    store, _access, service, settings = _deps(context)
    if not (text or "").strip():
        await update.message.reply_text("Send a question.")
        return
    chat_id = update.effective_chat.id
    sid = store.active_session(chat_id)
    cfg = store.get_settings(sid)
    tool = tool_override or cfg.get("tool", "council")
    store.add_message(sid, "user", text)
    store.maybe_autotitle(sid, text)
    history = store.recent_messages(sid, settings.context_turns)[:-1]
    prompt = build_prompt(history, text, turns=settings.context_turns,
                          char_budget=settings.context_char_budget)
    if service is None:
        await update.message.reply_text("Council backend unavailable — start the proxy.")
        return
    if tool == "ask":
        await _run_ask(update, service, store, sid, cfg, prompt)
    else:
        await _run_council(update, service, store, sid, cfg, prompt)


async def _send_chunks_reply(update, text) -> None:
    parts = render.chunk(text)
    for p in parts:
        await update.message.reply_text(p)


async def _run_ask(update, service, store, sid, cfg, prompt) -> None:
    try:
        res = await service.ask(prompt, model=cfg.get("model") or None, capability=None,
                                sensitivity=cfg.get("sensitivity", "sensitive"))
    except _SERVICE_ERRORS as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        return
    except Exception as exc:  # noqa: BLE001 - never crash a chat on an unexpected error
        await update.message.reply_text(f"⚠️ internal error: {exc.__class__.__name__}")
        return
    meta = {"model": res.model_used, "note": res.note}
    await _send_chunks_reply(update, render.answer_text(
        res.answer, meta, show_footer=cfg.get("show_footer", True)))
    store.add_message(sid, "assistant", res.answer)


async def _run_council(update, service, store, sid, cfg, prompt) -> None:
    progress = await update.message.reply_text("\U0001f9e0 Council starting…")
    q: asyncio.Queue = asyncio.Queue()

    def on_progress(evt) -> None:
        q.put_nowait(evt)

    async def run() -> None:
        try:
            res = await service.council(
                prompt, members=cfg.get("members") or None, size=cfg.get("size"),
                mode=cfg.get("mode") or None, sensitivity=cfg.get("sensitivity", "sensitive"),
                on_progress=on_progress,
            )
            q.put_nowait(("final", res))
        except _SERVICE_ERRORS as exc:
            q.put_nowait(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001 - map any error to a friendly message
            q.put_nowait(("error", f"internal error: {exc.__class__.__name__}"))
        finally:
            q.put_nowait(None)

    task = asyncio.ensure_future(run())
    roster: list = []
    done: dict = {}
    aggregating = False
    last = 0.0
    try:
        while True:
            item = await q.get()
            if item is None:
                break
            if isinstance(item, tuple):
                kind, payload = item
                if kind == "final":
                    meta = {"mode": payload.mode, "confidence": payload.confidence,
                            "note": payload.note}
                    parts = render.chunk(render.answer_text(
                        payload.answer, meta, show_footer=cfg.get("show_footer", True)))
                    await progress.edit_text(parts[0])
                    for p in parts[1:]:
                        await update.message.reply_text(p)
                    store.add_message(sid, "assistant", payload.answer)
                else:
                    await progress.edit_text(f"⚠️ {payload}")
                continue
            event = item.get("event")
            if event == "roster":
                roster = item.get("members", [])
            elif event == "member":
                done[item["alias"]] = item["ok"]
            elif event == "aggregating":
                aggregating = True
            now = time.monotonic()
            if now - last >= 1.0:
                with contextlib.suppress(Exception):
                    await progress.edit_text(render.progress_text(roster, done, aggregating))
                last = now
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def approve_cmd(update, context) -> None:
    _store, access, _service, _settings = _deps(context)
    if not access.is_owner(update.effective_user.id) or not context.args:
        return
    access.approve(int(context.args[0]))
    await update.message.reply_text(f"Approved {context.args[0]}.")


async def deny_cmd(update, context) -> None:
    _store, access, _service, _settings = _deps(context)
    if not access.is_owner(update.effective_user.id) or not context.args:
        return
    access.deny(int(context.args[0]))
    await update.message.reply_text(f"Denied {context.args[0]}.")


async def pending_cmd(update, context) -> None:
    _store, access, _service, _settings = _deps(context)
    if not access.is_owner(update.effective_user.id):
        return
    pend = access.list_pending()
    body = ", ".join(f"{k} ({v})" for k, v in pend.items()) or "none"
    await update.message.reply_text(f"Pending: {body}")


def _cycle(seq, cur):
    return seq[(seq.index(cur) + 1) % len(seq)] if cur in seq else seq[0]


async def on_callback(update, context) -> None:
    store, access, service, _settings = _deps(context)
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = update.effective_user.id

    if data.startswith(("appr:", "deny:")):
        if access.is_owner(uid):
            target = int(data.split(":", 1)[1])
            if data.startswith("appr:"):
                access.approve(target)
                with contextlib.suppress(Exception):
                    await context.bot.send_message(target, "You're approved — send a message.")
                await query.edit_message_text(f"Approved {target}.")
            else:
                access.deny(target)
                await query.edit_message_text(f"Denied {target}.")
        return

    if not access.is_allowed(uid):
        return
    chat_id = update.effective_chat.id
    sid = store.active_session(chat_id)

    if data.startswith("sess:"):
        rest = data[len("sess:"):]
        if rest == "new":
            store.create_session(chat_id)
        elif rest.startswith("switch:"):
            store.switch_session(chat_id, int(rest.split(":", 1)[1]))
        elif rest.startswith("del:"):
            store.delete_session(chat_id, int(rest.split(":", 1)[1]))
        await query.edit_message_text(
            "Sessions:", reply_markup=kb(render.sessions_layout(store.list_sessions(chat_id))))
        return

    if data == "menu:settings":
        await query.edit_message_text(
            "Settings (this session):",
            reply_markup=kb(render.settings_layout(store.get_settings(sid))))
        return

    if data == "menu:models" or data.startswith("mdl:"):
        if data.startswith("mdl:"):
            alias = data.split(":", 1)[1]
            cur = list(store.get_settings(sid).get("members", []))
            if alias == "auto":
                cur = []
            elif alias in cur:
                cur = [a for a in cur if a != alias]
            else:
                cur.append(alias)
            store.set_members(sid, cur)
        models = service.list_models() if service is not None else []
        selected = store.get_settings(sid).get("members", [])
        await query.edit_message_text(
            "Attach council models:",
            reply_markup=kb(render.models_layout(models, selected)))
        return

    if data.startswith("set:"):
        key = data.split(":", 1)[1]
        cur = store.get_settings(sid)
        if key == "tool":
            store.set_setting(sid, "tool", "ask" if cur["tool"] == "council" else "council")
        elif key == "sensitivity":
            store.set_setting(sid, "sensitivity",
                              "public" if cur["sensitivity"] == "sensitive" else "sensitive")
        elif key == "mode":
            store.set_setting(sid, "mode", _cycle(_MODES, cur["mode"]))
        elif key == "size":
            store.set_setting(sid, "size", _cycle(_SIZES, cur["size"]))
        elif key == "show_footer":
            store.set_setting(sid, "show_footer", 0 if cur["show_footer"] else 1)
        await query.edit_message_text(
            "Settings (this session):",
            reply_markup=kb(render.settings_layout(store.get_settings(sid))))
        return


def register(application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("new", new_session))
    application.add_handler(CommandHandler("sessions", sessions_cmd))
    application.add_handler(CommandHandler("settings", settings_cmd))
    application.add_handler(CommandHandler("ask", ask_cmd))
    application.add_handler(CommandHandler("council", council_cmd))
    application.add_handler(CommandHandler("approve", approve_cmd))
    application.add_handler(CommandHandler("deny", deny_cmd))
    application.add_handler(CommandHandler("pending", pending_cmd))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
