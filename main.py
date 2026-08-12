import os
import re
import time
import json
import hashlib
import html
from datetime import datetime, timedelta, timezone

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

MOSCOW_TZ = timezone(timedelta(hours=3))

CHECK_INTERVAL = 180  # каждые 3 минуты

STATE_FILE = "state.json"


# ============================================================
# ИСТОЧНИКИ
# ============================================================

SOURCES = [
    {
        "name": "ТАСС",
        "rss": "https://tass.ru/rss/v2.xml",
        "domains": ["tass.ru"]
    },
    {
        "name": "РИА Новости",
        "rss": "https://ria.ru/export/rss2/archive/index.xml",
        "domains": ["ria.ru"]
    },
    {
        "name": "Интерфакс",
        "rss": "https://www.interfax.ru/rss.asp",
        "domains": ["interfax.ru"]
    },
    {
        "name": "Российская газета",
        "rss": "https://rg.ru/xml/index.xml",
        "domains": ["rg.ru"]
    },
]


# ============================================================
# HTTP
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


# ============================================================
# СОСТОЯНИЕ / АНТИДУБЛЬ
# ============================================================

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"events": {}}

        if "events" not in data:
            data["events"] = {}

        return data

    except Exception:
        return {"events": {}}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception as e:
        print("Ошибка сохранения state:", e)


state = load_state()


# ============================================================
# ТЕКУЩАЯ ДАТА
# ============================================================

def now_moscow():
    return datetime.now(MOSCOW_TZ)


def today_moscow():
    return now_moscow().date()


# ============================================================
# ОЧИСТКА ТЕКСТА
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = html.unescape(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# ПОЛУЧЕНИЕ ТЕКСТА СТАТЬИ
# ============================================================

def get_article_text(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Удаляем мусор
        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form"
        ]):
            tag.decompose()

        paragraphs = []

        for p in soup.find_all("p"):
            text = clean_text(p.get_text(" "))

            if len(text) >= 25:
                paragraphs.append(text)

        # ВАЖНО:
        # не собираем заголовки/карточки других новостей.
        # Только абзацы статьи.
        article = " ".join(paragraphs)

        # Защита от огромных страниц
        return article[:30000]

    except Exception as e:
        print("Ошибка загрузки статьи:", url, e)
        return ""


# ============================================================
# ФИЛЬТР: ТЕМА АТАКИ
# ============================================================

ATTACK_WORDS = [
    "бпла",
    "беспилотник",
    "беспилотного",
    "дрон",
    "fpv",
    "обстрел",
    "обстреля",
    "атаковал",
    "атаковала",
    "атаковали",
    "атака",
    "удар",
    "удары",
    "ракет",
    "ракета",
    "боеприпас",
    "снаряд",
    "артиллер",
    "миномет",
    "мина",
    "детонац",
    "пво",
    "противовоздуш",
    "обломк",
    "падение обломков",
    "сбитого беспилотника",
]


CASUALTY_WORDS = [
    "погиб",
    "погибли",
    "погибла",
    "погибло",
    "пострадал",
    "пострадали",
    "пострадала",
    "пострадало",
    "ранен",
    "ранены",
    "ранена",
    "ранено",
    "жертв",
    "госпитализирован",
]


def contains_attack(text):
    low = text.lower()

    return any(word in low for word in ATTACK_WORDS)


def contains_casualties(text):
    low = text.lower()

    return any(word in low for word in CASUALTY_WORDS)


# ============================================================
# ИСКЛЮЧАЕМ НЕ НУЖНЫЕ НАМ МАТЕРИАЛЫ
# ============================================================

BAD_ARTICLE_MARKERS = [
    "корреспондент побывал",
    "корреспондент \"рг\" побывал",
    "корреспондент «рг» побывал",
    "наш корреспондент побывал",
    "специальный корреспондент",
    "репортаж",
    "фоторепортаж",
    "интервью",
    "воспоминания",
    "история о том",
    "рассказал о поездке",
    "рассказала о поездке",
    "как добирался",
    "что увидел и пережил",
]


def looks_like_reportage(title, text):
    sample = (title + " " + text[:2500]).lower()

    return any(marker in sample for marker in BAD_ARTICLE_MARKERS)


# ============================================================
# ФИЛЬТР АКТУАЛЬНОСТИ СОБЫТИЯ
# ============================================================

MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


CURRENT_EVENT_MARKERS = [
    "сегодня",
    "сегодня утром",
    "сегодня днем",
    "сегодня днём",
    "сегодня вечером",
    "сегодня ночью",
    "этой ночью",
    "минувшей ночью",
    "утром",
    "днем",
    "днём",
    "вечером",
    "ночью",
]


OLD_EVENT_MARKERS = [
    "год назад",
    "года назад",
    "несколько лет назад",
    "в прошлом году",
    "в 2022 году",
    "в 2023 году",
    "в 2024 году",
    "в 2025 году",
]


def explicit_dates(text):
    """
    Возвращает найденные явные даты вида:
    12 августа
    12 августа 2026
    """

    found = []

    pattern = (
        r"\b([0-3]?\d)\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|"
        r"августа|сентября|октября|ноября|декабря)"
        r"(?:\s+(\d{4})\s*(?:года|г\.?)?)?"
    )

    for match in re.finditer(pattern, text.lower()):
        day = int(match.group(1))
        month = MONTHS[match.group(2)]

        year = (
            int(match.group(3))
            if match.group(3)
            else today_moscow().year
        )

        try:
            found.append(
                datetime(year, month, day).date()
            )
        except ValueError:
            pass

    return found


def event_is_today(title, text, published_dt=None):
    """
    Главное правило:
    дата публикации НЕ считается автоматически датой события.

    Нам нужно подтверждение из самого текста/заголовка,
    что событие относится к сегодняшнему дню.
    """

    today = today_moscow()

    combined = clean_text(title + " " + text[:7000])
    low = combined.lower()

    # Явно старые материалы
    if any(marker in low for marker in OLD_EVENT_MARKERS):
        return False

    dates = explicit_dates(combined)

    # Если в начале текста есть сегодняшняя дата — хорошо.
    if today in dates:
        return True

    # Если присутствует явный год/дата прошлого события,
    # не принимаем его за сегодняшнее.
    for date in dates:
        if date != today:
            # Старые даты сами по себе не всегда означают,
            # что статья старая — они могут быть справкой.
            # Поэтому смотрим особенно начало текста.
            first_part = combined[:1800].lower()

            date_string = f"{date.day}"

            if date_string in first_part and date < today:
                return False

    # Явные маркеры сегодняшнего события
    if any(marker in low[:3500] for marker in CURRENT_EVENT_MARKERS):
        return True

    # Если нет даты события, разрешаем только очень свежую
    # публикацию с прямым сообщением об атаке.
    if published_dt:
        age = now_moscow() - published_dt

        direct_attack = bool(
            re.search(
                r"\b("
                r"бпла|беспилотник|дрон|fpv-дрон|"
                r"обстрел|обстреляли|"
                r"атаковал|атаковала|атаковали|"
                r"ракетн\w*\s+удар|"
                r"удар\w*\s+бпла"
                r")\b",
                low[:1800]
            )
        )

        if (
            timedelta(0) <= age <= timedelta(hours=3)
            and direct_attack
        ):
            return True

    return False


# ============================================================
# ДАТА RSS
# ============================================================

def entry_datetime(entry):
    try:
        if getattr(entry, "published_parsed", None):
            t = entry.published_parsed

            dt = datetime(
                t.tm_year,
                t.tm_mon,
                t.tm_mday,
                t.tm_hour,
                t.tm_min,
                t.tm_sec,
                tzinfo=timezone.utc
            )

            return dt.astimezone(MOSCOW_TZ)

    except Exception:
        pass

    return None


def publication_is_fresh(entry):
    dt = entry_datetime(entry)

    if not dt:
        return False

    now = now_moscow()

    # Только сегодняшние публикации.
    return dt.date() == now.date()


# ============================================================
# РАЗБИВАЕМ СТАТЬЮ НА ПРЕДЛОЖЕНИЯ
# ============================================================

def sentences(text):
    text = clean_text(text)

    return [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) > 10
    ]


# ============================================================
# ЧИСЛА
# ============================================================

NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "одного": 1,
    "одному": 1,
    "одним": 1,

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
    "десятеро": 10,

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
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
}


NUM_PATTERN = (
    r"(?:\d+|"
    + "|".join(
        sorted(
            NUMBER_WORDS.keys(),
            key=len,
            reverse=True
        )
    )
    + r")"
)


def parse_number(value):
    value = value.lower().strip()

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


# ============================================================
# ИЗВЛЕЧЕНИЕ ПОГИБШИХ / ПОСТРАДАВШИХ
# ============================================================

DEAD_PATTERNS = [
    rf"(?:погибли|погибло)\s+(?:как минимум\s+|не менее\s+)?({NUM_PATTERN})\s+(?:человек|человека|людей)",
    rf"(?:погиб|погибла)\s+({NUM_PATTERN})\s+(?:человек|человека)",
    rf"(?:число|количество)\s+погибших\D{{0,35}}?(?:до|составило|достигло)\s+({NUM_PATTERN})",
    rf"погибших\D{{0,25}}?(?:до|составило|достигло)\s+({NUM_PATTERN})",
    rf"({NUM_PATTERN})\s+(?:человек|человека|людей)\s+(?:погибли|погибло)",
]


INJURED_PATTERNS = [
    rf"(?:пострадали|пострадало)\s+(?:как минимум\s+|не менее\s+)?({NUM_PATTERN})\s+(?:человек|человека|людей)",
    rf"(?:пострадал|пострадала)\s+({NUM_PATTERN})\s+(?:человек|человека)",
    rf"(?:число|количество)\s+пострадавших\D{{0,35}}?(?:до|составило|достигло)\s+({NUM_PATTERN})",
    rf"пострадавших\D{{0,25}}?(?:до|составило|достигло)\s+({NUM_PATTERN})",
    rf"({NUM_PATTERN})\s+(?:человек|человека|людей)\s+(?:пострадали|пострадало)",
    rf"(?:ранены|ранено)\s+({NUM_PATTERN})\s+(?:человек|человека|людей)",
    rf"({NUM_PATTERN})\s+(?:человек|человека|людей)\s+(?:ранены|ранено)",
]


OLD_COUNT_MARKERS = [
    "ранее",
    "до этого",
    "первоначально",
    "сначала",
    "прежде",
    "ранее сообщалось",
    "ранее стало известно",
]


UPDATE_MARKERS = [
    "увеличилось",
    "увеличилось до",
    "возросло",
    "возросло до",
    "выросло",
    "выросло до",
    "уточненным данным",
    "уточнённым данным",
    "по новым данным",
    "по последним данным",
    "к настоящему времени",
    "на данный момент",
    "к этой минуте",
    "теперь",
]


def extract_values_from_sentence(sentence, patterns):
    values = []

    low = sentence.lower()

    for pattern in patterns:
        for match in re.finditer(pattern, low, flags=re.I):
            value = parse_number(match.group(1))

            if value is not None:
                values.append(value)

    return values


def extract_casualties(title, text):
    """
    Берём цифры только из предложений, где есть контекст
    атаки/последствий или соседних предложений.

    Последние уточнённые цифры имеют приоритет над
    "ранее было ...".
    """

    sents = sentences(title + ". " + text)

    dead_candidates = []
    injured_candidates = []

    for i, sent in enumerate(sents):
        low = sent.lower()

        has_casualty = contains_casualties(sent)

        if not has_casualty:
            continue

        # Контекст: само предложение + соседние
        context_parts = []

        if i > 0:
            context_parts.append(sents[i - 1])

        context_parts.append(sent)

        if i + 1 < len(sents):
            context_parts.append(sents[i + 1])

        context = " ".join(context_parts).lower()

        # Цифры принимаются только если рядом есть контекст атаки
        if not contains_attack(context):
            continue

        dead_values = extract_values_from_sentence(
            sent,
            DEAD_PATTERNS
        )

        injured_values = extract_values_from_sentence(
            sent,
            INJURED_PATTERNS
        )

        is_old = any(
            marker in low
            for marker in OLD_COUNT_MARKERS
        )

        is_update = any(
            marker in low
            for marker in UPDATE_MARKERS
        )

        priority = 0

        if is_old:
            priority = -10

        if is_update:
            priority = 10

        for value in dead_values:
            dead_candidates.append(
                (priority, i, value, sent)
            )

        for value in injured_values:
            injured_candidates.append(
                (priority, i, value, sent)
            )

    def choose(candidates):
        if not candidates:
            return None

        # Сначала уточнённые данные,
        # затем более позднее предложение.
        candidates.sort(
            key=lambda x: (x[0], x[1]),
            reverse=True
        )

        best_priority = candidates[0][0]

        same_priority = [
            x for x in candidates
            if x[0] == best_priority
        ]

        # При одинаковом приоритете выбираем максимальную
        # цифру — это защищает от формулировок:
        # "число погибших увеличилось с 3 до 5".
        return max(x[2] for x in same_priority)

    dead = choose(dead_candidates)
    injured = choose(injured_candidates)

    return dead, injured


# ============================================================
# ГЕОГРАФИЯ
# ============================================================

REGION_PATTERNS = [
    r"([А-ЯЁ][а-яё\-]+(?:ская|ская)\s+область)",
    r"([А-ЯЁ][а-яё\-]+(?:ский|ской)\s+край)",
    r"(Республика\s+[А-ЯЁ][а-яё\-]+)",
    r"(Республике\s+[А-ЯЁ][а-яё\-]+)",
    r"(Москва)",
    r"(Санкт-Петербург)",
    r"(Севастополь)",
]


KNOWN_REGIONS = [
    "Белгородская область",
    "Брянская область",
    "Курская область",
    "Воронежская область",
    "Ростовская область",
    "Липецкая область",
    "Орловская область",
    "Тульская область",
    "Московская область",
    "Калужская область",
    "Смоленская область",
    "Тверская область",
    "Псковская область",
    "Ленинградская область",
    "Новгородская область",
    "Вологодская область",
    "Ярославская область",
    "Костромская область",
    "Ивановская область",
    "Владимирская область",
    "Рязанская область",
    "Тамбовская область",
    "Пензенская область",
    "Саратовская область",
    "Волгоградская область",
    "Астраханская область",
    "Самарская область",
    "Ульяновская область",
    "Оренбургская область",
    "Челябинская область",
    "Свердловская область",
    "Тюменская область",
    "Омская область",
    "Новосибирская область",
    "Томская область",
    "Кемеровская область",
    "Иркутская область",
    "Амурская область",
    "Магаданская область",
    "Сахалинская область",
    "Калининградская область",
    "Мурманская область",
    "Архангельская область",

    "Краснодарский край",
    "Ставропольский край",
    "Пермский край",
    "Красноярский край",
    "Алтайский край",
    "Приморский край",
    "Хабаровский край",
    "Забайкальский край",
    "Камчатский край",

    "Республика Татарстан",
    "Республика Башкортостан",
    "Республика Дагестан",
    "Республика Крым",
    "Республика Адыгея",
    "Республика Калмыкия",
    "Республика Мордовия",
    "Республика Марий Эл",
    "Республика Коми",
    "Республика Карелия",
    "Республика Алтай",
    "Республика Тыва",
    "Республика Бурятия",
    "Республика Хакасия",
    "Республика Саха",
    "Республика Северная Осетия",
    "Кабардино-Балкарская Республика",
    "Карачаево-Черкесская Республика",
    "Чеченская Республика",
    "Удмуртская Республика",
    "Чувашская Республика",
    "Республика Ингушетия",

    "Москва",
    "Санкт-Петербург",
    "Севастополь",
]


CITY_REGION_MAP = {
    "Белгород": "Белгородская область",
    "Шебекино": "Белгородская область",
    "Грайворон": "Белгородская область",
    "Валуйки": "Белгородская область",

    "Курск": "Курская область",
    "Рыльск": "Курская область",
    "Суджа": "Курская область",
    "Льгов": "Курская область",

    "Брянск": "Брянская область",
    "Клинцы": "Брянская область",

    "Воронеж": "Воронежская область",

    "Ростов-на-Дону": "Ростовская область",
    "Таганрог": "Ростовская область",
    "Новошахтинск": "Ростовская область",

    "Краснодар": "Краснодарский край",
    "Новороссийск": "Краснодарский край",
    "Анапа": "Краснодарский край",
    "Геленджик": "Краснодарский край",
    "Сочи": "Краснодарский край",
    "Туапсе": "Краснодарский край",
    "Темрюк": "Краснодарский край",

    "Казань": "Республика Татарстан",
    "Нижнекамск": "Республика Татарстан",
    "Елабуга": "Республика Татарстан",

    "Москва": "Москва",
    "Санкт-Петербург": "Санкт-Петербург",
    "Севастополь": "Севастополь",
}


def normalize_region(region):
    if not region:
        return None

    region = region.replace(
        "Республике ",
        "Республика "
    )

    return region.strip()


def find_region(text):
    """
    Ищем регион только в тексте конкретного происшествия.
    Никаких регионов из меню сайта / других заголовков.
    """

    for region in KNOWN_REGIONS:
        if region.lower() in text.lower():
            return region

    return None


def find_city(text):
    for city in CITY_REGION_MAP.keys():
        if re.search(
            rf"\b{re.escape(city)}\b",
            text,
            flags=re.I
        ):
            return city

    # Некоторые типовые конструкции:
    patterns = [
        r"\bв\s+городе\s+([А-ЯЁ][а-яё\-]+)",
        r"\bв\s+([А-ЯЁ][а-яё\-]+е)\b",
        r"\bпод\s+([А-ЯЁ][а-яё\-]+ом)\b",
    ]

    # Не пытаемся автоматически преобразовывать падежи,
    # чтобы не получить "Москва" из случайного текста.
    return None


def extract_location(title, text):
    """
    Сначала смотрим заголовок + первые абзацы.
    Если город известен, регион можно получить из
    безопасной таблицы CITY_REGION_MAP.
    """

    relevant = clean_text(
        title + " " + text[:3000]
    )

    city = find_city(relevant)
    region = find_region(relevant)

    if city and not region:
        region = CITY_REGION_MAP.get(city)

    # Если город и регион противоречат друг другу —
    # не публикуем.
    if city:
        expected = CITY_REGION_MAP.get(city)

        if expected and region and expected != region:
            return None, None

    return city, region


# ============================================================
# ДАТА И ВРЕМЯ ПРОИСШЕСТВИЯ
# ============================================================

def event_date_string(title, text):
    today = today_moscow()

    # Мы уже проверили, что событие сегодняшнее.
    months_ru = [
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря"
    ]

    return (
        f"{today.day} "
        f"{months_ru[today.month]} "
        f"{today.year} года"
    )


def extract_event_time(title, text):
    """
    Время показываем только если оно прямо указано.
    Ничего не придумываем.
    """

    relevant = clean_text(
        title + " " + text[:3500]
    )

    patterns = [
        r"\bв\s+([0-2]?\d:[0-5]\d)\b",
        r"\bоколо\s+([0-2]?\d:[0-5]\d)\b",
        r"\bпримерно\s+в\s+([0-2]?\d:[0-5]\d)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, relevant)

        if match:
            return match.group(1)

    return None


# ============================================================
# КРАТКОЕ ОПИСАНИЕ
# ============================================================

def build_description(title, text):
    """
    Не копируем весь материал.
    Берём 1-2 предложения непосредственно о происшествии.
    """

    all_sentences = sentences(
        title + ". " + text
    )

    selected = []

    for i, sent in enumerate(all_sentences):
        if contains_attack(sent):
            selected.append(sent)

            # Можно добавить следующее предложение,
            # если там последствия.
            if i + 1 < len(all_sentences):
                nxt = all_sentences[i + 1]

                if contains_casualties(nxt):
                    selected.append(nxt)

            break

    if not selected:
        return None

    description = " ".join(selected)

    # Убираем слишком длинные публикации
    if len(description) > 550:
        description = description[:547].rsplit(
            " ",
            1
        )[0] + "..."

    return description


# ============================================================
# СОЗДАЁМ КЛЮЧ СОБЫТИЯ
# ============================================================

def event_key(city, region, title, description):
    """
    URL НЕ является ключом.
    Разные СМИ могут написать об одной атаке.

    Ключ строим по:
    дата + география + тип происшествия.
    """

    today = today_moscow().isoformat()

    location = "|".join(
        x for x in [city, region] if x
    ).lower()

    combined = (
        title + " " + (description or "")
    ).lower()

    attack_type = "attack"

    if "бпла" in combined or "беспилот" in combined or "дрон" in combined:
        attack_type = "uav"

    elif "обстрел" in combined:
        attack_type = "shelling"

    elif "ракет" in combined:
        attack_type = "missile"

    elif "пво" in combined or "обломк" in combined:
        attack_type = "airdefense"

    raw = f"{today}|{location}|{attack_type}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# ПРОВЕРКА ДУБЛЯ / ОБНОВЛЕНИЯ
# ============================================================

def determine_publication_type(
    key,
    dead,
    injured
):
    old = state["events"].get(key)

    if old is None:
        return "new"

    old_dead = old.get("dead")
    old_injured = old.get("injured")

    dead_increased = (
        dead is not None
        and (
            old_dead is None
            or dead > old_dead
        )
    )

    injured_increased = (
        injured is not None
        and (
            old_injured is None
            or injured > old_injured
        )
    )

    if dead_increased or injured_increased:
        return "update"

    # Те же или меньшие цифры — ничего не публикуем.
    return "skip"


def update_state(
    key,
    dead,
    injured,
    url
):
    old = state["events"].get(key, {})

    old_dead = old.get("dead")
    old_injured = old.get("injured")

    if dead is None:
        dead = old_dead

    elif old_dead is not None:
        dead = max(dead, old_dead)

    if injured is None:
        injured = old_injured

    elif old_injured is not None:
        injured = max(
            injured,
            old_injured
        )

    state["events"][key] = {
        "dead": dead,
        "injured": injured,
        "last_url": url,
        "updated": now_moscow().isoformat()
    }

    save_state(state)


# ============================================================
# TELEGRAM
# ============================================================

def make_location(city, region):
    if city and region:
        if city == region:
            return city

        return f"{city}, {region}"

    if region:
        return region

    return city


def build_message(
    city,
    region,
    date_text,
    event_time,
    description,
    dead,
    injured,
    source_name,
    url,
    is_update=False
):
    location = make_location(
        city,
        region
    )

    parts = []

    if is_update:
        parts.append(
            "🔄 <b>По новым уточнённым данным</b>"
        )

    parts.append(
        f"⚡️ <b>{html.escape(location)}</b>"
    )

    date_line = (
        f"📅 {html.escape(date_text)}"
    )

    if event_time:
        date_line += (
            f", около {html.escape(event_time)}"
        )

    parts.append(date_line)

    if description:
        parts.append(
            html.escape(description)
        )

    casualty_lines = []

    if dead is not None:
        casualty_lines.append(
            f"<b>Погибли: {dead} чел.</b>"
        )

    if injured is not None:
        casualty_lines.append(
            f"<b>Пострадали: {injured} чел.</b>"
        )

    if casualty_lines:
        parts.append(
            "\n".join(casualty_lines)
        )

    # Название СМИ кликабельное.
    safe_url = html.escape(
        url,
        quote=True
    )

    safe_source = html.escape(
        source_name
    )

    parts.append(
        f'Источник: '
        f'<a href="{safe_url}">{safe_source}</a>'
    )

    return "\n\n".join(parts)


# ============================================================
# ОБРАБОТКА ОДНОЙ НОВОСТИ
# ============================================================

def process_entry(entry, source):
    try:
        title = clean_text(
            getattr(entry, "title", "")
        )

        url = getattr(entry, "link", "")

        if not title or not url:
            return

        # ----------------------------------------
        # 1. RSS публикация должна быть сегодня
        # ----------------------------------------

        if not publication_is_fresh(entry):
            return

        published_dt = entry_datetime(entry)

        rss_summary = clean_text(
            getattr(entry, "summary", "")
        )

        preliminary = (
            title + " " + rss_summary
        )

        # ----------------------------------------
        # 2. Уже на RSS уровне должна быть тема
        # атаки или жертв.
        # ----------------------------------------

        if (
            not contains_attack(preliminary)
            and
            not contains_casualties(preliminary)
        ):
            return

        # ----------------------------------------
        # 3. Загружаем только саму статью
        # ----------------------------------------

        article_text = get_article_text(url)

        if not article_text:
            return

        full_text = clean_text(
            title + ". " + article_text
        )

        # ----------------------------------------
        # 4. Это должна быть атака
        # ----------------------------------------

        if not contains_attack(full_text):
            return

        # ----------------------------------------
        # 5. Должны быть погибшие/пострадавшие
        # ----------------------------------------

        if not contains_casualties(full_text):
            return

        # ----------------------------------------
        # 6. Репортажи/исторические материалы
        # не публикуем
        # ----------------------------------------

        if looks_like_reportage(
            title,
            article_text
        ):
            print(
                "SKIP REPORTAGE:",
                source["name"],
                title
            )
            return

        # ----------------------------------------
        # 7. Само СОБЫТИЕ должно быть сегодня
        # ----------------------------------------

        if not event_is_today(
            title,
            article_text,
            published_dt
        ):
            print(
                "SKIP OLD EVENT:",
                source["name"],
                title
            )
            return

        # ----------------------------------------
        # 8. География
        # ----------------------------------------

        city, region = extract_location(
            title,
            article_text
        )

        # Не угадываем географию.
        if not city and not region:
            print(
                "SKIP NO LOCATION:",
                source["name"],
                title
            )
            return

        # ----------------------------------------
        # 9. Потери
        # ----------------------------------------

        dead, injured = extract_casualties(
            title,
            article_text
        )

        # Если не удалось получить НИ ОДНОЙ
        # достоверной цифры — не публикуем.
        if dead is None and injured is None:
            print(
                "SKIP NO COUNTS:",
                source["name"],
                title
            )
            return

        # ----------------------------------------
        # 10. Описание
        # ----------------------------------------

        description = build_description(
            title,
            article_text
        )

        if not description:
            print(
                "SKIP NO DESCRIPTION:",
                source["name"],
                title
            )
            return

        # ----------------------------------------
        # 11. Дата/время события
        # ----------------------------------------

        date_text = event_date_string(
            title,
            article_text
        )

        event_time = extract_event_time(
            title,
            article_text
        )

        # ----------------------------------------
        # 12. Антидубли
        # ----------------------------------------

        key = event_key(
            city,
            region,
            title,
            description
        )

        pub_type = determine_publication_type(
            key,
            dead,
            injured
        )

        if pub_type == "skip":
            print(
                "SKIP DUPLICATE:",
                source["name"],
                title
            )
            return

        # ----------------------------------------
        # 13. Формируем сообщение
        # ----------------------------------------

        message = build_message(
            city=city,
            region=region,
            date_text=date_text,
            event_time=event_time,
            description=description,
            dead=dead,
            injured=injured,
            source_name=source["name"],
            url=url,
            is_update=(pub_type == "update")
        )

        # ----------------------------------------
        # 14. Отправляем
        # ----------------------------------------

        bot.send_message(
            CHANNEL_ID,
            message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        update_state(
            key,
            dead,
            injured,
            url
        )

        print(
            "PUBLISHED:",
            pub_type,
            source["name"],
            location_for_log(city, region),
            dead,
            injured
        )

    except Exception as e:
        print(
            "ENTRY ERROR:",
            source["name"],
            e
        )


def location_for_log(city, region):
    return make_location(
        city,
        region
    )


# ============================================================
# ЧИСТИМ СТАРЫЕ СОБЫТИЯ ИЗ STATE
# ============================================================

def cleanup_state():
    today_string = today_moscow().isoformat()

    new_events = {}

    for key, value in state.get(
        "events",
        {}
    ).items():

        updated = value.get(
            "updated",
            ""
        )

        if updated.startswith(today_string):
            new_events[key] = value

    state["events"] = new_events

    save_state(state)


# ============================================================
# ПРОВЕРКА RSS
# ============================================================

def check_sources():
    for source in SOURCES:
        try:
            print(
                "Checking:",
                source["name"]
            )

            feed = feedparser.parse(
                source["rss"]
            )

            # Сначала старые записи,
            # потом новые.
            entries = list(
                feed.entries[:30]
            )

            entries.reverse()

            for entry in entries:
                process_entry(
                    entry,
                    source
                )

        except Exception as e:
            print(
                "SOURCE ERROR:",
                source["name"],
                e
            )


# ============================================================
# ЗАПУСК
# ============================================================

print("================================")
print("Civilian casualties bot started")
print("Date:", today_moscow())
print("Channel:", CHANNEL_ID)
print("================================")

last_cleanup_date = today_moscow()

while True:
    try:
        current_date = today_moscow()

        # После полуночи очищаем события предыдущего дня.
        if current_date != last_cleanup_date:
            cleanup_state()
            last_cleanup_date = current_date

        check_sources()

    except Exception as e:
        print(
            "MAIN LOOP ERROR:",
            e
        )

    time.sleep(CHECK_INTERVAL)