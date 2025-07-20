#!/usr/bin/env python3
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
import asyncio
import os
import re
from database.db import Session
from database.models import UserBot
import logging
import boto3
from botocore.exceptions import ClientError
import tempfile
from urllib.parse import urlparse
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levellevelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Параметры для S3 Bucketeer
BUCKETEER_AWS_ACCESS_KEY_ID = os.environ.get('BUCKETEER_AWS_ACCESS_KEY_ID')
BUCKETEER_AWS_SECRET_ACCESS_KEY = os.environ.get('BUCKETEER_AWS_SECRET_ACCESS_KEY')
BUCKETEER_BUCKET_NAME = os.environ.get('BUCKETEER_BUCKET_NAME')
BUCKETEER_REGION = os.environ.get('BUCKETEER_REGION', 'us-east-1')

# Инициализация клиента S3
s3_client = boto3.client(
    's3',
    aws_access_key_id=BUCKETEER_AWS_ACCESS_KEY_ID,
    aws_secret_access_key=BUCKETEER_AWS_SECRET_ACCESS_KEY,
    region_name=BUCKETEER_REGION
) if all([BUCKETEER_AWS_ACCESS_KEY_ID, BUCKETEER_AWS_SECRET_ACCESS_KEY, BUCKETEER_BUCKET_NAME]) else None

if s3_client:
    logger.info(f"S3 клиент инициализирован для бакета {BUCKETEER_BUCKET_NAME}")
else:
    logger.warning("S3 клиент не инициализирован. Отсутствуют необходимые переменные окружения.")

# Пути к локальным директориям для резервного доступа
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_SESSIONS_DIRS = [
    os.path.join(ROOT_DIR, "adminbot", "sessions"),  # /adminbot/sessions/
    ROOT_DIR  # Корневая директория
]

def extract_session_name(session_string):
    """
    Извлекает имя сессии из строки, которая может быть URL или простым именем сессии.
    
    Args:
        session_string (str): Строка с именем сессии или URL
    
    Returns:
        str: Имя файла сессии (без .session)
    """
    logger.debug(f"Извлечение имени сессии из: {session_string}")
    
    # Если строка содержит URL
    if session_string.startswith(('http://', 'https://')):
        try:
            parsed_url = urlparse(session_string)
            path = parsed_url.path.strip('/')
            # Извлекаем последнюю часть пути
            session_name = path.split('/')[-1]
            # Убираем расширение .session, если есть
            if session_name.endswith('.session'):
                session_name = session_name[:-8]
            
            logger.debug(f"Извлечено имя сессии из URL: {session_name}")
            return session_name
        except Exception as e:
            logger.error(f"Ошибка при извлечении имени сессии из URL: {e}")
            # В случае ошибки возвращаем исходную строку
            return session_string
    
    # Если это просто путь к файлу
    if '/' in session_string:
        session_name = session_string.split('/')[-1]
    else:
        session_name = session_string
    
    # Убираем расширение .session, если есть
    if session_name.endswith('.session'):
        session_name = session_name[:-8]
    
    logger.debug(f"Извлечено имя сессии: {session_name}")
    return session_name

async def download_session_from_s3(session_name):
    """
    Загружает файл сессии из S3 хранилища.
    
    Args:
        session_name (str): Имя сессии
        
    Returns:
        str: Путь к загруженному файлу или None если ошибка
    """
    if not s3_client:
        logger.error("S3 клиент не инициализирован")
        return None
    
    # Создаем временный файл для сохранения сессии
    with tempfile.NamedTemporaryFile(suffix='.session', delete=False) as tmp_file:
        temp_path = tmp_file.name
        
    try:
        # Полный путь к файлу в S3
        s3_key = f"sessions/{session_name}.session"
        
        logger.info(f"Загрузка сессии из S3: {BUCKETEER_BUCKET_NAME}/{s3_key}")
        
        # Загружаем файл из S3
        s3_client.download_file(BUCKETEER_BUCKET_NAME, s3_key, temp_path)
        
        logger.info(f"Сессия успешно загружена из S3 во временный файл: {temp_path}")
        return temp_path
    
    except ClientError as e:
        logger.error(f"Ошибка при загрузке сессии из S3: {e}")
        # Удаляем временный файл в случае ошибки
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return None
    
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке сессии из S3: {e}")
        # Удаляем временный файл в случае ошибки
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return None

async def find_local_session_file(session_name):
    """
    Ищет локальный файл сессии в доступных директориях.
    
    Args:
        session_name (str): Имя сессии
        
    Returns:
        str: Путь к найденному файлу или None
    """
    for dir_path in LOCAL_SESSIONS_DIRS:
        full_path = os.path.join(dir_path, f"{session_name}.session")
        if os.path.exists(full_path):
            logger.info(f"Найден локальный файл сессии: {full_path}")
            return full_path
    
    logger.warning(f"Локальный файл сессии '{session_name}.session' не найден")
    return None

async def get_client_by_session_name(session_name):
    """
    Получает клиент Telethon по имени сессии.
    Приоритет: S3 хранилище -> локальные файлы.
    
    Args:
        session_name (str): Имя сессии или URL к файлу сессии
        
    Returns:
        TelegramClient: Клиент Telethon
    """
    # Извлекаем чистое имя сессии
    clean_name = extract_session_name(session_name)
    logger.info(f"Получение клиента для сессии: {clean_name}")
    
    session_path = None
    temp_file = None
    
    # Сначала пытаемся загрузить из S3
    if s3_client:
        temp_file = await download_session_from_s3(clean_name)
        if temp_file:
            session_path = temp_file
    
    # Если не удалось загрузить из S3, ищем локально
    if not session_path:
        session_path = await find_local_session_file(clean_name)
    
    # Если файл сессии не найден ни в S3, ни локально
    if not session_path:
        logger.error(f"Файл сессии для {clean_name} не найден")
        return None
    
    try:
        # При использовании временного файла из S3, указываем путь без расширения
        if temp_file:
            client_session_path = temp_file[:-8]
        else:
            client_session_path = session_path[:-8] if session_path.endswith('.session') else session_path
        
        # Создаем клиент с указанием пути к сессии
        client = TelegramClient(client_session_path, api_id=1, api_hash="x")
        
        # Подключаемся к Telegram
        await client.connect()
        
        # Проверяем авторизацию
        if not await client.is_user_authorized():
            logger.error(f"Сессия {clean_name} не авторизована")
            await client.disconnect()
            
            # Удаляем временный файл если он был создан
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
            
            return None
        
        logger.info(f"Успешное подключение к сессии {clean_name}")
        return client
        
    except Exception as e:
        logger.error(f"Ошибка при создании клиента Telethon для {clean_name}: {e}")
        
        # Удаляем временный файл если он был создан
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)
        
        return None

async def update_bot_profile(userbot_id, first_name=None, bio=None, photo_path=None):
    """
    Обновляет профиль юзербота (имя, био, фото).
    
    Args:
        userbot_id (int): ID юзербота в базе данных
        first_name (str, optional): Новое имя для юзербота
        bio (str, optional): Новое описание для юзербота
        photo_path (str, optional): Путь к файлу фото для аватарки
        
    Returns:
        bool: True в случае успеха, False в случае ошибки
    """
    # Получаем информацию о юзерботе из базы данных
    session = Session()
    try:
        userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
        if not userbot:
            logger.error(f"Юзербот с ID {userbot_id} не найден в базе данных")
            return False
        
        session_name = userbot.session_name
    finally:
        session.close()
    
    # Получаем клиент Telethon
    client = await get_client_by_session_name(session_name)
    if not client:
        return False
    
    try:
        # Обновляем имя и био, если они указаны
        if first_name or bio:
            # Получаем текущие значения, если новые не указаны
            me = await client.get_me()
            
            # Безопасно получаем текущее имя и биографию
            current_first_name = getattr(me, 'first_name', '') or ''
            # В некоторых версиях Telethon, 'about' может называться 'bio' или отсутствовать
            current_bio = ''
            if hasattr(me, 'about'):
                current_bio = me.about or ''
            elif hasattr(me, 'bio'):
                current_bio = me.bio or ''
            
            await client(UpdateProfileRequest(
                first_name=first_name if first_name else current_first_name,
                about=bio if bio else current_bio
            ))
            logger.info(f"Обновлен профиль для юзербота {session_name}")
        
        # Обновляем фото профиля, если указан путь к файлу
        if photo_path and os.path.exists(photo_path):
            # Загружаем фото
            result = await client(UploadProfilePhotoRequest(
                file=await client.upload_file(photo_path)
            ))
            logger.info(f"Обновлена аватарка для юзербота {session_name}")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении профиля юзербота {session_name}: {e}")
        return False
    finally:
        # Закрываем соединение
        await client.disconnect()

async def check_channel_admin(userbot_id, channel_username):
    """
    Проверяет, является ли юзербот администратором указанного канала.
    
    Args:
        userbot_id (int): ID юзербота в базе данных
        channel_username (str): Имя пользователя канала (без @)
        
    Returns:
        bool: True если юзербот является администратором, False в противном случае
    """
    # Получаем информацию о юзерботе из базы данных
    session = Session()
    try:
        userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
        if not userbot:
            logger.error(f"Юзербот с ID {userbot_id} не найден в базе данных")
            return False
        
        session_name = userbot.session_name
    finally:
        session.close()
    
    # Получаем клиент Telethon
    client = await get_client_by_session_name(session_name)
    if not client:
        return False
    
    try:
        # Получаем информацию о канале
        channel = await client.get_entity(channel_username)
        
        # Получаем список администраторов
        admins = await client.get_participants(channel, filter='admins')
        
        # Проверяем, является ли наш юзербот администратором
        me = await client.get_me()
        is_admin = any(admin.id == me.id for admin in admins)
        
        return is_admin
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса администратора для юзербота {session_name} в канале {channel_username}: {e}")
        return False
    finally:
        await client.disconnect()

async def add_channel_to_profile(userbot_id, channel_username):
    """
    Добавляет канал в профиль юзербота (в поле about).
    
    Args:
        userbot_id (int): ID юзербота в базе данных
        channel_username (str): Имя пользователя канала (с @ или без)
        
    Returns:
        bool: True в случае успеха, False в случае ошибки
    """
    # Нормализуем имя пользователя канала
    if not channel_username.startswith('@'):
        channel_username = f'@{channel_username}'
    
    # Получаем информацию о юзерботе из базы данных
    session = Session()
    try:
        userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
        if not userbot:
            logger.error(f"Юзербот с ID {userbot_id} не найден в базе данных")
            return False
        
        session_name = userbot.session_name
    finally:
        session.close()
    
    # Получаем клиент Telethon
    client = await get_client_by_session_name(session_name)
    if not client:
        return False
    
    try:
        # Получаем текущую информацию о профиле
        me = await client.get_me()
        current_bio = me.about or ""
        
        # Проверяем, есть ли уже ссылка на канал в профиле
        if channel_username in current_bio:
            logger.info(f"Канал {channel_username} уже добавлен в профиль юзербота {session_name}")
            return True
        
        # Добавляем канал в био
        new_bio = f"{current_bio}\n{channel_username}".strip()
        
        # Обновляем профиль
        await client(UpdateProfileRequest(about=new_bio))
        
        logger.info(f"Канал {channel_username} добавлен в профиль юзербота {session_name}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении канала в профиль юзербота {session_name}: {e}")
        return False
    finally:
        await client.disconnect()

# Функция для проверки доступности юзербота
async def check_userbot_availability(userbot_id):
    """
    Проверяет, что юзербот доступен и авторизован.
    
    Args:
        userbot_id (int): ID юзербота в базе данных
        
    Returns:
        bool: True если юзербот доступен, False в противном случае
    """
    # Получаем информацию о юзерботе из базы данных
    session = Session()
    try:
        userbot = session.query(UserBot).filter(UserBot.id == userbot_id).first()
        if not userbot:
            logger.error(f"Юзербот с ID {userbot_id} не найден в базе данных")
            return False
        
        session_name = userbot.session_name
    finally:
        session.close()
    
    # Пытаемся подключиться к аккаунту
    client = await get_client_by_session_name(session_name)
    if not client:
        return False
    
    try:
        # Проверяем, что аккаунт работает
        me = await client.get_me()
        logger.info(f"Юзербот {session_name} доступен. ID: {me.id}, Имя: {me.first_name}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при проверке доступности юзербота {session_name}: {e}")
        return False
    finally:
        await client.disconnect()

# Если файл запущен напрямую, выполняем тестовую функцию
if __name__ == "__main__":
    # Тестовая функция для проверки работы модуля
    async def test_userbot_manager():
        # Получаем id первого юзербота из базы данных
        session = Session()
        userbot = session.query(UserBot).first()
        session.close()
        
        if userbot:
            userbot_id = userbot.id
            print(f"Тестирование юзербота с ID {userbot_id}, session_name: {userbot.session_name}")
            
            # Проверяем доступность юзербота
            available = await check_userbot_availability(userbot_id)
            print(f"Юзербот доступен: {available}")
            
            if available:
                # Обновляем имя и био
                await update_bot_profile(userbot_id, first_name="Тестовый бот", bio="Это тестовый бот для проверки работы модуля")
                print("Профиль обновлен")
        else:
            print("Юзерботы не найдены в базе данных")
    
    # Запускаем тестовую функцию
    asyncio.run(test_userbot_manager())