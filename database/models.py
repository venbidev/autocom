from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, BigInteger, TIMESTAMP, func, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship

Base = declarative_base()

class UserBot(Base):
    __tablename__ = 'userbots'

    id = Column(Integer, primary_key=True)
    owner_id = Column(BigInteger, nullable=False)
    account_id = Column(BigInteger, nullable=False)  # Новый столбец для ID аккаунта
    session_name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)  # Отображаемое имя бота
    isoccupied = Column(Boolean, default=False, nullable=False)  # Столбец для отслеживания статуса занятости бота
    created_at = Column(TIMESTAMP, server_default=func.now())

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

class Campaign(Base):
    __tablename__ = 'campaigns'

    id = Column(Integer, primary_key=True)
    creator_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    name = Column(String, nullable=False)
    bot_id = Column(Integer, ForeignKey('userbots.id'), nullable=False)
    paid_until = Column(DateTime, nullable=False)
    target = Column(String, nullable=False)  # Целевые каналы/группы для комментирования
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Отношения
    creator = relationship("User", foreign_keys=[creator_id])
    bot = relationship("UserBot", foreign_keys=[bot_id])
