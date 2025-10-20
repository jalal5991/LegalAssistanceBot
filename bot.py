# -*- coding: utf-8 -*-
import os
import asyncio
import logging
import json
from collections import defaultdict

# --- ВАЖНО: ДЛЯ ЛОКАЛЬНОГО ЗАПУСКА ---
# Установите библиотеку: pip install python-dotenv
# Она нужна, чтобы код мог прочитать .env файл
from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage # Для FSM достаточно, т.к. состояния временные
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.utils.markdown import hbold
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)

# --- ID ГРУПП ---
# Убедитесь, что они указаны как числа, а не строки
LAWYERS_GROUP_ID = -1002929346188
ARCHIVE_GROUP_ID = -1003171406428

# --- API ТОКЕН БОТА (БЕЗОПАСНЫЙ СПОСОБ) ---
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    # Если токен не найден, бот не запустится. Это предотвращает утечку.
    logging.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: API_TOKEN не найден в переменных окружения!")
    exit()

# --- НАСТРОЙКА БОТА И ДИСПЕТЧЕРА ---
storage = MemoryStorage()
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# --- НАДЕЖНОЕ ХРАНИЛИЩЕ ДЛЯ ЗАЯВОК (JSON) ---
DB_FILE = "request_owners.json"

def load_request_owners():
    """Загружает данные из файла. Если файла нет, возвращает пустой словарь."""
    try:
        with open(DB_FILE, "r", encoding='utf-8') as f:
            # Преобразуем ключи обратно в integer, т.к. JSON хранит их как строки
            return {int(k): v for k, v in json.load(f).items()}
    except FileNotFoundError:
        return {}

def save_request_owners(data):
    """Сохраняет данные в файл."""
    with open(DB_FILE, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- FSM (Машина состояний) ---
class RequestForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_category = State()
    waiting_for_description = State()

# --- КЛАВИАТУРЫ ---
def get_phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📲 Надіслати свій номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_categories_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="ДТП"), KeyboardButton(text="ТЦК")],
            [KeyboardButton(text="Сімейні справи"), KeyboardButton(text="Адміністративні справи")],
            [KeyboardButton(text="Кримінальні справи"), KeyboardButton(text="Інше")],
            [KeyboardButton(text="Написання заяв/скарг/клопотань/ позовів до суду")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_all_category_names():
    return [
        "ДТП", "ТЦК", "Сімейні справи", "Адміністративні справи",
        "Кримінальні справи", "Інше", "Написання заяв/скарг/клопотань/ позовів до суду"
    ]

def get_restart_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Почати знову", callback_data="start_again")]
    ])

def get_request_inline_kb(request_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Прийняти", callback_data=f"status_accept_{request_id}")]
    ])

# --- ОБРАБОТЧИКИ FSM ---
@dp.message(CommandStart())
async def command_start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Вітаємо, {hbold(message.from_user.full_name)}! 👋\n"
        "Цей бот допоможе Вам подати заявку на отримання юридичної допомоги.\n\n"
        "Для початку введіть Ваше <b>ПІБ</b> (або ім'я та прізвище):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RequestForm.waiting_for_name)

@dp.message(F.text, RequestForm.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer(
        "Дякую! Тепер надішліть свій <b>номер телефону</b>.",
        reply_markup=get_phone_kb()
    )
    await state.set_state(RequestForm.waiting_for_phone)

@dp.message(F.contact, RequestForm.waiting_for_phone)
async def process_phone_contact(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await message.answer("Номер прийнято. Тепер оберіть <b>категорію</b>:", reply_markup=get_categories_kb())
    await state.set_state(RequestForm.waiting_for_category)

@dp.message(F.text.regexp(r'^\+?[\d\s\-\(\)]+$'), RequestForm.waiting_for_phone)
async def process_phone_text(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await message.answer("Номер прийнято. Тепер оберіть <b>категорію</b>:", reply_markup=get_categories_kb())
    await state.set_state(RequestForm.waiting_for_category)

@dp.message(F.text, RequestForm.waiting_for_category)
async def process_category(message: types.Message, state: FSMContext):
    if message.text not in get_all_category_names():
        await message.answer("Будь ласка, оберіть категорію за допомогою кнопок.")
        return
    await state.update_data(category=message.text.strip())
    await message.answer(
        f"Ви обрали категорію <b>'{message.text}'</b>.\n"
        "Опишіть суть Вашої проблеми (мінімум 20 символів):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RequestForm.waiting_for_description)

@dp.message(F.text, RequestForm.waiting_for_description)
async def process_description_and_send(message: types.Message, state: FSMContext):
    desc = message.text.strip()
    if len(desc) < 20:
        await message.answer("⚠️ Опис проблеми повинен бути не менше 20 символів. Будь ласка, спробуйте ще раз.")
        return
    await state.update_data(description=desc)
    data = await state.get_data()

    base_user_info = (
        f"<b>📝 НОВА ЗАЯВКА НА ЮР. ДОПОМОГУ</b>\n\n"
        f"<b>👤 ПІБ:</b> {data.get('name')}\n"
        f"<b>📞 Телефон:</b> {data.get('phone')}\n"
        f"<b>🗂️ Категорія:</b> {data.get('category')}\n"
        f"<b>💡 Проблема:</b>\n{data.get('description')}\n\n"
        f"<b>Статус:</b> ⏳ Очікує розгляду"
    )

    try:
        # Отправляем первое сообщение, чтобы получить его ID
        sent_message = await bot.send_message(
            chat_id=LAWYERS_GROUP_ID,
            text=base_user_info,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        request_id = sent_message.message_id
        
        # --- СОХРАНЯЕМ ДАННЫЕ В ФАЙЛ ---
        owners = load_request_owners()
        owners[request_id] = message.from_user.id
        save_request_owners(owners)
        # -----------------------------

        # Редактируем сообщение, добавляя ID заявки и кнопку
        full_user_info_with_id = f"<b>#ЗАЯВКА №{request_id}</b>\n\n" + base_user_info
        await bot.edit_message_text(
            chat_id=LAWYERS_GROUP_ID,
            message_id=request_id,
            text=full_user_info_with_id,
            parse_mode=ParseMode.HTML,
            reply_markup=get_request_inline_kb(request_id)
        )
        await message.answer(
            f"✅ <b>Заявку №{request_id} успішно відправлено!</b>\n"
            "Ми повідомимо Вам про її статус.",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logging.error(f"Помилка при відправці заявки: {e}")
        await message.answer("⚠️ Виникла помилка при відправці заявки. Спробуйте ще раз.")
    await state.clear()

# --- INLINE КНОПКИ ---
@dp.callback_query(F.data.startswith("status_accept_"))
async def handle_accept(callback: types.CallbackQuery):
    request_id = int(callback.data.split('_')[-1])
    
    # --- ЗАГРУЖАЕМ ДАННЫЕ ИЗ ФАЙЛА ---
    owners = load_request_owners()
    user_id = owners.get(request_id)
    # -----------------------------

    if not user_id:
        await callback.answer("⚠️ Не вдалося знайти заявника. Можливо, бот перезапускався.", show_alert=True)
        return

    try:
        current_text = callback.message.html_text
    except AttributeError:
        await callback.answer("⚠️ Помилка при отриманні тексту.", show_alert=True)
        return

    jurist_info = f"<b>🧑‍⚖️ Юрист:</b> {callback.from_user.full_name} (@{callback.from_user.username})" if callback.from_user.username else f"<b>🧑‍⚖️ Юрист:</b> {callback.from_user.full_name}"
    
    # Убираем старый статус и юриста, если он был
    lines = [line for line in current_text.split('\n') if not line.startswith('<b>Статус:') and not line.startswith('<b>🧑‍⚖️ Юрист:')]
    new_text_content = '\n'.join(lines)
    
    new_text = new_text_content + f"\n\n<b>Статус:</b> ✅ <b>Прийнято в роботу</b>\n{jurist_info}"

    await bot.edit_message_text(
        chat_id=LAWYERS_GROUP_ID,
        message_id=request_id,
        text=new_text,
        parse_mode=ParseMode.HTML,
        reply_markup=None # Убираем кнопку
    )
    await callback.answer("✅ Заявку прийнято! Вона одразу відправлена в архів.")

    # Уведомление заявителя
    await bot.send_message(
        chat_id=user_id,
        text=f"<b>🎉 Ваша заявка №{request_id} прийнята в роботу!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )

    # Отправка в архив
    await bot.send_message(
        chat_id=ARCHIVE_GROUP_ID,
        text=new_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# --- Эхо и рестарт ---
@dp.message(StateFilter(None))
async def echo_handler(message: types.Message):
    await message.answer("Щоб подати нову заявку, натисніть /start", reply_markup=get_restart_kb())

@dp.callback_query(F.data == "start_again", StateFilter(None))
async def handle_start_again(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await command_start_handler(callback.message, state)
    try:
        await callback.message.delete_reply_markup()
    except Exception:
        pass

# --- ЗАПУСК ---
async def main():
    try:
        bot_info = await bot.get_me()
        logging.info(f"✅ Бот успешно подключен! @{bot_info.username}")
    except Exception as e:
        logging.critical(f"❌ Не вдалося отримати інформацію про бота. Перевірте токен. Помилка: {e}")
        return
    
    logging.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинений.")
