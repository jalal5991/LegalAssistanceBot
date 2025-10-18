# Импорт необходимых библиотек
import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from keep_alive import keep_alive # Импорт веб-сервера для Replit/Render
import logging

# Конфигурация логирования
logging.basicConfig(level=logging.INFO)

# --- КОНСТАНТЫ И НАСТРОЙКИ ---

# ВНИМАНИЕ: Замените эти заглушки на реальные ID ваших групп!
# ID группы, куда будут отправляться новые заявки (Должен быть числовым)
LAWYERS_GROUP_ID = -1002929346188  # Пример: -100XXXXXXXXXX
# ID группы для архива
ARCHIVE_GROUP_ID = -1003171406428   # Пример: -100YYYYYYYYYY

# Токен берется из переменных окружения Replit Secrets
API_TOKEN = os.getenv("API_TOKEN")

# Словник категорий з перекладом (УКР)
CATEGORIES_UK = {
    "Сімейне право": "Сімейне право",
    "Кримінальне право": "Кримінальне право",
    "Нерухомість": "Нерухомість",
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
    # Формируем кнопки из словаря категорий, по 2 кнопки в ряд
    category_list = list(CATEGORIES_UK.keys())
    for i in range(0, len(category_list), 2):
        row = [KeyboardButton(text=category_list[i])]
        if i + 1 < len(category_list):
            row.append(KeyboardButton(text=category_list[i+1]))
        kb.append(row)

    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_contact_kb():
    """Создает клавиатуру для отправки контакта"""
    # ИСПРАВЛЕНИЕ BASEMODEL: Используем именованный аргумент text=
    contact_btn = KeyboardButton(text="📱 Надіслати свій номер", request_contact=True)
    manual_btn = KeyboardButton(text="✍️ Ввести вручну")
    kb = ReplyKeyboardMarkup(
        keyboard=[[contact_btn], [manual_btn]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb

def get_restart_kb():
    """Создает инлайн-кнопку для начала новой заявки"""
    # ИСПРАВЛЕНИЕ BASEMODEL: Используем именованный аргумент text=
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Розпочати нову заявку", callback_data="start_new_ticket")]
    ])

# --- ОБРАБОТЧИКИ КОМАНД И СОСТОЯНИЙ ---

@dp.message(CommandStart())
@dp.callback_query(F.data == "start_new_ticket")
async def command_start_handler(callback_or_message: types.CallbackQuery | types.Message, state: FSMContext):
    """
    Обработчик команды /start и нажатия кнопки "Розпочати нову заявку".
    Запускает FSM и запрашивает имя.
    """
    # Определяем, что пришло: сообщение или колбэк
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
        await message.edit_text(
            "👋 Вітаємо! Я ваш помічник у створенні юридичної заявки. Будь ласка, вкажіть ваше ім'я та прізвище:",
            reply_markup=None # Удаляем инлайн-кнопку
        )

    # Устанавливаем первое состояние
    await state.set_state(Form.waiting_for_name)
    # Очищаем контекст, чтобы начать новую заявку
    await state.clear()

@dp.message(StateFilter(Form.waiting_for_name), F.text)
async def process_name(message: types.Message, state: FSMContext):
    """Обрабатывает введенное имя и запрашивает контакт."""
    user_name = message.text.strip()
    await state.update_data(name=user_name)
    await state.set_state(Form.waiting_for_contact)
    await message.answer(
        f"✅ Дякую, {user_name}! Тепер вкажіть контакт для зв'язку.",
        reply_markup=get_contact_kb()
    )

# --- ОБРАБОТЧИКИ КОНТАКТОВ ---

@dp.message(StateFilter(Form.waiting_for_contact), F.contact)
async def process_contact(message: types.Message, state: FSMContext):
    """Обрабатывает контакт, полученный через кнопку 'Надіслати свій номер'."""
    contact = message.contact.phone_number
    await state.update_data(contact=contact)
    await state.set_state(Form.waiting_for_category)
    await message.answer(
        "📞 Ваш контакт збережено. Тепер оберіть категорію вашого питання:",
        reply_markup=get_category_kb()
    )

@dp.message(StateFilter(Form.waiting_for_contact), F.text == "✍️ Ввести вручну")
async def process_contact_manual_start(message: types.Message, state: FSMContext):
    """Запрашивает ручной ввод контакта."""
    await message.answer(
        "Будь ласка, введіть ваш номер телефону або інший контакт (наприклад, Email/Telegram username):",
        reply_markup=types.ReplyKeyboardRemove()
    )
    # Состояние остается Form.waiting_for_contact, но мы ждем текст, а не контакт-объект

@dp.message(StateFilter(Form.waiting_for_contact), F.text)
async def process_contact_manual(message: types.Message, state: FSMContext):
    """Обрабатывает контакт, введенный вручную."""
    contact = message.text.strip()
    
    if contact == "✍️ Ввести вручну":
        # Если пользователь повторно нажал кнопку "Ввести вручну", игнорируем
        return
        
    await state.update_data(contact=contact)
    await state.set_state(Form.waiting_for_category)
    await message.answer(
        "📞 Ваш контакт збережено. Тепер оберіть категорію вашого питання:",
        reply_markup=get_category_kb()
    )

# --- ОБРАБОТЧИКИ КАТЕГОРИЙ И ОПИСАНИЙ ---

@dp.message(StateFilter(Form.waiting_for_category), F.text.in_(CATEGORIES_UK.keys()))
async def process_category(message: types.Message, state: FSMContext):
    """Обрабатывает выбранную категорию и запрашивает описание."""
    category = message.text
    await state.update_data(category=category)
    await state.set_state(Form.waiting_for_description)
    await message.answer(
        f"🛠 Ви обрали категорію **{category}**. Тепер детально опишіть вашу проблему. Будь ласка, вкажіть усі ключові деталі:",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(StateFilter(Form.waiting_for_description), F.text)
async def process_description(message: types.Message, state: FSMContext):
    """Обрабатывает описание, формирует заявку и завершает FSM."""
    description = message.text.strip()
    data = await state.get_data()
    
    # 1. Формируем текст заявки
    user_info = (
        f"🧑 Користувач: {data.get('name')}\n"
        f"📞 Контакт: {data.get('contact')}\n"
        f"🏷 Категорія: {data.get('category')}\n"
        f"🆔 ID користувача: `{message.from_user.id}`\n"
        f"🔗 Посилання: [@{message.from_user.username}](tg://user?id={message.from_user.id})"
    )
    ticket_text = (
        f"**🚨 НОВА ЗАЯВКА - {data.get('category').upper()} 🚨**\n\n"
        f"{user_info}\n\n"
        f"📝 **ОПИС ПРОБЛЕМИ:**\n{description}"
    )

    # 2. Отправляем заявку в группу юристов
    try:
        sent_message = await bot.send_message(
            LAWYERS_GROUP_ID,
            ticket_text,
            parse_mode=ParseMode.MARKDOWN
        )
        ticket_id = sent_message.message_id
        await state.update_data(ticket_id=ticket_id)
        
        # 3. Отправляем подтверждение пользователю
        await message.answer(
            "🎉 **Ваша заявка успішно надіслана!**\n\n"
            "Наші спеціалісти вже її обробляють. Очікуйте відповіді найближчим часом.",
            reply_markup=get_restart_kb(),
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logging.error(f"Помилка відправки заявки до групи юристів: {e}")
        await message.answer(
            "❌ Виникла помилка при відправці заявки. Спробуйте пізніше або зв'яжіться з нами.",
            reply_markup=get_restart_kb()
        )

    # 4. Сохраняем заявку в архив
    try:
        await bot.send_message(
            ARCHIVE_GROUP_ID,
            f"АРХІВ ЗАЯВКИ #{ticket_id}\n{ticket_text}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logging.error(f"Помилка відправки в архів: {e}")

    # 5. Завершаем FSM
    await state.clear()


@dp.message()
async def echo_handler(message: types.Message):
    """Ловит все сообщения вне FSM и отправляет пользователю команду начала."""
    # Проверяем, находится ли пользователь в каком-либо состоянии FSM
    state = await dp.fsm.storage.get_state(bot=bot, chat_id=message.chat.id, user_id=message.from_user.id)
    if state is None:
        await message.answer(
            "Будь ласка, скористайтеся командою /start, щоб почати нову заявку."
        )

# --- ЗАПУСК БОТА ---
async def main():
    # Проверка на наличие токена
    if not API_TOKEN:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: API_TOKEN не найден в переменных окружения. Убедитесь, что он добавлен в Replit Secrets.")
        return

    # Инициализация бота и диспетчера
    global bot, dp # Объявляем глобально для доступа в обработчиках
    bot = Bot(API_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Регистрация обработчиков (делаем это явно, чтобы избежать проблем)
    dp.message.register(command_start_handler, CommandStart())
    dp.callback_query.register(command_start_handler, F.data == "start_new_ticket")
    
    dp.message.register(process_name, StateFilter(Form.waiting_for_name), F.text)
    
    dp.message.register(process_contact, StateFilter(Form.waiting_for_contact), F.contact)
    dp.message.register(process_contact_manual_start, StateFilter(Form.waiting_for_contact), F.text == "✍️ Ввести вручну")
    dp.message.register(process_contact_manual, StateFilter(Form.waiting_for_contact), F.text)

    dp.message.register(process_category, StateFilter(Form.waiting_for_category), F.text.in_(CATEGORIES_UK.keys()))
    dp.message.register(process_description, StateFilter(Form.waiting_for_description), F.text)

    # Ловим все остальные сообщения
    dp.message.register(echo_handler)
    
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
