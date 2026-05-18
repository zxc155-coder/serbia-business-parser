"""Telegram bot wrapper around the parser.

Usage:
    export TELEGRAM_BOT_TOKEN=<token>
    python -m serbia_parser.bot

Commands:
    /start         — greet + show menu
    /categories    — inline keyboard with all 10 categories
    /parse <key>   — run one category, send CSV when done
    /parse_all     — run every category sequentially
    /status        — show current job progress
    /cancel        — cancel current job (this user only)
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
)

from . import keep_alive
from .categories import CATEGORIES, by_key
from .pipeline import Cancelled, Progress, run_category

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("SERBIA_PARSER_DATA", "data")).resolve()
DEFAULT_USE_MAPS = os.environ.get("SERBIA_PARSER_USE_MAPS", "0") == "1"
MAX_SEARCH = int(os.environ.get("SERBIA_PARSER_MAX_SEARCH", "20"))
MAX_MAPS = int(os.environ.get("SERBIA_PARSER_MAX_MAPS", "15"))
MAX_WEBSITES = int(os.environ.get("SERBIA_PARSER_MAX_WEBSITES", "120"))
# Default budget used only when /status is shown before a job starts.
DEFAULT_TARGET_VALID = int(os.environ.get("SERBIA_PARSER_TARGET_VALID", "500"))
DEADLINE_S = int(os.environ.get("SERBIA_PARSER_DEADLINE_S", "1200"))  # 20 min

# Pre-parse count picker. The user explicitly chooses the target number of
# valid contacts before the run starts; the value is split across the
# selected categories at runtime.
COUNT_OPTIONS = (50, 100, 200, 500, 1000, 2000)

PROGRESS_EDIT_INTERVAL = 2.5  # seconds — avoid Telegram rate limits.

STAGE_LABEL = {
    "search": "Поиск в DDG/Bing",
    "directory": "Каталоги (companywall + privredni-imenik)",
    "maps": "Google Maps",
    "crawl": "Краулинг сайтов",
    "done": "Готово",
}


def _per_category_targets(target_total: int, n_categories: int) -> tuple[int, float]:
    """Split the user-chosen target / global DEADLINE_S budget across N categories."""
    if n_categories <= 0:
        return target_total, float(DEADLINE_S)
    return (
        max(10, target_total // n_categories),
        max(60.0, DEADLINE_S / n_categories),
    )


@dataclass
class Job:
    chat_id: int
    user_id: int
    category_keys: list[str]
    target_total: int = DEFAULT_TARGET_VALID
    cancel_event: threading.Event = field(default_factory=threading.Event)
    progress_msg_id: int | None = None
    last_edit_at: float = 0.0
    latest_progress: Progress | None = None
    current_index: int = 0
    started_at: float = field(default_factory=time.time)


def _categories_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, c in enumerate(CATEGORIES, 1):
        row.append(InlineKeyboardButton(f"{i}. {c.title_ru}", callback_data=f"parse:cat:{c.key}"))
        if len(row) == 1:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⏩ Все 10", callback_data="parse:cat:__all__")])
    return InlineKeyboardMarkup(rows)


def _count_keyboard(cat_key: str) -> InlineKeyboardMarkup:
    """Inline keyboard for picking the target number of valid contacts."""
    buttons = [
        InlineKeyboardButton(str(n), callback_data=f"parse:cnt:{cat_key}:{n}")
        for n in COUNT_OPTIONS
    ]
    # Three buttons per row.
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton("« Назад к категориям", callback_data="parse:cat:__menu__")])
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
        f"Найдено компаний: <b>{p.found}</b> (валидных: <b>{p.valid}</b>)\n"
        f"Время: {elapsed}s\n"
        f"<i>{(p.detail or '')[:120]}</i>"
    )


class BotApp:
    def __init__(self, token: str) -> None:
        self.app = Application.builder().token(token).build()
        self._jobs: dict[int, Job] = {}  # user_id -> Job
        self._jobs_lock = asyncio.Lock()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("categories", self.cmd_categories))
        self.app.add_handler(CommandHandler("parse", self.cmd_parse))
        self.app.add_handler(CommandHandler("parse_all", self.cmd_parse_all))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("cancel", self.cmd_cancel))
        self.app.add_handler(CallbackQueryHandler(self.on_callback, pattern=r"^parse:"))

    # ----- commands ---------------------------------------------------------

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            "<b>Serbia B2B Parser</b>\n\n"
            "Парсит сербские бизнесы по 10 категориям (металлоискатели, "
            "сельхозтехника, промышленное оборудование и т.д.).\n\n"
            "Источники: DuckDuckGo, Bing, companywall.rs, privredni-imenik.com, "
            "Google Maps (опц.) + краулинг найденных сайтов на контакты.\n\n"
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
                "Использование: <code>/parse &lt;key&gt;</code>\n\n"
                "Доступные ключи:\n"
                + "\n".join(f"• <code>{c.key}</code> — {c.title_ru}" for c in CATEGORIES),
                parse_mode=ParseMode.HTML,
            )
            return
        key = ctx.args[0]
        try:
            cat = by_key(key)
        except KeyError:
            await update.message.reply_text(f"Неизвестная категория: {key}")
            return
        await update.message.reply_text(
            f"<b>{cat.title_ru}</b>\nСколько компаний с телефоном нужно найти?",
            parse_mode=ParseMode.HTML,
            reply_markup=_count_keyboard(key),
        )

    async def cmd_parse_all(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "<b>Все 10 категорий</b>\nСколько компаний с телефоном нужно найти суммарно?",
            parse_mode=ParseMode.HTML,
            reply_markup=_count_keyboard("__all__"),
        )

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

    async def on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if not q.data:
            return
        parts = q.data.split(":")
        # Backward compat: old "parse:<key>" → treat as category pick.
        if len(parts) == 2 and parts[0] == "parse":
            parts = ["parse", "cat", parts[1]]
        if len(parts) < 3 or parts[0] != "parse":
            return
        action = parts[1]
        if action == "cat":
            cat_key = parts[2]
            if cat_key == "__menu__":
                await q.message.reply_text("Категории:", reply_markup=_categories_keyboard())
                return
            title = "Все 10 категорий" if cat_key == "__all__" else by_key(cat_key).title_ru
            text = (
                f"<b>{title}</b>\nСколько компаний с телефоном нужно найти"
                f"{' суммарно' if cat_key == '__all__' else ''}?"
            )
            await q.message.reply_text(
                text, parse_mode=ParseMode.HTML, reply_markup=_count_keyboard(cat_key)
            )
            return
        if action == "cnt":
            if len(parts) < 4:
                return
            cat_key = parts[2]
            try:
                target_total = int(parts[3])
            except ValueError:
                return
            if cat_key == "__all__":
                keys = [c.key for c in CATEGORIES]
            else:
                try:
                    by_key(cat_key)
                except KeyError:
                    await q.message.reply_text(f"Неизвестная категория: {cat_key}")
                    return
                keys = [cat_key]
            await self._launch_from_query(update, ctx, keys, target_total)

    # ----- core launch ------------------------------------------------------

    async def _launch_from_query(
        self,
        update: Update,
        ctx: ContextTypes.DEFAULT_TYPE,
        keys: list[str],
        target_total: int,
    ) -> None:
        await self._do_launch(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id,
            keys=keys,
            target_total=target_total,
            ctx=ctx,
        )

    async def _do_launch(
        self,
        chat_id: int,
        user_id: int,
        keys: list[str],
        target_total: int,
        ctx: ContextTypes.DEFAULT_TYPE,
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
                target_total=target_total,
            )
            self._jobs[user_id] = job

        # Initial progress message we will edit.
        msg = await ctx.bot.send_message(
            chat_id,
            f"Стартую парсинг ({len(keys)} категорий, цель {target_total} валидных)…",
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
            target_valid, deadline_s = _per_category_targets(
                job.target_total, len(job.category_keys)
            )
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
                    target_valid=target_valid,
                    deadline_s=deadline_s,
                    on_progress=on_progress,
                    cancel_event=job.cancel_event,
                )

                # Send CSV (already filtered to valid records on disk).
                row_count = _count_rows(out_path)
                if row_count == 0:
                    await ctx.bot.send_message(
                        job.chat_id,
                        f"<b>{cat.title_ru}</b>\nНи одной компании с телефоном не нашлось — файл не отправляю.",
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    await ctx.bot.send_document(
                        job.chat_id,
                        document=out_path.open("rb"),
                        filename=out_path.name,
                        caption=(
                            f"<b>{cat.title_ru}</b>\n"
                            f"Компаний с телефоном: {row_count}\n"
                            f"Файл: <code>{out_path.name}</code>"
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
    """Return the number of data rows in a CSV (excluding the header line)."""
    if not path.exists():
        return 0
    n = 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0:
                continue  # skip header
            if any(cell.strip() for cell in row):
                n += 1
    return n


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

    # Keep-alive HTTP server for Render (and any other host that idles
    # long-polling workers without inbound traffic).
    if os.environ.get("SERBIA_PARSER_DISABLE_KEEPALIVE", "0") != "1":
        try:
            keep_alive.start()
        except OSError as e:
            log.warning("keep_alive server failed to start: %s", e)

    BotApp(token).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
