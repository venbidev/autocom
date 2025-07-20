#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telethon import TelegramClient, events, utils
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import User, Channel, InputPeerUser, InputPeerChannel, UserStatusOnline, UserStatusOffline, UserStatusRecently
import asyncio
import logging
import sys
import os
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("online_tracker.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Данные для авторизации клиента Telegram
API_ID = 12345  # Замените на ваш API_ID
API_HASH = 'your_api_hash'  # Замените на ваш API_HASH
SESSION_NAME = 'user1'  # Используем существующую сессию

# Имя пользователя Telegram (без @) или телефон пользователя, которого нужно отслеживать
TARGET_USER = "nikonikto"  # Замените на username пользователя (без @) или его телефон

# ID пользователя или имя пользователя, кому отправлять уведомления
NOTIFICATION_USER = "@lavrehin"  # "me" для отправки сообщений самому себе

# Интервал проверки (в секундах)
CHECK_INTERVAL = 15
# Словарь для хранения состояния пользователя
user_status = {
    'online': False,
    'last_seen': None,
    'entity': None
}

async def send_notification(message):
    """Отправляет уведомление пользователю."""
    try:
        await client.send_message(NOTIFICATION_USER, message)
        logger.info(f"Уведомление отправлено: {message}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления: {e}")

async def get_user_entity():
    """Получает сущность пользователя по имени пользователя или номеру телефона."""
    try:
        # Пробуем найти пользователя по имени пользователя или номеру телефона
        entity = await client.get_entity(TARGET_USER)
        
        # Проверяем, что сущность - это пользователь, а не канал или группа
        if not isinstance(entity, User):
            if isinstance(entity, Channel):
                logger.error(f"Ошибка: {TARGET_USER} - это канал или группа, а не пользователь.")
                await send_notification(f"⚠️ Ошибка: {TARGET_USER} - это канал или группа, а не пользователь. Укажите имя пользователя.")
            else:
                logger.error(f"Ошибка: {TARGET_USER} - это не пользователь.")
                await send_notification(f"⚠️ Ошибка: {TARGET_USER} - не является пользователем. Укажите корректное имя пользователя.")
            return None
            
        logger.info(f"Успешно найден пользователь: {entity.first_name} {entity.last_name or ''} (ID: {entity.id})")
        return entity
    except Exception as e:
        logger.error(f"Ошибка при получении сущности пользователя: {e}")
        await send_notification(f"⚠️ Ошибка при поиске пользователя {TARGET_USER}: {str(e)}")
        return None

async def check_user_status():
    """Проверяет статус пользователя и отправляет уведомление при изменении."""
    try:
        # Если у нас еще нет сущности пользователя, получаем её
        if user_status['entity'] is None:
            user_status['entity'] = await get_user_entity()
            if user_status['entity'] is None:
                logger.error("Не удалось получить сущность пользователя")
                return
        
        # Получаем полную информацию о пользователе (включая статус)
        full_user = await client(GetFullUserRequest(user_status['entity']))
        user = full_user.users[0]
        status = user.status
        
        # Получаем имя пользователя для отображения в уведомлениях
        user_name = user.first_name
        if user.last_name:
            user_name += " " + user.last_name
        
        # Логирование текущего статуса для отладки
        logger.info(f"Текущий статус пользователя {user_name}: {type(status).__name__}")
        
        # Определяем, онлайн ли пользователь
        is_online = isinstance(status, UserStatusOnline)
        
        if is_online:
            # Пользователь онлайн
            if not user_status['online']:
                user_status['online'] = True
                current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                await send_notification(
                    f"✅ {user_name} сейчас онлайн! ({current_time})"
                )
                logger.info(f"{user_name} вошел в сеть в {current_time}")
        else:
            # Пользователь оффлайн
            if user_status['online']:
                user_status['online'] = False
                
                if isinstance(status, UserStatusOffline) and hasattr(status, 'was_online'):
                    last_seen = status.was_online
                    user_status['last_seen'] = last_seen
                    last_seen_str = last_seen.strftime("%d.%m.%Y %H:%M:%S")
                    offline_msg = f"❌ {user_name} вышел из сети\nПоследний раз был онлайн: {last_seen_str}"
                elif isinstance(status, UserStatusRecently):
                    offline_msg = f"❌ {user_name} вышел из сети\nБыл в сети недавно"
                else:
                    offline_msg = f"❌ {user_name} вышел из сети\nСтатус: {type(status).__name__}"
                
                await send_notification(offline_msg)
                logger.info(f"{user_name} вышел из сети. Статус: {type(status).__name__}")
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса: {e}")
        # При ошибке пробуем сбросить кэшированную сущность
        user_status['entity'] = None
        await asyncio.sleep(10)  # Ждем немного перед повторной попыткой

async def main():
    """Основная функция, запускает бесконечный цикл проверки статуса."""
    try:
        # Отправляем начальное сообщение
        await send_notification(f"🔍 Скрипт запущен и отслеживает активность пользователя {TARGET_USER}")
        
        # Первая проверка для инициализации
        await check_user_status()
        
        # Входим в цикл проверки
        while True:
            await asyncio.sleep(CHECK_INTERVAL)
            await check_user_status()
    except KeyboardInterrupt:
        logger.info("Скрипт остановлен пользователем")
        await send_notification("⚠️ Скрипт остановлен пользователем")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
        await send_notification(f"⚠️ Ошибка в скрипте: {str(e)}")

if __name__ == '__main__':
    # Создаем клиента
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    with client:
        logger.info(f"Скрипт запущен и отслеживает активность пользователя {TARGET_USER}")
        client.loop.run_until_complete(main())