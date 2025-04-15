import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from dotenv import load_dotenv
import os

load_dotenv()
bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))

# Підключення до Google Таблиці
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Записи_ВетКлиника").sheet1

user_data = {}

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🐾 Записатись на прийом"))
    markup.add(KeyboardButton("📅 Переглянути запис"))
    markup.add(KeyboardButton("ℹ️ Про клініку"))
    markup.add(KeyboardButton("📞 Контакти"))
    markup.add(KeyboardButton("❌ Скасувати запис"))
    markup.add(KeyboardButton("🐕 Послуги / Ціни"))
    return markup

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, "Привіт! Я бот для запису до ветеринара 🐾", reply_markup=main_menu())

@bot.message_handler(commands=['cancel'])
def cancel_handler(message):
    user_data.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Дію скасовано. Ви в головному меню.", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "❌ Скасувати запис")
def cancel_record(message):
    chat_id = str(message.chat.id)
    records = sheet.get_all_records()
    found = False

    for i, record in enumerate(records, start=2):
        if str(record.get("ChatID")) == chat_id:
            sheet.delete_rows(i)
            found = True
            break

    if found:
        bot.send_message(message.chat.id, "✅ Ваш запис було успішно скасовано.", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "❌ У вас немає запису. Щоб записатися, натисніть «🐾 Записатись на прийом».", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "🐾 Записатись на прийом")
def choose_animal(message):
    chat_id = str(message.chat.id)
    records = sheet.get_all_records()
    already_booked = any(str(row.get("ChatID")) == chat_id for row in records)

    if already_booked:
        bot.send_message(
            message.chat.id,
            "❗ У вас вже є дійсний запис.\n\n"
            "Щоб зробити новий, спочатку скасуйте попередній запис, натиснувши на кнопку ❌ Скасувати запис.",
            reply_markup=main_menu()
        )
        return

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for animal in ["🐶 Собака", "🐱 Кіт", "🐦 Папуга", "🐹 Хом’як", "🐾 Інше"]:
        markup.add(KeyboardButton(animal))
    bot.send_message(message.chat.id, "Оберіть тварину:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["🐶 Собака", "🐱 Кіт", "🐦 Папуга", "🐹 Хом’як", "🐾 Інше"])
def get_owner_name_step(message):
    user_data[message.chat.id] = {"animal": message.text}
    bot.send_message(message.chat.id, "Введіть ПІБ власника:", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.chat.id in user_data and "owner" not in user_data[message.chat.id])
def get_pet_name_step(message):
    user_data[message.chat.id]["owner"] = message.text
    bot.send_message(message.chat.id, "Введіть кличку тварини:")

@bot.message_handler(func=lambda message: message.chat.id in user_data and "pet_name" not in user_data[message.chat.id])
def get_breed_name_step(message):
    user_data[message.chat.id]["pet_name"] = message.text
    bot.send_message(message.chat.id, "Введіть породу тварини (якщо немає — напишіть 'немає'):")    

@bot.message_handler(func=lambda message: message.chat.id in user_data and "breed" not in user_data[message.chat.id])
def get_description_step(message):
    user_data[message.chat.id]["breed"] = message.text
    bot.send_message(message.chat.id, "Опишіть проблему або причину візиту:")

@bot.message_handler(func=lambda message: message.chat.id in user_data and "description" not in user_data[message.chat.id])
def get_record_date_step(message):
    user_data[message.chat.id]["description"] = message.text
    bot.send_message(message.chat.id, "Введіть бажану дату прийому (наприклад, 12.04.2025):")

@bot.message_handler(func=lambda message: message.chat.id in user_data and "Record_data" not in user_data[message.chat.id])
def get_record_time_step(message):
    user_data[message.chat.id]["Record_data"] = message.text
    available = get_available_slots(user_data[message.chat.id]["Record_data"])

    if not available:
        bot.send_message(message.chat.id, "❌ На цю дату немає вільних годин. Виберіть іншу дату або спробуйте пізніше.", reply_markup=main_menu())
        user_data.pop(message.chat.id)
        return

    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    for time in available:
        markup.add(KeyboardButton(time))
    bot.send_message(message.chat.id, "Оберіть з доступних годин:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.chat.id in user_data and "Record_time" not in user_data[message.chat.id])
def save_appointment(message):
    chat_id = message.chat.id
    user_data[chat_id]["Record_time"] = message.text

    now = datetime.now()
    user_data[chat_id]["date_made"] = now.strftime("%Y-%m-%d")
    user_data[chat_id]["time_made"] = now.strftime("%H:%M:%S")

    sheet.append_row([
        str(chat_id),
        user_data[chat_id].get("owner", ""),
        user_data[chat_id].get("breed", ""),
        user_data[chat_id].get("pet_name", ""),
        user_data[chat_id].get("animal", ""),
        user_data[chat_id].get("description", ""),
        user_data[chat_id].get("date_made", ""),
        user_data[chat_id].get("time_made", ""),
        user_data[chat_id].get("Record_data", ""),
        user_data[chat_id].get("Record_time", "")
    ])

    bot.send_message(chat_id, "✅ Ви успішно записані на прийом! З вами зв'яжуться найближчим часом.", reply_markup=main_menu())
    user_data.pop(chat_id)

def generate_time_slots(start_time, end_time, interval_minutes=30):
    slots = []
    current = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=interval_minutes)
    return slots

def get_booked_times(date_str):
    records = sheet.get_all_records()
    return [r["Желаемое время"] for r in records if r["Желаемая дата"] == date_str]

def get_available_slots(date_str):
    try:
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        return []
    weekday = date_obj.weekday()
    slots = generate_time_slots("08:30", "18:00") if weekday < 5 else generate_time_slots("08:30", "17:00")
    booked = get_booked_times(date_str)
    return [s for s in slots if s not in booked]

@bot.message_handler(func=lambda message: message.text == "📅 Переглянути запис")
def these_records(message):
    chat_id = str(message.chat.id)

    try:
        records = sheet.get_all_records()
        user_rows = [row for row in records if str(row.get("ChatID")) == chat_id]

        if user_rows:
            row = user_rows[-1]
            response = (
                f"🗓 Ваш запис:\n"
                f"👤 Власник: {row.get('ФИО', 'Не вказано')}\n"
                f"🐾 Тварина: {row.get('Животное', 'Не вказано')} "
                f"({row.get('Кличка', 'Не вказано')}, {row.get('Порода', 'Не вказано')})\n"
                f"📋 Проблема: {row.get('Описание', 'Не вказано')}\n"
                f"📅 Бажана дата: {row.get('Желаемая дата', 'Не вказано')}\n"
                f"🕒 Бажаний час: {row.get('Желаемое время', 'Не вказано')}"
            )
        else:
            response = "❌ У вас ще немає записів. Щоб записатися, натисніть '🐾 Записатись на прийом'."

        bot.send_message(chat_id, response, reply_markup=main_menu())

    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Помилка зчитування даних: {e}", reply_markup=main_menu())

@bot.message_handler(func=lambda message: message.text == "ℹ️ Про клініку")
def clinic_info(message):
    bot.send_message(message.chat.id, 
        "🐾 *Назва клініки* — сучасна ветеринарна клініка у місті...\n\n"
        "📍 *Адреса:* адреса\n"
        "🕒 *Графік роботи:*\n"
        "Пн–Пт: 08:30–18:00\n"
        "Сб–Нд: 08:30–17:00",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "📞 Контакти")
def contact_info(message):
    bot.send_message(message.chat.id, 
        "📞 *Телефон:* номер телефону\n"
        "📸 *Instagram:* [акаунт](посилання)\n"
        "📘 *Facebook:* [акаунт](посилання)",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "🐕 Послуги / Ціни")
def services_info(message):
     bot.send_message(message.chat.id, 
        "💉 *Послуги:*\n"
        "• Консультації\n• Вакцинація\n• Документи\n• Діагностика\n• Хірургія\n• Стрижка котів тощо",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

bot.polling()
