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


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False)


def article_id(url):
    return hashlib.sha256(url.encode()).hexdigest()


def get_article_text(url):
    try:
        r = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        soup = BeautifulSoup(r.text, "html.parser")
        paragraphs = soup.find_all("p")
        return " ".join(p.get_text(" ", strip=True) for p in paragraphs)
    except Exception:
        return ""


def relevant(text):
    text = text.lower()
    return any(keyword in text for keyword in KEYWORDS)


def make_summary(source, title, text, url):
    text = " ".join(text.split())

    if len(text) > 600:
        text = text[:600].rsplit(" ", 1)[0] + "…"

    return (
        f"🕯 {title}\n\n"
        f"{text}\n\n"
        f"Источник: {source}\n"
        f"{url}"
    )


def check_news():
    seen = load_seen()

    for source, rss in SOURCES:
        try:
            feed = feedparser.parse(rss)

            for entry in feed.entries[:20]:
                url = entry.get("link", "")
                title = entry.get("title", "")

                if not url:
                    continue

                uid = article_id(url)

                if uid in seen:
                    continue

                article_text = get_article_text(url)
                full_text = title + " " + article_text

                if relevant(full_text):
                    message = make_summary(
                        source,
                        title,
                        article_text,
                        url
                    )

                    bot.send_message(
                        CHANNEL_ID,
                        message,
                        disable_web_page_preview=True
                    )

                seen.add(uid)

            save_seen(seen)

        except Exception as e:
            print(source, e)


print("Monitoring started")

while True:
    check_news()
    time.sleep(600)