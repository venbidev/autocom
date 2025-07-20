from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import os
import random
import sys
import logging
import traceback
from sqlalchemy import text

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_log.txt"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Добавляем родительскую директорию в путь для правильного импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from datetime import datetime, timedelta
from database.db import Session
from database.models import User, Campaign, UserBot
from sqlalchemy import and_, or_, not_, func
import io
import re
import tempfile

# Добавляем родительскую директорию в путь, чтобы можно было импортировать модули
from userbot_manager import update_bot_profile, check_channel_admin, add_channel_to_profile, check_userbot_availability

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Создание FSM хранилища и диспетчера
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Создаем основную клавиатуру
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мои кампании")],
            [KeyboardButton(text="Аккаунт"), KeyboardButton(text="Поддержка")]
        ],
        resize_keyboard=True,
        persistent=True
    )
    return keyboard

# Создаем клавиатуру с категориями для таргета
def get_target_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Технологии"), KeyboardButton(text="Еда")],
            [KeyboardButton(text="Мода"), KeyboardButton(text="Спорт")],
            [KeyboardButton(text="Путешествия"), KeyboardButton(text="Образование")],
            [KeyboardButton(text="Финансы"), KeyboardButton(text="Развлечения")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

# Создаем инлайн-клавиатуру для подтверждения действий
def get_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подтвердить ✅", callback_data="confirm"),
                InlineKeyboardButton(text="Отмена ❌", callback_data="cancel")
            ]
        ]
    )
    return keyboard

# Состояния для создания кампании
class CampaignStates(StatesGroup):
    # Начальное состояние
    waiting_for_payment = State()
    # Процесс создания
    waiting_for_name = State()
    waiting_for_target = State()
    waiting_for_bot_name = State()
    waiting_for_bot_avatar = State()
    waiting_for_bot_description = State()
    waiting_for_channel_username = State()  # Новое состояние для ввода username
    waiting_for_channel_confirmation = State()
    # Финальное подтверждение
    waiting_for_final_confirmation = State()

# Функция для регистрации пользователя
async def register_user(user_id: int, username: str = None) -> User:
    session = Session()
    try:
        # Проверяем, существует ли уже пользователь
        user = session.query(User).filter(User.telegram_id == user_id).first()
        
        if not user:
            # Создаем нового пользователя
            user = User(
                telegram_id=user_id,
                username=username,
                balance=0.0
            )
            session.add(user)
            session.commit()
            logger.info(f"Новый пользователь зарегистрирован: {user_id}, {username}")
        
        # Копируем нужные атрибуты вместо возврата самого объекта
        user_data = {
            'telegram_id': user.telegram_id,
            'username': user.username,
            'balance': user.balance,
            'id': user.id
        }
        
        return user_data
    except Exception as e:
        logger.error(f"Ошибка при регистрации пользователя: {e}")
        session.rollback()
        return None
        session.close()

# Вспомогательная функция для получения баланса пользователя
async def get_user_balance(user_id: int) -> float:
    session = Session()
    try:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            return user.balance
        return 0.0
    except Exception as e:
        logger.error(f"Ошибка при получении баланса пользователя: {e}")
        return 0.0
    finally:
        session.close()

# Функция для добавления баланса (для тестирования)
async def add_balance(user_id: int, amount: float) -> bool:
    session = Session()
    try:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            user.balance += amount
            session.commit()
            return True
        return Falseкрутой0гурец
    
    except Exception as e:
        print(f"Ошибка при пополнении баланса: {e}")
        session.rollback()
        return False
    finally:
        session.close()

# Функция для поиска свободного юзербота
async def get_free_userbot():
    session = Session()
    try:
        free_userbot = session.query(UserBot).filter(UserBot.isoccupied == False).order_by(func.random()).first()
        return free_userbot
    except Exception as e:
        print(f"Ошибка при поиске свободного юзербота: {e}")
        return None
    finally:
        session.close()

# Функция для обновления статуса юзербота
async def update_userbot_status(bot_id: int, is_occupied: bool, new_name: str = None):
    session = Session()
    try:
        userbot = session.query(UserBot).filter(UserBot.id == bot_id).first()
        if userbot:
            userbot.isoccupied = is_occupied
            if new_name:
                # Обновляем display_name вместо session_name
                userbot.display_name = new_name
            session.commit()
            return True
        return False
    except Exception as e:
        print(f"Ошибка при обновлении статуса юзербота: {e}")
        session.rollback()
        return False
    finally:
        session.close()

@dp.message(CommandStart())
async def start_cmd(message: Message):
    # Регистрируем пользователя или получаем существующего
    user_data = await register_user(
        user_id=message.from_user.id,
        username=message.from_user.username
    )
    
    welcome_text = (
        f"Привет, {message.from_user.first_name}! Это бот для продвижения твоего канала в Telegram.\n"
        f"Я умею писать комментарии к постам, которые будут привлекать внимание к твоему каналу.)\n\n"
    )
    
    if user_data:
        welcome_text += f"Ваш баланс: {user_data['balance']} руб.\n"
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

# Команда для создания новой кампании
@dp.message(Command("new_campaign"))
async def new_campaign_cmd(message: Message, state: FSMContext):
    # Получаем доступный (свободный) юзербот
    free_userbot = await get_free_userbot()
    
    if not free_userbot:
        await message.answer("К сожалению, сейчас нет доступных ботов для создания новой кампании. Попробуйте позже.")
        return
    
    # Сохраняем информацию о выбранном юзерботе
    await state.update_data(userbot_id=free_userbot.id, userbot_username=free_userbot.session_name)
    
    # Стоимость недельной подписки
    campaign_cost = 10.0
    
    # Получаем данные текущего пользователя
    session = Session()
    user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
    
    payment_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Оплатить 10₽", callback_data="pay_campaign")]
        ]
    )
    
    if user and user.balance >= campaign_cost:
        # У пользователя достаточно денег на балансе
        await message.answer(
            f"Для создания кампании на неделю требуется оплата 10₽.\n"
            f"На вашем балансе: {user.balance}₽\n\n"
            f"Нажмите кнопку ниже для оплаты:",
            reply_markup=payment_keyboard
        )
    else:
        # Недостаточно средств
        balance = user.balance if user else 0
        await message.answer(
            f"Для создания кампании на неделю требуется 10₽.\n"
            f"На вашем балансе: {balance}₽\n"
            f"Пополните баланс и попробуйте снова.\n\n"
            f"(Для демонстрации нажмите кнопку ниже, чтобы добавить 10₽ на ваш счет)",
            reply_markup=payment_keyboard
        )
    
    session.close()
    await state.set_state(CampaignStates.waiting_for_payment)

# Обработка оплаты кампании
@dp.callback_query(F.data == "pay_campaign", CampaignStates.waiting_for_payment)
async def process_payment(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    campaign_cost = 10.0
    
    # Получаем данные пользователя
    session = Session()
    user = session.query(User).filter(User.telegram_id == user_id).first()
    
    if not user:
        await callback.message.answer("Произошла ошибка при обработке платежа. Пользователь не найден.")
        await callback.answer()
        await state.clear()
        return
    
    # Проверяем баланс
    if user.balance < campaign_cost:
        # Демо-режим: пополняем баланс
        await add_balance(user_id, campaign_cost)
        user = session.query(User).filter(User.telegram_id == user_id).first()
        await callback.message.answer(f"Баланс пополнен на {campaign_cost}₽ (демо-режим)")
    
    # Списываем средства
    user.balance -= campaign_cost
    session.commit()
    
    # Устанавливаем дату окончания кампании (неделя)
    paid_until = datetime.now() + timedelta(days=7)
    await state.update_data(paid_until=paid_until)
    
    # Обновляем юзербот как занятый
    data = await state.get_data()
    userbot_id = data.get("userbot_id")
    await update_userbot_status(userbot_id, True)
    
    # Переходим к следующему шагу
    await callback.message.answer("Оплата прошла успешно! Теперь давайте настроим вашу кампанию.")
    await callback.message.answer("Введите название вашей кампании (оно будет видно только вам):")
    
    session.close()
    await callback.answer()
    await state.set_state(CampaignStates.waiting_for_name)

# Обработка ввода названия кампании
@dp.message(CampaignStates.waiting_for_name)
async def process_campaign_name(message: Message, state: FSMContext):
    # Сохраняем название кампании
    await state.update_data(campaign_name=message.text)
    
    # Просим выбрать категорию
    await message.answer(
        "Выберите категорию, на которую будет ориентирован ваш бот:",
        reply_markup=get_target_keyboard()
    )
    
    await state.set_state(CampaignStates.waiting_for_target)

# Обработка выбора категории
@dp.message(CampaignStates.waiting_for_target)
async def process_campaign_target(message: Message, state: FSMContext):
    valid_targets = ["Технологии", "Еда", "Мода", "Спорт", "Путешествия", "Образование", "Финансы", "Развлечения"]
    
    if message.text not in valid_targets:
        await message.answer(
            "Пожалуйста, выберите категорию из предложенных вариантов:",
            reply_markup=get_target_keyboard()
        )
        return
    
    # Сохраняем целевую категорию
    await state.update_data(target=message.text)
    
    # Переходим к настройке профиля бота
    await message.answer(
        "Теперь настроим профиль бота, который будет комментировать посты.\n\n"
        "Введите имя для бота (будет отображаться в его профиле):",
        reply_markup=types.ReplyKeyboardRemove()
    )
    
    await state.set_state(CampaignStates.waiting_for_bot_name)

# Обработка ввода имени бота
@dp.message(CampaignStates.waiting_for_bot_name)
async def process_bot_name(message: Message, state: FSMContext):
    bot_name = message.text.strip()
    
    # Проверяем длину имени
    if len(bot_name) < 3 or len(bot_name) > 30:
        await message.answer(
            "Имя бота должно содержать от 3 до 30 символов. Пожалуйста, введите другое имя:"
        )
        return
    
    # Получаем ID юзербота из состояния
    data = await state.get_data()
    userbot_id = data["userbot_id"]
    
    # Сохраняем имя бота
    await state.update_data(bot_name=bot_name)
    
    # Проверяем доступность юзербота
    is_available = await check_userbot_availability(userbot_id)
    if not is_available:
        await message.answer(
            "Произошла ошибка при подключении к боту. Пожалуйста, попробуйте позже или выберите другого бота.",
            reply_markup=get_main_keyboard()
        )
        # Освобождаем юзербота
        await update_userbot_status(userbot_id, False)
        # Возвращаем к начальному состоянию
        await state.clear()
        return
    
    # Изменяем имя юзербота через Telethon API
    success = await update_bot_profile(userbot_id, first_name=bot_name)
    if not success:
        await message.answer(
            "Произошла ошибка при изменении имени бота. Пожалуйста, попробуйте другое имя:"
        )
        return
    
    # Обновляем имя бота в базе данных
    await update_userbot_status(userbot_id, True, bot_name)
    
    # Переходим к загрузке аватара
    await message.answer(
        "Отлично! Теперь отправьте фотографию для аватара бота:"
    )
    
    await state.set_state(CampaignStates.waiting_for_bot_avatar)

# Обработка загрузки аватарки
@dp.message(F.photo, CampaignStates.waiting_for_bot_avatar)
async def process_bot_avatar(message: Message, state: FSMContext):
    data = await state.get_data()
    userbot_id = data["userbot_id"]
    
    # Скачиваем фотографию во временный файл
    photo = message.photo[-1]  # Берем самое большое разрешение
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
        await bot.download(photo.file_id, destination=temp_file.name)
        temp_path = temp_file.name
    
    try:
        # Применяем аватарку к юзерботу через Telethon API
        success = await update_bot_profile(userbot_id, photo_path=temp_path)
        
        if success:
            await message.answer(
                "Аватар успешно установлен! Теперь введите описание профиля бота (без ссылок):"
            )
            await state.set_state(CampaignStates.waiting_for_bot_description)
        else:
            await message.answer(
                "Произошла ошибка при установке аватара. Пожалуйста, попробуйте другое изображение:"
            )
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.unlink(temp_path)

# Обработка неправильного формата аватарки
@dp.message(CampaignStates.waiting_for_bot_avatar)
async def wrong_avatar_format(message: Message):
    await message.answer("Пожалуйста, отправьте фотографию для аватара бота.")

# Обработка ввода описания бота
@dp.message(CampaignStates.waiting_for_bot_description)
async def process_bot_description(message: Message, state: FSMContext):
    description = message.text.strip()
    
    # Проверяем наличие ссылок
    if re.search(r'(https?://|www\.|\bt\.me/)', description, re.IGNORECASE):
        await message.answer(
            "В описании не должно быть ссылок. Пожалуйста, введите другое описание:"
        )
        return
    
    # Проверяем длину описания
    if len(description) > 70:
        await message.answer(
            "Описание слишком длинное (максимум 70 символов). Пожалуйста, сократите текст:"
        )
        return
    
    # Сохраняем описание
    await state.update_data(bot_description=description)
    
    # Получаем данные о юзерботе
    data = await state.get_data()
    userbot_id = data["userbot_id"]
    
    # Обновляем описание юзербота через Telethon API
    success = await update_bot_profile(userbot_id, bio=description)
    
    if not success:
        await message.answer(
            "Произошла ошибка при обновлении описания бота. Пожалуйста, попробуйте другое описание:"
        )
        return
    
    # Получаем актуальную информацию о боте из БД
    session = Session()
    userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
    session.close()
    
    # Запрашиваем добавление бота в канал
    await message.answer(
        f"Отлично! Теперь вам нужно:\n\n"
        f"1. Создать новый канал в Telegram\n"
        f"2. Добавить в описание канала ссылку на ваш основной канал\n"
        f"3. Добавить нашего бота @{userbot.session_name} как администратора канала\n\n"
        f"После этого введите @username вашего нового канала и нажмите кнопку 'Подтвердить':"
    )
    
    # Создаем клавиатуру для ввода канала
    channel_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Я добавил бота как администратора", callback_data="check_admin")
            ],
            [
                InlineKeyboardButton(text="Отмена", callback_data="cancel")
            ]
        ]
    )
    
    await message.answer("Когда добавите бота как администратора, нажмите кнопку:", reply_markup=channel_keyboard)
    await state.set_state(CampaignStates.waiting_for_channel_confirmation)

# Обработка подтверждения добавления бота в канал
@dp.callback_query(F.data == "confirm", CampaignStates.waiting_for_channel_confirmation)
async def confirm_channel_setup(callback: CallbackQuery, state: FSMContext):
    # Для демонстрации просто считаем, что пользователь всё сделал правильно
    # В реальном проекте здесь должна быть проверка через API
    
    # Получаем все данные из состояния
    data = await state.get_data()
    
    # Формируем итоговое сообщение с подтверждением
    confirmation_text = (
        "📋 Проверьте данные вашей кампании:\n\n"
        f"📌 Название: {data['campaign_name']}\n"
        f"🎯 Категория: {data['target']}\n"
        f"🤖 Имя бота: {data['bot_name']}\n"
        f"📝 Описание бота: {data['bot_description']}\n"
        f"📅 Оплачено до: {data['paid_until'].strftime('%d.%m.%Y')}\n\n"
        "Всё верно? Нажмите 'Подтвердить' для запуска кампании."
    )
    
    await callback.message.answer(confirmation_text, reply_markup=get_confirmation_keyboard())
    await callback.answer()
    await state.set_state(CampaignStates.waiting_for_final_confirmation)

# Обработка отмены на этапе добавления бота в канал
@dp.callback_query(F.data == "cancel", CampaignStates.waiting_for_channel_confirmation)
async def cancel_channel_setup(callback: CallbackQuery, state: FSMContext):
    # Освобождаем юзербота
    data = await state.get_data()
    await update_userbot_status(data["userbot_id"], False)
    
    await callback.message.answer(
        "Создание кампании отменено. Ваши средства будут возвращены на баланс.",
        reply_markup=get_main_keyboard()
    )
    
    # Возвращаем деньги на баланс
    await add_balance(callback.from_user.id, 10.0)
    
    await callback.answer()
    await state.clear()

# Финальное подтверждение и создание кампании
@dp.callback_query(F.data == "confirm", CampaignStates.waiting_for_final_confirmation)
async def create_campaign(callback: CallbackQuery, state: FSMContext):
    # Получаем все данные из состояния
    data = await state.get_data()
    
    # Создаем запись в БД
    session = Session()
    try:
        new_campaign = Campaign(
            creator_id=callback.from_user.id,
            name=data["campaign_name"],
            bot_id=data["userbot_id"],
            paid_until=data["paid_until"],
            target=data["target"]
        )
        
        session.add(new_campaign)
        session.commit()
        
        await callback.message.answer(
            "🎉 Отлично! Ваша кампания успешно создана и запущена!\n"
            "Бот начнет комментировать посты в соответствии с выбранной категорией.\n\n"
            "Вы можете просмотреть свои кампании, нажав на кнопку 'Мои кампании'.",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        print(f"Ошибка при создании кампании: {e}")
        session.rollback()
        
        # Освобождаем юзербота
        await update_userbot_status(data["userbot_id"], False)
        
        await callback.message.answer(
            "Произошла ошибка при создании кампании. Ваши средства будут возвращены на баланс.",
            reply_markup=get_main_keyboard()
        )
        
        # Возвращаем деньги на баланс
        await add_balance(callback.from_user.id, 10.0)
    finally:
        session.close()
    
    await callback.answer()
    await state.clear()

# Отмена на последнем этапе
@dp.callback_query(F.data == "cancel", CampaignStates.waiting_for_final_confirmation)
async def cancel_final_confirmation(callback: CallbackQuery, state: FSMContext):
    # Освобождаем юзербота
    data = await state.get_data()
    await update_userbot_status(data["userbot_id"], False)
    
    await callback.message.answer(
        "Создание кампании отменено. Ваши средства будут возвращены на баланс.",
        reply_markup=get_main_keyboard()
    )
    
    # Возвращаем деньги на баланс
    await add_balance(callback.from_user.id, 10.0)
    
    await callback.answer()
    await state.clear()

# Обработчики для кнопок клавиатуры
@dp.message(lambda message: message.text == "Мои кампании")
async def show_my_campaigns(message: Message):
    # Получаем информацию о кампаниях пользователя из БД
    session = Session()
    try:
        campaigns = session.query(Campaign).filter(
            Campaign.creator_id == message.from_user.id
        ).all()
        
        if not campaigns:
            await message.answer(
                "У вас пока нет активных кампаний. Чтобы создать кампанию, напишите /new_campaign",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Формируем текст с информацией о кампаниях
        campaigns_text = "Ваши кампании:\n\n"
        
        for i, campaign in enumerate(campaigns, start=1):
            # Получаем информацию о боте для этой кампании
            bot = session.query(UserBot).filter(UserBot.id == campaign.bot_id).first()
            bot_name = bot.session_name if bot else "Неизвестный бот"
            
            # Форматируем дату окончания оплаты
            paid_until_str = campaign.paid_until.strftime("%d.%m.%Y") if campaign.paid_until else "Не оплачено"
            
            campaigns_text += (
                f"{i}. {campaign.name}\n"
                f"   Бот: {bot_name}\n"
                f"   Цель: {campaign.target}\n"
                f"   Оплачено до: {paid_until_str}\n\n"
            )
        
        campaigns_text += "Для управления кампанией, напишите /campaign_{id}, где {id} - номер кампании."
        
        await message.answer(campaigns_text, reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"Ошибка при получении кампаний: {e}")
        await message.answer(
            "Произошла ошибка при получении списка кампаний",
            reply_markup=get_main_keyboard()
        )
    finally:
        session.close()

# Добавляем состояние для ввода username канала
@dp.callback_query(F.data == "check_admin", CampaignStates.waiting_for_channel_confirmation)
async def request_channel_username(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите @username вашего канала (например, @mychannel):")
    await state.set_state(CampaignStates.waiting_for_channel_username)
    await callback.answer()

# Обработчик для проверки статуса администратора в канале после ввода username
@dp.message(CampaignStates.waiting_for_channel_username)
async def check_admin_status(message: Message, state: FSMContext):
    channel_username = message.text.strip()
    
    # Проверяем формат username
    if not channel_username.startswith('@'):
        await message.answer("Username канала должен начинаться с @. Пожалуйста, введите корректный username:")
        return
    
    # Убираем @ для внутренней обработки
    pure_username = channel_username[1:]
    
    # Сохраняем username канала
    await state.update_data(channel_username=channel_username)
    
    # Получаем данные о юзерботе
    data = await state.get_data()
    userbot_id = data["userbot_id"]
    
    # Проверяем, является ли юзербот администратором канала через Telethon API
    is_admin = await check_channel_admin(userbot_id, pure_username)
    
    if not is_admin:
        await message.answer(
            f"Бот не найден в списке администраторов канала {channel_username}.\n"
            f"Пожалуйста, убедитесь, что вы добавили бота как администратора и повторите попытку:"
        )
        return
    
    # Если бот является администратором, добавляем канал в профиль бота
    success = await add_channel_to_profile(userbot_id, channel_username)
    
    if not success:
        await message.answer(
            "Произошла ошибка при добавлении канала в профиль бота. Пожалуйста, попробуйте снова."
        )
        return
    
    # Все проверки пройдены, переходим к подтверждению
    confirmation_text = (
        "📋 Проверьте данные вашей кампании:\n\n"
        f"📌 Название: {data['campaign_name']}\n"
        f"🎯 Категория: {data['target']}\n"
        f"🤖 Имя бота: {data['bot_name']}\n"
        f"📝 Описание бота: {data['bot_description']}\n"
        f"📢 Канал: {channel_username}\n"
        f"📅 Оплачено до: {data['paid_until'].strftime('%d.%m.%Y')}\n\n"
        "Всё верно? Нажмите 'Подтвердить' для запуска кампании."
    )
    
    await message.answer(confirmation_text, reply_markup=get_confirmation_keyboard())
    await state.set_state(CampaignStates.waiting_for_final_confirmation)

async def main():
    try:
        logger.info("Запуск бота...")
        # Проверяем токен бота
        if not BOT_TOKEN:
            logger.error("Ошибка: BOT_TOKEN не найден в переменных среды")
            return
        
        logger.info(f"Токен бота получен, первые 5 символов: {BOT_TOKEN[:5]}...")
        
        # Проверяем подключение к базе данных
        session = Session()
        try:
            result = session.execute(text("SELECT 1")).scalar()
            logger.info(f"Подключение к БД успешно: {result}")
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {e}")
            return
        finally:
            session.close()
            
        logger.info("Начинаю поллинг бота...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        logger.error(traceback.format_exc())