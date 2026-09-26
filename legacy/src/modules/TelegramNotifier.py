from dotenv import load_dotenv
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()
telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")


# Função para responder ao comando /start
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("Olá! Eu sou um bot do Telegram feito em Python!")


# if __name__ == "__main__":
#     app = ApplicationBuilder().token(telegram_bot_token).build()

#     app.add_handler(CommandHandler("start", start))

#     print("Bot está rodando...")
#     app.run_polling()


import requests


def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    response = requests.post(url, data=payload)
    return response


# Parâmetros fixos
CHAT_ID = "6212208044"


def notificar_ordem(ativo, tipo, quantidade, preco):
    mensagem = f"Nova ordem executada!\n\nAtivo: <b>{ativo}</b>\nTipo: <b>{tipo}</b>\nQuantidade: <b>{quantidade}</b>\nPreço: <b>R$ {preco:.2f}</b>"
    send_telegram_message(telegram_bot_token, CHAT_ID, mensagem)


# Exemplo de uso após executar ordem
notificar_ordem("PETR4", "COMPRA", 100, 34.50)
