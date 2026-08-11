import os
import time
import json
import hashlib
import re
import html
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
import telebot


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан")

if not CHANNEL_ID:
    raise RuntimeError("CHANNEL_ID не задан")

bot = telebot.TeleBot(BOT_TOKEN)

CHECK_INTERVAL = 600
SEEN_FILE = "seen.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile Safari/604.1"
    )
}


# ============================================================
# ИСТОЧНИКИ
# ============================================================

RSS_SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Российская газета", "https://rg.ru/xml/index.xml"),
]

WEB_SOURCES = [
    (
        "Интерфакс",
        "https://www.interfax.ru/russia/",
        "https://www.interfax.ru"
    ),
    (
        "Коммерсантъ",
        "https://www.kommersant.ru/lenta",
        "https://www.kommersant.ru"
    ),
]


# ============================================================
# АТАКИ
# ============================================================

ATTACK_WORDS = [
    "бпла",
    "беспилотник",
    "беспилотника",
    "беспилотников",
    "беспилотного",
    "беспилотный",
    "дрон",
    "дрона",
    "дронов",
    "fpv",
    "fpv-дрон",

    "обстрел",
    "обстреляли",
    "обстрелян",
    "артобстрел",
    "артиллерийский обстрел",

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

    "снаряд",
    "боеприпас",

    "взрыв",
    "детонация",

    "пво",
    "противовоздушной обороны",
    "противоракетной обороны",
    "противодроновой",
    "рэб",

    "обломки",
    "падение обломков",
    "обломки бпла",
    "обломки беспилотника",
    "обломки ракеты",

    "сбитого беспилотника",
    "сбитого бпла",
    "сбитой ракеты",
]


# ============================================================
# ПОГИБШИЕ / ПОСТРАДАВШИЕ
# ============================================================

CASUALTY_WORDS = [
    "погиб",
    "погибла",
    "погибли",
    "погибло",
    "погибших",

    "пострадал",
    "пострадала",
    "пострадали",
    "пострадало",
    "пострадавших",

    "ранен",
    "ранена",
    "ранены",
    "ранено",
    "раненых",

    "получил ранение",
    "получила ранение",
    "получили ранения",

    "госпитализирован",
    "госпитализирована",
    "госпитализированы",
]


# ============================================================
# ИСКЛЮЧАЕМ ЗАРУБЕЖНЫЕ СОБЫТИЯ
# ============================================================

FOREIGN_WORDS = [
    "хусит",
    "йемен",
    "йеменск",
    "красное море",
    "баб-эль-мандеб",

    "израил",
    "сектор газа",
    "газе",
    "ливан",
    "сирия",
    "иран",
    "ирак",

    "палестин",
    "хамас",
    "хезболл",

    "судно в красном море",
    "корабль в красном море",
]


# ============================================================
# РЕГИОНЫ РФ
# ============================================================

REGIONS = {

    "Белгородская область": [
        "белгородская область",
        "белгородской области",
    ],

    "Курская область": [
        "курская область",
        "курской области",
    ],

    "Брянская область": [
        "брянская область",
        "брянской области",
    ],

    "Воронежская область": [
        "воронежская область",
        "воронежской области",
    ],

    "Ростовская область": [
        "ростовская область",
        "ростовской области",
    ],

    "Липецкая область": [
        "липецкая область",
        "липецкой области",
    ],

    "Орловская область": [
        "орловская область",
        "орловской области",
    ],

    "Тульская область": [
        "тульская область",
        "тульской области",
    ],

    "Калужская область": [
        "калужская область",
        "калужской области",
    ],

    "Московская область": [
        "московская область",
        "московской области",
        "подмосковье",
        "подмосковья",
    ],

    "Смоленская область": [
        "смоленская область",
        "смоленской области",
    ],

    "Тверская область": [
        "тверская область",
        "тверской области",
    ],

    "Рязанская область": [
        "рязанская область",
        "рязанской области",
    ],

    "Тамбовская область": [
        "тамбовская область",
        "тамбовской области",
    ],

    "Волгоградская область": [
        "волгоградская область",
        "волгоградской области",
    ],

    "Саратовская область": [
        "саратовская область",
        "саратовской области",
    ],

    "Самарская область": [
        "самарская область",
        "самарской области",
    ],

    "Оренбургская область": [
        "оренбургская область",
        "оренбургской области",
    ],

    "Нижегородская область": [
        "нижегородская область",
        "нижегородской области",
    ],

    "Ленинградская область": [
        "ленинградская область",
        "ленинградской области",
    ],

    "Краснодарский край": [
        "краснодарский край",
        "краснодарского края",
        "кубани",
    ],

    "Ставропольский край": [
        "ставропольский край",
        "ставропольского края",
    ],

    "Пермский край": [
        "пермский край",
        "пермского края",
    ],

    "Республика Татарстан": [
        "республика татарстан",
        "республике татарстан",
        "татарстан",
        "татарстана",
    ],

    "Республика Башкортостан": [
        "республика башкортостан",
        "башкортостан",
        "башкирии",
    ],

    "Республика Дагестан": [
        "республика дагестан",
        "дагестан",
        "дагестане",
    ],

    "Республика Крым": [
        "республика крым",
        "крым",
        "крыму",
    ],

    "Республика Адыгея": [
        "адыгея",
        "адыгее",
    ],

    "Республика Северная Осетия — Алания": [
        "северная осетия",
        "северной осетии",
    ],

    "Чеченская Республика": [
        "чечня",
        "чечне",
        "чеченская республика",
    ],

    "Республика Ингушетия": [
        "ингушетия",
        "ингушетии",
    ],

    "Москва": [
        "москва",
        "москве",
    ],

    "Санкт-Петербург": [
        "санкт-петербург",
        "санкт-петербурге",
        "петербург",
        "петербурге",
    ],

    "Севастополь": [
        "севастополь",
        "севастополе",
    ],
}


# ============================================================
# ИЗВЕСТНЫЕ НАСЕЛЁННЫЕ ПУНКТЫ
# ============================================================

KNOWN_CITIES = {

    "белгород": "Белгород",
    "шебекино": "Шебекино",
    "грайворон": "Грайворон",
    "валуйки": "Валуйки",
    "старый оскол": "Старый Оскол",
    "губкин": "Губкин",
    "октябрьский": "Октябрьский",

    "курск": "Курск",
    "рыльск": "Рыльск",
    "льгов": "Льгов",
    "железногорск": "Железногорск",
    "суджа": "Суджа",

    "брянск": "Брянск",
    "клинцы": "Клинцы",
    "стародуб": "Стародуб",

    "воронеж": "Воронеж",
    "лиски": "Лиски",
    "борисоглебск": "Борисоглебск",

    "ростов-на-дону": "Ростов-на-Дону",
    "таганрог": "Таганрог",
    "азов": "Азов",
    "батайск": "Батайск",
    "новочеркасск": "Новочеркасск",
    "шахты": "Шахты",

    "краснодар": "Краснодар",
    "сочи": "Сочи",
    "анапа": "Анапа",
    "геленджик": "Геленджик",
    "новороссийск": "Новороссийск",
    "туапсе": "Туапсе",
    "славянск-на-кубани": "Славянск-на-Кубани",

    "нижнекамск": "Нижнекамск",
    "казань": "Казань",
    "елабуга": "Елабуга",
    "альметьевск": "Альметьевск",

    "москва": "Москва",
    "севастополь": "Севастополь",
}


# ============================================================
# ЧИСЛА
# ============================================================

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


NUM_TOKEN = (
    r"(?:\d+|"
    + "|".join(
        sorted(
            map(re.escape, NUMBER_WORDS.keys()),
            key=len,
            reverse=True
        )
    )
    + r")"
)


# ============================================================
# ОЧИСТКА
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(text)

    soup = BeautifulSoup(
        text,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

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

    return text.strip()


# ============================================================
# SEEN
# ============================================================

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
            "Ошибка seen:",
            e
        )


def make_id(url):

    return hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()


# ============================================================
# ЧИСЛО ИЗ ТЕКСТА
# ============================================================

def number_value(value):

    if not value:
        return None

    value = value.lower().strip()

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


# ============================================================
# ПРЕДЛОЖЕНИЯ
# ============================================================

def split_sentences(text):

    return [
        sentence.strip()

        for sentence in re.split(
            r"(?<=[.!?])\s+",
            clean_text(text)
        )

        if len(
            sentence.strip()
        ) > 10
    ]


# ============================================================
# ЧТЕНИЕ СТАТЬИ
# ============================================================

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

        for tag in soup([
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "aside",
            "form"
        ]):

            tag.decompose()

        paragraphs = []

        for p in soup.find_all("p"):

            text = clean_text(
                p.get_text(
                    " ",
                    strip=True
                )
            )

            if len(text) >= 25:

                paragraphs.append(
                    text
                )

        return " ".join(
            paragraphs[:20]
        )

    except Exception as e:

        print(
            "Ошибка статьи:",
            url,
            e
        )

        return ""


# ============================================================
# РЕГИОН
# ============================================================

def detect_region(text):

    low = clean_text(
        text
    ).lower()

    found = []

    for canonical, variants in REGIONS.items():

        for variant in variants:

            pos = low.find(
                variant
            )

            if pos >= 0:

                found.append(
                    (
                        pos,
                        canonical
                    )
                )

    if not found:
        return None

    found.sort(
        key=lambda x: x[0]
    )

    return found[0][1]


# ============================================================
# ГОРОД
# ============================================================

def detect_city(text, region=None):

    clean = clean_text(text)
    low = clean.lower()

    positions = []

    for variant, canonical in KNOWN_CITIES.items():

        match = re.search(
            r"\b"
            + re.escape(variant)
            + r"\b",
            low
        )

        if match:

            positions.append(
                (
                    match.start(),
                    canonical
                )
            )

    if positions:

        positions.sort(
            key=lambda x: x[0]
        )

        city = positions[0][1]

        # Интерфакс часто начинает статью словом "Москва",
        # хотя само событие произошло в другом регионе.
        if (
            city == "Москва"
            and region
            and region != "Москва"
        ):

            for _, candidate in positions[1:]:

                if candidate != "Москва":
                    return candidate

            return None

        return city

    patterns = [

        r"(?:городе|город|г\.)\s+"
        r"([А-ЯЁ][а-яё-]+(?:-[А-ЯЁа-яё-]+)?)",

        r"(?:поселке|посёлке|поселок|посёлок)\s+"
        r"([А-ЯЁ][а-яё-]+(?:-[А-ЯЁа-яё-]+)?)",

        r"(?:селе|село)\s+"
        r"([А-ЯЁ][а-яё-]+(?:-[А-ЯЁа-яё-]+)?)",

        r"(?:деревне|деревня)\s+"
        r"([А-ЯЁ][а-яё-]+(?:-[А-ЯЁа-яё-]+)?)",

        r"(?:хуторе|хутор)\s+"
        r"([А-ЯЁ][а-яё-]+(?:-[А-ЯЁа-яё-]+)?)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            clean
        )

        if match:

            return match.group(1)

    return None


# ============================================================
# ПРОВЕРКА РЕЛЕВАНТНОСТИ
# ============================================================

def relevant(text):

    text = clean_text(text)
    low = text.lower()

    if not text:
        return False

    # Зарубежные события исключаем.
    if any(
        word in low
        for word in FOREIGN_WORDS
    ):

        return False

    # Обязательно должен определяться регион РФ.
    region = detect_region(text)

    if not region:
        return False

    # Должен быть признак атаки.
    has_attack = any(
        word in low
        for word in ATTACK_WORDS
    )

    if not has_attack:
        return False

    # Должны быть погибшие или пострадавшие.
    has_casualties = any(
        word in low
        for word in CASUALTY_WORDS
    )

    if not has_casualties:
        return False

    # ДТП без связи с атакой исключаем.
    if "дтп" in low:

        strong_attack = any(
            word in low
            for word in [
                "бпла",
                "беспилот",
                "дрон",
                "обстрел",
                "ракет",
                "атаковал",
                "атаковали",
            ]
        )

        if not strong_attack:
            return False

    return True


# ============================================================
# ПОГИБШИЕ
# ============================================================

def extract_dead(text):

    low = clean_text(
        text
    ).lower().replace(
        "ё",
        "е"
    )

    patterns = [

        rf"(?:погибли|погибло)\s+"
        rf"(?:как минимум\s+|не менее\s+)?"
        rf"({NUM_TOKEN})",

        rf"({NUM_TOKEN})\s+"
        rf"(?:человек[а-я]*\s+)?"
        rf"(?:погибли|погибло)",

        rf"(?:погиб|погибла)\s+"
        rf"({NUM_TOKEN})",

        rf"(?:число|количество)\s+"
        rf"погибших[^.!?]{{0,70}}?"
        rf"\bдо\s+({NUM_TOKEN})",

        rf"(?:число|количество)\s+"
        rf"жертв[^.!?]{{0,70}}?"
        rf"\bдо\s+({NUM_TOKEN})",

        rf"погибших\s+"
        rf"(?:насчитывается\s+)?"
        rf"({NUM_TOKEN})",
    ]

    values = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            low,
            flags=re.IGNORECASE
        ):

            value = number_value(
                match.group(1)
            )

            if value is not None:

                values.append(
                    value
                )

    if values:

        return max(values)

    if re.search(
        r"\bпогиб(?:ла)?\s+"
        r"(?:мужчина|женщина|ребенок|ребёнок|водитель|человек)\b",
        low
    ):

        return 1

    return None


# ============================================================
# ПОСТРАДАВШИЕ
# ============================================================

def extract_injured(text):

    low = clean_text(
        text
    ).lower().replace(
        "ё",
        "е"
    )

    patterns = [

        rf"(?:пострадали|пострадало)\s+"
        rf"(?:как минимум\s+|не менее\s+)?"
        rf"({NUM_TOKEN})",

        rf"({NUM_TOKEN})\s+"
        rf"(?:человек[а-я]*\s+)?"
        rf"(?:пострадали|пострадало)",

        rf"(?:пострадал|пострадала)\s+"
        rf"({NUM_TOKEN})",

        rf"(?:ранены|ранено)\s+"
        rf"(?:как минимум\s+|не менее\s+)?"
        rf"({NUM_TOKEN})",

        rf"({NUM_TOKEN})\s+"
        rf"(?:человек[а-я]*\s+)?"
        rf"(?:ранены|ранено)",

        rf"({NUM_TOKEN})\s+"
        rf"(?:человек[а-я]*\s+)?"
        rf"получил[аи]?\s+"
        rf"(?:различные\s+)?ранения",

        rf"(?:число|количество)\s+"
        rf"пострадавших[^.!?]{{0,70}}?"
        rf"\bдо\s+({NUM_TOKEN})",

        rf"(?:число|количество)\s+"
        rf"раненых[^.!?]{{0,70}}?"
        rf"\bдо\s+({NUM_TOKEN})",

        rf"пострадавших\s+"
        rf"(?:насчитывается\s+)?"
        rf"({NUM_TOKEN})",
    ]

    values = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            low,
            flags=re.IGNORECASE
        ):

            value = number_value(
                match.group(1)
            )

            if value is not None:

                values.append(
                    value
                )

    if values:

        return max(values)

    if re.search(
        r"\b(?:пострадал|пострадала|ранен|ранена)\s+"
        r"(?:мужчина|женщина|ребенок|ребёнок|водитель|человек)\b",
        low
    ):

        return 1

    return None


# ============================================================
# КРАТКОЕ ОПИСАНИЕ
# ============================================================

def make_description(title, text):

    sentences = split_sentences(
        text
    )

    selected = []

    for sentence in sentences:

        low = sentence.lower()

        if any(
            attack_word in low
            for attack_word in ATTACK_WORDS
        ):

            selected.append(
                sentence
            )

        if len(selected) >= 2:
            break

    if not selected:

        selected = [
            clean_text(title)
        ]

    result = " ".join(
        selected
    )

    # Убираем служебную вводную Интерфакса.
    result = re.sub(
        r"^Москва\.\s*"
        r"\d{1,2}\s+[а-яё]+\.\s*"
        r"INTERFAX\.RU\s*[-–—]?\s*",
        "",
        result,
        flags=re.IGNORECASE
    )

    result = re.sub(
        r"^INTERFAX\.RU\s*[-–—]\s*",
        "",
        result,
        flags=re.IGNORECASE
    )

    if len(result) > 450:

        result = (
            result[:447]
            .rsplit(
                " ",
                1
            )[0]
            + "..."
        )

    return result.strip()


# ============================================================
# ФОРМАТ ПОСТА
# ============================================================

def build_message(
    source,
    title,
    description,
    article,
    link
):

    full_text = " ".join([
        clean_text(title),
        clean_text(description),
        clean_text(article),
    ])

    if not relevant(
        full_text
    ):

        return None

    dead = extract_dead(
        full_text
    )

    injured = extract_injured(
        full_text
    )

    # Если число ни погибших, ни пострадавших
    # определить не удалось — не публикуем.
    if (
        dead is None
        and injured is None
    ):

        return None

    article_sentences = split_sentences(
        article
    )

    # Для географии используем только начало новости,
    # а не весь HTML сайта.
    location_text = " ".join([
        clean_text(title),
        clean_text(description),
        " ".join(
            article_sentences[:4]
        ),
    ])

    region = detect_region(
        location_text
    )

    city = detect_city(
        location_text,
        region
    )

    if city and region:

        location = (
            f"{city}, {region}"
        )

    elif region:

        location = region

    elif city:

        location = city

    else:

        return None

    situation = make_description(
        title,
        " ".join(
            article_sentences[:6]
        )
        or description
    )

    # Экранируем текст для HTML Telegram.
    safe_location = html.escape(
        location
    )

    safe_situation = html.escape(
        situation
    )

    safe_source = html.escape(
        source
    )

    safe_link = html.escape(
        link,
        quote=True
    )

    lines = [
        f"⚡️<b>{safe_location}</b>",
        "",
        safe_situation,
        "",
    ]

    if dead is not None:

        lines.append(
            f"<b>Погибли: {dead} человек</b>"
        )

    if injured is not None:

        lines.append(
            f"<b>Пострадали: {injured} человек</b>"
        )

    lines.extend([
        "",
        (
            "Источник: "
            f'<a href="{safe_link}">'
            f'{safe_source}'
            f'</a>'
        ),
    ])

    return "\n".join(
        lines
    )


# ============================================================
# ПУБЛИКАЦИЯ
# ============================================================

def publish(
    source,
    title,
    description,
    link,
    seen
):

    uid = make_id(
        link
    )

    if uid in seen:
        return

    article = get_article_text(
        link
    )

    message = build_message(
        source,
        title,
        description,
        article,
        link
    )

    if not message:

        seen.add(
            uid
        )

        save_seen(
            seen
        )

        return

    try:

        bot.send_message(
            CHANNEL_ID,
            message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        print(
            "Опубликовано:",
            source,
            title
        )

        seen.add(
            uid
        )

        save_seen(
            seen
        )

        time.sleep(2)

    except Exception as e:

        print(
            "Ошибка Telegram:",
            source,
            e
        )


# ============================================================
# RSS
# ============================================================

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
                    or getattr(
                        entry,
                        "summary",
                        ""
                    )
                )

                link = getattr(
                    entry,
                    "link",
                    ""
                )

                if (
                    not title
                    or not link
                ):

                    continue

                uid = make_id(
                    link
                )

                if uid in seen:
                    continue

                publish(
                    source,
                    title,
                    description,
                    link,
                    seen
                )

        except Exception as e:

            print(
                "RSS:",
                source,
                e
            )


# ============================================================
# ИНТЕРФАКС / КОММЕРСАНТЪ
# ============================================================

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

            base_domain = urlparse(
                base_url
            ).netloc

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

                link = urljoin(
                    base_url,
                    a["href"]
                )

                link_domain = urlparse(
                    link
                ).netloc

                if (
                    link_domain
                    != base_domain
                ):

                    continue

                # Зарубежный раздел Интерфакса исключаем.
                if (
                    source == "Интерфакс"
                    and "/world/" in link
                ):

                    continue

                low_title = (
                    title.lower()
                )

                # Сначала проверяем хотя бы наличие
                # признака атаки или человеческих потерь.
                if not (
                    any(
                        word in low_title
                        for word in ATTACK_WORDS
                    )
                    or any(
                        word in low_title
                        for word in CASUALTY_WORDS
                    )
                ):

                    continue

                links[link] = title

            for (
                link,
                title
            ) in list(
                links.items()
            )[:30]:

                publish(
                    source,
                    title,
                    "",
                    link,
                    seen
                )

        except Exception as e:

            print(
                "WEB:",
                source,
                e
            )


# ============================================================
# ПРОВЕРКА ВСЕХ СМИ
# ============================================================

def check_news():

    seen = load_seen()

    print(
        "Начинаю проверку СМИ"
    )

    check_rss(
        seen
    )

    check_web(
        seen
    )

    print(
        "Проверка СМИ завершена"
    )


# ============================================================
# ЗАПУСК
# ============================================================

print(
    "Monitoring started"
)

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