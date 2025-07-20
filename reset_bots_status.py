#!/usr/bin/env python3
"""
Скрипт для сброса статуса занятости всех юзерботов в базе данных.
Используйте этот скрипт, когда нужно освободить всех юзерботов, 
например, после сбоя или для отладки.
"""

import os
import sys
from dotenv import load_dotenv
import argparse
from sqlalchemy import text

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем модули для работы с базой данных
from database.db import Session, engine
from database.models import UserBot

# Загружаем переменные окружения
load_dotenv()

def reset_all_bots_status():
    """Сбрасывает статус занятости всех юзерботов."""
    session = Session()
    try:
        # Получаем количество занятых ботов до сброса
        occupied_bots_count = session.query(UserBot).filter(UserBot.isoccupied == True).count()
        
        if occupied_bots_count == 0:
            print("Все юзерботы уже свободны. Нет необходимости сбрасывать статусы.")
            return
        
        # Обновляем статус всех ботов на 'свободен'
        result = session.query(UserBot).filter(UserBot.isoccupied == True).update(
            {UserBot.isoccupied: False}, 
            synchronize_session=False
        )
        
        session.commit()
        print(f"Статус занятости сброшен для {result} юзерботов.")
        
        # Проверяем, что все боты теперь свободны
        remaining_occupied = session.query(UserBot).filter(UserBot.isoccupied == True).count()
        if remaining_occupied == 0:
            print("Все юзерботы теперь свободны.")
        else:
            print(f"ВНИМАНИЕ: {remaining_occupied} юзерботов все еще отмечены как занятые.")
            
    except Exception as e:
        print(f"Ошибка при сбросе статусов: {e}")
        session.rollback()
    finally:
        session.close()

def reset_specific_bot(bot_id):
    """Сбрасывает статус занятости конкретного юзербота."""
    session = Session()
    try:
        bot = session.query(UserBot).filter(UserBot.id == bot_id).first()
        
        if not bot:
            print(f"Юзербот с ID {bot_id} не найден.")
            return
        
        if not bot.isoccupied:
            print(f"Юзербот {bot.session_name} (ID: {bot_id}) уже свободен.")
            return
        
        bot.isoccupied = False
        session.commit()
        print(f"Юзербот {bot.session_name} (ID: {bot_id}) освобожден.")
        
    except Exception as e:
        print(f"Ошибка при сбросе статуса юзербота {bot_id}: {e}")
        session.rollback()
    finally:
        session.close()

def list_bots():
    """Показывает список всех юзерботов и их статусов."""
    session = Session()
    try:
        bots = session.query(UserBot).all()
        
        if not bots:
            print("В базе данных нет юзерботов.")
            return
        
        print("\nСписок юзерботов:")
        print("-" * 80)
        print(f"{'ID':<5} {'Имя сессии':<30} {'ID владельца':<15} {'Занят':<10}")
        print("-" * 80)
        
        for bot in bots:
            status = "Да" if bot.isoccupied else "Нет"
            print(f"{bot.id:<5} {bot.session_name:<30} {bot.owner_id:<15} {status:<10}")
            
        print("-" * 80)
        occupied_count = sum(1 for bot in bots if bot.isoccupied)
        print(f"Всего юзерботов: {len(bots)}, занято: {occupied_count}, свободно: {len(bots) - occupied_count}")
        
    except Exception as e:
        print(f"Ошибка при получении списка юзерботов: {e}")
    finally:
        session.close()

def check_database_connection():
    """Проверяет подключение к базе данных."""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            if result == 1:
                return True
            return False
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Управление статусом занятости юзерботов")
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="Сбросить статус всех юзерботов")
    group.add_argument("--bot", type=int, help="ID юзербота для сброса статуса")
    group.add_argument("--list", action="store_true", help="Показать список всех юзерботов и их статусов")
    
    args = parser.parse_args()
    
    # Проверяем подключение к базе данных
    if not check_database_connection():
        print("Не удалось подключиться к базе данных. Проверьте настройки подключения.")
        sys.exit(1)
    
    # Обрабатываем аргументы командной строки
    if args.all:
        reset_all_bots_status()
    elif args.bot is not None:
        reset_specific_bot(args.bot)
    elif args.list:
        list_bots()
    else:
        # Если нет аргументов, показываем справку
        parser.print_help()