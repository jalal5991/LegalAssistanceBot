# Импорт системных библиотек и модулей aiogram
import os
import asyncio
from collections import defaultdict
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F

# --- КОНФИГУРАЦИЯ ---
# Бот будет брать API_TOKEN из переменной окружения на хостинге
API_TOKEN = os.getenv("8030224064:AAE3ERioo_7jEU8HzExKhUFpi-3LYK7CrAE") 
LAWYERS_GROUP_ID = -1002929346188
ARCHIVE_GROUP_ID = -1003171406428

# Инициализация
if not API_TOKEN:
    print("❌ ОШИБКА: API_TOKEN не найден. Проверьте переменную окружения.")
    exit()
    
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- FSM (Машина конечных состояний) ---
class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_contact = State()
    waiting_for_category = State()
    waiting_for_problem = State()

# --- Категории ---
# Украинский (uk) установлен как единственный язык
CATEGORIES = {
    "dtp": {"ru": "🚗 ДТП", "uk": "🚗 ДТП"},
    "family": {"ru": "⚖️ Семейные споры", "uk": "⚖️ Сімейні спори"},
    "admin": {"ru": "🏢 Адміністративні/цивільні", "uk": "🏢 Адміністративні/цивільні"},
    "criminal": {"ru": "🕵️ Уголовные дела", "uk": "🕵️ Кримінальні справи"},
    "tck": {"ru": "🛡️ ТЦК", "uk": "🛡️ ТЦК"},
    "other": {"ru": "❓ Иное", "uk": "❓ Інше"}
}

# --- Тексты для разных языков (Используем только uk) ---
TEXTS = {
    "ask_name": {
        "uk": "Введіть ваше ім'я:"
    },
    "ask_contact": {
        "uk": "Вкажіть контакт для зв'язку."
    },
    "ask_category": {
        "uk": "Виберіть категорію вашої проблеми:"
    },
    "ask_problem": {
        "uk": "Опишіть вашу проблему:"
    },
    "ticket_sent": {
        "uk": "✅ Ваша заявка {ticket} відправлена юристам. Очікуйте відповіді ⏳"
    },
    "ticket_accepted_client": {
        "uk": "✅ Ваша заявка {ticket} прийнята. Юрист вже опрацьовує Ваше звернення та зв'яжеться з Вами найближчим часом."
    }
}

# --- Счетчик заявок (на основе файла counter.txt) ---
def get_next_ticket_number():
    # Эта логика работает локально. На хостинге нужно будет использовать базу данных.
    # Для целей тестирования оставим файловый метод.
    # В реальном приложении это место нужно будет изменить на работу с Firestore/SQL.
    if not os.path.exists("counter.txt"):
        with open("counter.txt", "w") as f:
            f.write("0")
    with open("counter.txt", "r") as f:
        number = int(f.read().strip())
    number += 1
    with open("counter.txt", "w") as f:
        f.write(str(number))
    return f"#{number:03d}"

# --- Клавиатуры ---

def get_category_kb():
    # Используем только uk, так как язык фиксирован
    lang = "uk"
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=name[lang])] for name in CATEGORIES.values()],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb

def get_contact_kb():
    lang = "uk"
    contact_btn = KeyboardButton("📱 Надіслати свій номер", request_contact=True)
    manual_btn = KeyboardButton("✍️ Ввести вручну")
    kb = ReplyKeyboardMarkup(
        keyboard=[[contact_btn], [manual_btn]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb

def get_restart_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Розпочати нову заявку", callback_data="start_new_ticket")]
    ])
    return kb


# --- ОБРАБОТЧИКИ ---

# --- Старт бота / Перезапуск ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(Form.waiting_for_name)
    await state.update_data(lang="uk") # Устанавливаем язык по умолчанию
    await message.answer(
        TEXTS["ask_name"]["uk"], 
        reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    )

# --- Имя ---
@dp.message(StateFilter(Form.waiting_for_name))
async def process_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    await state.update_data(name=message.text)
    await state.set_state(Form.waiting_for_contact)
    await message.answer(TEXTS["ask_contact"][lang], reply_markup=get_contact_kb())

# --- Контакт (share/contact) ---
@dp.message(StateFilter(Form.waiting_for_contact), F.contact)
async def process_contact_share(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    await state.update_data(contact=message.contact.phone_number)
    await state.set_state(Form.waiting_for_category)
    await message.answer(TEXTS["ask_category"][lang], reply_markup=get_category_kb())

# --- Контакт (вручную) ---
@dp.message(StateFilter(Form.waiting_for_contact))
async def process_contact_manual(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    
    if "Ввести" in message.text: # Если пользователь нажал кнопку "Ввести вручную"
        await message.answer("Введіть контакт вручну:", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
    else: # Пользователь ввел контакт вручную
        await state.update_data(contact=message.text)
        await state.set_state(Form.waiting_for_category)
        await message.answer(TEXTS["ask_category"][lang], reply_markup=get_category_kb())

# --- Категория ---
@dp.message(StateFilter(Form.waiting_for_category))
async def process_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    selected = None
    for key, names in CATEGORIES.items():
        if message.text == names[lang]:
            selected = key
            break
            
    if not selected:
        await message.answer(TEXTS["ask_category"][lang], reply_markup=get_category_kb())
        return
        
    await state.update_data(category=selected)
    await state.set_state(Form.waiting_for_problem)
    await message.answer(TEXTS["ask_problem"][lang], reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))

# --- Проблема (ФИНАЛ) ---
@dp.message(StateFilter(Form.waiting_for_problem))
async def process_problem(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    name = data["name"]
    contact = data["contact"]
    category = data["category"]
    problem = message.text
    ticket = get_next_ticket_number()
    user_id = message.from_user.id
    
    # 1. Уведомление клиента
    await message.answer(
        TEXTS["ticket_sent"][lang].format(ticket=ticket), 
        reply_markup=get_restart_kb() # Добавляем кнопку "Начать заново"
    )

    # 2. Формирование сообщения для юристов
    category_name_ru = CATEGORIES[category]["ru"] # Используем русское название для юристов
    username = message.from_user.username
    tg_link = f"@{username}" if username else "—"
    
    lawyer_text = (
        f"🆕 <b>Новая заявка {ticket}</b>\n"
        f"📂 Категория: {category_name_ru}\n\n"
        f"👤 Имя: {name}\n"
        f"📱 Контакт: {contact}\n"
        f"💬 Telegram: {tg_link} (ID: <code>{user_id}</code>)\n\n"
        f"📄 Проблема:\n{problem}"
    )

    # 3. Кнопки для юристов
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"accept:{user_id}:{ticket}"),
         InlineKeyboardButton(text="⛔ Отклонить", callback_data=f"decline:{user_id}:{ticket}")]
    ])
    
    # 4. Отправка в группу юристов и архив
    sent_message = await bot.send_message(LAWYERS_GROUP_ID, lawyer_text, parse_mode="HTML", reply_markup=keyboard)
    # Сохраняем ID сообщения юристов для дальнейшего редактирования
    await state.update_data(lawyers_msg_id=sent_message.message_id) 
    await bot.send_message(ARCHIVE_GROUP_ID, lawyer_text, parse_mode="HTML") # Архив

    # 5. Очистка состояния
    await state.clear()


# --- Обработка нажатий кнопок юристами ---
@dp.callback_query(F.data.startswith(("accept", "decline")))
async def process_lawyer_action(callback_query: types.CallbackQuery, state: FSMContext):
    action, user_id, ticket = callback_query.data.split(":")
    lawyer_id = callback_query.from_user.id
    lawyer_name = callback_query.from_user.full_name
    
    # 1. Получаем оригинальный текст сообщения (который содержит детали заявки)
    original_text = callback_query.message.html_text
    
    # 2. Определяем статус и текст уведомления
    if action == "accept":
        new_status_line = f"✅ ЗАЯВКА {ticket} ВЗЯТА В РАБОТУ"
        client_notification_key = "ticket_accepted_client"
    else: # action == "decline"
        new_status_line = f"⛔ ЗАЯВКА {ticket} ОТКЛОНЕНА"
        
    # 3. Редактируем сообщение в группе юристов (защита от двойного нажатия)
    try:
        # Разделяем оригинальный текст на заголовок и тело
        parts = original_text.split('\n', 1)
        if len(parts) < 2:
            body = original_text
        else:
            body = parts[1]
            
        final_text = (
            f"<b>{new_status_line}</b>\n"
            f"{body}\n\n"
            f"<i>Обработал: {lawyer_name} ({lawyer_id})</i>"
        )
        
        await callback_query.message.edit_text(
            final_text,
            reply_markup=None, # Убираем кнопки
            parse_mode="HTML"
        )
        
        # 4. Уведомление юриста
        await callback_query.answer(f"Заявка {ticket} успешно обработана!", show_alert=True)
        
        # 5. Уведомление клиента (только при принятии)
        if action == "accept":
            try:
                # Отправляем общее уведомление клиенту
                await bot.send_message(
                    int(user_id), 
                    TEXTS[client_notification_key]["uk"].format(ticket=ticket),
                    reply_markup=get_restart_kb()
                )
            except Exception as e:
                print(f"Ошибка при уведомлении клиента {user_id}: {e}")

    except Exception as e:
        # Срабатывает, если другой юрист успел отредактировать сообщение первым (конфликт)
        print(f"Ошибка редактирования сообщения (конфликт/ошибка парсинга): {e}")
        await callback_query.answer("⚠️ Заявка была обработана другим сотрудником или возникла техническая ошибка.", show_alert=True)
        
# --- Обработка кнопки "Начать заново" ---
@dp.callback_query(F.data == "start_new_ticket")
async def callback_restart(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    # Сбрасываем состояние и запускаем команду start
    await state.clear()
    await cmd_start(callback_query.message, state)


# --- ЗАПУСК ---
async def main():
    print(f"✅ Бот успешно подключен! Имя: @{await bot.get_me().username}. Начинаем опрос сервера...")
    # Удаляем вебхуки и запускаем polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Предупреждение: Не удалось удалить вебхук: {e}")
        
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен пользователем.")
