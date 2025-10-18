# Импорт необходимых библиотек
import os
import asyncio
import re # Импорт для работы с регулярными выражениями и экранированием
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from keep_alive import keep_alive # Импорт веб-сервера для Replit/Render
import logging

# Конфигурация логирования
logging.basicConfig(level=logging.INFO)

# --- УТИЛИТЫ ---

def escape_markdown_v2(text: str) -> str:
    """
    Экранирует специальные символы MarkdownV2 в тексте,
    чтобы избежать ошибок 'TelegramBadRequest: can't parse entities'.
    """
    # Список специальных символов в MarkdownV2, которые нужно экранировать
    # Используем re.sub для замены всех вхождений
    special_chars = r'([_*\\[\]()~`>#+\-=|{}.!])'
    return re.sub(special_chars, r'\\\1', text)

# --- КОНСТАНТЫ И НАСТРОЙКИ ---

# ВНИМАНИЕ: Замените эти заглушки на реальные ID ваших групп!
# ID группы, куда будут отправляться новые заявки (Должен быть числовым)
LAWYERS_GROUP_ID = -1002929346188  # Пример: -100XXXXXXXXXX
# ID группы для архива
ARCHIVE_GROUP_ID = -1003171406428   # Пример: -100YYYYYYYYYY

# Токен берется из переменных окружения Replit Secrets
API_TOKEN = os.getenv("API_TOKEN")

# Словник категорій з перекладом (УКР)
CATEGORIES_UK = {
    "Сімейне право": "Сімейне право",
    "Кримінальні справи": "Кримінальні справи", 
    "Нерухомість": "Нерухомість",
    "УБД": "УБД",
    "ТЦК": "ТЦК",
    "ДТП": "ДТП",
    "Адміністативні справи": "Адміністативні справи",
    "Написання заяв та позовів до суду": "Написання заяв та позовів до суду",
    "Інше": "Інше"
}

# --- FSM (Finite State Machine) ---
class Form(StatesGroup):
    """Классы состояний для конечного автомата"""
    waiting_for_name = State()
    waiting_for_contact = State()
    waiting_for_category = State()
    waiting_for_description = State()

# --- ФУНКЦИИ СОЗДАНИЯ КЛАВИАТУР ---

def get_category_kb():
    """Создает клавиатуру для выбора категории"""
    kb = []
    category_list = list(CATEGORIES_UK.keys())
    # Формируем кнопки по 2 в ряд
    for i in range(0, len(category_list), 2):
        row = [KeyboardButton(text=category_list[i])]
        if i + 1 < len(category_list):
            row.append(KeyboardButton(text=category_list[i+1]))
        kb.append(row)

    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_contact_kb():
    """Создает клавиатуру для отправки контакта (ИСПРАВЛЕНО BASEMODEL)"""
    # ИСПРАВЛЕНО: используем именованный аргумент text=
    contact_btn = KeyboardButton(text="📱 Надіслати свій номер", request_contact=True)
    manual_btn = KeyboardButton(text="✍️ Ввести вручну")
    kb = ReplyKeyboardMarkup(
        keyboard=[[contact_btn], [manual_btn]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb

def get_restart_kb():
    """Создает инлайн-кнопку для начала новой заявки (ИСПРАВЛЕНО BASEMODEL)"""
    # ИСПРАВЛЕНО: используем именованный аргумент text=
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Розпочати нову заявку", callback_data="start_new_ticket")]
    ])

# Инициализация диспетчера до обработчиков
dp = Dispatcher()
# Глобальная переменная для бота
bot = None 

# --- ОБРАБОТЧИКИ КОМАНД И СОСТОЯНИЙ ---

@dp.message(CommandStart())
@dp.callback_query(F.data == "start_new_ticket")
async def command_start_handler(callback_or_message: types.CallbackQuery | types.Message, state: FSMContext):
    """
    Обработчик команды /start и нажатия кнопки "Розпочати нову заявку".
    """
    await state.clear()
    
    if isinstance(callback_or_message, types.Message):
        message = callback_or_message
        await message.answer(
            "👋 Вітаємо! Я ваш помічник у створенні юридичної заявки. Будь ласка, вкажіть ваше ім'я та прізвище:",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        callback = callback_or_message
        message = callback.message
        await callback.answer()
        
        # Пытаемся удалить предыдущее сообщение, чтобы не засорять чат
        try:
            await message.delete()
        except Exception:
            # Игнорируем ошибку, если сообщение уже удалено или слишком старое
            pass 
            
        await message.answer(
            "👋 Вітаємо! Я ваш помічник у створенні юридичної заявки. Будь ласка, вкажіть ваше ім'я та прізвище:",
            reply_markup=types.ReplyKeyboardRemove()
        )

    await state.set_state(Form.waiting_for_name)


@dp.message(StateFilter(Form.waiting_for_name), F.text)
async def process_name(message: types.Message, state: FSMContext):
    """Обрабатывает введенное имя и запрашивает контакт."""
    user_name = message.text.strip()
    await state.update_data(name=user_name)
    await state.set_state(Form.waiting_for_contact)
    
    # Экранируем имя только для отображения в текущем ответе
    safe_name = escape_markdown_v2(user_name) 
    
    await message.answer(
        f"✅ Дякую, *{safe_name}*\! Тепер вкажіть контакт для зв'язку\.",
        reply_markup=get_contact_kb(),
        parse_mode=ParseMode.MARKDOWN_V2 # Указываем явно, что используем MarkdownV2
    )

# --- ОБРАБОТЧИКИ КОНТАКТОВ ---

@dp.message(StateFilter(Form.waiting_for_contact), F.contact)
async def process_contact(message: types.Message, state: FSMContext):
    """Обрабатывает контакт, полученный через кнопку 'Надіслати свій номер'."""
    contact = message.contact.phone_number
    await state.update_data(contact=contact)
    await state.set_state(Form.waiting_for_category)
    await message.answer(
        "📞 Ваш контакт збережено\. Тепер оберіть категорію вашого питання\:",
        reply_markup=get_category_kb(),
        parse_mode=ParseMode.MARKDOWN_V2
    )

@dp.message(StateFilter(Form.waiting_for_contact), F.text == "✍️ Ввести вручну")
async def process_contact_manual_start(message: types.Message, state: FSMContext):
    """Запрашивает ручной ввод контакта."""
    await message.answer(
        "Будь ласка, введіть ваш номер телефону або інший контакт \(наприклад, Email\/Telegram username\)\:",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN_V2
    )

@dp.message(StateFilter(Form.waiting_for_contact), F.text)
async def process_contact_manual(message: types.Message, state: FSMContext):
    """Обрабатывает контакт, введенный вручную."""
    contact = message.text.strip()
    
    if contact == "✍️ Ввести вручну":
        return
        
    await state.update_data(contact=contact)
    await state.set_state(Form.waiting_for_category)
    await message.answer(
        "📞 Ваш контакт збережено\. Тепер оберіть категорію вашого питання\:",
        reply_markup=get_category_kb(),
        parse_mode=ParseMode.MARKDOWN_V2
    )

# --- ОБРАБОТЧИКИ КАТЕГОРИЙ И ОПИСАНИЙ ---

@dp.message(StateFilter(Form.waiting_for_category), F.text.in_(CATEGORIES_UK.keys()))
async def process_category(message: types.Message, state: FSMContext):
    """Обрабатывает выбранную категорию и запрашивает описание."""
    category = message.text
    await state.update_data(category=category)
    await state.set_state(Form.waiting_for_description)
    
    # Экранируем название категории только для отображения в текущем ответе
    safe_category = escape_markdown_v2(category)
    
    await message.answer(
        f"🛠 Ви обрали категорію \*{safe_category}\*\. Тепер детально опишіть вашу проблему\. Будь ласка, вкажіть усі ключові деталі\:",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN_V2
    )

@dp.message(StateFilter(Form.waiting_for_description), F.text)
async def process_description(message: types.Message, state: FSMContext):
    """Обрабатывает описание, формирует заявку и завершает FSM."""
    description = message.text.strip()
    data = await state.get_data()
    
    # 1. Формируем текст заявки с ОБЯЗАТЕЛЬНЫМ экранированием всех полей, 
    # введенных пользователем. (ИСПРАВЛЕНИЕ BAD REQUEST)
    
    escaped_name = escape_markdown_v2(data.get('name', 'N/A'))
    escaped_contact = escape_markdown_v2(data.get('contact', 'N/A'))
    escaped_category = escape_markdown_v2(data.get('category', 'N/A'))
    escaped_description = escape_markdown_v2(description)
    
    user_info = (
        f"🧑 Користувач: {escaped_name}\n"
        f"📞 Контакт: {escaped_contact}\n"
        f"🏷 Категорія: {escaped_category}\n"
        f"🆔 ID користувача: `{message.from_user.id}`\n"
    )
    
    # Добавление ссылки на пользователя (ID не нужно экранировать)
    username = message.from_user.username
    if username:
        # Экранируем только сам username, если он используется в тексте
        escaped_username = escape_markdown_v2(username)
        user_info += f"🔗 Посилання: [\@{escaped_username}](tg://user?id={message.from_user.id})"
    else:
        # Если username нет, используем ID
        user_info += f"🔗 Посилання: [Користувач](tg://user?id={message.from_user.id})"

    # Заголовок и описание
    ticket_text = (
        f"\*🚨 НОВА ЗАЯВКА \- {escaped_category\.upper()} 🚨\*\n\n"
        f"{user_info}\n\n"
        f"\*📝 ОПИС ПРОБЛЕМИ:\*\n{escaped_description}"
    )
    
    ticket_id = "N/A" # Инициализируем ticket_id
    
    # 2. Отправляем заявку в группу юристов
    try:
        sent_message = await bot.send_message(
            LAWYERS_GROUP_ID,
            ticket_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        ticket_id = sent_message.message_id
        await state.update_data(ticket_id=ticket_id)
        
        # 3. Отправляем подтверждение пользователю
        await message.answer(
            "\*🎉 Ваша заявка успішно надіслана\!\*\n\n"
            "Наші спеціалісти вже її обробляють\. Очікуйте відповіді найближчим часом\.",
            reply_markup=get_restart_kb(),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logging.error(f"Помилка відправки заявки до групи юристів: {e}")
        await message.answer(
            "❌ Виникла помилка при відправці заявки\. Спробуйте пізніше або зв'яжіться з нами\.",
            reply_markup=get_restart_kb(),
            parse_mode=ParseMode.MARKDOWN_V2
        )

    # 4. Сохраняем заявку в архив
    try:
        if ticket_id != "N/A":
             await bot.send_message(
                ARCHIVE_GROUP_ID,
                f"АРХІВ ЗАЯВКИ \#{ticket_id}\n{ticket_text}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except Exception as e:
        logging.error(f"Помилка відправки в архів: {e}")

    # 5. Завершаем FSM
    await state.clear()


@dp.message(StateFilter(None))
async def echo_handler(message: types.Message):
    """
    Обрабатывает сообщения вне FSM-состояний.
    """
    await message.answer(
        "Будь ласка, скористайтеся командою \/start, щоб почати нову заявку\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )

# --- ЗАПУСК БОТА ---
async def main():
    if not API_TOKEN:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: API_TOKEN не найден в переменных окружения. Убедитесь, что он добавлен в Replit Secrets.")
        return

    # ИСПРАВЛЕНИЕ ПРЕДУПРЕЖДЕНИЯ: Используем DefaultBotProperties для установки parse_mode
    default_properties = DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2)

    # Инициализация бота
    global bot
    bot = Bot(token=API_TOKEN, default=default_properties)
    
    # 1. Запуск веб-сервера Flask для Replit
    keep_alive()

    # 2. Проверка токена и имени бота
    try:
        me = await bot.get_me()
        print(f"✅ Бот успешно подключен! Имя: @{me.username}. Начинаем опрос сервера...")
    except Exception as e:
        print(f"❌ Ошибка подключения бота (токен неверный?): {e}")
        return

    # 3. Запуск основного цикла бота
    try:
        # Удаляем старые вебхуки (если были)
        await bot.delete_webhook(drop_pending_updates=True)
        # Начинаем опрос сервера
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Критическая ошибка при запуске polling: {e}")

if __name__ == '__main__':
    # Запускаем асинхронную функцию main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка при запуске main(): {e}")
