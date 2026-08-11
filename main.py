import os
import time
import json
import hashlib
import re
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
import telebot


# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")

if not CHANNEL_ID:
    raise RuntimeError("CHANNEL_ID не задан")

bot = telebot.TeleBot(BOT_TOKEN)

CHECK_INTERVAL = 600  # проверка каждые 10 минут
SEEN_FILE = "seen.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
    )
}


# =========================================================
# ИСТОЧНИКИ
# =========================================================

RSS_SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Российская газета", "https://rg.ru/xml/index.xml"),
]

WEB_SOURCES = [
    (
        "Интерфакс",
        "https://www.interfax.ru/",
        "https://www.interfax.ru"
    ),
    (
        "Коммерсантъ",
        "https://www.kommersant.ru/lenta",
        "https://www.kommersant.ru"
    ),
]


# =========================================================
# ФИЛЬТР АТАК
# =========================================================

ATTACK_WORDS = [
    "бпла",
    "беспилотник",
    "беспилотника",
    "беспилотников",
    "беспилотный",
    "дрон",
    "дрона",
    "дронов",

    "обстрел",
    "обстреляли",
    "обстрелян",
    "артиллерийский",

    "ракетный удар",
    "ракетная атака",
    "ракетный обстрел",
    "ракета",
    "ракеты",

    "атака",
    "атаковал",
    "атаковала",
    "атаковали",

    "удар",
    "удары",

    "взрыв",
    "взрыва",

    "боеприпас",
    "снаряд",

    "пво",
    "противовоздушной обороны",
    "противоракетной обороны",
    "противодроновой",

    "обломки",
    "падение обломков",
    "обломки беспилотника",
    "обломки бпла",
    "обломки ракеты",

    "сбитого беспилотника",
    "сбитого бпла",
    "сбитой ракеты",
]


# =========================================================
# ПОГИБШИЕ / ПОСТРАДАВШИЕ
# =========================================================

CASUALTY_WORDS = [
    "погиб",
    "погибла",
    "погибли",
    "погибло",

    "пострадал",
    "пострадала",
    "пострадали",
    "пострадало",

    "ранен",
    "ранена",
    "ранены",
    "ранено",

    "получил ранение",
    "получила ранение",
    "получили ранения",

    "госпитализирован",
    "госпитализирована",
    "госпитализированы",
]


# =========================================================
# ИСКЛЮЧЕНИЯ
# =========================================================

EXCLUDE_WORDS = [
    "дтп",
    "авария",
    "автоавария",
    "столкновение автомобилей",
    "утонул",
    "утонула",
    "отравление",
]


# =========================================================
# ЧИСЛА СЛОВАМИ
# =========================================================

NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "одного": 1,

    "два": 2,
    "двое": 2,
    "двух": 2,

    "три": 3,
    "трое": 3,
    "трех": 3,
    "трёх": 3,

    "четыре": 4,
    "четверо": 4,
    "четырех": 4,
    "четырёх": 4,

    "пять": 5,
    "пятеро": 5,

    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}


# =========================================================
# РЕГИОНЫ
# =========================================================

REGIONS = [
    "Белгородская область",
    "Брянская область",
    "Курская область",
    "Воронежская область",
    "Ростовская область",
    "Московская область",
    "Липецкая область",
    "Орловская область",
    "Тульская область",
    "Калужская область",
    "Смоленская область",
    "Тамбовская область",
    "Саратовская область",
    "Волгоградская область",

    "Краснодарский край",
    "Ставропольский край",

    "Республика Крым",
    "Крым",

    "Республика Адыгея",
    "Республика Дагестан",
    "Республика Северная Осетия — Алания",

    "Москва",
    "Севастополь",
]


# =========================================================
# ОЧИСТКА ТЕКСТА
# =========================================================

def clean_text(text):

    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")

    text = soup.get_text(
        " ",
        strip=True
    )

    text = " ".join(text.split())

    bad = [
        "if you are not a bot",
        "verify you are human",
        "access denied",
        "captcha",
        "support team",
        "datetime:",
    ]

    lower = text.lower()

    for phrase in bad:

        if phrase in lower:
            return ""

    return text


# =========================================================
# УЖЕ ОБРАБОТАННЫЕ НОВОСТИ
# =========================================================

def load_seen():

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return set(
                json.load(f)
            )

    except Exception:

        return set()


def save_seen(seen):

    try:

        with open(
            SEEN_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                list(seen),
                f,
                ensure_ascii=False
            )

    except Exception as e:

        print(
            "Ошибка сохранения seen:",
            e
        )


def make_id(url):

    return hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()


# =========================================================
# ПРОВЕРКА РЕЛЕВАНТНОСТИ
# =========================================================

def relevant(text):

    text = clean_text(text).lower()

    if not text:
        return False

    if any(
        word in text
        for word in EXCLUDE_WORDS
    ):
        return False

    attack = any(
        word in text
        for word in ATTACK_WORDS
    )

    casualties = any(
        word in text
        for word in CASUALTY_WORDS
    )

    return attack and casualties


# =========================================================
# ЧТЕНИЕ СТАТЬИ
# =========================================================

def get_article_text(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        parts = []

        for p in soup.find_all("p"):

            text = clean_text(
                p.get_text(
                    " ",
                    strip=True
                )
            )

            if len(text) >= 30:

                parts.append(text)

        result = " ".join(parts)

        return clean_text(result)

    except Exception as e:

        print(
            "Ошибка чтения статьи:",
            url,
            e
        )

        return ""


# =========================================================
# ИЗВЛЕЧЕНИЕ ЧИСЛА
# =========================================================

def number_from_text(text):

    match = re.search(
        r"\b(\d+)\b",
        text
    )

    if match:

        return int(
            match.group(1)
        )

    lower = text.lower()

    for word, number in NUMBER_WORDS.items():

        if re.search(
            r"\b" +
            re.escape(word) +
            r"\b",
            lower
        ):

            return number

    return None


# =========================================================
# ПОГИБШИЕ
# =========================================================

def extract_dead(text):

    sentences = re.split(
        r'(?<=[.!?])\s+',
        text
    )

    words = [
        "погиб",
        "погибла",
        "погибли",
        "погибло"
    ]

    for sentence in sentences:

        lower = sentence.lower()

        if not any(
            word in lower
            for word in words
        ):
            continue

        number = number_from_text(
            sentence
        )

        if number is not None:
            return number

        if (
            "погибла" in lower
            or re.search(
                r"\bпогиб\b",
                lower
            )
        ):
            return 1

    return None


# =========================================================
# ПОСТРАДАВШИЕ
# =========================================================

def extract_injured(text):

    sentences = re.split(
        r'(?<=[.!?])\s+',
        text
    )

    words = [
        "пострадал",
        "пострадала",
        "пострадали",
        "пострадало",
        "ранен",
        "ранена",
        "ранены",
        "ранено"
    ]

    for sentence in sentences:

        lower = sentence.lower()

        if not any(
            word in lower
            for word in words
        ):
            continue

        number = number_from_text(
            sentence
        )

        if number is not None:
            return number

        if (
            "пострадал" in lower
            or "пострадала" in lower
            or "ранен" in lower
            or "ранена" in lower
        ):
            return 1

    return None


# =========================================================
# ДЕТИ
# =========================================================

def extract_children(text):

    sentences = re.split(
        r'(?<=[.!?])\s+',
        text
    )

    for sentence in sentences:

        lower = sentence.lower()

        if not any(
            x in lower
            for x in [
                "ребенок",
                "ребёнок",
                "ребенка",
                "ребёнка",
                "детей",
                "дети"
            ]
        ):
            continue

        if not any(
            x in lower
            for x in CASUALTY_WORDS
        ):
            continue

        number = number_from_text(
            sentence
        )

        if number is not None:
            return number

        return 1

    return None


# =========================================================
# РЕГИОН
# =========================================================

def detect_region(text):

    lower = text.lower()

    for region in REGIONS:

        if region.lower() in lower:
            return region

    return ""


# =========================================================
# НАСЕЛЕННЫЙ ПУНКТ
# =========================================================

def detect_settlement(title, text):

    combined = (
        title + ". " + text
    )

    patterns = [

        r"(?:городе|город|г\.)\s+([А-ЯЁ][А-Яа-яёЁ\-]+)",

        r"(?:селе|село)\s+([А-ЯЁ][А-Яа-яёЁ\-]+)",

        r"(?:поселке|посёлке|поселок|посёлок)\s+"
        r"([А-ЯЁ][А-Яа-яёЁ\-]+)",

        r"(?:деревне|деревня)\s+([А-ЯЁ][А-Яа-яёЁ\-]+)",

        r"(?:хуторе|хутор)\s+([А-ЯЁ][А-Яа-яёЁ\-]+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            combined
        )

        if match:

            return match.group(1)

    # Частый вариант заголовка:
    # "В Белгороде..."
    # "В Шебекино..."

    match = re.search(
        r"^В\s+([А-ЯЁ][А-Яа-яёЁ\-]+)",
        title
    )

    if match:

        candidate = match.group(1)

        forbidden = [
            "России",
            "области",
            "результате",
            "регионе"
        ]

        if candidate not in forbidden:
            return candidate

    return ""


# =========================================================
# ЛОКАЦИЯ
# =========================================================

def detect_location(title, text):

    combined = (
        title + ". " + text
    )

    region = detect_region(
        combined
    )

    settlement = detect_settlement(
        title,
        combined
    )

    if settlement and region:

        return (
            f"{settlement}, "
            f"{region}"
        )

    if region:

        return region

    if settlement:

        return settlement

    return "Место уточняется"


# =========================================================
# КРАТКОЕ ОПИСАНИЕ ПРОИСШЕСТВИЯ
# =========================================================

def make_description(title, text):

    text = clean_text(text)

    if not text:

        return clean_text(title)

    sentences = re.split(
        r'(?<=[.!?])\s+',
        text
    )

    attack_sentence = ""
    casualty_sentence = ""

    for sentence in sentences:

        lower = sentence.lower()

        if (
            not attack_sentence
            and any(
                word in lower
                for word in ATTACK_WORDS
            )
        ):

            attack_sentence = sentence.strip()

        if (
            not casualty_sentence
            and any(
                word in lower
                for word in CASUALTY_WORDS
            )
        ):

            casualty_sentence = sentence.strip()

        if (
            attack_sentence
            and casualty_sentence
        ):
            break

    result = []

    if attack_sentence:

        result.append(
            attack_sentence
        )

    if (
        casualty_sentence
        and casualty_sentence
        != attack_sentence
    ):

        result.append(
            casualty_sentence
        )

    if not result:

        result.append(
            clean_text(title)
        )

    description = " ".join(result)

    if len(description) > 400:

        description = (
            description[:400]
            .rsplit(" ", 1)[0]
            + "…"
        )

    return description


# =========================================================
# СКЛОНЕНИЕ "ЧЕЛОВЕК"
# =========================================================

def human_count(number):

    if number is None:

        return "количество уточняется"

    if number == 0:

        return "0"

    return f"{number} человек"


# =========================================================
# ФОРМИРОВАНИЕ ПОСТА
# =========================================================

def format_post(
    source,
    title,
    description,
    article,
    url
):

    full_text = " ".join([
        title,
        description,
        article
    ])

    location = detect_location(
        title,
        full_text
    )

    dead = extract_dead(
        full_text
    )

    injured = extract_injured(
        full_text
    )

    children = extract_children(
        full_text
    )

    situation = make_description(
        title,
        article or description
    )

    post = (
        f"⚡️{location}\n\n"
        f"{situation}\n\n"
        f"Погибли: {human_count(dead)}\n"
        f"Пострадали: {human_count(injured)}"
    )

    if children is not None:

        post += (
            f"\nИз них детей: "
            f"{children}"
        )

    post += (
        f"\n\nИсточник: {source}\n"
        f"{url}"
    )

    return post


# =========================================================
# ПУБЛИКАЦИЯ
# =========================================================

def publish(
    source,
    title,
    description,
    url,
    seen
):

    uid = make_id(url)

    if uid in seen:
        return

    article = get_article_text(
        url
    )

    full_text = " ".join([
        title,
        description,
        article
    ])

    if not relevant(full_text):
        return

    post = format_post(
        source,
        title,
        description,
        article,
        url
    )

    bot.send_message(
        CHANNEL_ID,
        post,
        disable_web_page_preview=True
    )

    print(
        "Опубликовано:",
        source,
        title
    )

    seen.add(uid)

    save_seen(seen)

    time.sleep(2)


# =========================================================
# RSS
# =========================================================

def check_rss(seen):

    for source, rss_url in RSS_SOURCES:

        try:

            feed = feedparser.parse(
                rss_url
            )

            for entry in feed.entries[:40]:

                title = clean_text(
                    getattr(
                        entry,
                        "title",
                        ""
                    )
                )

                description = clean_text(
                    getattr(
                        entry,
                        "description",
                        ""
                    )
                )

                url = getattr(
                    entry,
                    "link",
                    ""
                )

                if not title or not url:
                    continue

                preliminary = (
                    title
                    + " "
                    + description
                )

                if not relevant(
                    preliminary
                ):
                    continue

                publish(
                    source,
                    title,
                    description,
                    url,
                    seen
                )

        except Exception as e:

            print(
                "RSS:",
                source,
                e
            )


# =========================================================
# ИНТЕРФАКС / КОММЕРСАНТЪ
# =========================================================

def check_web(seen):

    for (
        source,
        page_url,
        base_url
    ) in WEB_SOURCES:

        try:

            response = requests.get(
                page_url,
                headers=HEADERS,
                timeout=15
            )

            if response.status_code != 200:

                print(
                    source,
                    "HTTP",
                    response.status_code
                )

                continue

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            links = {}

            for a in soup.find_all(
                "a",
                href=True
            ):

                title = clean_text(
                    a.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(title) < 20:
                    continue

                url = urljoin(
                    base_url,
                    a["href"]
                )

                if base_url not in url:
                    continue

                if relevant(title):

                    links[url] = title

            for (
                url,
                title
            ) in list(
                links.items()
            )[:20]:

                publish(
                    source,
                    title,
                    "",
                    url,
                    seen
                )

        except Exception as e:

            print(
                "WEB:",
                source,
                e
            )


# =========================================================
# ОБЩАЯ ПРОВЕРКА
# =========================================================

def check_news():

    seen = load_seen()

    print(
        "Начинаю проверку СМИ"
    )

    check_rss(seen)

    check_web(seen)

    print(
        "Проверка СМИ завершена"
    )


# =========================================================
# ЗАПУСК
# =========================================================

print("Monitoring started")

while True:

    try:

        check_news()

    except Exception as e:

        print(
            "Ошибка основного цикла:",
            e
        )

    time.sleep(
        CHECK_INTERVAL
    )