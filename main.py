import os
import re
import json
import time
import hashlib
import html
from datetime import datetime, timezone, timedelta
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
    raise RuntimeError("Не задан BOT_TOKEN")

if not CHANNEL_ID:
    raise RuntimeError("Не задан CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

CHECK_INTERVAL = 300          # проверка каждые 5 минут
MAX_EVENT_AGE_HOURS = 48      # события не старше 48 часов
SEEN_FILE = "seen.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    )
}


# =========================================================
# ИСТОЧНИКИ
# =========================================================

SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Российская газета", "https://rg.ru/xml/index.xml"),
    ("Интерфакс", "https://www.interfax.ru/rss.asp"),
]


# =========================================================
# КЛЮЧЕВЫЕ СЛОВА АТАК
# =========================================================

ATTACK_WORDS = [
    "бпла",
    "беспилотник",
    "беспилотника",
    "беспилотников",
    "дрон",
    "дрона",
    "дронов",
    "fpv",
    "fpv-дрон",
    "обстрел",
    "обстрела",
    "обстреляли",
    "ракет",
    "ракета",
    "ракетный удар",
    "ракетная атака",
    "удар",
    "атака",
    "атаковал",
    "атаковали",
    "взрыв",
    "взрыва",
    "взрывы",
    "боеприпас",
    "снаряд",
    "мина",
    "пво",
    "противовоздушной обороны",
    "сбит",
    "сбили",
    "сбитого",
    "обломки",
    "обломков",
    "падение обломков",
    "украинский беспилотник",
    "украинского беспилотника",
    "атака всу",
    "удар всу",
    "обстрел всу",
]


# =========================================================
# СЛОВА, УКАЗЫВАЮЩИЕ НА ПОТЕРИ
# =========================================================

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
    "пострадавших",
    "ранен",
    "ранены",
    "ранена",
    "ранено",
    "раненых",
    "госпитализирован",
    "госпитализированы",
]


# =========================================================
# ИСКЛЮЧАЕМ ЗАРУБЕЖНЫЕ СОБЫТИЯ
# =========================================================

FOREIGN_WORDS = [
    "израил",
    "иран",
    "йемен",
    "хусит",
    "газа",
    "сектор газа",
    "ливан",
    "сирия",
    "ирак",
    "украине",
    "украина",
    "киев",
    "харьков",
    "одесса",
    "днепр",
    "львов",
    "польша",
    "германия",
    "франция",
    "сша",
    "американ",
    "британия",
    "лондон",
    "турция",
    "стамбул",
    "афганистан",
    "пакистан",
]


# =========================================================
# РЕГИОНЫ РФ
# =========================================================

REGIONS = [
    "Белгородская область",
    "Брянская область",
    "Курская область",
    "Воронежская область",
    "Ростовская область",
    "Краснодарский край",
    "Республика Крым",
    "Севастополь",
    "Республика Татарстан",
    "Московская область",
    "Москва",
    "Ленинградская область",
    "Санкт-Петербург",
    "Липецкая область",
    "Орловская область",
    "Тульская область",
    "Калужская область",
    "Рязанская область",
    "Тамбовская область",
    "Смоленская область",
    "Тверская область",
    "Ярославская область",
    "Нижегородская область",
    "Волгоградская область",
    "Астраханская область",
    "Самарская область",
    "Саратовская область",
    "Ульяновская область",
    "Пензенская область",
    "Оренбургская область",
    "Челябинская область",
    "Свердловская область",
    "Тюменская область",
    "Курганская область",
    "Омская область",
    "Новосибирская область",
    "Кемеровская область",
    "Иркутская область",
    "Амурская область",
    "Сахалинская область",
    "Мурманская область",
    "Архангельская область",
    "Псковская область",
    "Новгородская область",
    "Калининградская область",
    "Республика Адыгея",
    "Республика Дагестан",
    "Республика Ингушетия",
    "Кабардино-Балкарская Республика",
    "Карачаево-Черкесская Республика",
    "Республика Северная Осетия",
    "Чеченская Республика",
    "Ставропольский край",
    "Республика Башкортостан",
    "Республика Мордовия",
    "Удмуртская Республика",
    "Чувашская Республика",
    "Республика Марий Эл",
    "Республика Коми",
    "Республика Карелия",
    "Пермский край",
    "Алтайский край",
    "Красноярский край",
    "Приморский край",
    "Хабаровский край",
    "Забайкальский край",
    "Камчатский край",
]


# =========================================================
# ГОРОД -> РЕГИОН
# Нужен прежде всего для регионов, где регулярно бывают атаки
# =========================================================

CITY_REGION = {
    "белгород": "Белгородская область",
    "шебекино": "Белгородская область",
    "валуйки": "Белгородская область",
    "грайворон": "Белгородская область",
    "старый оскол": "Белгородская область",

    "курск": "Курская область",
    "рыльск": "Курская область",
    "суджа": "Курская область",
    "льгов": "Курская область",
    "железногорск": "Курская область",

    "брянск": "Брянская область",
    "клинцы": "Брянская область",
    "стародуб": "Брянская область",

    "воронеж": "Воронежская область",
    "борисоглебск": "Воронежская область",

    "ростов-на-дону": "Ростовская область",
    "таганрог": "Ростовская область",
    "новочеркасск": "Ростовская область",
    "шахты": "Ростовская область",

    "краснодар": "Краснодарский край",
    "анапа": "Краснодарский край",
    "геленджик": "Краснодарский край",
    "новороссийск": "Краснодарский край",
    "туапсе": "Краснодарский край",
    "темрюк": "Краснодарский край",
    "сочи": "Краснодарский край",

    "липецк": "Липецкая область",
    "елец": "Липецкая область",

    "орел": "Орловская область",
    "орёл": "Орловская область",

    "тамбов": "Тамбовская область",
    "рязань": "Рязанская область",
    "тула": "Тульская область",
    "калуга": "Калужская область",
    "смоленск": "Смоленская область",

    "волгоград": "Волгоградская область",
    "волжский": "Волгоградская область",

    "саратов": "Саратовская область",
    "энгельс": "Саратовская область",

    "самара": "Самарская область",
    "сызрань": "Самарская область",
    "тольятти": "Самарская область",

    "нижнекамск": "Республика Татарстан",
    "казань": "Республика Татарстан",
    "елабуга": "Республика Татарстан",
    "альметьевск": "Республика Татарстан",

    "уфа": "Республика Башкортостан",
    "ижевск": "Удмуртская Республика",
    "пермь": "Пермский край",

    "севастополь": "Севастополь",
    "симферополь": "Республика Крым",
    "керчь": "Республика Крым",
    "джанкой": "Республика Крым",
    "феодосия": "Республика Крым",
    "евпатория": "Республика Крым",

    "москва": "Москва",
    "санкт-петербург": "Санкт-Петербург",
}


# =========================================================
# ЧИСЛА СЛОВАМИ
# =========================================================

NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "одного": 1,
    "одной": 1,

    "два": 2,
    "две": 2,
    "двое": 2,
    "двоих": 2,

    "три": 3,
    "трое": 3,
    "троих": 3,

    "четыре": 4,
    "четверо": 4,
    "четверых": 4,

    "пять": 5,
    "пятеро": 5,
    "пятерых": 5,

    "шесть": 6,
    "шестеро": 6,

    "семь": 7,
    "семеро": 7,

    "восемь": 8,
    "девять": 9,
    "десять": 10,
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
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
    "сто": 100,
}


# =========================================================
# СОХРАНЕНИЕ СОБЫТИЙ
# =========================================================

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

            if isinstance(data, dict):
                return data

    except Exception:
        pass

    return {}


def save_seen(data):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )
    except Exception as e:
        print("Ошибка сохранения seen:", e)


seen = load_seen()


# =========================================================
# ТЕКСТ СТРАНИЦЫ
# =========================================================

def get_article_text(url):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside"
        ]):
            tag.decompose()

        paragraphs = []

        for p in soup.find_all("p"):
            txt = p.get_text(" ", strip=True)

            if len(txt) >= 20:
                paragraphs.append(txt)

        return " ".join(paragraphs)

    except Exception as e:
        print("Ошибка загрузки статьи:", url, e)
        return ""


# =========================================================
# ОЧИСТКА
# =========================================================

def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser"
    ).get_text(" ", strip=True)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# RSS-ДАТА
# =========================================================

def get_entry_datetime(entry):
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)

        if value:
            try:
                return datetime(
                    value.tm_year,
                    value.tm_mon,
                    value.tm_mday,
                    value.tm_hour,
                    value.tm_min,
                    value.tm_sec,
                    tzinfo=timezone.utc
                )
            except Exception:
                pass

    return None


def is_fresh(entry):
    dt = get_entry_datetime(entry)

    if not dt:
        # Если RSS вообще не отдал дату,
        # не доверяем такой новости.
        return False

    now = datetime.now(timezone.utc)

    age = now - dt

    if age < timedelta(hours=-2):
        return False

    return age <= timedelta(hours=MAX_EVENT_AGE_HOURS)


# =========================================================
# ПРОВЕРКА: ЕСТЬ ЛИ АТАКА
# =========================================================

def contains_attack(text):
    low = text.lower()

    return any(word in low for word in ATTACK_WORDS)


def contains_casualties(text):
    low = text.lower()

    return any(word in low for word in CASUALTY_WORDS)


# =========================================================
# ЗАРУБЕЖНЫЙ ФИЛЬТР
# =========================================================

def clearly_foreign(text):
    low = text.lower()

    # Если найден российский регион/город —
    # не считаем материал иностранным только потому,
    # что в тексте упомянута Украина.
    if detect_region(text):
        return False

    for city in CITY_REGION:
        if city in low:
            return False

    return any(word in low for word in FOREIGN_WORDS)


# =========================================================
# ОПРЕДЕЛЕНИЕ РЕГИОНА
# =========================================================

def detect_region(text):
    low = text.lower()

    # Сначала ищем точное название региона в тексте.
    for region in REGIONS:
        if region.lower() in low:
            return region

    # Потом город.
    for city, region in CITY_REGION.items():
        if city in low:
            return region

    # Падежные формы наиболее важных регионов.
    aliases = {
        "белгородской области": "Белгородская область",
        "курской области": "Курская область",
        "брянской области": "Брянская область",
        "воронежской области": "Воронежская область",
        "ростовской области": "Ростовская область",
        "краснодарском крае": "Краснодарский край",
        "краснодарского края": "Краснодарский край",
        "липецкой области": "Липецкая область",
        "орловской области": "Орловская область",
        "тульской области": "Тульская область",
        "калужской области": "Калужская область",
        "рязанской области": "Рязанская область",
        "тамбовской области": "Тамбовская область",
        "волгоградской области": "Волгоградская область",
        "саратовской области": "Саратовская область",
        "самарской области": "Самарская область",
        "татарстане": "Республика Татарстан",
        "татарстана": "Республика Татарстан",
        "башкирии": "Республика Башкортостан",
        "башкортостане": "Республика Башкортостан",
        "крыму": "Республика Крым",
        "крыма": "Республика Крым",
    }

    for alias, region in aliases.items():
        if alias in low:
            return region

    return None


# =========================================================
# ОПРЕДЕЛЕНИЕ ГОРОДА
# =========================================================

def detect_city(text):
    low = text.lower()

    # Сначала проверяем известные города.
    # Сортируем по длине, чтобы Ростов-на-Дону
    # проверялся раньше коротких вариантов.
    cities = sorted(
        CITY_REGION.keys(),
        key=len,
        reverse=True
    )

    for city in cities:
        if city in low:
            return city.title()

    return None


# =========================================================
# ЛОКАЦИЯ
# =========================================================

def detect_location(text):
    city = detect_city(text)
    region = detect_region(text)

    if city and region:
        # Москва и Петербург — самостоятельные субъекты.
        if city.lower() == region.lower():
            return region

        return f"{city}, {region}"

    if region:
        return region

    # Если достоверно определить место нельзя,
    # ничего не придумываем.
    return None


# =========================================================
# ЧИСЛО ИЗ СЛОВА/ЦИФРЫ
# =========================================================

def parse_number(value):
    if not value:
        return None

    value = value.lower().strip(" ,.:;—-\"'()")

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


NUMBER_PATTERN = (
    r"(?:\d{1,3}|"
    + "|".join(
        sorted(
            map(re.escape, NUMBER_WORDS.keys()),
            key=len,
            reverse=True
        )
    )
    + r")"
)


# =========================================================
# ИЗВЛЕЧЕНИЕ КАНДИДАТОВ ПОТЕРЬ
# =========================================================

def extract_candidates(text, kind):
    low = text.lower()

    if kind == "dead":
        roots = [
            r"погиб(?:ли|ла|ло|ших|ший|шая)?",
            r"число погибших",
            r"количество погибших",
            r"жертв"
        ]
    else:
        roots = [
            r"пострадал(?:и|а|о|ших|ший|шая)?",
            r"ранен(?:ы|а|о|ых|ый|ая)?",
            r"число пострадавших",
            r"количество пострадавших",
            r"число раненых"
        ]

    candidates = []

    # Число после слова:
    # "погибли 5 человек"
    for root in roots:
        pattern = (
            root
            + r".{0,45}?\b("
            + NUMBER_PATTERN
            + r")\b"
        )

        for m in re.finditer(pattern, low):
            n = parse_number(m.group(1))

            if n is not None:
                candidates.append(
                    (m.start(), n)
                )

    # Число перед словом:
    # "пять человек погибли"
    if kind == "dead":
        endings = r"(?:человек|мужчин\w*|женщин\w*|дет\w*)\s+погиб"
    else:
        endings = (
            r"(?:человек|мужчин\w*|женщин\w*|дет\w*)\s+"
            r"(?:пострадал|ранен)"
        )

    pattern = (
        r"\b("
        + NUMBER_PATTERN
        + r")\b.{0,25}?"
        + endings
    )

    for m in re.finditer(pattern, low):
        n = parse_number(m.group(1))

        if n is not None:
            candidates.append(
                (m.start(), n)
            )

    return candidates


# =========================================================
# ИЗВЛЕЧЕНИЕ ПОГИБШИХ / ПОСТРАДАВШИХ
# =========================================================

def extract_casualties(text):
    dead_candidates = extract_candidates(text, "dead")
    injured_candidates = extract_candidates(text, "injured")

    dead = None
    injured = None

    # Для уточняющей новости нам важно последнее
    # релевантное утверждение в тексте.
    if dead_candidates:
        dead_candidates.sort(key=lambda x: x[0])
        dead = dead_candidates[-1][1]

    if injured_candidates:
        injured_candidates.sort(key=lambda x: x[0])
        injured = injured_candidates[-1][1]

    # Специальные конструкции:
    # "с 3 до 5 увеличилось число погибших"
    update_patterns = [
        (
            "dead",
            r"с\s+("
            + NUMBER_PATTERN
            + r")\s+до\s+("
            + NUMBER_PATTERN
            + r").{0,60}?(?:погибших|жертв)"
        ),
        (
            "injured",
            r"с\s+("
            + NUMBER_PATTERN
            + r")\s+до\s+("
            + NUMBER_PATTERN
            + r").{0,60}?(?:пострадавших|раненых)"
        ),
    ]

    low = text.lower()

    for kind, pattern in update_patterns:
        for m in re.finditer(pattern, low):
            final_value = parse_number(m.group(2))

            if final_value is None:
                continue

            if kind == "dead":
                dead = final_value
            else:
                injured = final_value

    return dead, injured


# =========================================================
# ДАТА СОБЫТИЯ
# =========================================================

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


def detect_event_datetime(text, entry_dt):
    """
    Не ищем произвольный год где-то в статье.
    За основу берем дату публикации RSS.

    Если в тексте есть 'сегодня', 'во вторник',
    'ночью' и т.п. — оставляем дату публикации.
    Если есть явные день+месяц рядом с описанием
    происшествия — используем их только если дата
    находится рядом с текущей датой публикации.
    """

    if not entry_dt:
        return None

    local_dt = entry_dt.astimezone(
        timezone(timedelta(hours=3))
    )

    low = text.lower()

    candidates = []

    month_names = "|".join(MONTHS.keys())

    pattern = (
        r"\b([0-3]?\d)\s+("
        + month_names
        + r")(?:\s+(\d{4})\s+года)?\b"
    )

    for m in re.finditer(pattern, low):
        day = int(m.group(1))
        month = MONTHS[m.group(2)]

        # ВАЖНО:
        # Старый случайный год из статьи не принимаем.
        year = local_dt.year

        try:
            candidate = datetime(
                year,
                month,
                day,
                tzinfo=local_dt.tzinfo
            )
        except ValueError:
            continue

        diff = abs(
            (candidate.date() - local_dt.date()).days
        )

        # Явную дату принимаем только если она
        # близка к дате публикации.
        if diff <= 2:
            candidates.append(candidate)

    if candidates:
        event_dt = min(
            candidates,
            key=lambda x: abs(
                (x - local_dt).total_seconds()
            )
        )
    else:
        event_dt = local_dt

    # Попытка найти время.
    time_patterns = [
        r"\b(?:около|примерно|в)\s+([0-2]?\d):([0-5]\d)\b",
        r"\b([0-2]?\d):([0-5]\d)\b",
    ]

    for pattern in time_patterns:
        m = re.search(pattern, low)

        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))

            if hour <= 23:
                event_dt = event_dt.replace(
                    hour=hour,
                    minute=minute,
                    second=0
                )
                break

    return event_dt


# =========================================================
# ФОРМАТ ДАТЫ
# =========================================================

MONTH_NAMES_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_event_date(dt):
    if not dt:
        return ""

    return (
        f"{dt.day} "
        f"{MONTH_NAMES_RU[dt.month]} "
        f"{dt.year} года"
    )


# =========================================================
# КРАТКОЕ ОПИСАНИЕ
# =========================================================

def make_description(text):
    text = clean_text(text)

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    good = []

    for sentence in sentences:
        low = sentence.lower()

        # Берём предложения непосредственно об атаке
        # или её последствиях.
        if (
            contains_attack(sentence)
            or contains_casualties(sentence)
        ):
            good.append(sentence.strip())

        if len(good) >= 2:
            break

    if not good:
        return ""

    result = " ".join(good)

    # Ограничиваем слишком длинные статьи.
    if len(result) > 550:
        result = result[:550]

        last_space = result.rfind(" ")

        if last_space > 0:
            result = result[:last_space]

        result += "…"

    return result


# =========================================================
# КЛЮЧ СОБЫТИЯ ДЛЯ ДЕДУПЛИКАЦИИ
# =========================================================

def normalize_location(location):
    return re.sub(
        r"[^а-яёa-z0-9]+",
        " ",
        location.lower()
    ).strip()


def event_key(location, event_dt, text):
    date_part = (
        event_dt.strftime("%Y-%m-%d")
        if event_dt
        else "unknown"
    )

    low = text.lower()

    if "бпла" in low or "беспилот" in low or "дрон" in low:
        attack_type = "drone"
    elif "ракет" in low:
        attack_type = "missile"
    elif "обстрел" in low:
        attack_type = "shelling"
    elif "взрыв" in low:
        attack_type = "explosion"
    else:
        attack_type = "attack"

    raw = (
        normalize_location(location)
        + "|"
        + date_part
        + "|"
        + attack_type
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# =========================================================
# ПРОВЕРКА ДУБЛЯ / ОБНОВЛЕНИЯ
# =========================================================

def check_event_update(key, dead, injured):
    """
    Возвращает:
    new     — новое событие
    update  — цифры выросли
    skip    — дубль или цифры не изменились
    """

    old = seen.get(key)

    if not old:
        return "new", None

    old_dead = old.get("dead")
    old_injured = old.get("injured")

    increased = False

    if dead is not None:
        if old_dead is None or dead > old_dead:
            increased = True

    if injured is not None:
        if old_injured is None or injured > old_injured:
            increased = True

    if increased:
        return "update", old

    return "skip", old


# =========================================================
# HTML
# =========================================================

def safe(value):
    return html.escape(str(value))


# =========================================================
# ФОРМИРОВАНИЕ ПОСТА
# =========================================================

def build_message(
    source,
    url,
    location,
    event_dt,
    description,
    dead,
    injured,
    mode
):
    parts = []

    parts.append(
        f"⚡️ <b>{safe(location)}</b>"
    )

    if event_dt:
        parts.append(
            "📅 "
            + safe(format_event_date(event_dt))
        )

    if mode == "update":
        parts.append(
            "<b>По новым уточнённым данным:</b>"
        )

    if description:
        parts.append(
            safe(description)
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
    parts.append(
        f'Источник: <a href="{html.escape(url, quote=True)}">'
        f'{safe(source)}</a>'
    )

    return "\n\n".join(parts)


# =========================================================
# СОХРАНЕНИЕ СОБЫТИЯ
# =========================================================

def remember_event(
    key,
    dead,
    injured,
    location,
    event_dt,
    source,
    url
):
    old = seen.get(key, {})

    # Не уменьшаем уже известные цифры.
    old_dead = old.get("dead")
    old_injured = old.get("injured")

    final_dead = dead
    final_injured = injured

    if old_dead is not None:
        if final_dead is None:
            final_dead = old_dead
        else:
            final_dead = max(old_dead, final_dead)

    if old_injured is not None:
        if final_injured is None:
            final_injured = old_injured
        else:
            final_injured = max(
                old_injured,
                final_injured
            )

    seen[key] = {
        "dead": final_dead,
        "injured": final_injured,
        "location": location,
        "date": (
            event_dt.isoformat()
            if event_dt
            else None
        ),
        "source": source,
        "url": url,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    save_seen(seen)


# =========================================================
# ОБРАБОТКА ОДНОЙ НОВОСТИ
# =========================================================

def process_entry(source, entry):
    title = clean_text(
        getattr(entry, "title", "")
    )

    summary = clean_text(
        getattr(entry, "summary", "")
    )

    url = getattr(entry, "link", None)

    if not url:
        return

    # 1. Только свежие публикации.
    if not is_fresh(entry):
        return

    entry_dt = get_entry_datetime(entry)

    preliminary = (
        title
        + ". "
        + summary
    )

    # 2. Быстрый фильтр до загрузки статьи.
    if not contains_attack(preliminary):
        return

    # Загружаем полный текст.
    article = get_article_text(url)

    full_text = clean_text(
        title
        + ". "
        + summary
        + ". "
        + article
    )

    if not full_text:
        return

    # 3. Обязательно атака.
    if not contains_attack(full_text):
        return

    # 4. Обязательно есть погибшие/пострадавшие.
    if not contains_casualties(full_text):
        return

    # 5. Определяем место по ТЕКСТУ,
    # а не по рубрике СМИ.
    location = detect_location(full_text)

    if not location:
        print(
            "Пропуск: не удалось достоверно "
            "определить регион:",
            title
        )
        return

    # 6. Зарубежные события отбрасываем.
    if clearly_foreign(full_text):
        return

    # 7. Извлекаем цифры.
    dead, injured = extract_casualties(full_text)

    # Если нет ни одной конкретной цифры —
    # не публикуем.
    if dead is None and injured is None:
        return

    # 8. Дата происшествия.
    event_dt = detect_event_datetime(
        full_text,
        entry_dt
    )

    if not event_dt:
        return

    now_local = datetime.now(
        timezone(timedelta(hours=3))
    )

    # Дополнительная страховка от старых событий.
    if (
        now_local - event_dt
        > timedelta(hours=MAX_EVENT_AGE_HOURS)
    ):
        return

    # 9. Краткое описание.
    description = make_description(
        full_text
    )

    # 10. Ключ события.
    key = event_key(
        location,
        event_dt,
        full_text
    )

    mode, old = check_event_update(
        key,
        dead,
        injured
    )

    # 11. Полный дубль — ничего не публикуем.
    if mode == "skip":
        print(
            "Дубль пропущен:",
            location,
            dead,
            injured
        )
        return

    # 12. Создаём пост.
    message = build_message(
        source=source,
        url=url,
        location=location,
        event_dt=event_dt,
        description=description,
        dead=dead,
        injured=injured,
        mode=mode
    )

    # 13. Публикуем.
    try:
        bot.send_message(
            CHANNEL_ID,
            message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        remember_event(
            key,
            dead,
            injured,
            location,
            event_dt,
            source,
            url
        )

        print(
            "Опубликовано:",
            mode,
            location,
            dead,
            injured
        )

    except Exception as e:
        print(
            "Ошибка Telegram:",
            source,
            url,
            e
        )


# =========================================================
# МОНИТОРИНГ
# =========================================================

def monitor():
    print("Monitoring started")

    while True:
        for source, feed_url in SOURCES:
            try:
                feed = feedparser.parse(
                    feed_url
                )

                for entry in feed.entries[:30]:
                    try:
                        process_entry(
                            source,
                            entry
                        )
                    except Exception as e:
                        print(
                            "Ошибка обработки новости:",
                            source,
                            e
                        )

            except Exception as e:
                print(
                    "Ошибка RSS:",
                    source,
                    e
                )

        time.sleep(CHECK_INTERVAL)


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    print("Starting container")
    monitor()