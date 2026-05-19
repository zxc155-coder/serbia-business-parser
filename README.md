# Serbia B2B Parser + Telegram bot

Парсер сербских B2B-компаний по 10 категориям с выгрузкой контактов в CSV и
управлением через Telegram-бота.

## Категории

| ключ | категория |
|------|-----------|
| `metal_detectors` | Металлоискатели и детекторы (B2B опт) |
| `agri_machinery` | Сельхозтехника (тракторы, комбайны, ирригация) |
| `industrial_equipment` | Промышленное оборудование (ЧПУ, фрезеры, компрессоры) |
| `construction_equipment` | Строительная техника (экскаваторы, погрузчики, мини-заводы) |
| `electronic_components` | Электронные компоненты (разъемы, МК, ПЛИС, RF) |
| `auto_moto_parts` | Запчасти для авто/мото (поршневые, турбины, тормозные) |
| `medical_equipment` | Медицинское оборудование (УЗИ, ИВЛ, анализаторы) |
| `3d_scanners_printers` | 3D-сканеры и принтеры |
| `optical_devices` | Оптические приборы (тепловизоры, ночное видение, бинокли) |
| `furniture_interior` | Мебель и интерьер (премиум) |

## Источники

1. **DuckDuckGo HTML** и **Bing** — поиск по сербским и английским ключам.
2. **companywall.rs** — каталог сербского реестра (имя, ПИБ, МБ, e-mail, деятельность).
3. **privredni-imenik.com** — крупнейший публичный B2B-каталог Сербии (имя, сайт,
   e-mail, телефон, адрес, ПИБ, МБ, деятельность, директор).
4. **Google Maps** (через headless Selenium) — карточки бизнесов по городам Сербии.
5. **Краулер сайтов** — параллельно заходит на найденные домены, ищет страницы
   `/kontakt`, `/contact`, `/o-nama` и достаёт телефоны, e-mail, адреса и соцсети.

Все записи дедуплицируются по домену → телефону → имени.

## Установка

```bash
git clone <repo>
cd serbia-business-parser
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Для Google Maps нужен **Chrome/Chromium** + ChromeDriver (Selenium Manager
скачивает совместимый драйвер автоматически на современных версиях selenium).

## CLI

```bash
# Список категорий
PYTHONPATH=src python3 -m serbia_parser.cli --list-categories

# Одну категорию без Maps (быстро)
PYTHONPATH=src python3 -m serbia_parser.cli \
    --category metal_detectors --no-maps -v

# Все категории с Maps по конкретным городам
PYTHONPATH=src python3 -m serbia_parser.cli \
    --cities Beograd "Novi Sad" Niš \
    --max-search 25 --max-maps 20 -v

# Несколько категорий разом
PYTHONPATH=src python3 -m serbia_parser.cli \
    -c metal_detectors -c medical_equipment --no-maps
```

Результат: `data/<category_key>.csv` со столбцами
`category, company, website, phone, email, address, city, social, description, source, source_url`.

Проверку телефонов в WhatsApp бот не делает — это надёжнее и быстрее
делать локальными инструментами (whatcheck / Lyzem / собственный скрипт)
на готовом CSV.

## Telegram-бот

### Создание бота

1. Напишите [@BotFather](https://t.me/BotFather), выполните `/newbot`,
   получите токен вида `1234567890:ABCDEF...`.
2. Сохраните токен в переменной окружения `TELEGRAM_BOT_TOKEN` (или в `.env`).

### Запуск

```bash
export TELEGRAM_BOT_TOKEN=<токен_от_BotFather>
# опционально:
export SERBIA_PARSER_USE_MAPS=1          # включить Google Maps (медленнее)
export SERBIA_PARSER_MAX_SEARCH=15       # лимит результатов на поисковый запрос
export SERBIA_PARSER_MAX_MAPS=15         # лимит результатов на запрос в Maps
export SERBIA_PARSER_MAX_WEBSITES=40     # лимит сайтов на краулинг
export SERBIA_PARSER_DATA=./data         # папка для CSV

PYTHONPATH=src python3 -m serbia_parser.bot
```

### Команды бота

| команда | действие |
|---------|----------|
| `/start`, `/help` | приветствие + меню категорий с кнопками |
| `/categories` | inline-клавиатура со всеми 10 категориями |
| `/parse <ключ>` | спарсить одну категорию, в конце вернёт CSV |
| `/parse_all` | спарсить все 10 категорий по очереди |
| `/status` | прогресс текущей задачи |
| `/cancel` | отменить текущую задачу |

Во время работы бот редактирует одно сообщение и обновляет в нём прогресс-бар,
этап (поиск / каталог / Maps / краулинг сайтов) и количество найденных компаний.
По завершении каждой категории присылает CSV-файл в чат.

### Поведение по умолчанию

* Один пользователь — одна параллельная задача (новая отбивается сообщением).
* Maps выключен по умолчанию (без `SERBIA_PARSER_USE_MAPS=1`) — намного быстрее.
* Если поисковый сайт временно блокирует — соответствующий запрос пропускается,
  пайплайн идёт дальше.

## Цель ~500 валидных контактов за 20 минут

По умолчанию пайплайн идёт в режиме *target-budget*: останавливается, как только
собрано `SERBIA_PARSER_TARGET_VALID` записей с телефоном **или** email, либо когда
истёк `SERBIA_PARSER_DEADLINE_S` секунд на категорию. Бот делит этот бюджет на
число категорий в одной задаче (например, `/parse_all` → 50 контактов и 120 с
на категорию).

Ключевые рычаги под капотом:

* поиск в DDG/Bing идёт параллельно по всем ключевым словам (`SEARCH_WORKERS=8`);
* профили `privredni-imenik.com` и `companywall.rs` берутся параллельно
  (`DIRECTORY_WORKERS=8`) — это самый «жирный» источник: одна страница даёт
  имя + телефон + email + адрес + ПИБ;
* HTTP-клиент ограничивает темп **по хосту** (`per_host_min_gap=0.35s`), а не
  глобально, поэтому 16 воркеров краулинга разных доменов не упираются друг в друга;
* краулер сайтов сначала идёт на `/kontakt`/`/contact`/`/o-nama` (выше yield), и
  прекращает обход, как только нашёл хотя бы один телефон **и** один email.

## Деплой на Render

В корне репо лежит [`render.yaml`](./render.yaml). На Render:

1. **New → Blueprint** → выбрать этот репо. Render создаст Web Service на free-плане.
2. В переменных окружения сервиса задать `TELEGRAM_BOT_TOKEN` (token от @BotFather).
3. Открыть deploy-логи — бот запустит long-polling и keep-alive HTTP-сервер на
   `$PORT` (Render проставит автоматически).
4. Поднять внешний keep-alive — иначе free-инстанс уснёт после 15 минут без
   входящего HTTP. Любой uptime-pinger подойдёт:
   * https://cron-job.org → создайте задачу `GET https://<your-app>.onrender.com/health`
     каждые 5 минут;
   * https://uptimerobot.com → монитор типа HTTP(s) на тот же URL.

Если разворачиваете не через Blueprint, есть [`Procfile`](./Procfile) для совместимости
с Heroku-стилем платформ.

Keep-alive сервер можно отключить переменной окружения
`SERBIA_PARSER_DISABLE_KEEPALIVE=1` (например, при локальном запуске).

## Тесты и линтинг

```bash
PYTHONPATH=src python3 -m pytest tests/ -q
ruff check .
```

## Структура

```
src/serbia_parser/
├── bot.py                 # python-telegram-bot обёртка
├── categories.py          # 10 категорий + расширенные ключевые слова + города
├── cli.py                 # CLI-точка входа
├── crawler.py             # обход найденного сайта на контактах
├── dedup.py               # дедуп по домену/телефону/имени
├── driver.py              # headless Selenium (Chrome) для Maps
├── extractor.py           # извлечение email/phone/address из HTML
├── http.py                # общий requests.Session с задержками/ретраями
├── pipeline.py            # parallel search → directory → maps → crawl → dedup → save
├── storage.py             # CSV-вывод
└── sources/
    ├── bing.py
    ├── companywall.py
    ├── duckduckgo.py
    ├── maps.py
    └── privredni_imenik.py # B2B-каталог privredni-imenik.com
```

## Ограничения и заметки

* Сайты периодически отдают капчу / 202 / редирект на регистрацию при частых
  обращениях с одного IP — это нормальное rate-limiting поведение. Просто
  повторите запуск позже или через прокси.
* companywall.rs скрывает телефон, сайт и адрес за платным аккаунтом — оттуда
  забираем то, что доступно публично (название, ПИБ, МБ, e-mail, деятельность);
  телефон/сайт/адрес заполняем уже из краулинга сайтов.
* В headless-окружении (CI/контейнер) Google Maps иногда тормозит первые
  открытия — поэтому Maps выключен по умолчанию.
