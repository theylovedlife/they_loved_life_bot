import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "Привет! 👋\n\n"
        "Это бот they_loved_life."
    )

@bot.message_handler(func=lambda message: True)
def reply(message):
    bot.reply_to(message, "Я получил твоё сообщение.")

print("Bot started")
bot.infinity_polling()
