import os
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# 🔐 Переменные окружения
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL", "https://your-app.onrender.com")

# 📊 Память пользователей
user_limits = {}
user_pro = {}
user_payment_pending = set()

# 🧠 Системная инструкция
SYSTEM_PROMPT = '''
Ты профессиональный AI-ассистент, эксперт в аналитике, коммуникации и деловом подходе.
Отвечай:
– Строго по сути, без "воды"
– Структурировано, по пунктам (если можно), максимум 90 слов
– Грамотно, деловым и уверенным языком
– Добавляй уместные эмодзи для акцента
– Выделяй ключевые мысли ЗАГЛАВНЫМИ или ПОДЧЁРКИВАНИЕМ
– Делай пробелы между абзацами
– Отвечай только на русском, узбекском или английском
– Если запрос неполный — сначала уточни
– Никакой лишней вежливости
'''

# 📌 Главная страница
@app.route('/')
def index():
    return '✅ Бот работает. Webhook активен.'

# 📌 Установка Webhook
@app.route('/setup')
def setup():
    webhook_url = f'{BASE_URL}/webhook'
    r = requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}')
    return jsonify(r.json())

# 📌 Webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    if "message" not in data and "callback_query" not in data:
        return jsonify({"status": "no message"})

    if "callback_query" in data:
        query = data["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        if query["data"] == "payment_sent":
            user_payment_pending.add(chat_id)
            send_message(chat_id, "📸 Пожалуйста, отправьте *фото квитанции* для подтверждения оплаты.")
        return jsonify({"status": "callback processed"})

    message = data["message"]
    chat_id = message["chat"]["id"]
    username = message["from"].get("username", "пользователь")

    # 📌 Старт
    if "text" in message and message["text"] == "/start":
        today = datetime.now().date()
        user_limits.setdefault(chat_id, {}).setdefault(today, 0)
        remaining = 2 - user_limits[chat_id][today]
        model_info = "DeepSeek Chat (PRO)" if chat_id in user_pro and datetime.now() < user_pro[chat_id] else "DeepSeek Chat (бесплатно)"
        send_message(chat_id, f"👋 Привет!\n\n🧠 *Модель*: {model_info}\n🔄 *Осталось запросов*: {remaining} из 2")
        return jsonify({"status": "start message"})

    # 📌 Фото (оплата)
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

    # 📌 Текст
    if "text" in message:
        text = message["text"].strip()

        # 💳 Лимит
        if chat_id not in user_pro or datetime.now() > user_pro[chat_id]:
            today = datetime.now().date()
            user_limits.setdefault(chat_id, {}).setdefault(today, 0)
            if user_limits[chat_id][today] >= 2:
                send_message_with_button(
                    chat_id,
                    "*✨ Бесплатно*: 2 запроса/день\n🚀 *PRO*: 15 000 сум/мес — без лимитов\n\nПереведи 15 000 сум на карту:\n\n`8600 4904 6804 4854`\n\nЗатем отправь фото квитанции и нажми кнопку ниже ⬇️",
                    [[{"text": "Я оплатил ✅", "callback_data": "payment_sent"}]]
                )
                return jsonify({"status": "limit reached"})
            user_limits[chat_id][today] += 1

        # 🧠 Запрос в OpenRouter
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek/deepseek-chat",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text}
                    ]
                }
            )

            if response.status_code != 200:
                raise Exception(f"Error code: {response.status_code} - {response.text}")

            result = response.json()
            reply = format_reply(result["choices"][0]["message"]["content"])
            send_message(chat_id, reply)
        except Exception as e:
            send_message(chat_id, f"❌ Ошибка:\n\n{str(e)}")

    return jsonify({"status": "ok"})

# 📌 Отправка сообщений
def send_message(chat_id, text):
    requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
        data={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
    )

def send_message_with_button(chat_id, text, buttons):
    requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
        json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown',
            'reply_markup': {'inline_keyboard': buttons}
        }
    )

# 📌 Ограничение длины
def format_reply(text):
    words = text.split()
    if len(words) > 90:
        text = ' '.join(words[:90]) + '...'
    return text.replace("**", "*").replace("_", "_")

# 📌 Запуск (Render использует PORT)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)















