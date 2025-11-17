#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from typing import Tuple
import os
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class OpenAIProcessor:
    """Процессор для работы с OpenAI Chat API (gpt-4o-mini)."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "gpt-4o-mini"

        # Прокси
        proxy_user = os.getenv('proxy_user')
        proxy_pass = os.getenv('proxy_pass')
        proxy_host = "109.196.107.63"
        proxy_port = "1336"
        self.proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
        self.proxies = {"http": self.proxy_url, "https": self.proxy_url}

        self.chat_url = "https://api.openai.com/v1/chat/completions"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def convert_to_genitive(self, position: str, fio: str, max_retries: int = 3) -> Tuple[str, str]:
        """Возвращает (должность_в_родительном, ФИО_в_родительном)."""
        instruction = (
            "Ты эксперт по русскому языку. "
            "Преобразуй должность и ФИО в родительный падеж (кого? чего?). "
            "Верни ТОЛЬКО результат в формате: должность|ФИО\n\n"
            "Примеры:\n"
            "Генеральный директор|Иванов Иван Иванович -> Генерального директора|Иванова Ивана Ивановича\n"
            "Директор|Петров Петр Петрович -> Директора|Петрова Петра Петровича"
        )
        user_part = f"Должность: {position}\nФИО: {fio}"

        last_err = None
        last_response = None

        for attempt in range(max_retries):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": user_part}
                    ],
                    "max_tokens": 200,
                    "temperature": 0.1
                }

                logger.debug(f"Попытка {attempt + 1}: Chat API ({self.model})")
                r = requests.post(self.chat_url, headers=self._headers(), json=payload,
                                  proxies=self.proxies, timeout=30)

                if r.status_code != 200:
                    logger.error(f"Ошибка API: {r.text}")
                    raise RuntimeError(f"Chat API {r.status_code}: {r.text}")

                js = r.json()
                content = js["choices"][0]["message"]["content"]
                last_response = content

                logger.info(f"Попытка {attempt + 1}: Получен ответ: '{content}'")

                # Очистка ответа
                content = content.strip()

                # Убираем markdown если есть
                if content.startswith("```") and content.endswith("```"):
                    content = content[3:-3].strip()

                # Если многострочный - берем первую строку с |
                if '\n' in content:
                    for line in content.split('\n'):
                        line = line.strip()
                        if '|' in line:
                            content = line
                            break

                # Проверка разделителя
                if "|" not in content:
                    raise ValueError(f"Нет разделителя | в ответе: {content}")

                # Разделение
                parts = content.split("|", 1)
                p1, p2 = parts[0].strip(), parts[1].strip()

                if not p1 or not p2:
                    raise ValueError(f"Пустые части: '{p1}' | '{p2}'")

                # Проверка что было преобразование
                if p1.lower() == position.lower() and p2.lower() == fio.lower():
                    logger.warning("Модель вернула исходные данные без изменений")
                    raise ValueError("Не преобразовано в родительный падеж")

                logger.info(f"✓ Успешно: {position} {fio} → {p1} {p2}")
                return p1, p2

            except Exception as e:
                last_err = str(e)
                logger.warning(f"Попытка {attempt + 1}/{max_retries} неудачна: {last_err}")
                if attempt < max_retries - 1:
                    logger.info("Повторяю запрос...")
                continue

        # Все попытки неудачны
        error_msg = f"Ошибка после {max_retries} попыток: {last_err}"
        if last_response:
            error_msg += f"\nПоследний ответ: {last_response}"
        logger.error(error_msg)
        raise Exception(error_msg)