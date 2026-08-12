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

MSK = timezone(timedelta(hours=3))
CHECK_INTERVAL = 180
STATE_FILE = "state.json"


# ============================================================
# ИСТОЧНИКИ
# Российская газета УДАЛЕНА
# ============================================================

SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Интерфакс", "https://www.interfax.ru/rss.asp"),
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


# ============================================================
# РЕГИОНЫ
# ============================================================

REGIONS = [
    "Республика Адыгея",
    "Республика Алтай",
    "Республика Башкортостан",
    "Республика Бурятия",
    "Республика Дагестан",
    "Республика Ингушетия",
    "Кабардино-Балкарская Республика",
    "Республика Калмыкия",
    "Карачаево-Черкесская Республика",
    "Республика Карелия",
    "Республика Коми",
    "Республика Крым",
    "Республика Марий Эл",
    "Республика Мордовия",
    "Республика Саха",
    "Республика Северная Осетия",
    "Республика Татарстан",
    "Республика Тыва",
    "Удмуртская Республика",
    "Республика Хакасия",
    "Чеченская Республика",
    "Чувашская Республика",

    "Алтайский край",
    "Забайкальский край",
    "Камчатский край",
    "Краснодарский край",
    "Красноярский край",
    "Пермский край",
    "Приморский край",
    "Ставропольский край",
    "Хабаровский край",

    "Амурская область",
    "Архангельская область",
    "Астраханская область",
    "Белгородская область",
    "Брянская область",
    "Владимирская область",
    "Волгоградская область",
    "Вологодская область",
    "Воронежская область",
    "Ивановская область",
    "Иркутская область",
    "Калининградская область",
    "Калужская область",
    "Кемеровская область",
    "Кировская область",
    "Костромская область",
    "Курганская область",
    "Курская область",
    "Ленинградская область",
    "Липецкая область",
    "Магаданская область",
    "Московская область",
    "Мурманская область",
    "Нижегородская область",
    "Новгородская область",
    "Новосибирская область",
    "Омская область",
    "Оренбургская область",
    "Орловская область",
    "Пензенская область",
    "Псковская область",
    "Ростовская область",
    "Рязанская область",
    "Самарская область",
    "Саратовская область",
    "Сахалинская область",
    "Свердловская область",
    "Смоленская область",
    "Тамбовская область",
    "Тверская область",
    "Томская область",
    "Тульская область",
    "Тюменская область",
    "Ульяновская область",
    "Челябинская область",
    "Ярославская область",

    "Москва",
    "Санкт-Петербург",
    "Севастополь",
]


# ============================================================
# ГОРОД -> РЕГИОН
# ============================================================

CITY_REGION = {
    # Белгородская область
    "Белгород": "Белгородская область",
    "Шебекино": "Белгородская область",
    "Грайворон": "Белгородская область",
    "Валуйки": "Белгородская область",
    "Старый Оскол": "Белгородская область",
    "Губкин": "Белгородская область",

    # Курская область
    "Курск": "Курская область",
    "Рыльск": "Курская область",
    "Суджа": "Курская область",
    "Льгов": "Курская область",
    "Курчатов": "Курская область",

    # Брянская область
    "Брянск": "Брянская область",
    "Клинцы": "Брянская область",
    "Стародуб": "Брянская область",

    # Воронежская область
    "Воронеж": "Воронежская область",

    # Ростовская область
    "Ростов-на-Дону": "Ростовская область",
    "Таганрог": "Ростовская область",
    "Новошахтинск": "Ростовская область",
    "Шахты": "Ростовская область",
    "Батайск": "Ростовская область",
    "Каменск-Шахтинский": "Ростовская область",

    # Краснодарский край
    "Краснодар": "Краснодарский край",
    "Новороссийск": "Краснодарский край",
    "Анапа": "Краснодарский край",
    "Геленджик": "Краснодарский край",
    "Сочи": "Краснодарский край",
    "Туапсе": "Краснодарский край",
    "Темрюк": "Краснодарский край",
    "Армавир": "Краснодарский край",
    "Славянск-на-Кубани": "Краснодарский край",

    # Татарстан
    "Казань": "Республика Татарстан",
    "Нижнекамск": "Республика Татарстан",
    "Елабуга": "Республика Татарстан",
    "Альметьевск": "Республика Татарстан",

    # Крым
    "Керчь": "Республика Крым",
    "Симферополь": "Республика Крым",
    "Ялта": "Республика Крым",
    "Феодосия": "Республика Крым",
    "Джанкой": "Республика Крым",
    "Евпатория": "Республика Крым",

    # федеральные города
    "Москва": "Москва",
    "Санкт-Петербург": "Санкт-Петербург",
    "Севастополь": "Севастополь",
}


# ============================================================
# КЛЮЧЕВЫЕ СЛОВА
# ============================================================

ATTACK_WORDS = [
    "бпла",
    "беспилот",
    "дрон",
    "fpv",
    "обстрел",
    "обстреля",
    "атак",
    "удар",
    "ракет",
    "снаряд",
    "боеприпас",
    "артиллер",
    "миномет",
    "миномёт",
    "пво",
    "про",
    "обломк",
    "детонац",
    "взрыв",
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
    "жертв",
]


# Материалы такого типа нам не нужны
OLD_MATERIAL_WORDS = [
    "корреспондент побывал",
    "репортаж",
    "фоторепортаж",
    "интервью",
    "воспоминания",
    "как добирался",
    "что увидел и пережил",
    "рассказал о поездке",
    "рассказала о поездке",
    "год назад",
    "года назад",
    "лет назад",
    "архив",
    "история очевидца",
]


# ============================================================
# СОСТОЯНИЕ
# ============================================================

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"events": {}}

        data.setdefault("events", {})
        return data

    except Exception:
        return {"events": {}}


state = load_state()


def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# ВРЕМЯ
# ============================================================

def now():
    return datetime.now(MSK)


def today():
    return now().date()


# ============================================================
# ТЕКСТ
# ============================================================

def clean(text):
    if not text:
        return ""

    text = BeautifulSoup(
        text,
        "html.parser"
    ).get_text(" ")

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def split_sentences(text):
    return [
        x.strip()
        for x in re.split(
            r"(?<=[.!?])\s+",
            clean(text)
        )
        if len(x.strip()) > 10
    ]


def has_attack(text):
    low = text.lower()
    return any(word in low for word in ATTACK_WORDS)


def has_casualty(text):
    low = text.lower()
    return any(word in low for word in CASUALTY_WORDS)


# ============================================================
# СТАТЬЯ
# ============================================================

def get_article(url):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        r.raise_for_status()

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        # Убираем всё, что чаще всего содержит
        # меню, связанные новости, рекламу и футер.
        for tag in soup.find_all([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "button",
            "noscript"
        ]):
            tag.decompose()

        paragraphs = []

        for p in soup.find_all("p"):
            txt = clean(p.get_text(" "))

            if 30 <= len(txt) <= 2500:
                paragraphs.append(txt)

        return " ".join(paragraphs)[:30000]

    except Exception as e:
        print("ARTICLE ERROR:", url, e)
        return ""


# ============================================================
# RSS ДАТА
# ============================================================

def published_datetime(entry):
    try:
        t = getattr(
            entry,
            "published_parsed",
            None
        )

        if not t:
            return None

        dt = datetime(
            t.tm_year,
            t.tm_mon,
            t.tm_mday,
            t.tm_hour,
            t.tm_min,
            t.tm_sec,
            tzinfo=timezone.utc
        )

        return dt.astimezone(MSK)

    except Exception:
        return None


# ============================================================
# ТОЛЬКО СВЕЖИЕ ПУБЛИКАЦИИ
# ============================================================

def publication_is_current(entry):
    dt = published_datetime(entry)

    if not dt:
        return False

    if dt.date() != today():
        return False

    age = now() - dt

    if age < timedelta(minutes=-10):
        return False

    # Не тащим старые публикации сегодняшнего дня,
    # найденные RSS спустя много часов.
    if age > timedelta(hours=8):
        return False

    return True


# ============================================================
# ДАТЫ
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


MONTH_NAMES = [
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
    "декабря",
]


def find_dates(text):
    result = []

    pattern = (
        r"\b([0-3]?\d)\s+"
        r"(января|февраля|марта|апреля|мая|июня|"
        r"июля|августа|сентября|октября|ноября|декабря)"
        r"(?:\s+(\d{4}))?"
    )

    for m in re.finditer(
        pattern,
        text.lower()
    ):
        day = int(m.group(1))
        month = MONTHS[m.group(2)]

        year = (
            int(m.group(3))
            if m.group(3)
            else today().year
        )

        try:
            result.append(
                datetime(
                    year,
                    month,
                    day
                ).date()
            )
        except ValueError:
            pass

    return result


def current_event(title, summary, article, pub_dt):
    """
    Строгая проверка:
    сегодняшняя публикация сама по себе
    НЕ означает сегодняшнее происшествие.
    """

    text = clean(
        title + ". " +
        summary + ". " +
        article[:5000]
    )

    low = text.lower()

    if any(
        marker in low
        for marker in OLD_MATERIAL_WORDS
    ):
        return False

    dates = find_dates(text[:3500])

    # Если явно упомянута сегодняшняя дата
    if today() in dates:
        return True

    # Если в начале статьи стоит прошлая дата,
    # материал не публикуем.
    beginning_dates = find_dates(
        text[:1800]
    )

    if any(
        d < today()
        for d in beginning_dates
    ):
        return False

    current_markers = [
        "сегодня",
        "сегодня утром",
        "сегодня днем",
        "сегодня днём",
        "сегодня ночью",
        "этой ночью",
        "минувшей ночью",
        "в ночь на",
        "утром в среду",
        "утром во вторник",
        "утром в понедельник",
        "утром в четверг",
        "утром в пятницу",
        "утром в субботу",
        "утром в воскресенье",
    ]

    first = low[:2500]

    if any(
        marker in first
        for marker in current_markers
    ):
        return True

    # Если дата события не написана,
    # допускаем только очень свежую публикацию,
    # где заголовок/начало прямо описывают происшествие.
    if pub_dt:
        age = now() - pub_dt

        direct_markers = [
            "атаковал",
            "атаковала",
            "атаковали",
            "атакован",
            "подвергся атаке",
            "подверглась атаке",
            "в результате атаки",
            "в результате обстрела",
            "при атаке",
            "при обстреле",
            "после атаки",
            "обломки бпла",
            "обломки беспилотника",
            "при падении обломков",
        ]

        if (
            timedelta(0)
            <= age
            <= timedelta(hours=3)
            and any(x in first for x in direct_markers)
        ):
            return True

    return False


# ============================================================
# ПРЕДЛОЖЕНИЯ, СВЯЗАННЫЕ С ОДНИМ ПРОИСШЕСТВИЕМ
# ============================================================

def incident_blocks(title, article):
    """
    Возвращает небольшие локальные блоки текста.

    Это важно: нельзя объединять всю статью в один incident,
    потому что в сводной статье могут одновременно быть
    Белгород, Курск, Краснодар и т.д.
    """

    sentences = split_sentences(
        title + ". " + article
    )

    blocks = []

    for i, sent in enumerate(sentences):

        if not has_casualty(sent):
            continue

        start = max(0, i - 2)
        end = min(len(sentences), i + 3)

        block_sentences = sentences[start:end]
        block = " ".join(block_sentences)

        if not has_attack(block):
            continue

        blocks.append({
            "sentences": block_sentences,
            "casualty_index": i - start,
            "text": block
        })

    return blocks


# ============================================================
# ГЕОГРАФИЯ
# ============================================================

def find_cities(text):
    low = text.lower()
    result = []

    for city in CITY_REGION:
        for m in re.finditer(
            r"(?<!\w)" +
            re.escape(city.lower()) +
            r"(?!\w)",
            low
        ):
            result.append(
                (m.start(), city)
            )

    return sorted(result)


def find_regions(text):
    low = text.lower()
    result = []

    for region in REGIONS:
        for m in re.finditer(
            r"(?<!\w)" +
            re.escape(region.lower()) +
            r"(?!\w)",
            low
        ):
            result.append(
                (m.start(), region)
            )

    return sorted(result)


def location_from_sentence(sentence):
    cities = find_cities(sentence)

    if cities:
        city = cities[0][1]

        # Москва особенно опасна как ложное место.
        if city == "Москва":
            low = sentence.lower()

            valid = [
                "в москве",
                "на москву",
                "над москвой",
                "атаковали москву",
                "атака на москву",
            ]

            if not any(x in low for x in valid):
                cities = [
                    x for x in cities
                    if x[1] != "Москва"
                ]

                if cities:
                    city = cities[0][1]
                else:
                    city = None

        if city:
            return city, CITY_REGION.get(city)

    regions = find_regions(sentence)

    if regions:
        return None, regions[0][1]

    return None, None


def determine_block_location(block):
    """
    Ищем место максимально близко
    к предложению с жертвами.

    Заголовок статьи НЕ имеет автоматического
    приоритета, потому что статья может быть сводной.
    """

    sentences = block["sentences"]
    ci = block["casualty_index"]

    # 1. Само предложение с потерями
    city, region = location_from_sentence(
        sentences[ci]
    )

    if city or region:
        return city, region

    # 2. Предыдущее предложение
    if ci - 1 >= 0:
        city, region = location_from_sentence(
            sentences[ci - 1]
        )

        if city or region:
            return city, region

    # 3. Следующее
    if ci + 1 < len(sentences):
        city, region = location_from_sentence(
            sentences[ci + 1]
        )

        if city or region:
            return city, region

    # 4. Только после этого весь локальный блок
    cities = find_cities(block["text"])

    # Если в маленьком блоке несколько разных городов,
    # не угадываем.
    unique_cities = list(dict.fromkeys(
        x[1] for x in cities
        if x[1] != "Москва"
    ))

    if len(unique_cities) == 1:
        city = unique_cities[0]
        return city, CITY_REGION.get(city)

    regions = find_regions(block["text"])

    unique_regions = list(dict.fromkeys(
        x[1] for x in regions
        if x[1] != "Москва"
    ))

    if len(unique_regions) == 1:
        return None, unique_regions[0]

    return None, None


# ============================================================
# ЧИСЛА
# ============================================================

WORDS = {
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
    "шесть": 6,
    "семь": 7,
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
}


NUM = (
    r"(?:\d+|"
    + "|".join(
        sorted(
            WORDS.keys(),
            key=len,
            reverse=True
        )
    )
    + ")"
)


def number(value):
    value = value.lower()

    if value.isdigit():
        return int(value)

    return WORDS.get(value)


DEAD_PATTERNS = [
    rf"(?:погибли|погибло)\s+(?:не менее\s+|как минимум\s+)?({NUM})\s+(?:человек|человека|людей)",
    rf"({NUM})\s+(?:человек|человека|людей)\s+(?:погибли|погибло)",
    rf"(?:число|количество)\s+погибших.*?(?:до|составило|достигло|увеличилось до)\s+({NUM})",
    rf"погибших.*?(?:до|составило|достигло|увеличилось до)\s+({NUM})",
]


INJURED_PATTERNS = [
    rf"(?:пострадали|пострадало)\s+(?:не менее\s+|как минимум\s+)?({NUM})\s+(?:человек|человека|людей)",
    rf"({NUM})\s+(?:человек|человека|людей)\s+(?:пострадали|пострадало)",
    rf"(?:число|количество)\s+пострадавших.*?(?:до|составило|достигло|увеличилось до)\s+({NUM})",
    rf"пострадавших.*?(?:до|составило|достигло|увеличилось до)\s+({NUM})",
    rf"(?:ранены|ранено)\s+({NUM})\s+(?:человек|человека|людей)",
    rf"({NUM})\s+(?:человек|человека|людей)\s+(?:ранены|ранено)",
]


SINGLE_DEAD = [
    r"\bпогиб\s+реб[её]нок\b",
    r"\bпогибла\s+девочк",
    r"\bпогиб\s+мальчик\b",
    r"\bпогиб\s+мужчина\b",
    r"\bпогибла\s+женщина\b",
    r"\bпогиб\s+водитель\b",
    r"\bпогибла\s+местная жительница\b",
    r"\bпогиб\s+местный житель\b",
    r"\bпогиб\s+мирный житель\b",
    r"\bпогибла\s+мирная жительница\b",
]


SINGLE_INJURED = [
    r"\bпострадал\s+реб[её]нок\b",
    r"\bпострадала\s+девочк",
    r"\bпострадал\s+мальчик\b",
    r"\bпострадал\s+мужчина\b",
    r"\bпострадала\s+женщина\b",
    r"\bранен\s+мужчина\b",
    r"\bранена\s+женщина\b",
    r"\bранен\s+реб[её]нок\b",
    r"\bпострадал\s+мирный житель\b",
    r"\bпострадала\s+мирная жительница\b",
]


def extract_from_sentence(sentence):
    low = sentence.lower()

    dead = []
    injured = []

    for pattern in DEAD_PATTERNS:
        for m in re.finditer(
            pattern,
            low,
            flags=re.I
        ):
            n = number(m.group(1))

            if n is not None:
                dead.append(n)

    if any(
        re.search(pattern, low)
        for pattern in SINGLE_DEAD
    ):
        dead.append(1)

    for pattern in INJURED_PATTERNS:
        for m in re.finditer(
            pattern,
            low,
            flags=re.I
        ):
            n = number(m.group(1))

            if n is not None:
                injured.append(n)

    if any(
        re.search(pattern, low)
        for pattern in SINGLE_INJURED
    ):
        injured.append(1)

    return (
        max(dead) if dead else None,
        max(injured) if injured else None
    )


def extract_block_numbers(block):
    """
    Цифры сначала берутся из предложения
    с жертвами.

    Это предотвращает перенос цифр из
    соседнего региона/эпизода.
    """

    sentences = block["sentences"]
    ci = block["casualty_index"]

    dead, injured = extract_from_sentence(
        sentences[ci]
    )

    # Если в самом предложении нашли хоть что-то,
    # этого достаточно.
    if dead is not None or injured is not None:
        return dead, injured

    # Иногда: "Погиб мужчина. Еще трое пострадали."
    # Поэтому смотрим одно соседнее предложение,
    # но только если оно тоже содержит потери.
    candidates = []

    for idx in [ci - 1, ci, ci + 1]:
        if 0 <= idx < len(sentences):
            sent = sentences[idx]

            if has_casualty(sent):
                d, inj = extract_from_sentence(sent)
                candidates.append((d, inj))

    dead_values = [
        d for d, _ in candidates
        if d is not None
    ]

    injured_values = [
        inj for _, inj in candidates
        if inj is not None
    ]

    return (
        max(dead_values) if dead_values else None,
        max(injured_values) if injured_values else None
    )


# ============================================================
# ВРЕМЯ СОБЫТИЯ
# ============================================================

def incident_time(text):
    patterns = [
        r"\bв\s+([01]?\d|2[0-3]):([0-5]\d)\b",
        r"\bоколо\s+([01]?\d|2[0-3]):([0-5]\d)\b",
    ]

    for pattern in patterns:
        m = re.search(
            pattern,
            text.lower()
        )

        if m:
            return (
                f"{int(m.group(1)):02d}:"
                f"{m.group(2)}"
            )

    return None


# ============================================================
# ОПИСАНИЕ
# ============================================================

def make_description(block):
    sentences = block["sentences"]
    ci = block["casualty_index"]

    chosen = []

    # Ищем предложение об атаке максимально близко
    # к предложению о жертвах.
    for distance in [0, 1, 2]:

        indexes = []

        if distance == 0:
            indexes = [ci]
        else:
            indexes = [
                ci - distance,
                ci + distance
            ]

        for idx in indexes:
            if 0 <= idx < len(sentences):
                sent = sentences[idx]

                if has_attack(sent):
                    chosen.append(sent)

        if chosen:
            break

    casualty_sentence = sentences[ci]

    if (
        casualty_sentence not in chosen
        and has_casualty(casualty_sentence)
    ):
        chosen.append(casualty_sentence)

    # Убираем повторы
    unique = []

    for sent in chosen:
        if sent not in unique:
            unique.append(sent)

    if not unique:
        return None

    result = " ".join(unique)

    if len(result) > 420:
        result = (
            result[:417]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return result


# ============================================================
# ДАТА В ПОСТЕ
# ============================================================

def date_text():
    d = today()

    return (
        f"{d.day} "
        f"{MONTH_NAMES[d.month]} "
        f"{d.year} года"
    )


# ============================================================
# ТИП АТАКИ
# ============================================================

def attack_type(text):
    low = text.lower()

    if (
        "бпла" in low
        or "беспилот" in low
        or "дрон" in low
        or "fpv" in low
    ):
        return "uav"

    if (
        "обстрел" in low
        or "артиллер" in low
        or "мином" in low
    ):
        return "shelling"

    if "ракет" in low:
        return "missile"

    if (
        "пво" in low
        or "про" in low
        or "обломк" in low
    ):
        return "airdefense"

    return "attack"


# ============================================================
# КЛЮЧ СОБЫТИЯ
# ============================================================

def event_key(city, region, block):
    """
    Место + сегодняшний день + тип атаки.

    Разные СМИ с одним происшествием
    не создают повторный пост.
    """

    place = city or region

    raw = (
        f"{today().isoformat()}|"
        f"{place.lower()}|"
        f"{attack_type(block['text'])}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# НОВАЯ ИНФОРМАЦИЯ / ОБНОВЛЕНИЕ
# ============================================================

def publication_status(
    key,
    dead,
    injured
):
    old = state["events"].get(key)

    if not old:
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

    return "skip"


def remember(
    key,
    dead,
    injured,
    url,
    city,
    region
):
    old = state["events"].get(
        key,
        {}
    )

    old_dead = old.get("dead")
    old_injured = old.get("injured")

    if old_dead is not None:
        if dead is None:
            dead = old_dead
        else:
            dead = max(
                dead,
                old_dead
            )

    if old_injured is not None:
        if injured is None:
            injured = old_injured
        else:
            injured = max(
                injured,
                old_injured
            )

    state["events"][key] = {
        "dead": dead,
        "injured": injured,
        "url": url,
        "city": city,
        "region": region,
        "date": today().isoformat(),
        "updated": now().isoformat()
    }

    save_state()


# ============================================================
# МЕСТО
# ============================================================

def location_text(city, region):
    if city and region:

        if city == region:
            return city

        return f"{city}, {region}"

    return region or city


# ============================================================
# TELEGRAM
# ============================================================

def build_message(
    city,
    region,
    description,
    dead,
    injured,
    source,
    url,
    update=False,
    event_time=None
):
    parts = []

    if update:
        parts.append(
            "🔄 <b>По новым уточнённым данным</b>"
        )

    place = location_text(
        city,
        region
    )

    parts.append(
        f"⚡️ <b>{html.escape(place)}</b>"
    )

    date_line = (
        f"📅 {html.escape(date_text())}"
    )

    if event_time:
        date_line += (
            f", {html.escape(event_time)}"
        )

    parts.append(date_line)

    parts.append(
        html.escape(description)
    )

    losses = []

    if dead is not None:
        losses.append(
            f"<b>Погибли: {dead} чел.</b>"
        )

    if injured is not None:
        losses.append(
            f"<b>Пострадали: {injured} чел.</b>"
        )

    parts.append(
        "\n".join(losses)
    )

    safe_url = html.escape(
        url,
        quote=True
    )

    parts.append(
        'Источник: '
        f'<a href="{safe_url}">'
        f'{html.escape(source)}</a>'
    )

    return "\n\n".join(parts)


# ============================================================
# ОБРАБОТКА ОДНОГО БЛОКА
# ============================================================

def process_block(
    block,
    source,
    url
):
    city, region = determine_block_location(
        block
    )

    if not city and not region:
        print(
            "SKIP BLOCK UNKNOWN LOCATION:",
            block["text"][:150]
        )
        return

    dead, injured = extract_block_numbers(
        block
    )

    if dead is None and injured is None:
        print(
            "SKIP BLOCK NO NUMBERS:",
            block["text"][:150]
        )
        return

    description = make_description(
        block
    )

    if not description:
        return

    key = event_key(
        city,
        region,
        block
    )

    status = publication_status(
        key,
        dead,
        injured
    )

    if status == "skip":
        print(
            "SKIP DUPLICATE:",
            location_text(city, region),
            dead,
            injured
        )
        return

    ev_time = incident_time(
        block["text"]
    )

    message = build_message(
        city=city,
        region=region,
        description=description,
        dead=dead,
        injured=injured,
        source=source,
        url=url,
        update=(status == "update"),
        event_time=ev_time
    )

    bot.send_message(
        CHANNEL_ID,
        message,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    remember(
        key,
        dead,
        injured,
        url,
        city,
        region
    )

    print(
        "PUBLISHED:",
        status,
        location_text(city, region),
        "dead=",
        dead,
        "injured=",
        injured
    )


# ============================================================
# ОБРАБОТКА НОВОСТИ
# ============================================================

def process(entry, source):
    title = clean(
        getattr(
            entry,
            "title",
            ""
        )
    )

    url = getattr(
        entry,
        "link",
        ""
    )

    if not title or not url:
        return

    if not publication_is_current(entry):
        return

    pub_dt = published_datetime(entry)

    summary = clean(
        getattr(
            entry,
            "summary",
            ""
        )
    )

    preview = (
        title + ". " + summary
    )

    # Сначала дешёвая RSS-фильтрация
    if not (
        has_attack(preview)
        or has_casualty(preview)
    ):
        return

    article = get_article(url)

    if not article:
        return

    # Нужны одновременно атака и жертвы
    whole_start = (
        title + ". " +
        summary + ". " +
        article[:6000]
    )

    if not has_attack(whole_start):
        return

    if not has_casualty(whole_start):
        return

    # Только сегодняшнее событие
    if not current_event(
        title,
        summary,
        article,
        pub_dt
    ):
        print(
            "SKIP OLD EVENT:",
            title
        )
        return

    blocks = incident_blocks(
        title,
        article
    )

    if not blocks:
        print(
            "SKIP NO INCIDENT BLOCK:",
            title
        )
        return

    # В одной статье может быть несколько эпизодов.
    # Каждый обрабатывается отдельно.
    local_seen = set()

    for block in blocks:

        normalized = re.sub(
            r"\W+",
            " ",
            block["text"].lower()
        ).strip()

        block_hash = hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()

        if block_hash in local_seen:
            continue

        local_seen.add(block_hash)

        try:
            process_block(
                block,
                source,
                url
            )

        except Exception as e:
            print(
                "BLOCK ERROR:",
                source,
                e
            )


# ============================================================
# ОЧИСТКА СОСТОЯНИЯ
# ============================================================

def cleanup():
    current = today().isoformat()

    events = {}

    for key, value in state.get(
        "events",
        {}
    ).items():

        if value.get("date") == current:
            events[key] = value

    state["events"] = events

    save_state()


# ============================================================
# RSS
# ============================================================

def check_sources():
    for source, rss in SOURCES:

        try:
            print(
                "CHECK:",
                source
            )

            feed = feedparser.parse(
                rss
            )

            entries = list(
                feed.entries[:50]
            )

            # Сначала более ранние,
            # потом обновления.
            entries.reverse()

            for entry in entries:

                try:
                    process(
                        entry,
                        source
                    )

                except Exception as e:
                    print(
                        "ENTRY ERROR:",
                        source,
                        e
                    )

        except Exception as e:
            print(
                "SOURCE ERROR:",
                source,
                e
            )


# ============================================================
# START
# ============================================================

print("==============================")
print("BOT STARTED")
print("TIME:", now())
print("CHANNEL:", CHANNEL_ID)
print("SOURCES:", ", ".join(x[0] for x in SOURCES))
print("==============================")


last_day = today()


while True:

    try:
        if today() != last_day:
            cleanup()
            last_day = today()

        check_sources()

    except Exception as e:
        print(
            "MAIN ERROR:",
            e
        )

    time.sleep(CHECK_INTERVAL)