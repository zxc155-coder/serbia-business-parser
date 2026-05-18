"""Telegram bot wrapper around the parser.

Usage:
    export TELEGRAM_BOT_TOKEN=<token>
    python -m serbia_parser.bot

Commands:
    /start         — greet + show menu
    /categories    — inline keyboard with all 10 categories
    /parse <key> [verify]    — run one category, send CSV when done
    /parse_all     — run every category sequentially
    /status        — show current job progress
    /cancel        — cancel current job (this user only)
    /wa_login      — link WhatsApp Web (sends a QR PNG you scan from phone)
    /wa_status     — check WhatsApp Web login state
    /verify        — re-check phone numbers in a CSV (reply to a CSV with /verify)
    /help          — usage
"""

from __future__ import annotations

import asyncio
import csv
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .categories import CATEGORIES, by_key
from .pipeline import Cancelled, Progress, run_category
from .sources.whatsapp import WhatsAppVerifier, normalize_phone
from .storage import FIELDS, write_csv

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("SERBIA_PARSER_DATA", "data")).resolve()
DEFAULT_USE_MAPS = os.environ.get("SERBIA_PARSER_USE_MAPS", "0") == "1"
MAX_SEARCH = int(os.environ.get("SERBIA_PARSER_MAX_SEARCH", "15"))
MAX_MAPS = int(os.environ.get("SERBIA_PARSER_MAX_MAPS", "15"))
MAX_WEBSITES = int(os.environ.get("SERBIA_PARSER_MAX_WEBSITES", "40"))
AUTO_VERIFY_WHATSAPP = os.environ.get("SERBIA_PARSER_VERIFY_WA", "0") == "1"
WA_QR_PATH = Path(os.environ.get("SERBIA_PARSER_WA_QR", "data/wa_qr.png")).resolve()

PROGRESS_EDIT_INTERVAL = 2.5  # seconds — avoid Telegram rate limits.

STAGE_LABEL = {
    "search": "Поиск в DDG/Bing",
    "directory": "Каталоги (companywall + privredni-imenik)",
    "maps": "Google Maps",
    "crawl": "Краулинг сайтов",
    "verify": "Проверка WhatsApp",
    "done": "Готово",
}


@dataclass
class Job:
    chat_id: int
    user_id: int
    category_keys: list[str]
    cancel_event: threading.Event = field(default_factory=threading.Event)
    progress_msg_id: int | None = None
    last_edit_at: float = 0.0
    latest_progress: Progress | None = None
    current_index: int = 0
    started_at: float = field(default_factory=time.time)
    verify_whatsapp: bool = False


def _categories_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, c in enumerate(CATEGORIES, 1):
        row.append(InlineKeyboardButton(f"{i}. {c.title_sr}", callback_data=f"parse:{c.key}"))
        if len(row) == 1:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⏩ Все 10", callback_data="parse:__all__")])
    return InlineKeyboardMarkup(rows)


def _format_progress(job: Job) -> str:
    p = job.latest_progress
    header = (
        f"<b>Парсинг {job.current_index + 1}/{len(job.category_keys)}</b>\n"
        f"Категории: {', '.join(job.category_keys)}\n"
    )
    if p is None:
        return header + "Стартую…"
    stage = STAGE_LABEL.get(p.stage, p.stage)
    pct = (p.current / p.total * 100) if p.total else 0
    bar_len = 18
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    elapsed = int(time.time() - job.started_at)
    return (
        f"{header}"
        f"Этап: <b>{stage}</b>\n"
        f"<code>{bar}</code> {p.current}/{p.total} ({pct:.0f}%)\n"
        f"Найдено компаний: <b>{p.found}</b>\n"
        f"Время: {elapsed}s\n"
        f"<i>{(p.detail or '')[:120]}</i>"
    )


class BotApp:
    def __init__(self, token: str) -> None:
        self.app = Application.builder().token(token).build()
        self._jobs: dict[int, Job] = {}  # user_id -> Job
        self._jobs_lock = asyncio.Lock()
        self._wa_lock = asyncio.Lock()  # only one WhatsApp driver at a time
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("categories", self.cmd_categories))
        self.app.add_handler(CommandHandler("parse", self.cmd_parse))
        self.app.add_handler(CommandHandler("parse_all", self.cmd_parse_all))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("cancel", self.cmd_cancel))
        self.app.add_handler(CommandHandler("wa_login", self.cmd_wa_login))
        self.app.add_handler(CommandHandler("wa_status", self.cmd_wa_status))
        self.app.add_handler(CommandHandler("verify", self.cmd_verify))
        self.app.add_handler(CallbackQueryHandler(self.on_callback, pattern=r"^parse:"))
        # CSV uploaded with caption "/verify" gets routed to verify too.
        self.app.add_handler(
            MessageHandler(
                filters.Document.ALL & filters.CaptionRegex(r"^/verify"),
                self.cmd_verify,
            )
        )

    # ----- commands ---------------------------------------------------------

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "<b>Serbia B2B Parser</b>\n\n"
            "Парсит сербские бизнесы по 10 категориям (металлоискатели, "
            "сельхозтехника, промышленное оборудование и т.д.).\n\n"
            "Источники: DuckDuckGo, Bing, companywall.rs, Google Maps (опц.) + "
            "краулинг найденных сайтов на контакты.\n\n"
            "Команды:\n"
            "/categories — выбрать категорию кнопкой\n"
            "/parse &lt;ключ&gt; — спарсить одну\n"
            "/parse_all — спарсить все\n"
            "/status — текущий прогресс\n"
            "/cancel — отменить\n"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        await update.message.reply_text("Выбери категорию:", reply_markup=_categories_keyboard())

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self.cmd_start(update, ctx)

    async def cmd_categories(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Категории:", reply_markup=_categories_keyboard())

    async def cmd_parse(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not ctx.args:
            await update.message.reply_text(
                "Использование: <code>/parse &lt;key&gt; [verify]</code>\n"
                "Добавь <code>verify</code> чтобы проверить телефоны через WhatsApp Web.\n\n"
                "Доступные ключи:\n"
                + "\n".join(f"• <code>{c.key}</code> — {c.title_sr}" for c in CATEGORIES),
                parse_mode=ParseMode.HTML,
            )
            return
        key = ctx.args[0]
        verify = any(a.lower() in {"verify", "wa", "whatsapp"} for a in ctx.args[1:])
        try:
            by_key(key)
        except KeyError:
            await update.message.reply_text(f"Неизвестная категория: {key}")
            return
        await self._launch(update, ctx, [key], verify_whatsapp=verify)

    async def cmd_parse_all(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self._launch(update, ctx, [c.key for c in CATEGORIES])

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        job = self._jobs.get(update.effective_user.id)
        if job is None:
            await update.message.reply_text("Сейчас нет активных задач.")
            return
        await update.message.reply_text(_format_progress(job), parse_mode=ParseMode.HTML)

    async def cmd_cancel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        job = self._jobs.get(update.effective_user.id)
        if job is None:
            await update.message.reply_text("Нечего отменять.")
            return
        job.cancel_event.set()
        await update.message.reply_text("Отмена запрошена…")

    # ----- WhatsApp Web -----------------------------------------------------

    async def cmd_wa_login(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            "Открываю WhatsApp Web в фоне, забираю QR…\n"
            "Когда придёт картинка — открой WhatsApp на телефоне → "
            "<b>Настройки → Связанные устройства → Привязать устройство</b> "
            "и сосканируй QR.",
            parse_mode=ParseMode.HTML,
        )

        async def _do() -> None:
            async with self._wa_lock:
                # Capture QR in worker thread.
                qr_path: Path | None = await asyncio.to_thread(self._wa_capture_qr)
                if qr_path is None:
                    await ctx.bot.send_message(
                        chat_id,
                        "WhatsApp Web уже залогинен — повторный QR не нужен. "
                        "Можешь сразу запускать /verify или /parse … verify.",
                    )
                    return
                with qr_path.open("rb") as f:
                    await ctx.bot.send_photo(
                        chat_id,
                        photo=f,
                        caption="Сосканируй этот QR из приложения WhatsApp.",
                    )
                # Wait for login to complete in background thread.
                ok = await asyncio.to_thread(self._wa_wait_login, 180.0)
                if ok:
                    await ctx.bot.send_message(chat_id, "WhatsApp Web подключён ✅")
                else:
                    await ctx.bot.send_message(
                        chat_id,
                        "Не дождался сканирования (180 сек). Запусти /wa_login заново.",
                    )

        ctx.application.create_task(_do(), update=None)

    async def cmd_wa_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("Проверяю состояние сессии WhatsApp Web…")
        async with self._wa_lock:
            ok = await asyncio.to_thread(self._wa_check_login)
        if ok:
            await update.message.reply_text("WhatsApp Web: <b>подключено</b>.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(
                "WhatsApp Web не залогинен. Запусти /wa_login и сосканируй QR.",
            )

    async def cmd_verify(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        # Find a document: in the same message, or in a reply.
        msg = update.effective_message
        doc = None
        if msg.document is not None:
            doc = msg.document
        elif msg.reply_to_message and msg.reply_to_message.document:
            doc = msg.reply_to_message.document
        if doc is None:
            await msg.reply_text(
                "Пришли мне CSV (полученный из /parse) с командой <code>/verify</code> в подписи,\n"
                "или ответь командой <code>/verify</code> на сообщение с CSV.",
                parse_mode=ParseMode.HTML,
            )
            return

        await msg.reply_text(
            f"Принял <code>{doc.file_name or 'csv'}</code>. Загружаю и начинаю проверку WhatsApp Web…",
            parse_mode=ParseMode.HTML,
        )

        file = await doc.get_file()
        in_path = DATA_DIR / "verify_in" / (doc.file_name or "input.csv")
        in_path.parent.mkdir(parents=True, exist_ok=True)
        await file.download_to_drive(custom_path=str(in_path))

        out_path = (
            DATA_DIR / "verify_out" / ((doc.file_name or "input.csv").replace(".csv", "") + ".verified.csv")
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)

        progress_msg = await msg.reply_text("Готовлю драйвер WhatsApp Web…")
        loop = asyncio.get_running_loop()

        async def _do() -> None:
            async with self._wa_lock:
                try:
                    state = {"done": 0, "total": 0, "ok": 0, "miss": 0, "unknown": 0, "last": ""}
                    last_edit_at = [0.0]

                    def _progress(done: int, total: int, phone: str, st: str) -> None:
                        state["done"] = done
                        state["total"] = total
                        state["last"] = phone
                        if st == "on_whatsapp":
                            state["ok"] += 1
                        elif st == "not_on_whatsapp":
                            state["miss"] += 1
                        else:
                            state["unknown"] += 1
                        now = time.time()
                        if now - last_edit_at[0] < PROGRESS_EDIT_INTERVAL and done != total:
                            return
                        last_edit_at[0] = now
                        text = (
                            f"WhatsApp проверка: <b>{done}/{total}</b>\n"
                            f"✅ {state['ok']}  ❌ {state['miss']}  ❓ {state['unknown']}\n"
                            f"<i>{phone}</i>"
                        )
                        asyncio.run_coroutine_threadsafe(
                            ctx.bot.edit_message_text(
                                text,
                                chat_id=progress_msg.chat_id,
                                message_id=progress_msg.message_id,
                                parse_mode=ParseMode.HTML,
                            ),
                            loop,
                        )

                    written = await asyncio.to_thread(_verify_csv_file, in_path, out_path, _progress)
                    with out_path.open("rb") as f:
                        await ctx.bot.send_document(
                            msg.chat_id,
                            document=f,
                            filename=out_path.name,
                            caption=(
                                f"WhatsApp проверка завершена.\n"
                                f"Строк: <b>{written}</b>\n"
                                f"✅ on_whatsapp: <b>{state['ok']}</b>\n"
                                f"❌ not_on_whatsapp: <b>{state['miss']}</b>\n"
                                f"❓ unknown: <b>{state['unknown']}</b>"
                            ),
                            parse_mode=ParseMode.HTML,
                        )
                except RuntimeError as e:
                    await ctx.bot.send_message(msg.chat_id, f"❌ {e}")
                except Exception as e:
                    log.exception("verify failed")
                    await ctx.bot.send_message(
                        msg.chat_id, f"❌ Ошибка: <code>{e}</code>", parse_mode=ParseMode.HTML
                    )

        ctx.application.create_task(_do(), update=None)

    # WhatsApp helpers (run in worker threads).

    def _wa_capture_qr(self) -> Path | None:
        with WhatsAppVerifier() as wa:
            if wa.is_logged_in(timeout=5):
                return None
            return wa.save_qr(WA_QR_PATH)

    def _wa_wait_login(self, timeout: float) -> bool:
        with WhatsAppVerifier() as wa:
            return wa.wait_for_login(timeout=timeout)

    def _wa_check_login(self) -> bool:
        with WhatsAppVerifier() as wa:
            return wa.is_logged_in(timeout=8)

    async def on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if not q.data or not q.data.startswith("parse:"):
            return
        key = q.data.split(":", 1)[1]
        if key == "__all__":
            keys = [c.key for c in CATEGORIES]
        else:
            try:
                by_key(key)
            except KeyError:
                await q.message.reply_text(f"Неизвестная категория: {key}")
                return
            keys = [key]
        await self._launch_from_query(update, ctx, keys)

    # ----- core launch ------------------------------------------------------

    async def _launch(
        self,
        update: Update,
        ctx: ContextTypes.DEFAULT_TYPE,
        keys: list[str],
        *,
        verify_whatsapp: bool = False,
    ) -> None:
        await self._do_launch(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
            keys=keys,
            ctx=ctx,
            verify_whatsapp=verify_whatsapp,
        )

    async def _launch_from_query(
        self,
        update: Update,
        ctx: ContextTypes.DEFAULT_TYPE,
        keys: list[str],
        *,
        verify_whatsapp: bool = False,
    ) -> None:
        await self._do_launch(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
            keys=keys,
            ctx=ctx,
            verify_whatsapp=verify_whatsapp,
        )

    async def _do_launch(
        self,
        chat_id: int,
        user_id: int,
        keys: list[str],
        ctx: ContextTypes.DEFAULT_TYPE,
        *,
        verify_whatsapp: bool = False,
    ) -> None:
        async with self._jobs_lock:
            if user_id in self._jobs:
                await ctx.bot.send_message(
                    chat_id,
                    "Уже выполняется задача. Подожди или нажми /cancel.",
                )
                return
            job = Job(
                chat_id=chat_id,
                user_id=user_id,
                category_keys=keys,
                verify_whatsapp=verify_whatsapp or AUTO_VERIFY_WHATSAPP,
            )
            self._jobs[user_id] = job

        # Initial progress message we will edit.
        msg = await ctx.bot.send_message(
            chat_id,
            f"Стартую парсинг ({len(keys)} категорий)…",
            parse_mode=ParseMode.HTML,
        )
        job.progress_msg_id = msg.message_id

        loop = asyncio.get_running_loop()
        ctx.application.create_task(self._run_job(job, loop, ctx), update=None)

    async def _run_job(
        self, job: Job, loop: asyncio.AbstractEventLoop, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        def on_progress(p: Progress) -> None:
            job.latest_progress = p
            # Throttle Telegram edits.
            now = time.time()
            if now - job.last_edit_at < PROGRESS_EDIT_INTERVAL and p.stage != "done":
                return
            job.last_edit_at = now
            asyncio.run_coroutine_threadsafe(self._safe_edit_progress(job, ctx), loop)

        try:
            for idx, key in enumerate(job.category_keys):
                job.current_index = idx
                cat = by_key(key)
                # Each category runs in a worker thread so we can preempt with cancel_event.
                out_path = await asyncio.to_thread(
                    run_category,
                    cat,
                    DATA_DIR,
                    use_maps=DEFAULT_USE_MAPS,
                    max_search_results=MAX_SEARCH,
                    max_maps_results=MAX_MAPS,
                    max_websites=MAX_WEBSITES,
                    on_progress=on_progress,
                    cancel_event=job.cancel_event,
                )

                # Optional WhatsApp verification stage.
                if job.verify_whatsapp and not job.cancel_event.is_set():
                    cat_key = cat.key  # capture loop var for nested closure

                    def _wa_progress(
                        done: int, total: int, phone: str, st: str, *, _k: str = cat_key
                    ) -> None:
                        job.latest_progress = Progress(_k, "verify", done, total, done, phone)
                        now = time.time()
                        if now - job.last_edit_at < PROGRESS_EDIT_INTERVAL and done != total:
                            return
                        job.last_edit_at = now
                        asyncio.run_coroutine_threadsafe(self._safe_edit_progress(job, ctx), loop)

                    async with self._wa_lock:
                        try:
                            verified_out = out_path.with_suffix(".verified.csv")
                            await asyncio.to_thread(_verify_csv_file, out_path, verified_out, _wa_progress)
                            out_path = verified_out
                        except RuntimeError as e:
                            await ctx.bot.send_message(job.chat_id, f"⚠️ WhatsApp: {e}")
                        except Exception as e:
                            log.exception("WA verify in job failed")
                            await ctx.bot.send_message(
                                job.chat_id,
                                f"⚠️ WhatsApp проверка упала: <code>{e}</code>",
                                parse_mode=ParseMode.HTML,
                            )

                # Send CSV.
                row_count = _count_rows(out_path)
                await ctx.bot.send_document(
                    job.chat_id,
                    document=out_path.open("rb"),
                    filename=out_path.name,
                    caption=(
                        f"<b>{cat.title_sr}</b>\nСтрок: {row_count}\nФайл: <code>{out_path.name}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                if job.cancel_event.is_set():
                    break
            await ctx.bot.send_message(
                job.chat_id,
                "✅ Готово." if not job.cancel_event.is_set() else "⏹ Остановлено пользователем.",
            )
        except Cancelled:
            await ctx.bot.send_message(job.chat_id, "⏹ Парсинг отменён.")
        except Exception as e:
            log.exception("job failed")
            await ctx.bot.send_message(job.chat_id, f"❌ Ошибка: <code>{e}</code>", parse_mode=ParseMode.HTML)
        finally:
            async with self._jobs_lock:
                self._jobs.pop(job.user_id, None)

    async def _safe_edit_progress(self, job: Job, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if job.progress_msg_id is None:
            return
        try:
            await ctx.bot.edit_message_text(
                _format_progress(job),
                chat_id=job.chat_id,
                message_id=job.progress_msg_id,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            # Most commonly: "message is not modified" or rate limits — ignore.
            log.debug("edit failed: %s", e)

    def run(self) -> None:
        log.info("Bot polling started")
        self.app.run_polling(drop_pending_updates=True)


def _count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        # subtract header
        return max(0, sum(1 for _ in f) - 1)


def _verify_csv_file(in_path: Path, out_path: Path, on_progress) -> int:
    """Re-check phone numbers from ``in_path`` and write a new CSV at ``out_path``
    with the ``verified_whatsapp`` column populated.

    ``on_progress(done, total, phone, state)`` is called per phone.
    """
    rows: list[dict] = []
    with in_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Collect unique phones (each row may have multiple separated by "; ").
    phones: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = (row.get("phone") or "").strip()
        for part in raw.split(";"):
            n = normalize_phone(part)
            if not n or n in seen:
                continue
            seen.add(n)
            phones.append(n)

    if not phones:
        # Nothing to verify; still write the CSV with empty verified_whatsapp column.
        for row in rows:
            row.setdefault("verified_whatsapp", "")
        write_csv(out_path, rows)
        return len(rows)

    # Run the verifier.
    state: dict[str, str] = {}
    with WhatsAppVerifier() as wa:
        wa.ensure_logged_in()

        def _cb(done: int, total: int, phone: str, st: str) -> None:
            state[phone] = st
            try:
                on_progress(done, total, phone, st)
            except Exception:
                pass

        wa.verify_many(phones, on_progress=_cb)

    # Map each row's phone-list to the best verification outcome.
    out_rows: list[dict] = []
    for row in rows:
        raw = (row.get("phone") or "").strip()
        statuses: list[str] = []
        for part in raw.split(";"):
            n = normalize_phone(part)
            if not n:
                continue
            statuses.append(state.get(n, "unknown"))
        if "on_whatsapp" in statuses:
            verified = "yes"
        elif statuses and all(s == "not_on_whatsapp" for s in statuses):
            verified = "no"
        elif statuses:
            verified = "unknown"
        else:
            verified = ""
        new = {k: row.get(k, "") for k in FIELDS}
        new["verified_whatsapp"] = verified
        out_rows.append(new)

    return write_csv(out_path, out_rows)


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or os.environ.get("bot")
    if not token:
        raise SystemExit(
            "Set TELEGRAM_BOT_TOKEN (or BOT_TOKEN / bot) env var to the bot token from @BotFather."
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BotApp(token).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
