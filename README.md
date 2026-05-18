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

## WhatsApp-верификация (опционально)

После парсинга бот может прогнать собранные телефоны через web.whatsapp.com и
отметить в CSV столбце `verified_whatsapp` одно из значений:

| значение | смысл |
|----------|-------|
| `yes` | номер зарегистрирован в WhatsApp |
| `no` | номер не найден в WhatsApp |
| `unknown` | таймаут / WhatsApp не ответил уверенно |
| *(пусто)* | проверка не запускалась или нет нормализованного номера |

**Как это работает**: headless Chrome открывает `web.whatsapp.com/send?phone=…`
под залогиненной сессией. Сессия хранится в персистентном Chrome-профиле
(по умолчанию `~/.serbia_parser/wa_profile`), так что вход через QR
сканируется **один раз**.

> ⚠️ WhatsApp банит за массовую проверку с основных аккаунтов. Используйте
> технический номер. Реалистичная скорость — ~3–6 с/номер.

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
| `/parse <ключ> verify` | спарсить + сразу проверить все телефоны в WhatsApp |
| `/parse_all` | спарсить все 10 категорий по очереди |
| `/status` | прогресс текущей задачи |
| `/cancel` | отменить текущую задачу |
| `/wa_login` | прислать QR-код для входа в WhatsApp Web (один раз) |
| `/wa_status` | проверить, активна ли WhatsApp-сессия |
| `/verify` | прислать CSV в чат — бот вернёт его же со столбцом `verified_whatsapp` |

Во время работы бот редактирует одно сообщение и обновляет в нём прогресс-бар,
этап (поиск / каталог / Maps / краулинг сайтов) и количество найденных компаний.
По завершении каждой категории присылает CSV-файл в чат.

### Поведение по умолчанию

* Один пользователь — одна параллельная задача (новая отбивается сообщением).
* Maps выключен по умолчанию (без `SERBIA_PARSER_USE_MAPS=1`) — намного быстрее.
* Если поисковый сайт временно блокирует — соответствующий запрос пропускается,
  пайплайн идёт дальше.

## Тесты и линтинг

```bash
PYTHONPATH=src python3 -m pytest tests/ -q
ruff check .
```

## Структура

```
src/serbia_parser/
├── bot.py                 # python-telegram-bot обёртка + WA-команды
├── categories.py          # 10 категорий + расширенные ключевые слова + города
├── cli.py                 # CLI-точка входа
├── crawler.py             # обход найденного сайта на контактах
├── dedup.py               # дедуп по домену/телефону/имени
├── driver.py              # headless Selenium (Chrome) для Maps / WA
├── extractor.py           # извлечение email/phone/address из HTML
├── http.py                # общий requests.Session с задержками/ретраями
├── pipeline.py            # parallel search → directory → maps → crawl → dedup → save
├── storage.py             # CSV-вывод (+ verified_whatsapp)
└── sources/
    ├── bing.py
    ├── companywall.py
    ├── duckduckgo.py
    ├── maps.py
    ├── privredni_imenik.py # B2B-каталог privredni-imenik.com
    └── whatsapp.py        # headless WhatsApp Web verifier (QR + persistent profile)
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
