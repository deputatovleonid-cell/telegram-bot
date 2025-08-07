from flask import Flask, request, jsonify
from openai import OpenAI
import requests
import os
import tiktoken
from datetime import datetime, timedelta

# 🔐 API ключи
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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"
)

bot_token = "7558130234:AAF2y4_Uq51jlyur7ZJ0U7OcHJxFeC5-WFw"
replit_url = "https://telegram-bot-pr1u.onrender.com"

app = Flask(__name__)

user_limits = {}
user_pro = {}
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
    return '✅ Бот работает. Webhook активен.'

@app.route('/setup')
def setup():
    webhook_url = f'{replit_url}/webhook'
    r = requests.post(f'https://api.telegram.org/bot{bot_token}/setWebhook?url={webhook_url}')
    return jsonify(r.json())

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

    if "text" in message and message["text"] == "/start":
        today = datetime.now().date()
        user_limits.setdefault(chat_id, {}).setdefault(today, 0)
        remaining = 2 - user_limits[chat_id][today]
        model_info = "GPT-4 (PRO)" if chat_id in user_pro and datetime.now() < user_pro[chat_id] else "GPT-3.5 (бесплатно)"
        send_message(chat_id, f"👋 Привет!\n\n🧠 *Модель*: {model_info}\n🔄 *Осталось запросов*: {remaining} из 2")
        return jsonify({"status": "start message"})

    if "photo" in message:
        if chat_id in user_payment_pending:
            activation = datetime.now()
            expiration = activation + timedelta(days=30)
            user_pro[chat_id] = expiration
            user_payment_pending.remove(chat_id)
            send_message(chat_id, f"✅ *PRO активирован!*\n@{username}\nДействует до {expiration.strftime('%d.%m.%Y')}")
        else:
            send_message_with_button(
                chat_id,
                "📸 Фото получено, но оно не связано с оплатой.",
                [[{"text": "Я оплатил ✅", "callback_data": "payment_sent"}]]
            )
        return jsonify({"status": "photo processed"})

    if "text" in message:
        text = message["text"].strip()

        # лимит для бесплатного доступа
        if chat_id not in user_pro or datetime.now() > user_pro[chat_id]:
            today = datetime.now().date()
            user_limits.setdefault(chat_id, {}).setdefault(today, 0)
            if user_limits[chat_id][today] >= 2:
                send_message_with_button(
                    chat_id,
                    "*✨ Бесплатно*: 2 запроса/день с GPT‑3.5\n🚀 *PRO*: 15 000 сум/мес — GPT‑4 без лимитов\n\nПереведи 15 000 сум на карту:\n\n`8600 4904 6804 4854`\n\nЗатем отправь фото квитанции и нажми кнопку ниже ⬇️",
                    [[{"text": "Я оплатил ✅", "callback_data": "payment_sent"}]]
                )
                return jsonify({"status": "limit reached"})
            user_limits[chat_id][today] += 1
            model = "deepseek/deepseek-chat"
        else:
            model = "openchat/openchat-3.5-1210"

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ]
            )
            reply = format_reply(response.choices[0].message.content)
            send_message(chat_id, reply)
        except Exception as e:
            send_message(chat_id, f"❌ Ошибка: {str(e)}")

    return jsonify({"status": "ok"})

def send_message(chat_id, text):
    requests.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        data={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    )

def send_message_with_button(chat_id, text, buttons):
    requests.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown',
            'reply_markup': {'inline_keyboard': buttons}
        }
    )

def format_reply(text):
    words = text.split()
    if len(words) > 90:
        text = ' '.join(words[:90]) + '...'
    return text.replace("**", "*").replace("_", "_")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=81)
