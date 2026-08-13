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
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    )
}


# ============================================================
# ГЕОГРАФИЯ
#
# Ключ — каноническое название для Telegram.
# Значения — формы, которые могут встретиться в тексте.
# ============================================================

REGION_FORMS = {
    "Республика Адыгея": [
        "республика адыгея", "адыгея", "адыгее", "адыгеи"
    ],
    "Республика Алтай": [
        "республика алтай", "республике алтай"
    ],
    "Республика Башкортостан": [
        "республика башкортостан", "республике башкортостан",
        "башкортостан", "башкортостане",
        "башкирия", "башкирии", "башкирию"
    ],
    "Республика Бурятия": [
        "республика бурятия", "бурятия", "бурятии", "бурятию"
    ],
    "Республика Дагестан": [
        "республика дагестан", "дагестан", "дагестане"
    ],
    "Республика Ингушетия": [
        "республика ингушетия", "ингушетия", "ингушетии"
    ],
    "Кабардино-Балкарская Республика": [
        "кабардино-балкарская республика",
        "кабардино-балкарии",
        "кабардино-балкария"
    ],
    "Республика Калмыкия": [
        "республика калмыкия", "калмыкия", "калмыкии"
    ],
    "Карачаево-Черкесская Республика": [
        "карачаево-черкесская республика",
        "карачаево-черкесии"
    ],
    "Республика Карелия": [
        "республика карелия", "карелия", "карелии"
    ],
    "Республика Коми": [
        "республика коми", "республике коми"
    ],
    "Республика Крым": [
        "республика крым", "республике крым",
        "крым", "крыму", "крыме", "крыма"
    ],
    "Республика Марий Эл": [
        "республика марий эл", "марий эл"
    ],
    "Республика Мордовия": [
        "республика мордовия", "мордовия", "мордовии"
    ],
    "Республика Саха (Якутия)": [
        "республика саха", "якутия", "якутии"
    ],
    "Республика Северная Осетия — Алания": [
        "северная осетия", "северной осетии",
        "северная осетия — алания"
    ],
    "Республика Татарстан": [
        "республика татарстан", "республике татарстан",
        "татарстан", "татарстане", "татарстана"
    ],
    "Республика Тыва": [
        "республика тыва", "тыва", "тыве"
    ],
    "Удмуртская Республика": [
        "удмуртская республика", "удмуртия", "удмуртии"
    ],
    "Республика Хакасия": [
        "республика хакасия", "хакасия", "хакасии"
    ],
    "Чеченская Республика": [
        "чеченская республика", "чечня", "чечне"
    ],
    "Чувашская Республика": [
        "чувашская республика", "чувашия", "чувашии"
    ],

    "Алтайский край": [
        "алтайский край", "алтайском крае"
    ],
    "Забайкальский край": [
        "забайкальский край", "забайкальском крае"
    ],
    "Камчатский край": [
        "камчатский край", "камчатском крае", "камчатке"
    ],
    "Краснодарский край": [
        "краснодарский край", "краснодарском крае",
        "кубань", "кубани"
    ],
    "Красноярский край": [
        "красноярский край", "красноярском крае"
    ],
    "Пермский край": [
        "пермский край", "пермском крае"
    ],
    "Приморский край": [
        "приморский край", "приморском крае", "приморье"
    ],
    "Ставропольский край": [
        "ставропольский край", "ставропольском крае",
        "ставрополье"
    ],
    "Хабаровский край": [
        "хабаровский край", "хабаровском крае"
    ],

    "Белгородская область": [
        "белгородская область", "белгородской области"
    ],
    "Брянская область": [
        "брянская область", "брянской области"
    ],
    "Воронежская область": [
        "воронежская область", "воронежской области"
    ],
    "Курская область": [
        "курская область", "курской области"
    ],
    "Липецкая область": [
        "липецкая область", "липецкой области"
    ],
    "Ростовская область": [
        "ростовская область", "ростовской области"
    ],
    "Московская область": [
        "московская область", "московской области",
        "подмосковье", "подмосковье"
    ],
    "Калужская область": [
        "калужская область", "калужской области"
    ],
    "Орловская область": [
        "орловская область", "орловской области"
    ],
    "Тульская область": [
        "тульская область", "тульской области"
    ],
    "Рязанская область": [
        "рязанская область", "рязанской области"
    ],
    "Тверская область": [
        "тверская область", "тверской области"
    ],
    "Смоленская область": [
        "смоленская область", "смоленской области"
    ],
    "Волгоградская область": [
        "волгоградская область", "волгоградской области"
    ],
    "Саратовская область": [
        "саратовская область", "саратовской области"
    ],
    "Самарская область": [
        "самарская область", "самарской области"
    ],
    "Нижегородская область": [
        "нижегородская область", "нижегородской области"
    ],
    "Ленинградская область": [
        "ленинградская область", "ленинградской области"
    ],
    "Псковская область": [
        "псковская область", "псковской области"
    ],
    "Новгородская область": [
        "новгородская область", "новгородской области"
    ],
    "Мурманская область": [
        "мурманская область", "мурманской области"
    ],
    "Архангельская область": [
        "архангельская область", "архангельской области"
    ],
    "Астраханская область": [
        "астраханская область", "астраханской области"
    ],
    "Оренбургская область": [
        "оренбургская область", "оренбургской области"
    ],
    "Пензенская область": [
        "пензенская область", "пензенской области"
    ],
    "Ульяновская область": [
        "ульяновская область", "ульяновской области"
    ],
    "Челябинская область": [
        "челябинская область", "челябинской области"
    ],
    "Свердловская область": [
        "свердловская область", "свердловской области"
    ],
    "Тюменская область": [
        "тюменская область", "тюменской области"
    ],
    "Новосибирская область": [
        "новосибирская область", "новосибирской области"
    ],
    "Омская область": [
        "омская область", "омской области"
    ],
    "Иркутская область": [
        "иркутская область", "иркутской области"
    ],
    "Амурская область": [
        "амурская область", "амурской области"
    ],
    "Сахалинская область": [
        "сахалинская область", "сахалинской области"
    ],
    "Калининградская область": [
        "калининградская область", "калининградской области"
    ],
    "Ярославская область": [
        "ярославская область", "ярославской области"
    ],

    "Москва": [
        "москва", "москве", "москву", "москвой"
    ],
    "Санкт-Петербург": [
        "санкт-петербург", "санкт-петербурге",
        "петербург", "петербурге"
    ],
    "Севастополь": [
        "севастополь", "севастополе", "севастополя"
    ],
}


# ============================================================
# ГОРОДА
# ============================================================

CITY_FORMS = {
    "Белгород": [
        "белгород", "белгороде", "белгорода", "белгороду"
    ],
    "Шебекино": [
        "шебекино"
    ],
    "Грайворон": [
        "грайворон", "грайвороне"
    ],
    "Валуйки": [
        "валуйки", "валуйках"
    ],
    "Старый Оскол": [
        "старый оскол", "старом осколе"
    ],
    "Губкин": [
        "губкин", "губкине"
    ],

    "Курск": [
        "курск", "курске", "курска"
    ],
    "Рыльск": [
        "рыльск", "рыльске"
    ],
    "Суджа": [
        "суджа", "судже", "суджи"
    ],
    "Льгов": [
        "льгов", "льгове"
    ],
    "Курчатов": [
        "курчатов", "курчатове"
    ],

    "Брянск": [
        "брянск", "брянске", "брянска"
    ],
    "Клинцы": [
        "клинцы", "клинцах"
    ],
    "Стародуб": [
        "стародуб", "стародубе"
    ],

    "Воронеж": [
        "воронеж", "воронеже", "воронежа"
    ],

    "Ростов-на-Дону": [
        "ростов-на-дону", "ростове-на-дону"
    ],
    "Таганрог": [
        "таганрог", "таганроге"
    ],
    "Новошахтинск": [
        "новошахтинск", "новошахтинске"
    ],
    "Шахты": [
        "шахты", "шахтах"
    ],
    "Батайск": [
        "батайск", "батайске"
    ],
    "Каменск-Шахтинский": [
        "каменск-шахтинский", "каменске-шахтинском"
    ],

    "Краснодар": [
        "краснодар", "краснодаре", "краснодара"
    ],
    "Новороссийск": [
        "новороссийск", "новороссийске", "новороссийска"
    ],
    "Анапа": [
        "анапа", "анапе", "анапы"
    ],
    "Геленджик": [
        "геленджик", "геленджике"
    ],
    "Сочи": [
        "сочи"
    ],
    "Туапсе": [
        "туапсе"
    ],
    "Темрюк": [
        "темрюк", "темрюке"
    ],
    "Армавир": [
        "армавир", "армавире"
    ],
    "Славянск-на-Кубани": [
        "славянск-на-кубани", "славянске-на-кубани"
    ],

    "Казань": [
        "казань", "казани"
    ],
    "Нижнекамск": [
        "нижнекамск", "нижнекамске", "нижнекамска"
    ],
    "Елабуга": [
        "елабуга", "елабуге", "елабуги"
    ],
    "Альметьевск": [
        "альметьевск", "альметьевске"
    ],

    "Уфа": [
        "уфа", "уфе", "уфы"
    ],
    "Стерлитамак": [
        "стерлитамак", "стерлитамаке"
    ],
    "Салават": [
        "салават", "салавате"
    ],

    "Керчь": [
        "керчь", "керчи"
    ],
    "Симферополь": [
        "симферополь", "симферополе"
    ],
    "Ялта": [
        "ялта", "ялте"
    ],
    "Феодосия": [
        "феодосия", "феодосии"
    ],
    "Джанкой": [
        "джанкой", "джанкое"
    ],
    "Евпатория": [
        "евпатория", "евпатории"
    ],

    "Москва": [
        "москва", "москве", "москву", "москвой"
    ],
    "Санкт-Петербург": [
        "санкт-петербург", "санкт-петербурге",
        "петербург", "петербурге"
    ],
    "Севастополь": [
        "севастополь", "севастополе", "севастополя"
    ],
}


CITY_REGION = {
    "Белгород": "Белгородская область",
    "Шебекино": "Белгородская область",
    "Грайворон": "Белгородская область",
    "Валуйки": "Белгородская область",
    "Старый Оскол": "Белгородская область",
    "Губкин": "Белгородская область",

    "Курск": "Курская область",
    "Рыльск": "Курская область",
    "Суджа": "Курская область",
    "Льгов": "Курская область",
    "Курчатов": "Курская область",

    "Брянск": "Брянская область",
    "Клинцы": "Брянская область",
    "Стародуб": "Брянская область",

    "Воронеж": "Воронежская область",

    "Ростов-на-Дону": "Ростовская область",
    "Таганрог": "Ростовская область",
    "Новошахтинск": "Ростовская область",
    "Шахты": "Ростовская область",
    "Батайск": "Ростовская область",
    "Каменск-Шахтинский": "Ростовская область",

    "Краснодар": "Краснодарский край",
    "Новороссийск": "Краснодарский край",
    "Анапа": "Краснодарский край",
    "Геленджик": "Краснодарский край",
    "Сочи": "Краснодарский край",
    "Туапсе": "Краснодарский край",
    "Темрюк": "Краснодарский край",
    "Армавир": "Краснодарский край",
    "Славянск-на-Кубани": "Краснодарский край",

    "Казань": "Республика Татарстан",
    "Нижнекамск": "Республика Татарстан",
    "Елабуга": "Республика Татарстан",
    "Альметьевск": "Республика Татарстан",

    "Уфа": "Республика Башкортостан",
    "Стерлитамак": "Республика Башкортостан",
    "Салават": "Республика Башкортостан",

    "Керчь": "Республика Крым",
    "Симферополь": "Республика Крым",
    "Ялта": "Республика Крым",
    "Феодосия": "Республика Крым",
    "Джанкой": "Республика Крым",
    "Евпатория": "Республика Крым",

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
    "артиллер",
    "миномет",
    "миномёт",
    "обломк",
    "детонац",
    "взрыв",
    "пво",
    "противовоздуш",
    "противоракет",
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
# СТАРЫЕ БОЕПРИПАСЫ / НЕ ТЕКУЩАЯ АТАКА
# ============================================================

OLD_AMMO_MARKERS = [
    "боеприпас времен",
    "боеприпас времён",
    "снаряд времен",
    "снаряд времён",
    "великой отечественной",
    "боеприпас был обнаружен",
    "снаряд был обнаружен",
    "при обезвреживании снаряда",
    "при обезвреживании боеприпаса",
    "при разминировании",
]


def is_old_ammo_incident(text):
    low = text.lower()

    if any(x in low for x in OLD_AMMO_MARKERS):
        # Пропускаем только если нет явного указания,
        # что это последствие текущей атаки.
        current_attack = [
            "после атаки",
            "после обстрела",
            "после удара",
            "в результате атаки",
            "в результате обстрела",
            "в результате удара",
            "неразорвавшийся боеприпас после",
        ]

        if not any(x in low for x in current_attack):
            return True

    return False


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
# СКАЧИВАНИЕ СТАТЬИ
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


def publication_is_current(entry):
    dt = published_datetime(entry)

    if not dt:
        return False

    if dt.date() != today():
        return False

    age = now() - dt

    if age < timedelta(minutes=-10):
        return False

    # Только действительно свежие публикации.
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

    for m in re.finditer(pattern, text.lower()):
        day = int(m.group(1))
        month = MONTHS[m.group(2)]

        year = (
            int(m.group(3))
            if m.group(3)
            else today().year
        )

        try:
            result.append(
                datetime(year, month, day).date()
            )
        except ValueError:
            pass

    return result


def current_event(title, summary, article, pub_dt):
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

    if today() in dates:
        return True

    beginning_dates = find_dates(
        text[:1800]
    )

    # Явная старая дата в начале — отказ.
    if any(d < today() for d in beginning_dates):
        return False

    current_markers = [
        "сегодня",
        "сегодня утром",
        "сегодня днем",
        "сегодня днём",
        "сегодня ночью",
        "этой ночью",
        "минувшей ночью",
        "прошедшей ночью",
        "в ночь на",
    ]

    first = low[:2500]

    if any(
        marker in first
        for marker in current_markers
    ):
        return True

    if pub_dt:
        age = now() - pub_dt

        direct_markers = [
            "атаковал",
            "атаковала",
            "атаковали",
            "атакован",
            "атакована",
            "подвергся атаке",
            "подверглась атаке",
            "в результате атаки",
            "в результате обстрела",
            "в результате удара",
            "при атаке",
            "при обстреле",
            "после атаки",
            "обломки бпла",
            "обломки беспилотника",
            "при падении обломков",
        ]

        if (
            timedelta(0) <= age <= timedelta(hours=3)
            and any(x in first for x in direct_markers)
        ):
            return True

    return False


# ============================================================
# ЛОКАЛЬНЫЕ БЛОКИ ПРОИСШЕСТВИЙ
# ============================================================

def incident_blocks(title, article):
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

        if is_old_ammo_incident(block):
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

def contains_form(text, form):
    return re.search(
        r"(?<![а-яёa-z0-9])" +
        re.escape(form.lower()) +
        r"(?![а-яёa-z0-9])",
        text.lower(),
        re.I
    ) is not None


def find_city_candidates(text):
    result = []

    low = text.lower()

    for city, forms in CITY_FORMS.items():
        for form in forms:
            m = re.search(
                r"(?<![а-яёa-z0-9])" +
                re.escape(form) +
                r"(?![а-яёa-z0-9])",
                low,
                re.I
            )

            if m:
                result.append(
                    (m.start(), city, form)
                )

    return sorted(result)


def find_region_candidates(text):
    result = []

    low = text.lower()

    for region, forms in REGION_FORMS.items():
        for form in forms:
            m = re.search(
                r"(?<![а-яёa-z0-9])" +
                re.escape(form) +
                r"(?![а-яёa-z0-9])",
                low,
                re.I
            )

            if m:
                result.append(
                    (m.start(), region, form)
                )

    return sorted(result)


def moscow_is_real_location(sentence):
    """
    Москва у информагентств часто означает
    место выпуска сообщения.

    Поэтому одного слова Москва недостаточно.
    """

    low = sentence.lower()

    patterns = [
        r"\bв москве\b",
        r"\bпо москве\b",
        r"\bна москву\b",
        r"\bнад москвой\b",
        r"\bмоскву атак",
        r"\bатак[аиуые]* на москву\b",
        r"\bобстрел москвы\b",
        r"\bудар по москве\b",
        r"\bбпла.*москв",
        r"\bдрон.*москв",
    ]

    return any(
        re.search(p, low)
        for p in patterns
    )


def location_from_sentence(sentence):
    cities = find_city_candidates(sentence)

    for _, city, _ in cities:

        if (
            city == "Москва"
            and not moscow_is_real_location(sentence)
        ):
            continue

        return city, CITY_REGION.get(city)

    regions = find_region_candidates(sentence)

    for _, region, _ in regions:

        if (
            region == "Москва"
            and not moscow_is_real_location(sentence)
        ):
            continue

        return None, region

    return None, None


def determine_block_location(block):
    sentences = block["sentences"]
    ci = block["casualty_index"]

    # 1. Предложение непосредственно с жертвами.
    city, region = location_from_sentence(
        sentences[ci]
    )

    if city or region:
        return city, region

    # 2. Сначала предыдущее — там чаще описана атака.
    if ci - 1 >= 0:
        city, region = location_from_sentence(
            sentences[ci - 1]
        )

        if city or region:
            return city, region

    # 3. Следующее.
    if ci + 1 < len(sentences):
        city, region = location_from_sentence(
            sentences[ci + 1]
        )

        if city or region:
            return city, region

    # 4. Весь маленький блок.
    cities = []

    for _, city, _ in find_city_candidates(
        block["text"]
    ):
        if (
            city == "Москва"
            and not moscow_is_real_location(
                block["text"]
            )
        ):
            continue

        if city not in cities:
            cities.append(city)

    if len(cities) == 1:
        city = cities[0]
        return city, CITY_REGION.get(city)

    regions = []

    for _, region, _ in find_region_candidates(
        block["text"]
    ):
        if (
            region == "Москва"
            and not moscow_is_real_location(
                block["text"]
            )
        ):
            continue

        if region not in regions:
            regions.append(region)

    if len(regions) == 1:
        return None, regions[0]

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
    rf"(?:число|количество)\s+погибших.*?(?:до|составило|достигло)\s+({NUM})",
    rf"(?:число|количество)\s+погибших.*?увеличилось\s+до\s+({NUM})",
    rf"погибших.*?увеличилось\s+до\s+({NUM})",
]


INJURED_PATTERNS = [
    rf"(?:пострадали|пострадало)\s+(?:не менее\s+|как минимум\s+)?({NUM})\s+(?:человек|человека|людей)",
    rf"({NUM})\s+(?:человек|человека|людей)\s+(?:пострадали|пострадало)",
    rf"(?:число|количество)\s+пострадавших.*?(?:до|составило|достигло)\s+({NUM})",
    rf"(?:число|количество)\s+пострадавших.*?увеличилось\s+до\s+({NUM})",
    rf"пострадавших.*?увеличилось\s+до\s+({NUM})",
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
        for m in re.finditer(pattern, low, flags=re.I):
            n = number(m.group(1))

            if n is not None:
                dead.append(n)

    if any(
        re.search(pattern, low)
        for pattern in SINGLE_DEAD
    ):
        dead.append(1)

    for pattern in INJURED_PATTERNS:
        for m in re.finditer(pattern, low, flags=re.I):
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
    sentences = block["sentences"]
    ci = block["casualty_index"]

    # Сначала предложение непосредственно о потерях.
    dead, injured = extract_from_sentence(
        sentences[ci]
    )

    candidates = [(dead, injured)]

    # Берём соседние предложения только если
    # они сами содержат информацию о потерях.
    for idx in [ci - 1, ci + 1]:
        if 0 <= idx < len(sentences):
            sent = sentences[idx]

            if has_casualty(sent):
                candidates.append(
                    extract_from_sentence(sent)
                )

    dead_values = [
        d
        for d, _ in candidates
        if d is not None
    ]

    injured_values = [
        i
        for _, i in candidates
        if i is not None
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

    # Предложение о происшествии рядом с потерями.
    for distance in [0, 1, 2]:

        indexes = (
            [ci]
            if distance == 0
            else [ci - distance, ci + distance]
        )

        for idx in indexes:
            if 0 <= idx < len(sentences):
                sent = sentences[idx]

                if has_attack(sent):
                    chosen.append(sent)

        if chosen:
            break

    casualty_sentence = sentences[ci]

    if casualty_sentence not in chosen:
        chosen.append(casualty_sentence)

    unique = []

    for sent in chosen:
        if sent not in unique:
            unique.append(sent)

    result = " ".join(unique)

    # Удаляем агентское "Москва." в конце текста.
    result = re.sub(
        r"\s+Москва\.?$",
        "",
        result,
        flags=re.I
    ).strip()

    if len(result) > 420:
        result = (
            result[:417]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return result or None


# ============================================================
# ДАТА
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

    if any(
        x in low
        for x in [
            "бпла",
            "беспилот",
            "дрон",
            "fpv"
        ]
    ):
        return "uav"

    if any(
        x in low
        for x in [
            "обстрел",
            "артиллер",
            "мином"
        ]
    ):
        return "shelling"

    if "ракет" in low:
        return "missile"

    if any(
        x in low
        for x in [
            "пво",
            "противовоздуш",
            "противоракет",
            "обломк"
        ]
    ):
        return "airdefense"

    return "attack"


# ============================================================
# КЛЮЧ СОБЫТИЯ
# ============================================================

def event_key(city, region, block, event_time=None):
    """
    Не используем только "город + день + тип":
    за день в одном городе может быть несколько атак.

    Добавляем временной слот.
    Если точного времени нет — используем
    нормализованный смысловой отпечаток блока.
    """

    place = city or region
    attack = attack_type(block["text"])

    if event_time:
        hour = event_time.split(":")[0]
        discriminator = f"hour:{hour}"
    else:
        # Берём первые значимые слова.
        normalized = block["text"].lower()

        normalized = re.sub(
            r"\b\d+\b",
            "",
            normalized
        )

        normalized = re.sub(
            r"\W+",
            " ",
            normalized
        )

        words = [
            w for w in normalized.split()
            if len(w) >= 4
        ]

        fingerprint = " ".join(words[:12])

        discriminator = hashlib.sha1(
            fingerprint.encode("utf-8")
        ).hexdigest()[:12]

    raw = (
        f"{today().isoformat()}|"
        f"{place.lower()}|"
        f"{attack}|"
        f"{discriminator}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# ДУБЛИ / ОБНОВЛЕНИЯ
# ============================================================

def publication_status(key, dead, injured):
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


def merged_numbers(key, dead, injured):
    """
    При обновлении никогда не показываем
    меньшие цифры, чем уже были опубликованы.
    """

    old = state["events"].get(key, {})

    old_dead = old.get("dead")
    old_injured = old.get("injured")

    if old_dead is not None:
        dead = (
            old_dead
            if dead is None
            else max(dead, old_dead)
        )

    if old_injured is not None:
        injured = (
            old_injured
            if injured is None
            else max(injured, old_injured)
        )

    return dead, injured


def remember(
    key,
    dead,
    injured,
    url,
    city,
    region
):
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

    # Без 📅 — iPhone показывает JUL 17.
    date_line = (
        f"<b>{html.escape(date_text())}</b>"
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
# ОБРАБОТКА БЛОКА
# ============================================================

def process_block(block, source, url):

    if is_old_ammo_incident(block["text"]):
        print(
            "SKIP OLD AMMO:",
            block["text"][:150]
        )
        return

    city, region = determine_block_location(
        block
    )

    if not city and not region:
        print(
            "SKIP UNKNOWN LOCATION:",
            block["text"][:150]
        )
        return

    dead, injured = extract_block_numbers(
        block
    )

    if dead is None and injured is None:
        print(
            "SKIP NO NUMBERS:",
            block["text"][:150]
        )
        return

    description = make_description(
        block
    )

    if not description:
        return

    ev_time = incident_time(
        block["text"]
    )

    key = event_key(
        city,
        region,
        block,
        ev_time
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

    # При обновлении сохраняем уже известные
    # максимальные значения.
    dead, injured = merged_numbers(
        key,
        dead,
        injured
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
        getattr(entry, "title", "")
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
        getattr(entry, "summary", "")
    )

    preview = title + ". " + summary

    # RSS-фильтр.
    if not (
        has_attack(preview)
        or has_casualty(preview)
    ):
        return

    article = get_article(url)

    if not article:
        return

    whole_start = (
        title + ". " +
        summary + ". " +
        article[:6000]
    )

    # Нужна одновременно атака + потери.
    if not has_attack(whole_start):
        return

    if not has_casualty(whole_start):
        return

    if is_old_ammo_incident(whole_start):
        print(
            "SKIP OLD AMMO ARTICLE:",
            title
        )
        return

    # Только актуальное событие.
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

    state["events"] = {
        key: value
        for key, value in state.get(
            "events",
            {}
        ).items()
        if value.get("date") == current
    }

    save_state()


# ============================================================
# RSS
# ============================================================

def check_sources():

    for source, rss in SOURCES:

        try:
            print("CHECK:", source)

            feed = feedparser.parse(rss)

            entries = list(
                feed.entries[:50]
            )

            # Старые сначала, затем более новые обновления.
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
print(
    "SOURCES:",
    ", ".join(x[0] for x in SOURCES)
)
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