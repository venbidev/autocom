from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ContentType
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart
import asyncio
import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient
import boto3
from telethon.tl import types
import json

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now you can import the database module
from database.db import Session, engine
from database.models import UserBot

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN_ADMIN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# AWS S3 (Bucketeer) configuration
AWS_BUCKET_NAME = os.getenv("BUCKETEER_BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("BUCKETEER_AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("BUCKETEER_AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("BUCKETEER_REGION")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

@dp.message(CommandStart())
async def start_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Аккаунты")]],
        resize_keyboard=True
    )

    await message.answer("Привет! Что хочешь?", reply_markup=keyboard)

@dp.message(F.text == "Аккаунты")
async def handle_accounts_button(message: Message):
    print(f"Получено сообщение: {message.text}")
    if not is_admin(message.from_user.id):
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Управление аккаунтами")],
            [KeyboardButton(text="Статус")]
        ],
        resize_keyboard=True
    )

    await message.answer("Выберите действие:", reply_markup=keyboard)

@dp.message(F.text == "Управление аккаунтами")
async def handle_manage_accounts_button(message: Message):
    print(f"Получено сообщение: {message.text}")
    if not is_admin(message.from_user.id):
        return

    # Сначала отправим пустое сообщение для удаления предыдущей клавиатуры
    await message.answer("Обновляю клавиатуру...", reply_markup=ReplyKeyboardRemove())

    # Затем отправим новое сообщение с новой клавиатурой
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить")],
            [KeyboardButton(text="Удалить")]
        ],
        resize_keyboard=True
    )

    await message.answer("Выберите действие с аккаунтами:", reply_markup=keyboard)
    print("Клавиатура для управления аккаунтами отправлена.")

@dp.message(F.text == "Добавить")
async def handle_add_button(message: Message):
    print(f"Получено сообщение: {message.text}")
    if not is_admin(message.from_user.id):
        return

    await message.answer("Пожалуйста, отправьте файл сессии.")

@dp.message(F.content_type == ContentType.DOCUMENT)
async def handle_session_file(message: Message):
    print("Получен документ")
    if not is_admin(message.from_user.id):
        return

    document = message.document

    # Сохраняем файл локально
    local_path = f"adminbot/sessions/{document.file_name}"
    
    # Ensure the sessions directory exists
    os.makedirs("adminbot/sessions", exist_ok=True)
    
    # Fix: Use bot.download() instead of document.download()
    file = await bot.get_file(document.file_id)
    await bot.download_file(file.file_path, local_path)

    # Выполняем вход с помощью Telethon без использования api_id и api_hash
    client = TelegramClient(local_path, api_id=1, api_hash="1")

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await message.answer("Сессия недействительна. Пожалуйста, проверьте файл.")
            return

        # Получаем ID аккаунта
        me = await client.get_me()
        account_id = me.id
        
        # Попытка отправить сообщение администратору
        try:
            # Для отправки сообщения от имени юзербота администратору
            # нам нужно сначала получить информацию о пользователе
            # Используем getDialogs() для получения списка диалогов и поиска админа
            dialogs = await client.get_dialogs()
            
            # Попробуем найти пользователя с нужным ID в диалогах
            admin_found = False
            for dialog in dialogs:
                if dialog.entity.id == ADMIN_ID:
                    await client.send_message(dialog.entity, f"Привет! Успешный вход. Мой ID: {account_id}")
                    admin_found = True
                    break
            
            # Если админа нет в диалогах, попробуем найти его по ID
            if not admin_found:
                # Создаем сущность админа через API
                # Для этого сначала найдем пользователя по ID
                try:
                    # Пробуем получить информацию об админе
                    admin = await client.get_entity(ADMIN_ID)
                    await client.send_message(admin, f"Привет! Успешный вход. Мой ID: {account_id}")
                    admin_found = True
                except Exception as e:
                    print(f"Не удалось получить информацию об админе: {e}")
            
            # Если админа все равно не нашли, попробуем создать чат и отправить сообщение
            if not admin_found:
                # Создаем новый диалог с админом
                await client.send_message(ADMIN_ID, f"Привет! Успешный вход. Мой ID: {account_id}")
                
            await message.answer(f"Аккаунт успешно авторизован, ID: {account_id}. Отправлено тестовое сообщение.")
        except Exception as e:
            print(f"Ошибка при отправке сообщения админу: {str(e)}")
            await message.answer(f"Аккаунт успешно авторизован, ID: {account_id}, но не удалось отправить сообщение админу: {str(e)}")

    finally:
        await client.disconnect()

    # Загружаем файл в бакет на Heroku
    s3 = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    bucket_name = AWS_BUCKET_NAME
    s3_key = f"sessions/{document.file_name}"

    s3.upload_file(local_path, bucket_name, s3_key)
    heroku_url = f"https://{bucket_name}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

    # Сохраняем запись в базе данных
    session = Session(bind=engine)
    
    # Проверяем, есть ли уже аккаунт с таким же account_id
    existing_userbot = session.query(UserBot).filter(UserBot.account_id == account_id).first()
    
    if (existing_userbot):
        # Если аккаунт с таким ID уже существует, удаляем его
        session.delete(existing_userbot)
        session.commit()
        await message.answer(f"Аккаунт с ID {account_id} уже существовал в базе и был заменен на новый.")
    
    # Добавляем новый аккаунт
    new_userbot = UserBot(
        owner_id=message.from_user.id,
        account_id=account_id,
        session_name=heroku_url
    )
    session.add(new_userbot)
    session.commit()
    session.close()

    await message.answer(f"Файл сессии успешно добавлен, ID аккаунта: {account_id}. Успешно выполнен вход.")

@dp.message(F.text == "Статус")
async def handle_status_button(message: Message):
    print(f"Получено сообщение: {message.text}")
    if not is_admin(message.from_user.id):
        return

    # Получаем все записи из базы данных
    session = Session(bind=engine)
    userbots = session.query(UserBot).all()
    
    if not userbots:
        await message.answer("Нет добавленных аккаунтов.")
        session.close()
        return
    
    # Добавляем кнопку возврата
    keyboard_reply = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Аккаунты")]
        ],
        resize_keyboard=True
    )
    
    # Отправляем сообщение со списком аккаунтов
    await message.answer("📊 Статус аккаунтов:", reply_markup=keyboard_reply)
    
    # Для каждого аккаунта отправляем отдельное сообщение с инлайн кнопкой
    for i, userbot in enumerate(userbots, 1):
        account_info = f"{i}. ID аккаунта: {userbot.account_id}\n"
        account_info += f"   Добавлен: {userbot.created_at}\n"
        
        # Создаем инлайн клавиатуру с кнопкой проверки
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Проверить сессию", callback_data=f"check_session:{userbot.id}")]
        ])
        
        # Отправляем сообщение с инлайн-кнопкой
        await message.answer(account_info, reply_markup=inline_kb)
    
    session.close()

@dp.message(F.text == "Удалить")
async def handle_delete_button(message: Message):
    print(f"Получено сообщение: {message.text}")
    if not is_admin(message.from_user.id):
        return

    # Получаем все записи из базы данных
    session = Session(bind=engine)
    userbots = session.query(UserBot).all()
    
    if not userbots:
        # Если нет аккаунтов для удаления
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Аккаунты")]],
            resize_keyboard=True
        )
        await message.answer("Нет добавленных аккаунтов для удаления.", reply_markup=keyboard)
        session.close()
        return
    
    # Отправляем сообщение со списком аккаунтов для удаления
    await message.answer("Выберите аккаунт для удаления:", reply_markup=ReplyKeyboardRemove())
    
    # Для каждого аккаунта отправляем отдельное сообщение с инлайн кнопкой удаления
    for i, userbot in enumerate(userbots, 1):
        account_info = f"{i}. ID аккаунта: {userbot.account_id}\n"
        account_info += f"   Добавлен: {userbot.created_at}\n"
        
        # Создаем инлайн клавиатуру с кнопкой удаления
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить аккаунт", callback_data=f"delete_account:{userbot.id}")]
        ])
        
        # Отправляем сообщение с инлайн-кнопкой
        await message.answer(account_info, reply_markup=inline_kb)
    
    # Добавляем кнопку возврата
    keyboard_reply = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Аккаунты")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("Нажмите на кнопку рядом с аккаунтом для удаления или вернитесь назад", reply_markup=keyboard_reply)
    session.close()

@dp.callback_query(lambda call: call.data.startswith("delete_account:"))
async def delete_account_callback(call: CallbackQuery):
    print(f"Получен колбэк: {call.data}")
    if not is_admin(call.from_user.id):
        await call.answer("Недостаточно прав")
        return

    # Извлекаем ID аккаунта из данных колбэка
    userbot_id = int(call.data.split(":")[1])
    
    # Сообщаем пользователю, что началось удаление
    await call.answer("Начинаем процесс удаления...")
    await call.message.edit_text(call.message.text + "\n\n🔄 Удаление аккаунта...", reply_markup=None)
    
    # Получаем информацию об аккаунте из базы данных
    session = Session(bind=engine)
    userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
    
    if not userbot:
        await call.message.edit_text(call.message.text + "\n\n❌ Ошибка: Аккаунт не найден в базе данных.")
        session.close()
        return
    
    try:
        # Получаем URL сессии и имя файла
        session_url = userbot.session_name
        session_filename = session_url.split("/")[-1]
        local_path = f"adminbot/sessions/{session_filename}"
        
        # Удаляем файл из S3
        try:
            s3 = boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            
            # Предполагаем, что URL имеет формат https://<bucket>.s3.<region>.amazonaws.com/sessions/<filename>
            session_key = f"sessions/{session_filename}"
            
            # Удаляем файл из S3
            s3.delete_object(Bucket=AWS_BUCKET_NAME, Key=session_key)
            s3_deleted = True
            
        except Exception as e:
            s3_deleted = False
            print(f"Ошибка при удалении файла из S3: {e}")
        
        # Удаляем локальный файл, если он существует
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                local_deleted = True
            except Exception as e:
                local_deleted = False
                print(f"Ошибка при удалении локального файла: {e}")
        else:
            local_deleted = True  # Файла нет, поэтому считаем удаленным
            
        # Удаляем аккаунт из базы данных
        account_id = userbot.account_id
        session.delete(userbot)
        session.commit()
        db_deleted = True
        
        # Формируем сообщение об успешном удалении
        result_message = f"{call.message.text.split('🔄')[0]}\n\n✅ Аккаунт с ID {account_id} успешно удален!"
        if not s3_deleted:
            result_message += "\n⚠️ Не удалось удалить файл сессии из облака."
        if not local_deleted:
            result_message += "\n⚠️ Не удалось удалить локальный файл сессии."
        
        # Обновляем сообщение с результатом
        await call.message.edit_text(result_message)
            
    except Exception as e:
        # Обрабатываем любые другие непредвиденные ошибки
        await call.message.edit_text(
            call.message.text.split("\n\n")[0] + f"\n\n❌ Ошибка при удалении аккаунта: {str(e)}"
        )
    finally:
        session.close()

@dp.callback_query(lambda call: call.data.startswith("check_session:"))
async def check_session_callback(call: CallbackQuery):
    print(f"Получен колбэк: {call.data}")
    if not is_admin(call.from_user.id):
        await call.answer("Недостаточно прав")
        return

    # Извлекаем ID сессии из данных колбэка
    userbot_id = int(call.data.split(":")[1])
    
    # Сообщаем пользователю, что началась проверка
    await call.answer("Проверка сессии начата...")
    await call.message.edit_text(call.message.text + "\n\n🔄 Проверка сессии...", reply_markup=None)
    
    # Получаем информацию о сессии из базы данных
    session = Session(bind=engine)
    userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
    
    if not userbot:
        await call.message.edit_text(call.message.text + "\n\n❌ Ошибка: Сессия не найдена в базе данных.")
        session.close()
        return
    
    try:
        # Загружаем сессию из S3
        s3 = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        
        # Получаем имя файла из URL
        session_filename = userbot.session_name.split("/")[-1]
        local_path = f"adminbot/sessions/{session_filename}"
        
        # Ensure sessions directory exists
        os.makedirs("adminbot/sessions", exist_ok=True)
        
        # Предполагаем, что URL имеет формат https://<bucket>.s3.<region>.amazonaws.com/sessions/<filename>
        session_key = f"sessions/{session_filename}"
        
        # Загружаем файл
        try:
            # Define local_path before using it
            local_path = f"adminbot/sessions/{session_filename}"
            s3.download_file(AWS_BUCKET_NAME, session_key, local_path)
        except Exception as e:
            await call.message.edit_text(
                call.message.text + f"\n\n❌ Ошибка загрузки файла сессии: {str(e)}"
            )
            session.close()
            return
        
        # Пробуем авторизоваться
        client = TelegramClient(local_path.replace(".session", ""), api_id=1, api_hash="1")
        
        try:
            await client.connect()
            
            if await client.is_user_authorized():
                # Получаем информацию о пользователе
                me = await client.get_me()
                status = f"✅ Сессия действительна!\nИмя пользователя: {me.first_name}"
                if me.username:
                    status += f"\nUsername: @{me.username}"
                if me.phone:
                    status += f"\nТелефон: {me.phone}"
                
                # Проверка на спам-блок
                await call.message.edit_text(
                    call.message.text.split("\n\n")[0] + f"\n\n{status}\n\n🔄 Проверка на спам-блок..."
                )
                
                try:
                    # Тестовый канал для проверки возможности отправки сообщений
                    test_chat_user = "SpamBot"  # Официальный бот для проверки статуса аккаунта
                    
                    try:
                        # Пытаемся найти SpamBot в диалогах
                        spam_bot = None
                        dialogs = await client.get_dialogs(limit=100)
                        for dialog in dialogs:
                            if dialog.entity.username == test_chat_user:
                                spam_bot = dialog.entity
                                break
                        
                        # Если не нашли в диалогах, ищем по username
                        if not spam_bot:
                            spam_bot = await client.get_entity(test_chat_user)
                        
                        # Отправляем сообщение /start спам-боту
                        await client.send_message(spam_bot, "/start")
                        
                        # Ждем ответа от спам-бота
                        timeout = 5  # секунд
                        start_time = asyncio.get_event_loop().time()
                        spam_status = "⚠️ Статус блокировки неизвестен (не получен ответ от SpamBot)"
                        
                        # Ждем сообщения от SpamBot
                        while (asyncio.get_event_loop().time() - start_time) < timeout:
                            # Читаем последнее сообщение от SpamBot
                            async for message in client.iter_messages(spam_bot, limit=1):
                                if message.date.timestamp() > start_time:
                                    # Если сообщение свежее (пришло после нашего запроса)
                                    spam_message = message.text.lower()
                                    
                                    if "good news" in spam_message or "не ограничен" in spam_message:
                                        spam_status = "✅ Аккаунт не заблокирован"
                                    elif "спам" in spam_message or "spam" in spam_message:
                                        spam_status = "❌ Обнаружены ограничения: возможен спам-блок"
                                    else:
                                        spam_status = f"⚠️ Ответ от SpamBot получен: {message.text[:100]}..."
                                    
                                    break
                            
                            # Если уже получили статус, выходим
                            if spam_status != "⚠️ Статус блокировки неизвестен (не получен ответ от SpamBot)":
                                break
                                
                            await asyncio.sleep(0.5)
                            
                        # Получаем дополнительные детали о SpamBot ответе, если доступны
                        details = ""
                        if "⚠️" not in spam_status:  # Если получили конкретный статус
                            async for message in client.iter_messages(spam_bot, limit=1):
                                if message.date.timestamp() > start_time:
                                    details = f"\n\nДетали от SpamBot:\n{message.text}"
                        
                        status += f"\n\n👮‍♂️ Проверка спам-блока: {spam_status}{details}"
                    except Exception as e:
                        status += f"\n\n👮‍♂️ Проверка спам-блока: ⚠️ Ошибка при проверке: {str(e)}"
                except Exception as e:
                    status += f"\n\n👮‍♂️ Проверка спам-блока: ⚠️ Невозможно проверить: {str(e)}"
                
                # Обновляем сообщение с результатом
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Проверить сессию снова", callback_data=f"check_session:{userbot_id}")],
                    [InlineKeyboardButton(text="Проверить только спам-блок", callback_data=f"check_spam:{userbot_id}")]
                ])
                
                await call.message.edit_text(
                    call.message.text.split("\n\n")[0] + f"\n\n{status}",
                    reply_markup=inline_kb
                )
            else:
                # Если сессия недействительна
                await call.message.edit_text(
                    call.message.text.split("\n\n")[0] + "\n\n❌ Сессия недействительна",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Проверить сессию снова", callback_data=f"check_session:{userbot_id}")]
                    ])
                )
        except Exception as e:
            # В случае других ошибок
            await call.message.edit_text(
                call.message.text.split("\n\n")[0] + f"\n\n❌ Ошибка при проверке сессии: {str(e)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Проверить сессию снова", callback_data=f"check_session:{userbot_id}")]
                ])
            )
        finally:
            await client.disconnect()
            
    except Exception as e:
        # Обрабатываем любые другие непредвиденные ошибки
        await call.message.edit_text(
            call.message.text.split("\n\n")[0] + f"\n\n❌ Непредвиденная ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Проверить сессию снова", callback_data=f"check_session:{userbot_id}")]
            ])
        )
    finally:
        session.close()

@dp.callback_query(lambda call: call.data.startswith("check_spam:"))
async def check_spam_callback(call: CallbackQuery):
    print(f"Получен колбэк: {call.data}")
    if not is_admin(call.from_user.id):
        await call.answer("Недостаточно прав")
        return

    # Извлекаем ID сессии из данных колбэка
    userbot_id = int(call.data.split(":")[1])
    
    # Сообщаем пользователю, что началась проверка
    await call.answer("Проверка на спам-блок начата...")
    await call.message.edit_text(call.message.text + "\n\n🔄 Проверка на спам-блок...", reply_markup=None)
    
    # Получаем информацию о сессии из базы данных
    session = Session(bind=engine)
    userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
    
    if not userbot:
        await call.message.edit_text(call.message.text + "\n\n❌ Ошибка: Сессия не найдена в базе данных.")
        session.close()
        return
    
    try:
        # Загружаем сессию из S3
        s3 = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        
        # Получаем имя файла из URL
        session_filename = userbot.session_name.split("/")[-1]
        
        # Загружаем файл
        try:
            s3.download_file(AWS_BUCKET_NAME, session_key, local_path)
        except Exception as e:
            await call.message.edit_text(
                call.message.text + f"\n\n❌ Ошибка загрузки файла сессии: {str(e)}"
            )
            session.close()
            return
        
        # Пробуем авторизоваться
        client = TelegramClient(local_path.replace(".session", ""), api_id=1, api_hash="1")
        
        try:
            await client.connect()
            
            if await client.is_user_authorized():
                # Проверка на спам-блок
                try:
                    # Тестовый канал для проверки возможности отправки сообщений
                    test_chat_user = "SpamBot"  # Официальный бот для проверки статуса аккаунта
                    
                    try:
                        # Пытаемся найти SpamBot в диалогах
                        spam_bot = None
                        dialogs = await client.get_dialogs(limit=100)
                        for dialog in dialogs:
                            if dialog.entity.username == test_chat_user:
                                spam_bot = dialog.entity
                                break
                        
                        # Если не нашли в диалогах, ищем по username
                        if not spam_bot:
                            spam_bot = await client.get_entity(test_chat_user)
                        
                        # Отправляем сообщение /start спам-боту
                        await client.send_message(spam_bot, "/start")
                        
                        # Ждем ответа от спам-бота
                        timeout = 5  # секунд
                        start_time = asyncio.get_event_loop().time()
                        spam_status = "⚠️ Статус блокировки неизвестен (не получен ответ от SpamBot)"
                        
                        # Ждем сообщения от SpamBot
                        while (asyncio.get_event_loop().time() - start_time) < timeout:
                            # Читаем последнее сообщение от SpamBot
                            async for message in client.iter_messages(spam_bot, limit=1):
                                if message.date.timestamp() > start_time:
                                    # Если сообщение свежее (пришло после нашего запроса)
                                    spam_message = message.text.lower()
                                    
                                    if "good news" in spam_message or "не ограничен" in spam_message:
                                        spam_status = "✅ Аккаунт не заблокирован"
                                    elif "спам" in spam_message or "spam" in spam_message:
                                        spam_status = "❌ Обнаружены ограничения: возможен спам-блок"
                                    else:
                                        spam_status = f"⚠️ Ответ от SpamBot получен: {message.text[:100]}..."
                                    
                                    break
                            
                            # Если уже получили статус, выходим
                            if spam_status != "⚠️ Статус блокировки неизвестен (не получен ответ от SpamBot)":
                                break
                                
                            await asyncio.sleep(0.5)
                        
                        # Получаем дополнительные детали о SpamBot ответе, если доступны
                        details = ""
                        if "⚠️" not in spam_status:  # Если получили конкретный статус
                            async for message in client.iter_messages(spam_bot, limit=1):
                                if message.date.timestamp() > start_time:
                                    details = f"\n\nДетали от SpamBot:\n{message.text}"
                        
                        # Обновляем сообщение с результатом
                        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="Проверить сессию полностью", callback_data=f"check_session:{userbot_id}")],
                            [InlineKeyboardButton(text="Проверить спам-блок снова", callback_data=f"check_spam:{userbot_id}")]
                        ])
                        
                        await call.message.edit_text(
                            call.message.text.split("\n\n🔄")[0] + f"\n\n👮‍♂️ Результат проверки: {spam_status}{details}",
                            reply_markup=inline_kb
                        )
                        
                    except Exception as e:
                        await call.message.edit_text(
                            call.message.text.split("\n\n🔄")[0] + f"\n\n❌ Ошибка при проверке спам-блока: {str(e)}",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="Проверить сессию полностью", callback_data=f"check_session:{userbot_id}")],
                                [InlineKeyboardButton(text="Проверить спам-блок снова", callback_data=f"check_spam:{userbot_id}")]
                            ])
                        )
                except Exception as e:
                    await call.message.edit_text(
                        call.message.text.split("\n\n🔄")[0] + f"\n\n❌ Ошибка при проверке спам-блока: {str(e)}",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="Проверить сессию полностью", callback_data=f"check_session:{userbot_id}")],
                            [InlineKeyboardButton(text="Проверить спам-блок снова", callback_data=f"check_spam:{userbot_id}")]
                        ])
                    )
            else:
                # Если сессия недействительна
                await call.message.edit_text(
                    call.message.text.split("\n\n🔄")[0] + "\n\n❌ Сессия недействительна, невозможно проверить спам-блок",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Проверить сессию полностью", callback_data=f"check_session:{userbot_id}")]
                    ])
                )
        except Exception as e:
            # В случае других ошибок
            await call.message.edit_text(
                call.message.text.split("\n\n🔄")[0] + f"\n\n❌ Ошибка при проверке сессии: {str(e)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Проверить сессию полностью", callback_data=f"check_session:{userbot_id}")],
                    [InlineKeyboardButton(text="Проверить спам-блок снова", callback_data=f"check_spam:{userbot_id}")]
                ])
            )
        finally:
            await client.disconnect()
            
    except Exception as e:
        # Обрабатываем любые другие непредвиденные ошибки
        await call.message.edit_text(
            call.message.text.split("\n\n🔄")[0] + f"\n\n❌ Непредвиденная ошибка: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Проверить сессию полностью", callback_data=f"check_session:{userbot_id}")],
                [InlineKeyboardButton(text="Проверить спам-блок снова", callback_data=f"check_spam:{userbot_id}")]
            ])
        )
    finally:
        session.close()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
