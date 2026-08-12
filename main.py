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
# ============================================================

SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Интерфакс", "https://www.interfax.ru/rss.asp"),
    ("Российская газета", "https://rg.ru/xml/index.xml"),
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


# ============================================================
# РЕГИОНЫ РФ
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
    # Белгородская
    "Белгород": "Белгородская область",
    "Шебекино": "Белгородская область",
    "Грайворон": "Белгородская область",
    "Валуйки": "Белгородская область",
    "Старый Оскол": "Белгородская область",
    "Губкин": "Белгородская область",

    # Курская
    "Курск": "Курская область",
    "Рыльск": "Курская область",
    "Суджа": "Курская область",
    "Льгов": "Курская область",
    "Курчатов": "Курская область",

    # Брянская
    "Брянск": "Брянская область",
    "Клинцы": "Брянская область",
    "Стародуб": "Брянская область",

    # Воронежская
    "Воронеж": "Воронежская область",

    # Ростовская
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

    # отдельные города
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
    "обломк",
    "детонац",
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


REPORTAGE_WORDS = [
    "корреспондент побывал",
    "корреспондент \"рг\"",
    "корреспондент «рг»",
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


def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


state = load_state()


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
    return any(x in low for x in ATTACK_WORDS)


def has_casualty(text):
    low = text.lower()
    return any(x in low for x in CASUALTY_WORDS)


# ============================================================
# СКАЧИВАЕМ СТАТЬЮ
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

        # Очень важно:
        # убираем элементы, где часто находятся
        # меню, рекомендации и другие новости.
        for tag in soup.find_all([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "button"
        ]):
            tag.decompose()

        paragraphs = []

        for p in soup.find_all("p"):
            txt = clean(p.get_text(" "))

            if 25 <= len(txt) <= 2500:
                paragraphs.append(txt)

        return " ".join(paragraphs)[:25000]

    except Exception as e:
        print("ARTICLE ERROR:", url, e)
        return ""


# ============================================================
# RSS ДАТА
# ============================================================

def published_datetime(entry):
    try:
        t = entry.published_parsed

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
# ТОЛЬКО НОВЫЕ ПУБЛИКАЦИИ
# ============================================================

def publication_is_current(entry):
    dt = published_datetime(entry)

    if not dt:
        return False

    age = now() - dt

    # Только сегодняшний день
    if dt.date() != today():
        return False

    # Защита от странной будущей даты
    if age < timedelta(minutes=-10):
        return False

    return True


# ============================================================
# ДАТА СОБЫТИЯ
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


def is_current_event(title, article, pub_dt):
    """
    Нельзя считать дату публикации датой события.

    Проверяем именно текст события.
    """

    intro = clean(
        title + ". " + article[:5000]
    )

    low = intro.lower()

    # Репортаж / старый материал
    if any(x in low for x in REPORTAGE_WORDS):
        return False

    dates = find_dates(intro)

    # Если сегодняшняя дата прямо указана
    if today() in dates:
        return True

    # Важный случай:
    # в начале текста прямо указана старая дата.
    beginning = intro[:1800]

    old_dates = [
        d for d in find_dates(beginning)
        if d < today()
    ]

    if old_dates:
        return False

    CURRENT_MARKERS = [
        "сегодня",
        "сегодня утром",
        "сегодня днем",
        "сегодня днём",
        "сегодня ночью",
        "этой ночью",
        "минувшей ночью",
        "в ночь на",
        "утром",
    ]

    if any(
        x in low[:2500]
        for x in CURRENT_MARKERS
    ):
        return True

    # Если конкретной даты нет:
    # разрешаем только действительно свежую
    # публикацию о непосредственном событии.
    if pub_dt:
        age = now() - pub_dt

        if timedelta(0) <= age <= timedelta(hours=4):
            first = low[:1800]

            DIRECT = [
                "атаковал",
                "атаковала",
                "атаковали",
                "подвергся атаке",
                "подверглась атаке",
                "в результате атаки",
                "в результате обстрела",
                "при атаке",
                "при обстреле",
                "обломки бпла",
                "обломки беспилотника",
            ]

            if any(x in first for x in DIRECT):
                return True

    return False


# ============================================================
# ВЫДЕЛЯЕМ ТОЛЬКО КОНТЕКСТ ПРОИСШЕСТВИЯ
# ============================================================

def get_incident_context(title, article):
    """
    Это ключевое изменение.

    Мы больше НЕ определяем место и цифры
    по всей странице.

    Сначала находим предложения непосредственно
    об атаке и пострадавших.
    """

    sents = split_sentences(
        title + ". " + article
    )

    relevant_indexes = set()

    for i, sent in enumerate(sents):

        # Само предложение об атаке
        if has_attack(sent):
            relevant_indexes.add(i)

            if i > 0:
                relevant_indexes.add(i - 1)

            if i + 1 < len(sents):
                relevant_indexes.add(i + 1)

            if i + 2 < len(sents):
                relevant_indexes.add(i + 2)

        # Предложение с потерями
        if has_casualty(sent):
            # Но рядом обязательно должна быть атака
            neighborhood = " ".join(
                sents[max(0, i - 2):min(
                    len(sents),
                    i + 3
                )]
            )

            if has_attack(neighborhood):
                relevant_indexes.add(i)

                if i > 0:
                    relevant_indexes.add(i - 1)

                if i + 1 < len(sents):
                    relevant_indexes.add(i + 1)

    if not relevant_indexes:
        return ""

    selected = [
        sents[i]
        for i in sorted(relevant_indexes)
    ]

    return " ".join(selected)[:5000]


# ============================================================
# ГЕОГРАФИЯ
# ============================================================

def city_in_text(text):
    """
    Город ищется ТОЛЬКО в контексте происшествия.

    Москва больше не может появиться из футера,
    связанной новости или служебного текста.
    """

    matches = []

    low = text.lower()

    for city in CITY_REGION:
        pos = low.find(city.lower())

        if pos >= 0:
            matches.append(
                (pos, city)
            )

    if not matches:
        return None

    matches.sort()

    return matches[0][1]


def region_in_text(text):
    matches = []

    low = text.lower()

    for region in REGIONS:
        pos = low.find(
            region.lower()
        )

        if pos >= 0:
            matches.append(
                (pos, region)
            )

    if not matches:
        return None

    matches.sort()

    return matches[0][1]


def determine_location(title, incident):
    """
    Приоритет:
    1. город в заголовке;
    2. город в предложении об атаке;
    3. регион в заголовке;
    4. регион в предложении об атаке.

    НИКОГДА не смотрим всю страницу.
    """

    title_city = city_in_text(title)

    if title_city:
        return (
            title_city,
            CITY_REGION.get(title_city)
        )

    incident_city = city_in_text(
        incident
    )

    if incident_city:
        return (
            incident_city,
            CITY_REGION.get(incident_city)
        )

    title_region = region_in_text(
        title
    )

    if title_region:
        return None, title_region

    incident_region = region_in_text(
        incident
    )

    if incident_region:
        return None, incident_region

    return None, None


# ============================================================
# ОСОБАЯ ЗАЩИТА ОТ "МОСКВЫ"
# ============================================================

def validate_location(city, region, incident):
    """
    Москва допускается ТОЛЬКО если само предложение
    о происшествии явно говорит об атаке в Москве.
    """

    if city == "Москва" or region == "Москва":

        low = incident.lower()

        strong_moscow = [
            "в москве",
            "на москву",
            "над москвой",
            "москву атак",
            "атаке на москву",
            "атаки на москву",
        ]

        if not any(x in low for x in strong_moscow):
            return False

    return True


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


# ============================================================
# ПОГИБШИЕ
# ============================================================

DEAD_PATTERNS = [
    rf"(?:погибли|погибло)\s+(?:не менее\s+|как минимум\s+)?({NUM})\s+(?:человек|человека|людей)",
    rf"({NUM})\s+(?:человек|человека|людей)\s+(?:погибли|погибло)",

    rf"(?:число|количество)\s+погибших.*?(?:до|составило|достигло)\s+({NUM})",
    rf"погибших.*?(?:до|составило|достигло)\s+({NUM})",
]


# ============================================================
# ПОСТРАДАВШИЕ
# ============================================================

INJURED_PATTERNS = [
    rf"(?:пострадали|пострадало)\s+(?:не менее\s+|как минимум\s+)?({NUM})\s+(?:человек|человека|людей)",
    rf"({NUM})\s+(?:человек|человека|людей)\s+(?:пострадали|пострадало)",

    rf"(?:число|количество)\s+пострадавших.*?(?:до|составило|достигло)\s+({NUM})",
    rf"пострадавших.*?(?:до|составило|достигло)\s+({NUM})",

    rf"(?:ранены|ранено)\s+({NUM})\s+(?:человек|человека|людей)",
    rf"({NUM})\s+(?:человек|человека|людей)\s+(?:ранены|ранено)",
]


# ============================================================
# "ПОГИБ РЕБЁНОК" = 1
# ============================================================

SINGLE_DEAD = [
    r"\bпогиб\s+реб[её]нок\b",
    r"\bпогибла\s+девочк",
    r"\bпогиб\s+мальчик\b",
    r"\bпогиб\s+мужчина\b",
    r"\bпогибла\s+женщина\b",
    r"\bпогиб\s+водитель\b",
    r"\bпогибла\s+местная жительница\b",
    r"\bпогиб\s+местный житель\b",
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
]


def extract_numbers(incident):
    sents = split_sentences(incident)

    dead_candidates = []
    injured_candidates = []

    for index, sent in enumerate(sents):
        low = sent.lower()

        # ----------------------------
        # погибшие
        # ----------------------------

        for pattern in DEAD_PATTERNS:
            for m in re.finditer(
                pattern,
                low,
                flags=re.I
            ):
                n = number(m.group(1))

                if n is not None:
                    dead_candidates.append(
                        (index, n, sent)
                    )

        if any(
            re.search(p, low)
            for p in SINGLE_DEAD
        ):
            dead_candidates.append(
                (index, 1, sent)
            )

        # ----------------------------
        # пострадавшие
        # ----------------------------

        for pattern in INJURED_PATTERNS:
            for m in re.finditer(
                pattern,
                low,
                flags=re.I
            ):
                n = number(m.group(1))

                if n is not None:
                    injured_candidates.append(
                        (index, n, sent)
                    )

        if any(
            re.search(p, low)
            for p in SINGLE_INJURED
        ):
            injured_candidates.append(
                (index, 1, sent)
            )

    def choose(candidates):
        if not candidates:
            return None

        # Максимальная цифра в текущем
        # контексте происшествия.
        return max(
            x[1]
            for x in candidates
        )

    return (
        choose(dead_candidates),
        choose(injured_candidates)
    )


# ============================================================
# ВРЕМЯ ПРОИСШЕСТВИЯ
# ============================================================

def incident_time(incident):
    patterns = [
        r"\bв\s+([01]?\d|2[0-3]):([0-5]\d)\b",
        r"\bоколо\s+([01]?\d|2[0-3]):([0-5]\d)\b",
    ]

    for p in patterns:
        m = re.search(p, incident)

        if m:
            return (
                f"{int(m.group(1)):02d}:"
                f"{m.group(2)}"
            )

    return None


# ============================================================
# ОПИСАНИЕ
# ============================================================

def make_description(incident):
    sents = split_sentences(incident)

    chosen = []

    for sent in sents:
        if has_attack(sent):
            chosen.append(sent)

        elif chosen and has_casualty(sent):
            chosen.append(sent)

        if len(chosen) >= 2:
            break

    if not chosen:
        return None

    result = " ".join(chosen)

    if len(result) > 450:
        result = (
            result[:447]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return result


# ============================================================
# ДАТА ДЛЯ TELEGRAM
# ============================================================

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


def date_text():
    d = today()

    return (
        f"{d.day} "
        f"{MONTH_NAMES[d.month]} "
        f"{d.year} года"
    )


# ============================================================
# КЛЮЧ СОБЫТИЯ
# ============================================================

def attack_type(text):
    low = text.lower()

    if (
        "бпла" in low
        or "беспилот" in low
        or "дрон" in low
    ):
        return "uav"

    if "обстрел" in low:
        return "shelling"

    if "ракет" in low:
        return "missile"

    if "пво" in low or "обломк" in low:
        return "airdefense"

    return "attack"


def event_key(city, region, incident):
    """
    Одно место + один день + тип атаки.

    Поэтому статья другого СМИ с теми же
    цифрами не создаст новый пост.
    """

    place = (
        city
        or region
        or "unknown"
    )

    raw = (
        f"{today().isoformat()}|"
        f"{place.lower()}|"
        f"{attack_type(incident)}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# НОВОСТЬ ИЛИ ОБНОВЛЕНИЕ
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

    increased = False

    if dead is not None:
        if (
            old_dead is None
            or dead > old_dead
        ):
            increased = True

    if injured is not None:
        if (
            old_injured is None
            or injured > old_injured
        ):
            increased = True

    if increased:
        return "update"

    return "skip"


def remember(
    key,
    dead,
    injured,
    url
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
        "date": today().isoformat(),
        "updated": now().isoformat()
    }

    save_state()


# ============================================================
# ФОРМАТ МЕСТА
# ============================================================

def location_text(city, region):
    if city and region:
        if city == region:
            return city

        return f"{city}, {region}"

    return region or city


# ============================================================
# СООБЩЕНИЕ
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

    parts.append(
        'Источник: '
        f'<a href="{html.escape(url, quote=True)}">'
        f'{html.escape(source)}</a>'
    )

    return "\n\n".join(parts)


# ============================================================
# ОБРАБОТКА НОВОСТИ
# ============================================================

def process(entry, source):
    title = clean(
        getattr(entry, "title", "")
    )

    url = getattr(
        entry,
        "link",
        ""
    )

    if not title or not url:
        return

    # Только свежая публикация
    if not publication_is_current(entry):
        return

    pub_dt = published_datetime(entry)

    summary = clean(
        getattr(entry, "summary", "")
    )

    preview = (
        title + ". " + summary
    )

    # Уже RSS должен быть потенциально релевантным
    if (
        not has_attack(preview)
        and not has_casualty(preview)
    ):
        return

    article = get_article(url)

    if not article:
        return

    # Старые репортажи
    test_text = (
        title + " " + article[:4000]
    ).lower()

    if any(
        marker in test_text
        for marker in REPORTAGE_WORDS
    ):
        print(
            "SKIP REPORTAGE:",
            title
        )
        return

    # Именно сегодняшнее событие
    if not is_current_event(
        title,
        article,
        pub_dt
    ):
        print(
            "SKIP OLD EVENT:",
            title
        )
        return

    # Выделяем только конкретное происшествие
    incident = get_incident_context(
        title,
        article
    )

    if not incident:
        print(
            "SKIP NO INCIDENT:",
            title
        )
        return

    if not has_attack(incident):
        return

    if not has_casualty(incident):
        return

    # ------------------------------------------
    # МЕСТО
    # ------------------------------------------

    city, region = determine_location(
        title,
        incident
    )

    if not city and not region:
        print(
            "SKIP UNKNOWN LOCATION:",
            title
        )
        return

    # Дополнительная защита от ложной Москвы
    if not validate_location(
        city,
        region,
        incident
    ):
        print(
            "SKIP FALSE MOSCOW:",
            title
        )
        return

    # ------------------------------------------
    # ПОТЕРИ
    # ------------------------------------------

    dead, injured = extract_numbers(
        incident
    )

    if dead is None and injured is None:
        print(
            "SKIP NO NUMBERS:",
            title
        )
        return

    # ------------------------------------------
    # ОПИСАНИЕ
    # ------------------------------------------

    description = make_description(
        incident
    )

    if not description:
        return

    # ------------------------------------------
    # АНТИДУБЛЬ
    # ------------------------------------------

    key = event_key(
        city,
        region,
        incident
    )

    status = publication_status(
        key,
        dead,
        injured
    )

    if status == "skip":
        print(
            "SKIP DUPLICATE:",
            title
        )
        return

    # ------------------------------------------
    # ВРЕМЯ
    # ------------------------------------------

    ev_time = incident_time(
        incident
    )

    # ------------------------------------------
    # TELEGRAM
    # ------------------------------------------

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
        url
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
# ОЧИСТКА СТАРЫХ СОБЫТИЙ
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
                feed.entries[:40]
            )

            # От старых к новым
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