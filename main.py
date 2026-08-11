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
# КЛЮЧЕВЫЕ СЛОВА
# Публикуем только последствия атак/обстрелов/БПЛА и т.п.
# ============================================================

ATTACK_WORDS = [
    "бпла",
    "беспилотник",
    "беспилотного",
    "беспилотника",
    "дрон",
    "fpv",
    "fpv-дрон",
    "обстрел",
    "обстреля",
    "атаковал",
    "атаковала",
    "атаковали",
    "атака",
    "удар",
    "ракет",
    "ракета",
    "боеприпас",
    "снаряд",
    "взрыв",
    "пво",
    "противовоздуш",
    "подавлен",
    "сбит",
    "сбили",
    "уничтожен",
    "уничтожили",
    "обломки",
    "падение обломков",
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
    "получил ранения",
    "получили ранения",
    "получила ранения",
    "госпитализирован",
    "госпитализированы",
]


# Исключаем очевидные происшествия, не связанные с атакой
EXCLUDE_WORDS = [
    "дтп",
    "аварии на дороге",
    "столкнулись автомобили",
    "утонул",
    "пожар произошел",
    "пожар произошёл",
    "отравлен",
    "криминал",
]


# ============================================================
# РЕГИОНЫ
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
    "Калужская область",
    "Московская область",
    "Ленинградская область",
    "Смоленская область",
    "Тверская область",
    "Ярославская область",
    "Рязанская область",
    "Тамбовская область",
    "Волгоградская область",
    "Саратовская область",
    "Самарская область",
    "Ульяновская область",
    "Оренбургская область",
    "Пензенская область",
    "Нижегородская область",
    "Новгородская область",
    "Псковская область",
    "Мурманская область",
    "Архангельская область",
    "Вологодская область",
    "Костромская область",
    "Ивановская область",
    "Владимирская область",
    "Кировская область",
    "Курганская область",
    "Свердловская область",
    "Челябинская область",
    "Тюменская область",
    "Омская область",
    "Новосибирская область",
    "Томская область",
    "Кемеровская область",
    "Иркутская область",
    "Амурская область",
    "Магаданская область",
    "Сахалинская область",

    "Краснодарский край",
    "Ставропольский край",
    "Пермский край",
    "Алтайский край",
    "Красноярский край",
    "Забайкальский край",
    "Приморский край",
    "Хабаровский край",
    "Камчатский край",

    "Республика Татарстан",
    "Татарстан",
    "Республика Башкортостан",
    "Башкортостан",
    "Республика Дагестан",
    "Дагестан",
    "Республика Крым",
    "Крым",
    "Республика Адыгея",
    "Адыгея",
    "Республика Калмыкия",
    "Калмыкия",
    "Республика Северная Осетия",
    "Северная Осетия",
    "Кабардино-Балкарская Республика",
    "Кабардино-Балкария",
    "Карачаево-Черкесская Республика",
    "Карачаево-Черкесия",
    "Чеченская Республика",
    "Чечня",
    "Республика Ингушетия",
    "Ингушетия",
    "Республика Мордовия",
    "Мордовия",
    "Республика Марий Эл",
    "Марий Эл",
    "Удмуртская Республика",
    "Удмуртия",
    "Чувашская Республика",
    "Чувашия",
    "Республика Коми",
    "Коми",

    "Москва",
    "Санкт-Петербург",
    "Севастополь",
]


REGION_NORMALIZE = {
    "Татарстан": "Республика Татарстан",
    "Башкортостан": "Республика Башкортостан",
    "Дагестан": "Республика Дагестан",
    "Крым": "Республика Крым",
    "Адыгея": "Республика Адыгея",
    "Калмыкия": "Республика Калмыкия",
    "Северная Осетия": "Республика Северная Осетия",
    "Кабардино-Балкария": "Кабардино-Балкарская Республика",
    "Карачаево-Черкесия": "Карачаево-Черкесская Республика",
    "Чечня": "Чеченская Республика",
    "Ингушетия": "Республика Ингушетия",
    "Мордовия": "Республика Мордовия",
    "Марий Эл": "Республика Марий Эл",
    "Удмуртия": "Удмуртская Республика",
    "Чувашия": "Чувашская Республика",
}


# ============================================================
# ФАЙЛ ПРОЧИТАННЫХ НОВОСТЕЙ
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
            json.dump(list(seen), f, ensure_ascii=False)
    except Exception as e:
        print("Ошибка сохранения seen:", e)


# ============================================================
# ОЧИСТКА ТЕКСТА
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)

    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text(" ", strip=True)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# ЗАГРУЗКА СТАТЬИ
# ============================================================

def get_article_text(url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Version/18.0 Mobile Safari/604.1"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        # Удаляем служебные элементы страницы
        for tag in soup([
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
        ]):
            tag.decompose()

        paragraphs = []

        for p in soup.find_all("p"):
            txt = clean_text(p.get_text(" ", strip=True))

            if len(txt) >= 20:
                paragraphs.append(txt)

        # Ограничиваем текст статьи.
        # Нам не нужны футеры, ссылки редакции и т.п.
        return " ".join(paragraphs[:30])

    except Exception as e:
        print("Ошибка загрузки статьи:", url, e)
        return ""


# ============================================================
# ПРОВЕРКА: НУЖНА ЛИ НАМ НОВОСТЬ
# ============================================================

def is_relevant(text):
    low = text.lower()

    has_attack = any(word in low for word in ATTACK_WORDS)
    has_casualties = any(word in low for word in CASUALTY_WORDS)

    if not (has_attack and has_casualties):
        return False

    # Не исключаем статью только из-за слова "автомобиль":
    # автомобиль может быть атакован БПЛА.
    #
    # Исключаем очевидные ДТП, если в тексте нет явного описания атаки.
    if "дтп" in low:
        strong_attack = any(
            x in low
            for x in [
                "бпла",
                "беспилот",
                "дрон",
                "обстрел",
                "ракет",
                "атаковал",
                "атаковали",
                "ударил",
                "удар по",
            ]
        )

        if not strong_attack:
            return False

    return True


# ============================================================
# ЧИСЛА
# ============================================================

NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "одно": 1,
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

    "пять": 5,
    "пятеро": 5,

    "шесть": 6,
    "шестеро": 6,

    "семь": 7,
    "семеро": 7,

    "восемь": 8,
    "восьмеро": 8,

    "девять": 9,
    "девятеро": 9,

    "десять": 10,
    "десятеро": 10,
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


def number_value(value):
    if not value:
        return None

    value = value.lower().strip()

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


# ============================================================
# ИЗВЛЕЧЕНИЕ ПОГИБШИХ
# ============================================================

def extract_dead(text):
    low = text.lower().replace("ё", "е")

    patterns = [
        # "погибли 13 человек"
        rf"(?:погибли|погибло)\s+(?:как минимум\s+|не менее\s+)?({NUM_TOKEN})",

        # "погиб 1 человек", "погиб один мужчина"
        rf"(?:погиб|погибла)\s+({NUM_TOKEN})",

        # "13 человек погибли"
        rf"({NUM_TOKEN})\s+(?:человек[а-я]*\s+)?(?:погибли|погибло)",

        # "число погибших увеличилось до 13"
        rf"(?:число|количество)\s+погибших[^.!?]{{0,50}}?\bдо\s+({NUM_TOKEN})",

        # "число жертв выросло до 13"
        rf"(?:число|количество)\s+жертв[^.!?]{{0,50}}?\bдо\s+({NUM_TOKEN})",

        # "жертвами стали 13 человек"
        rf"жертвами[^.!?]{{0,30}}?(?:стали|стало)\s+({NUM_TOKEN})",
    ]

    values = []

    for pattern in patterns:
        for match in re.finditer(pattern, low, flags=re.IGNORECASE):
            value = number_value(match.group(1))

            if value is not None:
                values.append(value)

    if values:
        # В обновляемых новостях часто встречается:
        # "сначала погибли 12, затем число выросло до 13".
        # Берём максимальное подтверждённое значение.
        return max(values)

    # Отдельные конструкции без числа
    if re.search(
        r"\bпогиб(?:ла)?\s+(?:мужчина|женщина|ребенок|ребёнок|водитель|человек)\b",
        low
    ):
        return 1

    return None


# ============================================================
# ИЗВЛЕЧЕНИЕ ПОСТРАДАВШИХ
# ============================================================

def extract_injured(text):
    low = text.lower().replace("ё", "е")

    patterns = [
        # "пострадали 39 человек"
        rf"(?:пострадали|пострадало)\s+(?:как минимум\s+|не менее\s+)?({NUM_TOKEN})",

        # "пострадал один человек"
        rf"(?:пострадал|пострадала)\s+({NUM_TOKEN})",

        # "39 человек пострадали"
        rf"({NUM_TOKEN})\s+(?:человек[а-я]*\s+)?(?:пострадали|пострадало)",

        # "ранены 39 человек"
        rf"(?:ранены|ранено)\s+(?:как минимум\s+|не менее\s+)?({NUM_TOKEN})",

        # "39 человек ранены"
        rf"({NUM_TOKEN})\s+(?:человек[а-я]*\s+)?(?:ранены|ранено)",

        # "39 человек получили ранения"
        rf"({NUM_TOKEN})\s+(?:человек[а-я]*\s+)?получил[аи]?\s+(?:различные\s+)?ранения",

        # "число пострадавших выросло до 39"
        rf"(?:число|количество)\s+пострадавших[^.!?]{{0,60}}?\bдо\s+({NUM_TOKEN})",

        # "число раненых выросло до 39"
        rf"(?:число|количество)\s+раненых[^.!?]{{0,60}}?\bдо\s+({NUM_TOKEN})",
    ]

    values = []

    for pattern in patterns:
        for match in re.finditer(pattern, low, flags=re.IGNORECASE):
            value = number_value(match.group(1))

            if value is not None:
                values.append(value)

    if values:
        return max(values)

    # Конструкции типа "пострадал мужчина"
    if re.search(
        r"\bпострадал(?:а)?\s+(?:мужчина|женщина|ребенок|ребёнок|водитель|человек)\b",
        low
    ):
        return 1

    if re.search(
        r"\bранен(?:а)?\s+(?:мужчина|женщина|ребенок|ребёнок|водитель|человек)\b",
        low
    ):
        return 1

    return None


# ============================================================
# ПРЕДЛОЖЕНИЯ
# ============================================================

def split_sentences(text):
    return [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) > 10
    ]


# ============================================================
# КРАТКОЕ ОПИСАНИЕ
# ============================================================

def make_description(title, text):
    sentences = split_sentences(text)

    selected = []

    for sentence in sentences:
        low = sentence.lower()

        if any(word in low for word in ATTACK_WORDS):
            # Убираем слишком длинный мусор
            if len(sentence) <= 350:
                selected.append(sentence)

        if len(selected) >= 2:
            break

    if not selected:
        return clean_text(title)[:350]

    description = " ".join(selected)

    # Не дублируем огромные куски
    if len(description) > 500:
        description = description[:497].rstrip() + "..."

    return description


# ============================================================
# ОПРЕДЕЛЕНИЕ РЕГИОНА
# ============================================================

def detect_region(title, description):
    # ВАЖНО:
    # не используем весь HTML страницы.
    # Только заголовок + краткое описание происшествия.
    search_text = f"{title}. {description}"

    low = search_text.lower()

    found = []

    for region in REGIONS:
        pos = low.find(region.lower())

        if pos != -1:
            found.append((pos, region))

    if not found:
        return None

    found.sort(key=lambda x: x[0])

    region = found[0][1]

    return REGION_NORMALIZE.get(region, region)


# ============================================================
# ОПРЕДЕЛЕНИЕ НАСЕЛЁННОГО ПУНКТА
# ============================================================

def detect_city(title, description, region):
    text = f"{title}. {description}"

    # Наиболее надёжные конструкции в новостях:
    patterns = [
        r"\bв\s+(?:городе\s+)?([А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+)?)",
        r"\bв\s+(?:поселке|посёлке|селе|деревне|хуторе|станице)\s+([А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+)?)",
        r"\bпод\s+([А-ЯЁ][а-яё-]+)",
    ]

    bad_words = {
        "результате",
        "районе",
        "области",
        "регионе",
        "россии",
        "понедельник",
        "воскресенье",
        "субботу",
        "пятницу",
        "четверг",
        "среду",
        "вторник",
        "момент",
        "итоге",
    }

    candidates = []

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            city = match.group(1).strip(" ,.-")

            if city.lower() in bad_words:
                continue

            # Название региона не должно стать городом
            if region and city.lower() in region.lower():
                continue

            candidates.append(city)

    if candidates:
        return candidates[0]

    return None


# ============================================================
# ФОРМАТ ЧИСЛА ЛЮДЕЙ
# ============================================================

def people_word(n):
    if n is None:
        return "количество уточняется"

    n10 = n % 10
    n100 = n % 100

    if n10 == 1 and n100 != 11:
        return f"{n} человек"

    return f"{n} человек"


# ============================================================
# СОЗДАНИЕ ПОСТА
# ============================================================

def build_message(source, title, link, article_text):
    # Для анализа используем заголовок + текст статьи
    analysis_text = f"{title}. {article_text}"

    dead = extract_dead(analysis_text)
    injured = extract_injured(analysis_text)

    # Если вообще нет подтверждённых человеческих жертв/пострадавших,
    # не публикуем.
    if dead is None and injured is None:
        return None

    description = make_description(title, article_text)

    region = detect_region(title, description)
    city = detect_city(title, description, region)

    # Формируем место
    if city and region:
        location = f"{city}, {region}"
    elif region:
        location = region
    elif city:
        location = city
    else:
        location = "Место уточняется"

    # Не пишем "количество уточняется", если про категорию
    # в статье вообще ничего нет.
    lines = [
        f"⚡️{location}",
        "",
        description,
        "",
    ]

    if dead is not None:
        lines.append(f"Погибли: {people_word(dead)}")

    if injured is not None:
        lines.append(f"Пострадали: {people_word(injured)}")

    lines.extend([
        "",
        f"Источник: {source}",
        link,
    ])

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
                title = clean_text(entry.get("title", ""))
                link = entry.get("link", "")

                rss_description = clean_text(
                    entry.get("summary", "") or
                    entry.get("description", "")
                )

                if not link:
                    continue

                uid = hashlib.md5(
                    link.encode("utf-8")
                ).hexdigest()

                if uid in seen:
                    continue

                # Сначала быстрая проверка RSS
                preview_text = f"{title}. {rss_description}"

                # Если RSS уже явно не про нужную тему,
                # всё равно иногда статья содержит больше информации.
                article_text = get_article_text(link)

                full_text = (
                    f"{title}. "
                    f"{rss_description}. "
                    f"{article_text}"
                )

                if not is_relevant(full_text):
                    # Помечаем как просмотренное,
                    # чтобы не проверять одну и ту же нерелевантную
                    # статью каждые 10 минут.
                    seen.add(uid)
                    continue

                message = build_message(
                    source,
                    title,
                    link,
                    f"{rss_description}. {article_text}"
                )

                if not message:
                    seen.add(uid)
                    continue

                try:
                    bot.send_message(
                        CHANNEL_ID,
                        message,
                        disable_web_page_preview=True
                    )

                    print("Опубликовано:", source, title)

                    seen.add(uid)

                    # Небольшая пауза между публикациями
                    time.sleep(2)

                except Exception as e:
                    print("Ошибка Telegram:", source, e)

            save_seen(seen)

        except Exception as e:
            print("Ошибка источника:", source, e)


# ============================================================
# ЗАПУСК
# ============================================================

print("Monitoring started")

while True:
    try:
        check_news()
    except Exception as e:
        print("Ошибка цикла:", e)

    time.sleep(600)