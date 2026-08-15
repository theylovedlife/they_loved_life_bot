import os
import re
import time
import html
import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urljoin, urlparse

import requests
import feedparser
import telebot
from bs4 import BeautifulSoup


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")

if not CHANNEL_ID:
    raise RuntimeError("Не задан CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

MSK = timezone(timedelta(hours=3))

CHECK_INTERVAL = 180
DB_FILE = "liberation_bot.db"

WAR_START = datetime(2022, 2, 24, tzinfo=MSK)

# Один эпизод засчитывается только при подтверждении
# минимум двумя разными СМИ.
MIN_SOURCES_PER_EVENT = 2

# Для публикации должно быть минимум два разных
# подтвержденных эпизода.
MIN_CONFIRMED_EVENTS = 2

# Публикации соседних дат считаются одним эпизодом.
# Разные СМИ могут написать об одном заявлении
# поздно вечером / на следующий день.
SAME_EVENT_MAX_GAP_DAYS = 1

# Сколько страниц внутреннего поиска СМИ проверять.
SEARCH_PAGES = 12

REQUEST_TIMEOUT = 20
SEARCH_DELAY = 0.8

# Повторная историческая проверка.
HISTORY_REFRESH_HOURS = 6


# ============================================================
# 5 СМИ
# ============================================================

SOURCES = {
    "ТАСС": {
        "domain": "tass.ru",
        "rss": [
            "https://tass.ru/rss/v2.xml",
            "https://tass.ru/feed",
        ],
        "search": [
            "https://tass.ru/search?searchStr={query}&page={page}",
            "https://tass.ru/search?searchStr={query}",
        ],
    },

    "РИА Новости": {
        "domain": "ria.ru",
        "rss": [
            "https://ria.ru/export/rss2/archive/index.xml",
        ],
        "search": [
            "https://ria.ru/search/?query={query}&page={page}",
            "https://ria.ru/search/?query={query}",
        ],
    },

    "Интерфакс": {
        "domain": "interfax.ru",
        "rss": [
            "https://www.interfax.ru/rss.asp",
        ],
        "search": [
            "https://www.interfax.ru/search/?text={query}&page={page}",
            "https://www.interfax.ru/search/?query={query}&page={page}",
            "https://www.interfax.ru/search/?text={query}",
        ],
    },

    "Российская газета": {
        "domain": "rg.ru",
        "rss": [
            "https://rg.ru/xml/index.xml",
            "https://rg.ru/xml/",
        ],
        "search": [
            "https://rg.ru/search/?q={query}&page={page}",
            "https://rg.ru/search/?q={query}",
        ],
    },

    "RT": {
        "domain": "russian.rt.com",
        "rss": [
            "https://russian.rt.com/rss",
        ],
        "search": [
            "https://russian.rt.com/search?q={query}&page={page}",
            "https://russian.rt.com/search?q={query}",
        ],
    },
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# ФРАЗЫ ОБ ОСВОБОЖДЕНИИ
# ============================================================

LIBERATION_PATTERNS = [
    r"\bосвободил(?:и|а|о)?\b",
    r"\bосвобожд[её]н(?:а|о|ы)?\b",

    r"\bвзял(?:и|а|о)?\s+под\s+контроль\b",
    r"\bвзят(?:а|о|ы)?\s+под\s+контроль\b",

    r"\bпереш[её]л\s+под\s+контроль\b",
    r"\bперешла\s+под\s+контроль\b",
    r"\bперешло\s+под\s+контроль\b",

    r"\bзанял(?:и|а|о)?\b",
    r"\bзанят(?:а|о|ы)?\b",

    r"\bовладел(?:и|а|о)?\b",

    r"\bустановил(?:и|а|о)?\s+контроль\b",
    r"\bустановлен\s+контроль\b",
]


MILITARY_MARKERS = [
    "минобороны",
    "мо рф",
    "российские войска",
    "российская армия",
    "вс рф",
    "вооруженные силы россии",
    "вооружённые силы россии",
    "российские военнослужащие",
    "российские подразделения",
    "группировка войск",
    "подразделения группировки",
]


SEARCH_PHRASES = [
    "освободили",
    "освобожден",
    "освобождён",
    "взяли под контроль",
    "взят под контроль",
    "заняли",
    "овладели",
]


# ============================================================
# SQLITE
# ============================================================

def db_connect():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = db_connect()

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            source TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,

            title TEXT,
            body TEXT,

            published_at TEXT,

            place TEXT,
            place_key TEXT,
            region TEXT,

            event_text TEXT,

            inserted_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_articles_place
        ON articles(place_key);

        CREATE INDEX IF NOT EXISTS idx_articles_date
        ON articles(published_at);


        CREATE TABLE IF NOT EXISTS history_checks (
            place_key TEXT PRIMARY KEY,

            place TEXT NOT NULL,
            region TEXT,

            last_checked TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS published_posts (
            place_key TEXT PRIMARY KEY,

            signature TEXT NOT NULL,

            published_at TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS rss_seen (
            url TEXT PRIMARY KEY,

            first_seen TEXT NOT NULL
        );
        """
    )

    db.commit()
    db.close()


# ============================================================
# ТЕКСТ
# ============================================================

def clean(value):
    if not value:
        return ""

    value = BeautifulSoup(
        str(value),
        "html.parser"
    ).get_text(" ")

    value = html.unescape(value)

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize(value):
    return (
        clean(value)
        .lower()
        .replace("ё", "е")
    )


def normalize_place(value):
    value = normalize(value)

    value = re.sub(
        r"[«»\"'.,:;!?()\[\]]",
        "",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def split_sentences(text):
    text = clean(text)

    if not text:
        return []

    return [
        x.strip()

        for x in re.split(
            r"(?<=[.!?])\s+",
            text
        )

        if len(x.strip()) > 5
    ]


def contains_liberation_phrase(text):
    low = normalize(text)

    return any(
        re.search(
            pattern,
            low,
            re.I
        )

        for pattern in LIBERATION_PATTERNS
    )


def contains_military_context(text):
    low = normalize(text)

    return any(
        normalize(marker) in low

        for marker in MILITARY_MARKERS
    )


# ============================================================
# HTTP
# ============================================================

def http_get(
    url,
    timeout=REQUEST_TIMEOUT
):
    try:
        response = session.get(
            url,
            timeout=timeout,
            allow_redirects=True
        )

        if response.status_code != 200:
            print(
                "HTTP",
                response.status_code,
                url
            )

            return None

        return response

    except Exception as exc:
        print(
            "HTTP ERROR:",
            url,
            exc
        )

        return None


def domain_matches(
    url,
    domain
):
    try:
        host = (
            urlparse(url)
            .hostname
            or ""
        ).lower()

        domain = domain.lower()

        return (
            host == domain
            or
            host.endswith(
                "." + domain
            )
        )

    except Exception:
        return False


# ============================================================
# ДАТЫ
# ============================================================

def parse_datetime(value):
    if not value:
        return None

    value = str(value).strip()

    try:
        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00"
            )
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=MSK
            )

        return dt.astimezone(
            MSK
        )

    except Exception:
        pass

    m = re.search(
        r"\b([0-3]?\d)"
        r"[./-]"
        r"(0?[1-9]|1[0-2])"
        r"[./-]"
        r"(20\d{2})\b",
        value
    )

    if m:
        try:
            return datetime(
                int(m.group(3)),
                int(m.group(2)),
                int(m.group(1)),
                tzinfo=MSK
            )

        except ValueError:
            pass

    return None


def extract_article_date(
    soup,
    url
):
    variants = [
        (
            "property",
            "article:published_time"
        ),
        (
            "name",
            "article:published_time"
        ),
        (
            "itemprop",
            "datePublished"
        ),
        (
            "name",
            "date"
        ),
        (
            "name",
            "publish-date"
        ),
        (
            "name",
            "pubdate"
        ),
    ]

    for attr, value in variants:

        tag = soup.find(
            "meta",
            attrs={
                attr: value
            }
        )

        if not tag:
            continue

        dt = parse_datetime(
            tag.get("content")
            or
            tag.get("datetime")
            or
            tag.get("value")
        )

        if dt:
            return dt

    for tag in soup.find_all(
        "time"
    ):
        dt = parse_datetime(
            tag.get("datetime")
        )

        if dt:
            return dt

    # JSON-LD

    for script in soup.find_all(
        "script",
        attrs={
            "type":
            "application/ld+json"
        }
    ):
        raw = (
            script.string
            or
            script.get_text(" ")
        )

        if not raw:
            continue

        for field in [
            "datePublished",
            "dateCreated"
        ]:
            m = re.search(
                rf'"{field}"\s*:\s*"([^"]+)"',
                raw,
                re.I
            )

            if m:
                dt = parse_datetime(
                    m.group(1)
                )

                if dt:
                    return dt

    # YYYY/MM/DD

    m = re.search(
        r"/(20\d{2})/"
        r"(0?[1-9]|1[0-2])/"
        r"(0?[1-9]|[12]\d|3[01])"
        r"(?:/|$)",
        url
    )

    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                tzinfo=MSK
            )

        except ValueError:
            pass

    # YYYYMMDD

    m = re.search(
        r"(20\d{2})"
        r"(0[1-9]|1[0-2])"
        r"(0[1-9]|[12]\d|3[01])",
        url
    )

    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                tzinfo=MSK
            )

        except ValueError:
            pass

    return None


# ============================================================
# СТАТЬЯ
# ============================================================

def parse_article(url):

    response = http_get(
        url
    )

    if not response:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = ""

    og = soup.find(
        "meta",
        attrs={
            "property":
            "og:title"
        }
    )

    if og:
        title = clean(
            og.get("content")
        )

    if not title:

        h1 = soup.find("h1")

        if h1:
            title = clean(
                h1.get_text(" ")
            )

    if (
        not title
        and
        soup.title
    ):
        title = clean(
            soup.title.get_text(" ")
        )

    published_at = (
        extract_article_date(
            soup,
            response.url
        )
    )

    for tag in soup.find_all(
        [
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "button",
            "noscript",
            "svg"
        ]
    ):
        tag.decompose()

    paragraphs = []

    for p in soup.find_all("p"):

        text = clean(
            p.get_text(" ")
        )

        if (
            25
            <= len(text)
            <= 4000
        ):
            paragraphs.append(
                text
            )

    body = " ".join(
        paragraphs[:80]
    )

    return {
        "url":
        response.url,

        "title":
        title,

        "body":
        body[:50000],

        "published_at":
        published_at,
    }


# ============================================================
# НАЗВАНИЕ НАСЕЛЕННОГО ПУНКТА
# ============================================================

PLACE_PATTERNS = [

    (
        r"(?:освободил(?:и|а|о)?|"
        r"освобожд[её]н(?:а|о|ы)?)"
        r"\s+"
        r"(?:насел[её]нн(?:ый|ого)\s+"
        r"пункт(?:а)?\s+)?"
        r"[«\"]?"
        r"([А-ЯЁ][А-Яа-яЁё0-9\-]{2,60})"
    ),

    (
        r"(?:взял(?:и|а|о)?|"
        r"взят(?:а|о|ы)?)"
        r"\s+под\s+контроль\s+"
        r"(?:насел[её]нн(?:ый|ого)\s+"
        r"пункт(?:а)?\s+)?"
        r"[«\"]?"
        r"([А-ЯЁ][А-Яа-яЁё0-9\-]{2,60})"
    ),

    (
        r"(?:занял(?:и|а|о)?|"
        r"занят(?:а|о|ы)?)"
        r"\s+"
        r"(?:насел[её]нн(?:ый|ого)\s+"
        r"пункт(?:а)?\s+)?"
        r"[«\"]?"
        r"([А-ЯЁ][А-Яа-яЁё0-9\-]{2,60})"
    ),

    (
        r"(?:овладел(?:и|а|о)?)"
        r"\s+"
        r"(?:насел[её]нным\s+"
        r"пунктом\s+)?"
        r"[«\"]?"
        r"([А-ЯЁ][А-Яа-яЁё0-9\-]{2,60})"
    ),
]


BAD_PLACE_WORDS = {
    "территория",
    "территорию",
    "район",
    "района",
    "позиции",
    "позициями",
    "рубеж",
    "рубежи",
    "населенный",
    "населённый",
    "пункт",
}


def extract_place(text):

    text = clean(text)

    for pattern in PLACE_PATTERNS:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if not match:
            continue

        place = clean(
            match.group(1)
        ).strip(
            ".,:;!?«»\"' "
        )

        if not place:
            continue

        if (
            normalize(place)
            in BAD_PLACE_WORDS
        ):
            continue

        if (
            2
            < len(place)
            <= 60
        ):
            return place

    return None


# ============================================================
# РЕГИОН
# ============================================================

REGION_PATTERNS = [

    r"\b(?:в|на)\s+"
    r"([А-ЯЁ][А-Яа-яЁё\-]+ской\s+области)\b",

    r"\b(?:в|на)\s+"
    r"([А-ЯЁ][А-Яа-яЁё\-]+ском\s+крае)\b",

    r"\b(?:в|на)\s+"
    r"(Республике\s+[А-ЯЁ][А-Яа-яЁё\- ]+)\b",

    r"\b"
    r"([А-ЯЁ][А-Яа-яЁё\-]+ская\s+область)\b",

    r"\b"
    r"([А-ЯЁ][А-Яа-яЁё\-]+ский\s+край)\b",
]


def extract_region(text):

    text = clean(text)

    for pattern in REGION_PATTERNS:

        match = re.search(
            pattern,
            text
        )

        if match:
            return clean(
                match.group(1)
            )

    return None


def make_place_key(
    place,
    region=None
):

    base = normalize_place(
        place
    )

    if region:
        return (
            base
            + "|"
            + normalize_place(region)
        )

    return base


# ============================================================
# ПРОВЕРКА СМЫСЛА
#
# Название населенного пункта должно быть связано именно
# с сообщением об освобождении / взятии под контроль.
# ============================================================

def matching_event_sentences(
    text,
    place
):

    sentences = split_sentences(
        text
    )

    place_low = normalize_place(
        place
    )

    matches = []

    for i, sentence in enumerate(
        sentences
    ):

        low = normalize(
            sentence
        )

        if place_low not in low:
            continue

        if contains_liberation_phrase(
            sentence
        ):
            matches.append(
                sentence
            )

            continue

        for j in [
            i - 1,
            i + 1
        ]:

            if (
                0
                <= j
                < len(sentences)
            ):

                pair = (
                    sentence
                    + " "
                    + sentences[j]
                )

                if contains_liberation_phrase(
                    pair
                ):
                    matches.append(
                        pair
                    )

                    break

    return matches


def article_is_real_match(
    article,
    place
):

    if not article:
        return False

    title = article.get(
        "title",
        ""
    )

    body = article.get(
        "body",
        ""
    )

    combined = (
        title
        + ". "
        + body
    )

    if (
        normalize_place(place)
        not in normalize(combined)
    ):
        return False

    event_sentences = (
        matching_event_sentences(
            combined,
            place
        )
    )

    if not event_sentences:
        return False

    context = " ".join(
        event_sentences
    )

    if not contains_military_context(
        context
    ):

        if not contains_military_context(
            combined[:8000]
        ):
            return False

    return True


# ============================================================
# КРАТКАЯ СВОДКА
# ============================================================

def build_summary(
    article,
    place
):

    combined = (
        article.get(
            "title",
            ""
        )
        + ". "
        + article.get(
            "body",
            ""
        )
    )

    sentences = split_sentences(
        combined
    )

    place_low = normalize_place(
        place
    )

    selected = []

    for sentence in sentences:

        low = normalize(
            sentence
        )

        if (
            place_low in low
            and
            contains_liberation_phrase(
                sentence
            )
        ):
            selected.append(
                sentence
            )

            break

    if not selected:

        matches = (
            matching_event_sentences(
                combined,
                place
            )
        )

        if matches:
            selected.append(
                matches[0]
            )

    context_words = [
        "группировк",
        "подразделен",
        "минобороны",
        "направлен",
        "наступлен",
        "контроль",
        "боев",
        "операци",
    ]

    for sentence in sentences:

        if sentence in selected:
            continue

        low = normalize(
            sentence
        )

        if any(
            word in low
            for word in context_words
        ):
            selected.append(
                sentence
            )

        if len(selected) >= 2:
            break

    if not selected:

        selected = [
            article.get(
                "title",
                ""
            )
        ]

    result = clean(
        " ".join(selected)
    )

    if len(result) > 650:

        result = (
            result[:647]
            .rsplit(
                " ",
                1
            )[0]
            + "..."
        )

    return result


# ============================================================
# СОХРАНЕНИЕ СТАТЬИ
# ============================================================

def save_article(
    source,
    article,
    place,
    region=None
):

    if not article:
        return

    published_at = article.get(
        "published_at"
    )

    if not published_at:
        return

    if published_at < WAR_START:
        return

    place_key = make_place_key(
        place,
        region
    )

    event_text = build_summary(
        article,
        place
    )

    db = db_connect()

    db.execute(
        """
        INSERT OR IGNORE INTO articles
        (
            source,
            url,
            title,
            body,
            published_at,
            place,
            place_key,
            region,
            event_text,
            inserted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            article.get("url"),
            article.get("title"),
            article.get("body"),
            published_at.isoformat(),
            place,
            place_key,
            region,
            event_text,
            datetime.now(
                MSK
            ).isoformat(),
        )
    )

    db.commit()
    db.close()


# ============================================================
# УЖЕ ПРОВЕРЕННЫЕ RSS
# ============================================================

def rss_already_seen(url):

    db = db_connect()

    row = db.execute(
        """
        SELECT 1
        FROM rss_seen
        WHERE url = ?
        """,
        (url,)
    ).fetchone()

    db.close()

    return row is not None


def remember_rss(url):

    db = db_connect()

    db.execute(
        """
        INSERT OR IGNORE
        INTO rss_seen
        (
            url,
            first_seen
        )
        VALUES (?, ?)
        """,
        (
            url,
            datetime.now(
                MSK
            ).isoformat()
        )
    )

    db.commit()
    db.close()


# ============================================================
# RSS ДАТА
# ============================================================

def rss_entry_datetime(
    entry
):

    for field in [
        "published_parsed",
        "updated_parsed"
    ]:

        value = getattr(
            entry,
            field,
            None
        )

        if not value:
            continue

        try:
            dt = datetime(
                value.tm_year,
                value.tm_mon,
                value.tm_mday,
                value.tm_hour,
                value.tm_min,
                value.tm_sec,
                tzinfo=timezone.utc
            )

            return dt.astimezone(
                MSK
            )

        except Exception:
            pass

    return None


def get_working_feed(
    source_name,
    source_config
):

    for rss_url in source_config[
        "rss"
    ]:

        try:
            feed = feedparser.parse(
                rss_url,
                request_headers=HEADERS
            )

            if feed.entries:

                return (
                    rss_url,
                    feed
                )

        except Exception as exc:

            print(
                "RSS ERROR:",
                source_name,
                rss_url,
                exc
            )

    return None, None


# ============================================================
# ПОИСК НА САЙТАХ СМИ
# ============================================================

def looks_like_article_url(
    url,
    domain
):

    if not domain_matches(
        url,
        domain
    ):
        return False

    parsed = urlparse(
        url
    )

    path = parsed.path.lower()

    bad_parts = [
        "/search",
        "/tag/",
        "/tags/",
        "/theme/",
        "/themes/",
        "/rubric/",
        "/category/",
        "/author/",
        "/authors/",
        "/photo/",
        "/video/",
        "/rss",
        "/feed",
    ]

    if any(
        part in path
        for part in bad_parts
    ):
        return False

    if path in [
        "",
        "/"
    ]:
        return False

    return True


def extract_search_links(
    page_html,
    base_url,
    domain
):

    soup = BeautifulSoup(
        page_html,
        "html.parser"
    )

    result = []

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        url = urljoin(
            base_url,
            href
        )

        url = url.split(
            "#",
            1
        )[0]

        if not looks_like_article_url(
            url,
            domain
        ):
            continue

        if url not in result:
            result.append(
                url
            )

    return result


def search_source_site(
    source_name,
    source_config,
    query
):

    domain = source_config[
        "domain"
    ]

    all_links = []

    encoded_query = quote_plus(
        query
    )

    for template in source_config[
        "search"
    ]:

        template_found = False

        for page in range(
            1,
            SEARCH_PAGES + 1
        ):

            url = template.format(
                query=encoded_query,
                page=page
            )

            response = http_get(
                url
            )

            if not response:

                if page == 1:
                    break

                continue

            links = extract_search_links(
                response.text,
                response.url,
                domain
            )

            new_links = [
                link

                for link in links

                if link not in all_links
            ]

            if new_links:

                template_found = True

                all_links.extend(
                    new_links
                )

            if (
                page > 1
                and
                not new_links
            ):
                break

            if "{page}" not in template:
                break

            time.sleep(
                SEARCH_DELAY
            )

        if template_found:
            break

    return all_links


# ============================================================
# ИСТОРИЧЕСКИЙ ПОИСК
# ============================================================

def history_needs_refresh(
    place_key
):

    db = db_connect()

    row = db.execute(
        """
        SELECT last_checked
        FROM history_checks
        WHERE place_key = ?
        """,
        (place_key,)
    ).fetchone()

    db.close()

    if not row:
        return True

    dt = parse_datetime(
        row["last_checked"]
    )

    if not dt:
        return True

    return (
        datetime.now(MSK)
        -
        dt
        >=
        timedelta(
            hours=
            HISTORY_REFRESH_HOURS
        )
    )


def mark_history_checked(
    place,
    region
):

    key = make_place_key(
        place,
        region
    )

    db = db_connect()

    db.execute(
        """
        INSERT INTO history_checks
        (
            place_key,
            place,
            region,
            last_checked
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(place_key)

        DO UPDATE SET
            last_checked =
                excluded.last_checked,
            place =
                excluded.place,
            region =
                excluded.region
        """,
        (
            key,
            place,
            region,
            datetime.now(
                MSK
            ).isoformat()
        )
    )

    db.commit()
    db.close()


def historical_search(
    place,
    region=None,
    force=False
):

    place_key = make_place_key(
        place,
        region
    )

    if (
        not force
        and
        not history_needs_refresh(
            place_key
        )
    ):
        return

    print()
    print(
        "=" * 70
    )

    print(
        "ИСТОРИЧЕСКИЙ ПОИСК:",
        place,
        region or ""
    )

    print(
        "ПЕРИОД: С 24.02.2022"
    )

    print(
        "=" * 70
    )

    successful_sources = 0

    for (
        source_name,
        source_config
    ) in SOURCES.items():

        source_had_response = False

        candidate_urls = []

        queries = []

        for phrase in SEARCH_PHRASES:

            queries.append(
                f'"{place}" "{phrase}"'
            )

        queries.append(
            place
        )

        for query in queries:

            try:

                urls = search_source_site(
                    source_name,
                    source_config,
                    query
                )

                if urls:
                    source_had_response = True

                for url in urls:

                    if (
                        url
                        not in candidate_urls
                    ):
                        candidate_urls.append(
                            url
                        )

            except Exception as exc:

                print(
                    "SEARCH ERROR:",
                    source_name,
                    query,
                    exc
                )

            time.sleep(
                SEARCH_DELAY
            )

        print(
            source_name,
            "кандидатов:",
            len(candidate_urls)
        )

        matched = 0

        for url in candidate_urls:

            try:

                article = parse_article(
                    url
                )

                if not article:
                    continue

                dt = article.get(
                    "published_at"
                )

                if (
                    not dt
                    or
                    dt < WAR_START
                ):
                    continue

                if not article_is_real_match(
                    article,
                    place
                ):
                    continue

                detected_region = (
                    region
                    or
                    extract_region(
                        article.get(
                            "title",
                            ""
                        )
                        + ". "
                        + article.get(
                            "body",
                            ""
                        )[:5000]
                    )
                )

                if (
                    region
                    and
                    detected_region
                    and
                    normalize_place(
                        region
                    )
                    !=
                    normalize_place(
                        detected_region
                    )
                ):
                    continue

                save_article(
                    source_name,
                    article,
                    place,
                    region
                    or
                    detected_region
                )

                matched += 1

            except Exception as exc:

                print(
                    "ARTICLE CHECK ERROR:",
                    source_name,
                    url,
                    exc
                )

        print(
            source_name,
            "подтвержденных публикаций:",
            matched
        )

        if (
            source_had_response
            or
            matched
        ):
            successful_sources += 1

    if successful_sources >= 2:

        mark_history_checked(
            place,
            region
        )

    else:

        print(
            "Историческая проверка "
            "неполная. Повторим позже."
        )


# ============================================================
# СТАТЬИ ПО НАСЕЛЕННОМУ ПУНКТУ
# ============================================================

def get_place_articles(
    place,
    region=None
):

    place_norm = normalize_place(
        place
    )

    db = db_connect()

    rows = db.execute(
        """
        SELECT *
        FROM articles

        WHERE published_at
        IS NOT NULL

        ORDER BY published_at ASC
        """
    ).fetchall()

    db.close()

    result = []

    for row in rows:

        row_place = normalize_place(
            row["place"]
            or
            ""
        )

        if row_place != place_norm:
            continue

        if (
            region
            and
            row["region"]
        ):

            if (
                normalize_place(
                    region
                )
                !=
                normalize_place(
                    row["region"]
                )
            ):
                continue

        result.append(
            dict(row)
        )

    return result


# ============================================================
# ГРУППИРОВКА ПУБЛИКАЦИЙ В ЭПИЗОДЫ
# ============================================================

def group_events(
    articles
):

    prepared = []

    for article in articles:

        dt = parse_datetime(
            article.get(
                "published_at"
            )
        )

        if not dt:
            continue

        prepared.append(
            (
                dt,
                article
            )
        )

    prepared.sort(
        key=lambda x: x[0]
    )

    events = []

    for dt, article in prepared:

        target = None

        for event in reversed(
            events
        ):

            gap = (
                dt.date()
                -
                event[
                    "last_date"
                ].date()
            ).days

            if (
                0
                <= gap
                <=
                SAME_EVENT_MAX_GAP_DAYS
            ):
                target = event
                break

            if (
                gap
                >
                SAME_EVENT_MAX_GAP_DAYS
            ):
                break

        if target is None:

            target = {
                "date":
                dt,

                "last_date":
                dt,

                "reports":
                []
            }

            events.append(
                target
            )

        existing_sources = {
            report["source"]

            for report
            in target["reports"]
        }

        if (
            article["source"]
            not in existing_sources
        ):

            target[
                "reports"
            ].append(
                article
            )

        if (
            dt
            >
            target["last_date"]
        ):

            target[
                "last_date"
            ] = dt

    return events


def confirmed_events(
    events
):

    result = []

    for event in events:

        sources = {
            report["source"]

            for report
            in event["reports"]
        }

        if (
            len(sources)
            >=
            MIN_SOURCES_PER_EVENT
        ):

            result.append(
                event
            )

    return result


# ============================================================
# ЗАЩИТА ОТ ПОВТОРНОЙ ПУБЛИКАЦИИ
# ============================================================

def events_signature(
    events
):

    pieces = []

    for event in events:

        sources = sorted(
            {
                report["source"]

                for report
                in event["reports"]
            }
        )

        pieces.append(
            event["date"]
            .strftime(
                "%Y-%m-%d"
            )
            + ":"
            + ",".join(
                sources
            )
        )

    raw = "|".join(
        pieces
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()


def was_published(
    place_key,
    signature
):

    db = db_connect()

    row = db.execute(
        """
        SELECT signature
        FROM published_posts
        WHERE place_key = ?
        """,
        (place_key,)
    ).fetchone()

    db.close()

    return bool(
        row
        and
        row["signature"]
        ==
        signature
    )


def remember_publication(
    place_key,
    signature
):

    db = db_connect()

    db.execute(
        """
        INSERT INTO published_posts
        (
            place_key,
            signature,
            published_at
        )
        VALUES (?, ?, ?)

        ON CONFLICT(place_key)

        DO UPDATE SET
            signature =
                excluded.signature,

            published_at =
                excluded.published_at
        """,
        (
            place_key,
            signature,
            datetime.now(
                MSK
            ).isoformat()
        )
    )

    db.commit()
    db.close()


# ============================================================
# TELEGRAM
# ============================================================

def telegram_source_link(
    source,
    url
):

    return (
        '<a href="'
        + html.escape(
            url,
            quote=True
        )
        + '">'
        + html.escape(
            source
        )
        + "</a>"
    )


def best_summary(
    event,
    place
):

    reports = event[
        "reports"
    ]

    candidates = []

    for report in reports:

        text = clean(
            report.get(
                "event_text",
                ""
            )
        )

        if text:
            candidates.append(
                text
            )

    if not candidates:

        return (
            "Российские СМИ "
            "сообщили об освобождении "
            f"населённого пункта {place}."
        )

    candidates.sort(
        key=lambda x: (
            0
            if
            80 <= len(x) <= 500
            else
            1,

            -len(x)
        )
    )

    return candidates[0]


def build_message(
    place,
    region,
    events
):

    location = place

    if region:

        location += (
            f", {region}"
        )

    parts = [
        (
            "⚠️ <b>"
            + html.escape(
                location
            )
            + "</b>"
        ),

        (
            "Российские СМИ "
            "неоднократно сообщали "
            "об освобождении этого "
            "населённого пункта."
        )
    ]

    for (
        index,
        event
    ) in enumerate(
        events,
        1
    ):

        date_text = (
            event["date"]
            .strftime(
                "%d.%m.%Y"
            )
        )

        summary = best_summary(
            event,
            place
        )

        links = []

        for report in event[
            "reports"
        ]:

            links.append(
                telegram_source_link(
                    report["source"],
                    report["url"]
                )
            )

        block = (
            f"<b>{index}. "
            f"{date_text}</b>\n"
            f"{html.escape(summary)}"
            "\n\n"
            "<b>Источники:</b> "
            +
            " • ".join(
                links
            )
        )

        parts.append(
            block
        )

    parts.append(
        (
            "Подтверждённых "
            "отдельных эпизодов: "
            f"<b>{len(events)}</b>."
        )
    )

    return "\n\n".join(
        parts
    )


def send_html_message(
    text
):

    if len(text) <= 4000:

        bot.send_message(
            CHANNEL_ID,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        return

    blocks = text.split(
        "\n\n"
    )

    current = ""

    for block in blocks:

        candidate = (
            current
            + "\n\n"
            + block

            if current

            else block
        )

        if len(candidate) > 3900:

            if current:

                bot.send_message(
                    CHANNEL_ID,
                    current,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )

                time.sleep(1)

            current = block

        else:

            current = candidate

    if current:

        bot.send_message(
            CHANNEL_ID,
            current,
            parse_mode="HTML",
            disable_web_page_preview=True
        )


# ============================================================
# ПРОВЕРКА ПОВТОРНОГО ОСВОБОЖДЕНИЯ
# ============================================================

def check_and_publish(
    place,
    region=None
):

    articles = get_place_articles(
        place,
        region
    )

    events = group_events(
        articles
    )

    confirmed = confirmed_events(
        events
    )

    print(
        "CHECK PLACE:",
        place,
        region or "",
        "articles=",
        len(articles),
        "confirmed_events=",
        len(confirmed)
    )

    if (
        len(confirmed)
        <
        MIN_CONFIRMED_EVENTS
    ):
        return

    signature = events_signature(
        confirmed
    )

    place_key = make_place_key(
        place,
        region
    )

    if was_published(
        place_key,
        signature
    ):
        return

    message = build_message(
        place,
        region,
        confirmed
    )

    send_html_message(
        message
    )

    remember_publication(
        place_key,
        signature
    )

    print(
        "PUBLISHED:",
        place,
        "events=",
        len(confirmed)
    )


# ============================================================
# НОВАЯ RSS-НОВОСТЬ
# ============================================================

def process_rss_entry(
    entry,
    source_name
):

    title = clean(
        getattr(
            entry,
            "title",
            ""
        )
    )

    url = clean(
        getattr(
            entry,
            "link",
            ""
        )
    )

    summary = clean(
        getattr(
            entry,
            "summary",
            ""
        )
    )

    if (
        not title
        or
        not url
    ):
        return

    if rss_already_seen(
        url
    ):
        return

    remember_rss(
        url
    )

    preview = (
        title
        + ". "
        + summary
    )

    if not contains_liberation_phrase(
        preview
    ):
        return

    place = extract_place(
        title
    )

    if not place:

        place = extract_place(
            preview
        )

    article = parse_article(
        url
    )

    if not article:

        print(
            "NO ARTICLE:",
            source_name,
            title
        )

        return

    if not article.get(
        "published_at"
    ):

        article[
            "published_at"
        ] = rss_entry_datetime(
            entry
        )

    full_text = (
        article.get(
            "title",
            ""
        )
        + ". "
        + article.get(
            "body",
            ""
        )
    )

    if not place:

        place = extract_place(
            full_text
        )

    if not place:

        print(
            "SKIP NO PLACE:",
            source_name,
            title
        )

        return

    if not article_is_real_match(
        article,
        place
    ):

        print(
            "SKIP FALSE MATCH:",
            source_name,
            title
        )

        return

    region = extract_region(
        title
        + ". "
        + summary
        + ". "
        + article.get(
            "body",
            ""
        )[:5000]
    )

    save_article(
        source_name,
        article,
        place,
        region
    )

    print()
    print(
        "NEW LIBERATION:",
        source_name,
        place,
        region or ""
    )

    # Проверяем историю этого населенного
    # пункта с 24 февраля 2022 года.

    historical_search(
        place,
        region,
        force=True
    )

    # Публикуем только если найдено минимум
    # два подтвержденных эпизода.

    check_and_publish(
        place,
        region
    )


# ============================================================
# ПРОВЕРКА ВСЕХ 5 СМИ
# ============================================================

def check_sources():

    for (
        source_name,
        source_config
    ) in SOURCES.items():

        try:

            rss_url, feed = (
                get_working_feed(
                    source_name,
                    source_config
                )
            )

            if not feed:

                print(
                    "RSS UNAVAILABLE:",
                    source_name
                )

                continue

            print(
                "RSS:",
                source_name,
                rss_url,
                "entries=",
                len(feed.entries)
            )

            entries = list(
                feed.entries[:60]
            )

            entries.reverse()

            for entry in entries:

                try:

                    process_rss_entry(
                        entry,
                        source_name
                    )

                except Exception as exc:

                    print(
                        "ENTRY ERROR:",
                        source_name,
                        exc
                    )

        except Exception as exc:

            print(
                "SOURCE ERROR:",
                source_name,
                exc
            )

        time.sleep(1)


# ============================================================
# ПОВТОРНАЯ ПРОВЕРКА
# ============================================================

def recheck_known_places():

    db = db_connect()

    rows = db.execute(
        """
        SELECT
            place,
            region,
            MAX(published_at)
            AS last_date

        FROM articles

        WHERE place
        IS NOT NULL

        GROUP BY
            place,
            region

        ORDER BY
            last_date DESC

        LIMIT 100
        """
    ).fetchall()

    db.close()

    for row in rows:

        try:

            place = row[
                "place"
            ]

            region = row[
                "region"
            ]

            if history_needs_refresh(
                make_place_key(
                    place,
                    region
                )
            ):

                historical_search(
                    place,
                    region,
                    force=False
                )

            check_and_publish(
                place,
                region
            )

        except Exception as exc:

            print(
                "RECHECK ERROR:",
                row["place"],
                exc
            )


# ============================================================
# ЗАПУСК
# ============================================================

def main():

    init_db()

    print(
        "=" * 72
    )

    print(
        "БОТ: ПОВТОРНЫЕ СООБЩЕНИЯ "
        "ОБ ОСВОБОЖДЕНИИ"
    )

    print(
        "Историческая проверка: "
        "с 24.02.2022"
    )

    print(
        "Источники:",
        ", ".join(
            SOURCES.keys()
        )
    )

    print(
        "Для подтверждения одного эпизода:",
        MIN_SOURCES_PER_EVENT,
        "разных СМИ"
    )

    print(
        "Для публикации нужно эпизодов:",
        MIN_CONFIRMED_EVENTS,
        "или больше"
    )

    print(
        "CHANNEL:",
        CHANNEL_ID
    )

    print(
        "=" * 72
    )

    while True:

        cycle_started = datetime.now(
            MSK
        )

        try:

            check_sources()

            recheck_known_places()

        except KeyboardInterrupt:

            print(
                "BOT STOPPED"
            )

            break

        except Exception as exc:

            print(
                "MAIN ERROR:",
                exc
            )

        elapsed = (
            datetime.now(MSK)
            -
            cycle_started
        ).total_seconds()

        sleep_seconds = max(
            10,
            CHECK_INTERVAL
            -
            int(elapsed)
        )

        print(
            "NEXT CHECK IN:",
            sleep_seconds,
            "sec"
        )

        time.sleep(
            sleep_seconds
        )


if __name__ == "__main__":
    main()