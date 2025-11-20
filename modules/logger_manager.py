#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime
from typing import Optional


class LoggerManager:
    """Менеджер логирования для приложения"""
    
    def __init__(self, log_folder: str = "logs"):
        self.log_folder = log_folder
        os.makedirs(log_folder, exist_ok=True)
        
        # Создаем имя файла лога с текущей датой и временем
        session_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(log_folder, f"session_{session_time}.log")
        
        # Настраиваем логгер
        self.logger = logging.getLogger("AgreementGenerator")
        self.logger.setLevel(logging.DEBUG)
        
        # Убираем старые обработчики
        self.logger.handlers.clear()
        
        # Файловый обработчик
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Формат логов
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
    
    def info(self, message: str):
        """Записывает информационное сообщение"""
        self.logger.info(message)
    
    def error(self, message: str):
        """Записывает сообщение об ошибке"""
        self.logger.error(message)
    
    def warning(self, message: str):
        """Записывает предупреждение"""
        self.logger.warning(message)
    
    def debug(self, message: str):
        """Записывает отладочное сообщение"""
        self.logger.debug(message)
    
    def get_log_file_path(self) -> str:
        """Возвращает путь к текущему файлу лога"""
        return self.log_file


def setup_error_logger(counterparty_name: str, inn: str) -> logging.Logger:
    """Создает отдельный логгер для ошибок по конкретному контрагенту"""
    error_folder = "error_logs"
    os.makedirs(error_folder, exist_ok=True)

    # Создаем безопасное имя файла
    safe_name = "".join(c for c in counterparty_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name[:50]  # Ограничиваем длину

    log_file = os.path.join(error_folder, f"error_{safe_name}_{inn}.log")

    logger = logging.getLogger(f"error_{inn}")
    logger.setLevel(logging.DEBUG)

    # Убираем старые обработчики
    logger.handlers.clear()

    # Файловый обработчик
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger


def log_counterparty_error(counterparty_name: str, inn: str, error_message: str, details: str = ""):
    """Логирует ошибку по конкретному контрагенту в отдельный файл"""
    try:
        error_logger = setup_error_logger(counterparty_name, inn)
        error_logger.error(f"Контрагент: {counterparty_name} (ИНН: {inn})")
        error_logger.error(f"Ошибка: {error_message}")
        if details:
            error_logger.error(f"Детали: {details}")
        error_logger.error("=" * 50)
    except Exception as e:
        print(f"Не удалось записать лог ошибки: {e}")