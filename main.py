import os
import re
import time
import json
import hashlib
import html
from datetime import datetime, timedelta

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
    raise RuntimeError("Не задан BOT_TOKEN")

if not CHANNEL_ID:
    raise RuntimeError("Не задан CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

CHECK_INTERVAL = 600
SEEN_FILE = "seen.json"


# ============================================================
# СМИ
# ============================================================

SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Российская газета", "https://rg.ru/xml/index.xml"),
    ("Интерфакс", "https://www.interfax.ru/rss.asp"),
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


# ============================================================
# СУБЪЕКТЫ РФ
#
# Список нужен прежде всего для распознавания текста российских
# СМИ. Он не используется для определения международного статуса.
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
    "Республика Марий Эл",
    "Республика Мордовия",
    "Республика Саха (Якутия)",
    "Республика Северная Осетия — Алания",
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

    "Еврейская автономная область",

    "Ненецкий автономный округ",
    "Ханты-Мансийский автономный округ",
    "Чукотский автономный округ",
    "Ямало-Ненецкий автономный округ",

    # Названия, которые могут встречаться в российских СМИ
    "Республика Крым",
    "Севастополь",
    "Донецкая Народная Республика",
    "Луганская Народная Республика",
    "Запорожская область",
    "Херсонская область",
]


# ============================================================
# ВАРИАНТЫ НАЗВАНИЙ РЕГИОНОВ
# ============================================================

REGION_ALIASES = {
    "татарстан": "Республика Татарстан",
    "башкирия": "Республика Башкортостан",
    "башкортостан": "Республика Башкортостан",
    "дагестан": "Республика Дагестан",
    "удмуртия": "Удмуртская Республика",
    "чувашия": "Чувашская Республика",
    "мордовия": "Республика Мордовия",
    "бурятия": "Республика Бурятия",
    "карелия": "Республика Карелия",
    "хакасия": "Республика Хакасия",
    "калмыкия": "Республика Калмыкия",
    "якутия": "Республика Саха (Якутия)",
    "адыгея": "Республика Адыгея",
    "алтай": "Республика Алтай",
    "ингушетия": "Республика Ингушетия",
    "чечня": "Чеченская Республика",
    "кубань": "Краснодарский край",
    "подмосковье": "Московская область",
    "ставрополье": "Ставропольский край",
    "приморье": "Приморский край",
    "забайкалье": "Забайкальский край",
    "кузбасс": "Кемеровская область",
}


# ============================================================
# ОСНОВНЫЕ ГОРОДА И НАСЕЛЕННЫЕ ПУНКТЫ
# Это не единственный способ определения региона.
# ============================================================

CITY_REGION = {
    "белгород": "Белгородская область",
    "шебекино": "Белгородская область",
    "грайворон": "Белгородская область",
    "валуйки": "Белгородская область",
    "старый оскол": "Белгородская область",
    "губкин": "Белгородская область",

    "курск": "Курская область",
    "рыльск": "Курская область",
    "льгов": "Курская область",
    "железногорск": "Курская область",
    "курчатов": "Курская область",

    "брянск": "Брянская область",
    "клинцы": "Брянская область",
    "стародуб": "Брянская область",

    "воронеж": "Воронежская область",
    "борисоглебск": "Воронежская область",

    "ростов-на-дону": "Ростовская область",
    "таганрог": "Ростовская область",
    "новочеркасск": "Ростовская область",
    "шахты": "Ростовская область",
    "азов": "Ростовская область",
    "батайск": "Ростовская область",

    "краснодар": "Краснодарский край",
    "новороссийск": "Краснодарский край",
    "анапа": "Краснодарский край",
    "геленджик": "Краснодарский край",
    "сочи": "Краснодарский край",
    "туапсе": "Краснодарский край",
    "ейск": "Краснодарский край",
    "славянск-на-кубани": "Краснодарский край",

    "ставрополь": "Ставропольский край",
    "невинномысск": "Ставропольский край",

    "волгоград": "Волгоградская область",
    "волжский": "Волгоградская область",
    "калач-на-дону": "Волгоградская область",

    "саратов": "Саратовская область",
    "энгельс": "Саратовская область",
    "балаково": "Саратовская область",

    "самара": "Самарская область",
    "тольятти": "Самарская область",
    "сызрань": "Самарская область",
    "новокуйбышевск": "Самарская область",

    "казань": "Республика Татарстан",
    "нижнекамск": "Республика Татарстан",
    "елабуга": "Республика Татарстан",
    "набережные челны": "Республика Татарстан",
    "альметьевск": "Республика Татарстан",

    "липецк": "Липецкая область",
    "елец": "Липецкая область",

    "орёл": "Орловская область",
    "орел": "Орловская область",

    "тула": "Тульская область",
    "новомосковск": "Тульская область",

    "калуга": "Калужская область",
    "обнинск": "Калужская область",

    "рязань": "Рязанская область",
    "тамбов": "Тамбовская область",

    "нижний новгород": "Нижегородская область",
    "дзержинск": "Нижегородская область",
    "кстово": "Нижегородская область",

    "оренбург": "Оренбургская область",
    "орск": "Оренбургская область",

    "пенза": "Пензенская область",
    "ульяновск": "Ульяновская область",

    "смоленск": "Смоленская область",
    "тверь": "Тверская область",
    "ярославль": "Ярославская область",

    "псков": "Псковская область",
    "великий новгород": "Новгородская область",

    "москва": "Москва",
    "санкт-петербург": "Санкт-Петербург",

    "мурманск": "Мурманская область",
    "архангельск": "Архангельская область",

    "пермь": "Пермский край",
    "екатеринбург": "Свердловская область",
    "челябинск": "Челябинская область",
    "уфа": "Республика Башкортостан",

    "омск": "Омская область",
    "новосибирск": "Новосибирская область",
    "красноярск": "Красноярский край",
    "иркутск": "Иркутская область",

    "владивосток": "Приморский край",
    "хабаровск": "Хабаровский край",

    "севастополь": "Севастополь",
    "симферополь": "Республика Крым",
    "керчь": "Республика Крым",
    "джанкой": "Республика Крым",
    "феодосия": "Республика Крым",
    "евпатория": "Республика Крым",
}


# ============================================================
# СЛОВА АТАК
# ============================================================

ATTACK_WORDS = [
    "бпла",
    "беспилотник",
    "беспилотники",
    "дрон",
    "дроны",
    "fpv",
    "fpv-дрон",
    "ракета",
    "ракеты",
    "ракетный удар",
    "ракетная атака",
    "обстрел",
    "обстреляли",
    "обстрелял",
    "артобстрел",
    "артиллерийский обстрел",
    "снаряд",
    "боеприпас",
    "атака всу",
    "атаки всу",
    "атаковали всу",
    "удар всу",
    "удар бпла",
    "удар беспилотника",
    "атака бпла",
    "атака беспилотников",
    "украинский беспилотник",
    "украинские беспилотники",
    "украинский дрон",
    "украинские дроны",
    "украинская ракета",
    "украинская атака",
    "со стороны украины",
    "со стороны всу",
]


DEFENCE_WORDS = [
    "пво",
    "противовоздушная оборона",
    "противовоздушной обороны",
    "про",
    "противоракетная оборона",
    "противоракетной обороны",
    "сбитый беспилотник",
    "сбитого беспилотника",
    "сбитый бпла",
    "обломки бпла",
    "обломки беспилотника",
    "обломки ракеты",
    "падение обломков",
    "работы пво",
    "работа пво",
    "средствами пво",
    "силами пво",
    "рэб",
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
    "ранено",
    "раненых",
    "ранение",
    "ранения",
]


# ============================================================
# ТОЧНО НЕ НУЖНЫЕ СОБЫТИЯ
# ============================================================

EXCLUDE_CONTEXT = [
    "хусит",
    "йемен",
    "баб-эль-мандеб",
    "красное море",
    "сектор газа",
    "хамас",
    "хезболл",
    "израиль",
    "ливан",
    "сирия",
    "иран",
    "ирак",
    "афганистан",
    "пакистан",
]


# ============================================================
# МЕСЯЦЫ
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


# ============================================================
# ЧИСЛА СЛОВАМИ
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
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
    "сто": 100,
}


# ============================================================
# SEEN
# ============================================================

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    try:
        values = list(seen)[-5000:]

        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(values, f, ensure_ascii=False)

    except Exception as e:
        print("save_seen error:", e)


# ============================================================
# НОРМАЛИЗАЦИЯ
# ============================================================

def normalize(text):
    if not text:
        return ""

    text = BeautifulSoup(str(text), "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def split_sentences(text):
    return [
        x.strip()
        for x in re.split(r"(?<=[.!?])\s+", text)
        if len(x.strip()) > 5
    ]


# ============================================================
# ЗАГРУЗКА СТАТЬИ
# ============================================================

def get_article_text(url):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

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
            t = normalize(p.get_text(" ", strip=True))

            if len(t) >= 30:
                paragraphs.append(t)

        return " ".join(paragraphs)[:40000]

    except Exception as e:
        print("ARTICLE ERROR:", url, e)
        return ""


# ============================================================
# РЕГИОН
# ============================================================

def find_region(text):
    low = text.lower()

    # Полные официальные названия
    for region in REGIONS:
        if region.lower() in low:
            return region

    # Разговорные / сокращенные
    for alias, region in REGION_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", low):
            return region

    return None


# ============================================================
# ГОРОД
# ============================================================

def find_city(text):
    low = text.lower()

    # Более длинные названия проверяем первыми
    cities = sorted(
        CITY_REGION.keys(),
        key=len,
        reverse=True
    )

    for city in cities:
        if re.search(r"\b" + re.escape(city) + r"\b", low):

            pretty = city.title()

            special = {
                "орел": "Орёл",
                "орёл": "Орёл",
                "ростов-на-дону": "Ростов-на-Дону",
                "славянск-на-кубани": "Славянск-на-Кубани",
                "нижний новгород": "Нижний Новгород",
                "санкт-петербург": "Санкт-Петербург",
                "старый оскол": "Старый Оскол",
                "набережные челны": "Набережные Челны",
            }

            pretty = special.get(city, pretty)

            return pretty, CITY_REGION[city]

    return None, None


# ============================================================
# МЕСТО ПРОИСШЕСТВИЯ
#
# ВАЖНО:
# сначала анализируем предложения об атаке/потерях,
# чтобы не получить "Москва" только потому, что статья
# начинается словами "МОСКВА, 11 августа. ИНТЕРФАКС".
# ============================================================

def find_location(title, article):

    relevant_sentences = []

    for s in split_sentences(title + ". " + article):
        low = s.lower()

        if (
            any(w in low for w in ATTACK_WORDS)
            or any(w in low for w in DEFENCE_WORDS)
            or any(w in low for w in CASUALTY_WORDS)
        ):
            relevant_sentences.append(s)

    focused = " ".join(relevant_sentences[:15])

    if not focused:
        focused = title

    city, city_region = find_city(focused)
    region = find_region(focused)

    # Если нашли город, его регион надежнее
    if city:
        region = city_region

        if region in [
            "Москва",
            "Санкт-Петербург",
            "Севастополь"
        ]:
            return city, region

        return city, region

    if region:
        return None, region

    # Последняя попытка — заголовок
    city, city_region = find_city(title)

    if city:
        return city, city_region

    region = find_region(title)

    if region:
        return None, region

    return None, None


# ============================================================
# ПРОВЕРКА РЕЛЕВАНТНОСТИ
# ============================================================

def is_relevant(title, article):

    text = (title + " " + article).lower()

    has_attack = any(
        word in text
        for word in ATTACK_WORDS
    )

    has_defence = any(
        word in text
        for word in DEFENCE_WORDS
    )

    if not has_attack and not has_defence:
        return False

    if not any(
        word in text
        for word in CASUALTY_WORDS
    ):
        return False

    city, region = find_location(title, article)

    if not region:
        return False

    # Иностранная тема — отбрасываем,
    # если российское место не установлено уверенно.
    foreign_hits = sum(
        1
        for x in EXCLUDE_CONTEXT
        if x in text
    )

    if foreign_hits >= 2 and not city:
        return False

    return True


# ============================================================
# ДАТА ПРОИСШЕСТВИЯ
# ============================================================

def extract_event_date(title, article, published_struct=None):

    sentences = split_sentences(title + ". " + article)

    candidates = []

    for index, sentence in enumerate(sentences):

        low = sentence.lower()

        if (
            any(w in low for w in ATTACK_WORDS)
            or any(w in low for w in DEFENCE_WORDS)
            or any(w in low for w in CASUALTY_WORDS)
        ):
            # Берем само предложение + соседнее
            start = max(0, index - 1)
            end = min(len(sentences), index + 2)

            candidates.extend(sentences[start:end])

    focused = " ".join(candidates[:20])

    if not focused:
        focused = title

    low = focused.lower()

    # 9 августа 2026
    pattern = (
        r"\b(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|"
        r"июля|августа|сентября|октября|ноября|декабря)"
        r"(?:\s+(\d{4}))?"
    )

    match = re.search(pattern, low)

    if match:

        day = int(match.group(1))
        month = MONTHS[match.group(2)]

        if match.group(3):
            year = int(match.group(3))
        elif published_struct:
            year = published_struct.tm_year
        else:
            year = datetime.now().year

        try:
            d = datetime(year, month, day)
            return d.strftime("%d.%m.%Y")
        except ValueError:
            pass

    # "сегодня / вчера" только в контексте события
    base = datetime.now()

    if published_struct:
        try:
            base = datetime(
                published_struct.tm_year,
                published_struct.tm_mon,
                published_struct.tm_mday
            )
        except Exception:
            pass

    if re.search(r"\bсегодня\b", low):
        return base.strftime("%d.%m.%Y")

    if re.search(r"\bвчера\b", low):
        return (
            base - timedelta(days=1)
        ).strftime("%d.%m.%Y")

    # Если в тексте дата события отсутствует,
    # НЕ выдаём дату публикации за дату атаки.
    return None


# ============================================================
# ВРЕМЯ ПРОИСШЕСТВИЯ
# ============================================================

def extract_event_time(title, article):

    event_sentences = []

    for s in split_sentences(title + ". " + article):

        low = s.lower()

        if (
            any(w in low for w in ATTACK_WORDS)
            or any(w in low for w in DEFENCE_WORDS)
        ):
            event_sentences.append(s)

    focused = " ".join(event_sentences[:10]).lower()

    if not focused:
        return None

    # Точное время
    patterns = [
        r"\bв\s+([01]?\d|2[0-3]):([0-5]\d)\b",
        r"\bоколо\s+([01]?\d|2[0-3]):([0-5]\d)\b",
        r"\bпримерно\s+в\s+([01]?\d|2[0-3]):([0-5]\d)\b",
    ]

    for pattern in patterns:

        m = re.search(pattern, focused)

        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"

    # Части суток
    if re.search(r"\bночью\b|\bночной\b|\bночная\b", focused):
        return "ночью"

    if re.search(r"\bутром\b|\bутренней\b|\bутренний\b", focused):
        return "утром"

    if re.search(r"\bднём\b|\bднем\b|\bдневной\b", focused):
        return "днём"

    if re.search(r"\bвечером\b|\bвечерней\b|\bвечерний\b", focused):
        return "вечером"

    return None


# ============================================================
# ИЗВЛЕЧЕНИЕ ЧИСЕЛ
# ============================================================

def word_number(value):

    value = value.lower().strip()

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


def get_number_candidates(sentence, casualty_type):

    low = sentence.lower()

    if casualty_type == "dead":

        patterns = [
            r"погибли\s+(?:не менее\s+|как минимум\s+|по меньшей мере\s+)?(\d+)",
            r"погибло\s+(?:не менее\s+|как минимум\s+|по меньшей мере\s+)?(\d+)",
            r"погибших\s+(?:стало\s+)?(\d+)",
            r"погибших[^0-9]{0,25}(\d+)",
            r"(\d+)\s+(?:человек|человека|людей)\s+погиб",
            r"число погибших[^0-9]{0,25}(\d+)",
            r"количество погибших[^0-9]{0,25}(\d+)",
            r"жертвами[^0-9]{0,25}стали\s+(\d+)",
        ]

        words = (
            r"(один|одна|два|двое|три|трое|четыре|четверо|"
            r"пять|шесть|семь|восемь|девять|десять|"
            r"одиннадцать|двенадцать|тринадцать|четырнадцать|"
            r"пятнадцать|шестнадцать|семнадцать|восемнадцать|"
            r"девятнадцать|двадцать)"
        )

        word_patterns = [
            r"погиб(?:ли|ло|ла)?[^.!?]{0,25}" + words,
            words + r"\s+(?:человек|человека|людей)[^.!?]{0,15}погиб",
        ]

    else:

        patterns = [
            r"пострадали\s+(?:не менее\s+|как минимум\s+|по меньшей мере\s+)?(\d+)",
            r"пострадало\s+(?:не менее\s+|как минимум\s+|по меньшей мере\s+)?(\d+)",
            r"пострадавших[^0-9]{0,25}(\d+)",
            r"(\d+)\s+(?:человек|человека|людей)\s+пострад",
            r"число пострадавших[^0-9]{0,25}(\d+)",
            r"ранены\s+(\d+)",
            r"ранено\s+(\d+)",
            r"ранеными[^0-9]{0,25}(\d+)",
            r"(\d+)\s+(?:человек|человека|людей)\s+ранен",
        ]

        words = (
            r"(один|одна|два|двое|три|трое|четыре|четверо|"
            r"пять|шесть|семь|восемь|девять|десять|"
            r"одиннадцать|двенадцать|тринадцать|четырнадцать|"
            r"пятнадцать|шестнадцать|семнадцать|восемнадцать|"
            r"девятнадцать|двадцать)"
        )

        word_patterns = [
            r"пострадал(?:и|о|а)?[^.!?]{0,25}" + words,
            words + r"\s+(?:человек|человека|людей)[^.!?]{0,15}пострад",
            r"ранен(?:ы|о|а)?[^.!?]{0,25}" + words,
        ]

    values = []

    for pattern in patterns:

        for m in re.finditer(pattern, low):

            try:
                n = int(m.group(1))

                if 0 < n < 10000:
                    values.append(n)

            except Exception:
                pass

    for pattern in word_patterns:

        for m in re.finditer(pattern, low):

            try:
                value = m.group(1)
                n = word_number(value)

                if n:
                    values.append(n)

            except Exception:
                pass

    return values


# ============================================================
# ПОТЕРИ
#
# Не складываем цифры из разных предложений.
# Берем наиболее позднее/актуальное число.
# ============================================================

def extract_casualties(title, article):

    sentences = split_sentences(title + ". " + article)

    dead_updates = []
    injured_updates = []

    for index, sentence in enumerate(sentences):

        low = sentence.lower()

        # Отбрасываем явно нерелевантные предложения
        if not any(w in low for w in CASUALTY_WORDS):
            continue

        dead = get_number_candidates(sentence, "dead")
        injured = get_number_candidates(sentence, "injured")

        for n in dead:
            dead_updates.append((index, n))

        for n in injured:
            injured_updates.append((index, n))

    dead = None
    injured = None

    # Обычно СМИ сначала пишут старую цифру,
    # затем "число увеличилось до..."
    # Поэтому последнее уверенное значение важнее.
    if dead_updates:
        dead = dead_updates[-1][1]

    if injured_updates:
        injured = injured_updates[-1][1]

    return dead, injured


# ============================================================
# КОРОТКОЕ ОПИСАНИЕ
# ============================================================

def make_description(title, article):

    title = normalize(title)

    # Если заголовок нормальный — используем его.
    if (
        25 <= len(title) <= 220
        and any(
            w in title.lower()
            for w in ATTACK_WORDS + DEFENCE_WORDS
        )
    ):
        return title.rstrip(".") + "."

    candidates = []

    for s in split_sentences(article):

        low = s.lower()

        has_attack = (
            any(w in low for w in ATTACK_WORDS)
            or any(w in low for w in DEFENCE_WORDS)
        )

        if not has_attack:
            continue

        # Не используем технические строки СМИ
        if "интерфакс" in low and len(s) < 40:
            continue

        if len(s) > 300:
            continue

        candidates.append(s)

        if len(candidates) >= 2:
            break

    if candidates:

        description = " ".join(candidates)

        if len(description) > 400:
            description = description[:397].rsplit(" ", 1)[0] + "..."

        return description

    return title[:300]


# ============================================================
# ФОРМАТ МЕСТА
# ============================================================

def format_location(city, region):

    if city and region:

        if city.lower() == region.lower():
            return region

        # Города федерального значения
        if region in [
            "Москва",
            "Санкт-Петербург",
            "Севастополь"
        ]:
            return region

        return f"{city}, {region}"

    if region:
        return region

    return None


# ============================================================
# СОЗДАНИЕ ПОСТА
# ============================================================

def make_message(
    source,
    url,
    title,
    article,
    published_struct=None
):

    city, region = find_location(title, article)

    location = format_location(city, region)

    if not location:
        return None

    dead, injured = extract_casualties(
        title,
        article
    )

    # Нам нужны ТОЛЬКО события с человеческими потерями
    if dead is None and injured is None:
        return None

    date = extract_event_date(
        title,
        article,
        published_struct
    )

    event_time = extract_event_time(
        title,
        article
    )

    description = make_description(
        title,
        article
    )

    location_safe = html.escape(location)
    description_safe = html.escape(description)
    source_safe = html.escape(source)
    url_safe = html.escape(url, quote=True)

    parts = []

    parts.append(
        f"⚡️ <b>{location_safe}</b>"
    )

    # Дата происшествия
    if date:

        if event_time:
            parts.append(
                f"📅 <b>{date}, {html.escape(event_time)}</b>"
            )
        else:
            parts.append(
                f"📅 <b>{date}</b>"
            )

    elif event_time:
        parts.append(
            f"🕒 <b>{html.escape(event_time)}</b>"
        )

    parts.append("")

    parts.append(description_safe)

    parts.append("")

    if dead is not None:
        parts.append(
            f"<b>Погибли: {dead} чел.</b>"
        )

    if injured is not None:
        parts.append(
            f"<b>Пострадали: {injured} чел.</b>"
        )

    parts.append("")

    # Название СМИ кликабельно
    parts.append(
        f'Источник: <a href="{url_safe}">{source_safe}</a>'
    )

    return "\n".join(parts)


# ============================================================
# ID НОВОСТИ
# ============================================================

def make_uid(source, url):

    raw = source + "|" + url

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# ПРОВЕРКА RSS
# ============================================================

def check_news():

    seen = load_seen()

    for source, rss_url in SOURCES:

        try:
            print("Checking:", source)

            feed = feedparser.parse(rss_url)

            entries = feed.entries[:30]

            # Старые сначала, новые потом
            entries = list(reversed(entries))

            for entry in entries:

                url = getattr(
                    entry,
                    "link",
                    ""
                )

                if not url:
                    continue

                uid = make_uid(
                    source,
                    url
                )

                if uid in seen:
                    continue

                title = normalize(
                    getattr(
                        entry,
                        "title",
                        ""
                    )
                )

                summary = normalize(
                    getattr(
                        entry,
                        "summary",
                        ""
                    )
                )

                article = get_article_text(url)

                if not article:
                    article = summary

                published_struct = getattr(
                    entry,
                    "published_parsed",
                    None
                )

                # Сначала проверяем релевантность
                if not is_relevant(
                    title,
                    article
                ):
                    seen.add(uid)
                    continue

                message = make_message(
                    source,
                    url,
                    title,
                    article,
                    published_struct
                )

                if not message:
                    seen.add(uid)
                    continue

                try:

                    bot.send_message(
                        CHANNEL_ID,
                        message,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )

                    print(
                        "POSTED:",
                        source,
                        title
                    )

                    seen.add(uid)

                    # Чтобы Telegram не получил пачку
                    # сообщений одновременно
                    time.sleep(2)

                except Exception as telegram_error:

                    print(
                        "TELEGRAM ERROR:",
                        source,
                        telegram_error
                    )

            save_seen(seen)

        except Exception as e:

            print(
                "SOURCE ERROR:",
                source,
                e
            )


# ============================================================
# ЗАПУСК
# ============================================================

print("Monitoring started")

while True:

    try:
        check_news()

    except Exception as e:
        print("MAIN LOOP ERROR:", e)

    time.sleep(CHECK_INTERVAL)