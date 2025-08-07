from flask import Flask, request, jsonify
from pydub import AudioSegment
from openai import OpenAI
import os
import requests
import tiktoken
import re
from datetime import datetime, timedelta

# Подключение к OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key = "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"
)

bot_token = '7558130234:AAF2y4_Uq51jlyur7ZJ0U7OcHJxFeC5-WFw'
replit_url = 'https://c219359c-08f7-420e-bf35-f37c2e8bc484-00-2cd29q7115mi3.pike.replit.dev'

app = Flask(__name__)

# Хранилище сообщений и подписок
user_messages = {}
user_limits = {}
user_pro = {}  # {chat_id: datetime}
user_payment_pending = set()

SYSTEM_PROMPT = '''
Ты профессиональный AI-ассистент, эксперт в аналитике, коммуникации и деловом подходе.
Отвечай:
– Строго по сути, без "воды"
– Структурировано, по пунктам (если можно), максимум 90 слов
– Грамотно, деловым и уверенным языком
– Добавляй уместные эмодзи для акцента
– Выделяй ключевые мысли ЗАГЛАВНЫМИ или ПОДЧЁРКИВАНИЕМ
– Делай пробелы между абзацами для читабельности
– Отвечай только на русском, узбекском или английском, в зависимости от запроса
– Если запрос неполный — сначала уточни
– Никакой лишней вежливости: без "рад помочь", "как я могу помочь", только факты и полезность
– Если требуется — выдай ссылку по теме (если есть источник)
'''

@app.route('/')
def index():
    return '✅ Бот запущен!\n\n💳 Карта для оплаты: `8600 4904 6804 4854` (нажмите для копирования)'

@app.route('/setup')
def setup():
    webhook_url = f'{replit_url}/webhook'
    response = requests.post(
        f'https://api.telegram.org/bot{bot_token}/setWebhook?url={webhook_url}'
    )
    return jsonify(response.json())

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    if "message" not in data and "callback_query" not in data:
        return jsonify({"status": "no message"})

    if "callback_query" in data:
        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        message_id = query["message"]["message_id"]
        if query["data"] == "payment_sent":
            user_payment_pending.add(chat_id)
            send_message(chat_id, "📸 Пожалуйста, отправьте *фото квитанции* для подтверждения оплаты.")
        return jsonify({"status": "callback processed"})

    message = data["message"]
    chat_id = message["chat"]["id"]
    username = message["from"].get("username", "пользователь")

    if message.get("text") == "/start":
        today = datetime.now().date()
        user_limits.setdefault(chat_id, {})
        user_limits[chat_id].setdefault(today, 0)
        remaining = 2 - user_limits[chat_id][today]
        model_info = "GPT-4 (PRO)" if chat_id in user_pro and datetime.now() < user_pro[chat_id] else "GPT-3.5 (бесплатно)"
        send_message(chat_id, f"👋 Привет!\n\n🧠 *Модель*: {model_info}\n🔄 *Осталось запросов*: {remaining} из 2")
        return jsonify({"status": "start message"})

    if "voice" in message or "audio" in message:
        send_message(chat_id, "❌ Я не могу обрабатывать *аудиосообщения*. Пожалуйста, отправьте текст. 🎤➡️💬")
        return jsonify({"status": "voice ignored"})

    if "photo" in message:
        if chat_id in user_payment_pending:
            activation_date = datetime.now()
            expiration_date = activation_date + timedelta(days=30)
            user_pro[chat_id] = expiration_date
            user_payment_pending.remove(chat_id)

            send_message(chat_id, f"✅ *Подписка PRO активирована!*\n\n👤 @{username}\n📅 С {activation_date.strftime('%d.%m.%Y')} по {expiration_date.strftime('%d.%m.%Y')}\n\n🚀 Доступ к GPT‑4 без ограничений включён.")
        else:
            send_message_with_button(
                chat_id,
                "📸 Фото получено, но оно не связано с оплатой. Если вы хотите подключить PRO, нажмите кнопку ниже.",
                [[{"text": "Я оплатил ✅", "callback_data": "payment_sent"}]]
            )
        return jsonify({"status": "photo processed"})

    if "text" in message:
        user_message = message["text"].strip()

        if chat_id not in user_pro or datetime.now() > user_pro[chat_id]:
            today = datetime.now().date()
            user_limits.setdefault(chat_id, {})
            user_limits[chat_id].setdefault(today, 0)
            if user_limits[chat_id][today] >= 2:
                send_message_with_button(
                    chat_id,
                    "*✨ Бесплатно*: до 2 запросов в день с GPT‑3.5\n🚀 *PRO‑подписка*: 15 000 сум/мес — GPT‑4 без лимитов\n\n👉 Чтобы подключить *PRO‑режим*:\n1. Переведи 15 000 сум на карту:\n\n`8600 4904 6804 4854` *(нажмите для копирования)*\n\n2. Отправь *квитанцию* (фото) сюда\n3. После оплаты нажми кнопку ниже ⬇️",
                    [[{"text": "Я оплатил ✅", "callback_data": "payment_sent"}]]
                )
                return jsonify({"status": "limit reached"})
            user_limits[chat_id][today] += 1
            model_name = "deepseek/deepseek-chat"
            remaining = 2 - user_limits[chat_id][today]
            send_message(chat_id, f"🧠 *GPT‑3.5* (бесплатно)\n🔄 Осталось запросов: {remaining} из 2")
        else:
            model_name = "deepseek/deepseek-chat"

        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ]
            )

            reply = completion.choices[0].message.content
            reply = format_reply(reply)
            send_message(chat_id, reply)

        except Exception as e:
            send_message(chat_id, f"❌ Ошибка: {str(e)}")

    return jsonify({"status": "ok"})

def send_message(chat_id, text):
    return requests.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        data={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
    )

def send_message_with_button(chat_id, text, buttons):
    return requests.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown',
            'reply_markup': {
                'inline_keyboard': buttons
            }
        }
    )

def num_tokens_from_messages(messages, model="gpt-3.5-turbo"):
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    num_tokens = 0
    for message in messages:
        num_tokens += 4
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens -= 1
    num_tokens += 2
    return num_tokens

def format_reply(text):
    words = text.split()
    if len(words) > 90:
        text = ' '.join(words[:90]) + '...'
    text = text.replace("**", "*").replace("_", "_")
    return text

app.run(host='0.0.0.0', port=81)