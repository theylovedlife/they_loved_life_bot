import os
import time
import json
import hashlib
import feedparser
import requests
from bs4 import BeautifulSoup
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

bot = telebot.TeleBot(BOT_TOKEN)

SOURCES = [
    ("ТАСС", "https://tass.ru/rss/v2.xml"),
    ("РИА Новости", "https://ria.ru/export/rss2/archive/index.xml"),
    ("Российская газета", "https://rg.ru/xml/index.xml"),
]

KEYWORDS = [
    "погиб мирный",
    "погибли мирные",
    "погибла мирная",
    "мирный житель погиб",
    "мирные жители погибли",
    "погиб ребенок",
    "погиб ребёнок",
    "погибли дети",
    "погибла женщина",
    "погиб мужчина",
]

SEEN_FILE = "seen.json"

BAD_TEXT = [
    "if you are not a bot",
    "datetime:",
    "ip:",
    "support team",
    "access denied",
    "captcha",
    "verify you are human",
]


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


def make_id(link):
    return hashlib.md5(link.encode("utf-8")).hexdigest()


def clean_text(text):
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text(" ", strip=True)

    text = " ".join(text.split())

    lower = text.lower()

    for bad in BAD_TEXT:
        if bad in lower:
            return ""

    return text


def get_article_text(url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        paragraphs = soup.find_all("p")

        parts = []

        for p in paragraphs:
            text = clean_text(p.get_text(" ", strip=True))

            if len(text) > 40:
                parts.append(text)

        result = " ".join(parts)

        result = clean_text(result)

        if len(result) > 900:
            result = result[:900].rsplit(" ", 1)[0] + "…"

        return result

    except Exception as e:
        print("Ошибка чтения статьи:", e)
        return ""


def relevant(title, description):
    text = (
        clean_text(title) + " " +
        clean_text(description)
    ).lower()

    return any(keyword in text for keyword in KEYWORDS)


def check_news():
    seen = load_seen()

    for source, rss_url in SOURCES:
        try:
            feed = feedparser.parse(rss_url)

            for entry in feed.entries[:20]:

                title = clean_text(
                    getattr(entry, "title", "")
                )

                description = clean_text(
                    getattr(entry, "description", "")
                )

                link = getattr(entry, "link", "")

                if not title or not link:
                    continue

                if not relevant(title, description):
                    continue

                uid = make_id(link)

                if uid in seen:
                    continue

                article_text = get_article_text(link)

                # Если сайт отдал защиту, CAPTCHA или мусор,
                # используем описание из RSS.
                if not article_text:
                    article_text = description

                article_text = clean_text(article_text)

                message = f"🕯 {title}\n\n"

                if article_text:
                    # Не повторяем заголовок второй раз
                    if article_text.lower() != title.lower():
                        message += article_text + "\n\n"

                message += f"Источник: {source}\n{link}"

                bot.send_message(
                    CHANNEL_ID,
                    message,
                    disable_web_page_preview=True
                )

                print("Опубликовано:", source, title)

                seen.add(uid)
                save_seen(seen)

                # небольшая пауза между публикациями
                time.sleep(3)

        except Exception as e:
            print(source, e)


print("Monitoring started")

while True:
    check_news()
    time.sleep(600)