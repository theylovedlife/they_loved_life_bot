import os
import time
import json
import hashlib
import re
import html
import feedparser
import requests
from bs4 import BeautifulSoup
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

# ============================================================
# ИСТОЧНИКИ
# ============================================================

SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Российская газета", "https://rg.ru/xml/index.xml"),
    ("Интерфакс", "https://www.interfax.ru/rss.asp"),
]

# ============================================================
# РЕГИОНЫ РОССИИ
# ============================================================

REGIONS = [
    "Белгородская область",
    "Брянская область",
    "Курская область",
    "Воронежская область",
    "Ростовская область",
    "Липецкая область",
    "Орловская область",
    "Тульская область",
    "Московская область",
    "Ленинградская область",
    "Смоленская область",
    "Калужская область",
    "Тверская область",
    "Рязанская область",
    "Тамбовская область",
    "Саратовская область",
    "Волгоградская область",
    "Астраханская область",
    "Самарская область",
    "Ульяновская область",
    "Нижегородская область",
    "Оренбургская область",
    "Пензенская область",
    "Ярославская область",
    "Ивановская область",
    "Владимирская область",
    "Костромская область",
    "Вологодская область",
    "Новгородская область",
    "Псковская область",
    "Мурманская область",
    "Архангельская область",
    "Калининградская область",
    "Свердловская область",
    "Челябинская область",
    "Тюменская область",
    "Курганская область",
    "Омская область",
    "Новосибирская область",
    "Томская область",
    "Кемеровская область",
    "Иркутская область",
    "Амурская область",
    "Магаданская область",
    "Сахалинская область",
    "Запорожская область",
    "Херсонская область",

    "Краснодарский край",
    "Ставропольский край",
    "Пермский край",
    "Красноярский край",
    "Алтайский край",
    "Забайкальский край",
    "Приморский край",
    "Хабаровский край",
    "Камчатский край",

    "Республика Татарстан",
    "Республика Башкортостан",
    "Республика Дагестан",
    "Республика Крым",
    "Республика Адыгея",
    "Республика Калмыкия",
    "Республика Ингушетия",
    "Чеченская Республика",
    "Кабардино-Балкарская Республика",
    "Карачаево-Черкесская Республика",
    "Республика Северная Осетия",
    "Республика Мордовия",
    "Республика Марий Эл",
    "Чувашская Республика",
    "Удмуртская Республика",
    "Республика Коми",
    "Республика Карелия",
    "Республика Алтай",
    "Республика Тыва",
    "Республика Хакасия",
    "Республика Бурятия",
    "Республика Саха",

    "Москва",
    "Санкт-Петербург",
    "Севастополь",

    "Луганская Народная Республика",
    "Донецкая Народная Республика",
]

# ============================================================
# ГОРОД → РЕГИОН
# ============================================================

CITY_REGION = {
    "Белгород": "Белгородская область",
    "Шебекино": "Белгородская область",
    "Грайворон": "Белгородская область",
    "Валуйки": "Белгородская область",

    "Курск": "Курская область",
    "Курчатов": "Курская область",
    "Рыльск": "Курская область",
    "Суджа": "Курская область",
    "Льгов": "Курская область",

    "Брянск": "Брянская область",
    "Клинцы": "Брянская область",

    "Воронеж": "Воронежская область",

    "Ростов-на-Дону": "Ростовская область",
    "Таганрог": "Ростовская область",
    "Новочеркасск": "Ростовская область",

    "Краснодар": "Краснодарский край",
    "Сочи": "Краснодарский край",
    "Новороссийск": "Краснодарский край",
    "Туапсе": "Краснодарский край",
    "Анапа": "Краснодарский край",

    "Казань": "Республика Татарстан",
    "Нижнекамск": "Республика Татарстан",
    "Елабуга": "Республика Татарстан",

    "Симферополь": "Республика Крым",
    "Керчь": "Республика Крым",
    "Джанкой": "Республика Крым",
    "Евпатория": "Республика Крым",

    "Севастополь": "Севастополь",

    "Москва": "Москва",
    "Санкт-Петербург": "Санкт-Петербург",
}

# ============================================================
# ТОЛЬКО АТАКИ / ОБСТРЕЛЫ / БПЛА / РАКЕТЫ / ПВО
# ============================================================

ATTACK_WORDS = [
    "бпла",
    "беспилотник",
    "беспилотников",
    "дрон",
    "fpv",
    "атака",
    "атаковал",
    "атаковали",
    "обстрел",
    "обстреляли",
    "ракет",
    "ракета",
    "удар",
    "взрыв",
    "пво",
    "противовоздуш",
    "сбит",
    "сбили",
    "обломк",
    "падение обломков",
]

CASUALTY_WORDS = [
    "погиб",
    "погибли",
    "погибла",
    "погибло",
    "погибших",
    "жертв",
    "пострадал",
    "пострадали",
    "пострадала",
    "пострадало",
    "пострадавших",
    "ранен",
    "ранены",
    "ранена",
    "раненых",
]

# Отсекаем явно нероссийские события
FOREIGN_WORDS = [
    "израиль",
    "газа",
    "сектор газа",
    "йемен",
    "хусит",
    "иран",
    "ирак",
    "сирия",
    "ливан",
    "украине",
    "украина",
    "киев",
    "харьков",
    "одесса",
    "днепр",
    "львов",
    "запорожье",
    "херсон",
    "сша",
    "американск",
]

# ============================================================
# SEEN
# ============================================================

SEEN_FILE = "seen.json"


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen)[-5000:], f, ensure_ascii=False)
    except Exception as e:
        print("save_seen:", e)


# ============================================================
# ЗАГРУЗКА СТАТЬИ
# ============================================================

def get_article_text(url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1"
            )
        }

        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
        ]):
            tag.decompose()

        paragraphs = []

        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)

            if len(text) >= 30:
                paragraphs.append(text)

        text = " ".join(paragraphs)

        text = re.sub(r"\s+", " ", text)

        return text[:30000]

    except Exception as e:
        print("article:", url, e)
        return ""


# ============================================================
# ПРОВЕРКА: ЭТО РОССИЯ?
# ============================================================

def detect_region(text):
    lower = text.lower()

    # Сначала город
    for city, region in CITY_REGION.items():
        if city.lower() in lower:
            return city, region

    # Потом непосредственно регион
    for region in REGIONS:
        if region.lower() in lower:
            return None, region

    return None, None


def is_russian_event(text):
    city, region = detect_region(text)

    if region:
        return True

    return False


# ============================================================
# ПРОВЕРКА ТЕМЫ
# ============================================================

def is_relevant(text):
    lower = text.lower()

    attack = any(word in lower for word in ATTACK_WORDS)
    casualties = any(word in lower for word in CASUALTY_WORDS)

    if not attack or not casualties:
        return False

    if not is_russian_event(text):
        return False

    # Если явно иностранная история и нет российского региона
    city, region = detect_region(text)

    if not region and any(word in lower for word in FOREIGN_WORDS):
        return False

    return True


# ============================================================
# ЧИСЛА
# ============================================================

NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "одного": 1,
    "одному": 1,

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
    "пяти": 5,

    "шесть": 6,
    "шестеро": 6,
    "шести": 6,

    "семь": 7,
    "семеро": 7,
    "семи": 7,

    "восемь": 8,
    "восьмеро": 8,
    "восьми": 8,

    "девять": 9,
    "девятеро": 9,
    "девяти": 9,

    "десять": 10,
    "десяти": 10,

    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
    "двадцать": 20,
}


def to_number(value):
    if value is None:
        return None

    value = value.lower().strip()

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


NUMBER_PATTERN = (
    r"(?:\d{1,4}|"
    + "|".join(
        sorted(
            [re.escape(x) for x in NUMBER_WORDS.keys()],
            key=len,
            reverse=True
        )
    )
    + r")"
)


# ============================================================
# ГЛАВНОЕ ИСПРАВЛЕНИЕ:
# АКТУАЛЬНОЕ ЧИСЛО ПОГИБШИХ / ПОСТРАДАВШИХ
# ============================================================

OLD_MARKERS = [
    "ранее",
    "до этого",
    "первоначально",
    "прежде сообщалось",
    "ранее сообщалось",
    "по предварительным данным",
]


def sentence_is_old(sentence):
    lower = sentence.lower()

    return any(marker in lower for marker in OLD_MARKERS)


def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def extract_latest_count(text, casualty_type):
    """
    casualty_type:
        death
        injured

    Приоритет:
    1. увеличилось/возросло/достигло ДО N
    2. число погибших/пострадавших составляет N
    3. погибли/пострадали N
    4. N человек погибли/пострадали

    Предложения со словами "ранее", "первоначально" и т.п.
    получают низкий приоритет.
    """

    sentences = split_sentences(text)

    candidates = []

    if casualty_type == "death":
        noun = (
            r"(?:погибших|жертв)"
        )

        verb = (
            r"(?:погибли|погибло|погиб|погибла)"
        )

    else:
        noun = (
            r"(?:пострадавших|раненых)"
        )

        verb = (
            r"(?:пострадали|пострадало|пострадал|"
            r"пострадала|ранены|ранено|ранен|ранена)"
        )

    for index, sentence in enumerate(sentences):
        s = sentence.lower()

        old = sentence_is_old(sentence)

        # ----------------------------------------------------
        # 1. "число погибших увеличилось до пяти"
        # ----------------------------------------------------

        patterns_priority_100 = [
            rf"(?:число|количество)\s+{noun}.{{0,70}}?"
            rf"(?:увеличил\w*|возрос\w*|вырос\w*|"
            rf"достиг\w*|повысил\w*)"
            rf".{{0,30}}?\bдо\s+({NUMBER_PATTERN})\b",

            rf"{noun}.{{0,60}}?"
            rf"(?:стало|насчитывается|составило|составляет)"
            rf".{{0,20}}?({NUMBER_PATTERN})",
        ]

        for pattern in patterns_priority_100:
            for m in re.finditer(pattern, s, re.I):
                n = to_number(m.group(1))

                if n is not None:
                    score = 100

                    if old:
                        score -= 80

                    # Более позднее предложение немного важнее
                    score += index / 1000

                    candidates.append(
                        (score, n, sentence)
                    )

        # ----------------------------------------------------
        # 2. "погибли пять человек"
        # ----------------------------------------------------

        pattern = (
            rf"\b{verb}\b"
            rf".{{0,25}}?"
            rf"({NUMBER_PATTERN})"
            rf"(?:\s+(?:человек|человека|жителей|мирных))?"
        )

        for m in re.finditer(pattern, s, re.I):
            n = to_number(m.group(1))

            if n is not None:
                score = 70

                if old:
                    score -= 60

                score += index / 1000

                candidates.append(
                    (score, n, sentence)
                )

        # ----------------------------------------------------
        # 3. "пять человек погибли"
        # ----------------------------------------------------

        pattern = (
            rf"\b({NUMBER_PATTERN})\b"
            rf"\s+(?:человек|человека|жителей|мирных)"
            rf".{{0,25}}?"
            rf"\b{verb}\b"
        )

        for m in re.finditer(pattern, s, re.I):
            n = to_number(m.group(1))

            if n is not None:
                score = 70

                if old:
                    score -= 60

                score += index / 1000

                candidates.append(
                    (score, n, sentence)
                )

        # ----------------------------------------------------
        # 4. "число погибших — пять человек"
        # ----------------------------------------------------

        pattern = (
            rf"(?:число|количество)\s+{noun}"
            rf".{{0,20}}?"
            rf"({NUMBER_PATTERN})"
        )

        for m in re.finditer(pattern, s, re.I):
            n = to_number(m.group(1))

            if n is not None:
                score = 80

                if old:
                    score -= 60

                score += index / 1000

                candidates.append(
                    (score, n, sentence)
                )

    if not candidates:
        return None

    # Берем кандидата с максимальным приоритетом
    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    best = candidates[0]

    print(
        casualty_type,
        "=>",
        best[1],
        "|",
        best[2][:200]
    )

    return best[1]


def extract_casualties(text):
    deaths = extract_latest_count(text, "death")
    injured = extract_latest_count(text, "injured")

    return deaths, injured


# ============================================================
# ДАТА И ВРЕМЯ ПРОИСШЕСТВИЯ
# ============================================================

MONTHS = (
    r"января|февраля|марта|апреля|мая|июня|"
    r"июля|августа|сентября|октября|ноября|декабря"
)


def extract_event_date(text):
    patterns = [
        rf"\b(\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}\s+года)\b",
        rf"\b(\d{{1,2}}\s+(?:{MONTHS}))\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)

        if m:
            return m.group(1)

    return None


def extract_event_time(text):
    patterns = [
        r"\b(?:около|примерно|в)\s+(\d{1,2}:\d{2})\b",
        r"\b(\d{1,2}:\d{2})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)

        if m:
            return m.group(1)

    return None


# ============================================================
# КОРОТКОЕ ОПИСАНИЕ
# ============================================================

def make_description(text):
    sentences = split_sentences(text)

    useful = []

    for sentence in sentences:
        lower = sentence.lower()

        if any(word in lower for word in ATTACK_WORDS):
            # Не берем старые цифры в описание, если можно
            if not sentence_is_old(sentence):
                useful.append(sentence.strip())

        if len(useful) >= 2:
            break

    if not useful:
        for sentence in sentences[:2]:
            useful.append(sentence.strip())

    description = " ".join(useful)

    if len(description) > 500:
        description = description[:497].rstrip() + "..."

    return description


# ============================================================
# ФОРМАТ МЕСТА
# ============================================================

def make_location(text):
    city, region = detect_region(text)

    if city and region:
        if city == region:
            return region

        return f"{city}, {region}"

    if region:
        return region

    return None


# ============================================================
# ФОРМИРОВАНИЕ ПОСТА
# ============================================================

def build_message(source, url, text):
    location = make_location(text)

    if not location:
        return None

    deaths, injured = extract_casualties(text)

    # Не публикуем, если вообще нет подтвержденных жертв
    if deaths is None and injured is None:
        return None

    description = make_description(text)

    event_date = extract_event_date(text)
    event_time = extract_event_time(text)

    lines = []

    lines.append(
        f"⚡ <b>{html.escape(location)}</b>"
    )

    if event_date:
        date_line = f"📅 {html.escape(event_date)}"

        if event_time:
            date_line += f", {html.escape(event_time)}"

        lines.append(date_line)

    elif event_time:
        lines.append(
            f"🕐 {html.escape(event_time)}"
        )

    lines.append("")

    if description:
        lines.append(
            html.escape(description)
        )
        lines.append("")

    if deaths is not None:
        lines.append(
            f"<b>Погибли: {deaths} человек</b>"
        )

    if injured is not None:
        lines.append(
            f"<b>Пострадали: {injured} человек</b>"
        )

    lines.append("")

    safe_url = html.escape(
        url,
        quote=True
    )

    safe_source = html.escape(source)

    lines.append(
        f'Источник: <a href="{safe_url}">{safe_source}</a>'
    )

    return "\n".join(lines)


# ============================================================
# ПРОВЕРКА НОВОСТЕЙ
# ============================================================

def check_news():
    seen = load_seen()

    for source, rss_url in SOURCES:
        try:
            feed = feedparser.parse(rss_url)

            for entry in feed.entries[:30]:
                url = getattr(entry, "link", "")

                if not url:
                    continue

                uid = hashlib.sha256(
                    url.encode("utf-8")
                ).hexdigest()

                if uid in seen:
                    continue

                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")

                rss_text = BeautifulSoup(
                    summary,
                    "html.parser"
                ).get_text(" ", strip=True)

                preliminary = (
                    title + " " + rss_text
                )

                # Сначала быстрая проверка,
                # но не слишком строгая
                attack_found = any(
                    word in preliminary.lower()
                    for word in ATTACK_WORDS
                )

                casualty_found = any(
                    word in preliminary.lower()
                    for word in CASUALTY_WORDS
                )

                if not attack_found and not casualty_found:
                    seen.add(uid)
                    continue

                article_text = get_article_text(url)

                full_text = (
                    title
                    + ". "
                    + rss_text
                    + ". "
                    + article_text
                )

                if not is_relevant(full_text):
                    seen.add(uid)
                    continue

                message = build_message(
                    source,
                    url,
                    full_text
                )

                if not message:
                    seen.add(uid)
                    continue

                try:
                    bot.send_message(
                        CHANNEL_ID,
                        message,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )

                    print(
                        "PUBLISHED:",
                        source,
                        title
                    )

                except Exception as e:
                    print(
                        "Telegram:",
                        source,
                        e
                    )

                seen.add(uid)

                # небольшая пауза между публикациями
                time.sleep(2)

        except Exception as e:
            print(
                "SOURCE ERROR:",
                source,
                e
            )

    save_seen(seen)


# ============================================================
# ЗАПУСК
# ============================================================

print("Monitoring started")

while True:
    try:
        check_news()
    except Exception as e:
        print("MAIN ERROR:", e)

    time.sleep(600)