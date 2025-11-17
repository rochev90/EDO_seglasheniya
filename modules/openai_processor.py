#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from typing import Tuple
import os
from dotenv import load_dotenv

load_dotenv()


class OpenAIProcessor:
    """Минимальный drop-in: прокси сохранены, только правильные поля для /responses.
    gpt-5* -> Responses API, gpt-4o/4.1 -> Chat Completions.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "gpt-5-nano"  # может быть перезаписана извне

        # Прокси
        proxy_user = os.getenv('proxy_user')
        proxy_pass = os.getenv('proxy_pass')
        proxy_host = "109.196.107.63"
        proxy_port = "1336"
        self.proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
        self.proxies = {"http": self.proxy_url, "https": self.proxy_url}

        self.chat_url = "https://api.openai.com/v1/chat/completions"
        self.responses_url = "https://api.openai.com/v1/responses"

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _use_responses_api(self) -> bool:
        m = (self.model or "").lower().strip()
        return m.startswith("gpt-5")  # всё семейство gpt-5 отправляем в /responses

    def convert_to_genitive(self, position: str, fio: str, max_retries: int = 3) -> Tuple[str, str]:
        """Возвращает (должность_в_родительном, ФИО_в_родительном)."""
        # Инструкцию НЕ кладём в поле 'system' для /responses — его там нет.
        instruction = (
            "Ты эксперт по русскому языку. "
            "Точно преобразуй должность и ФИО в родительный падеж. "
            "Верни ответ строго в формате: должность|ФИО"
        )
        user_part = f"Должность: {position}\nФИО: {fio}\nФормат: должность|ФИО"

        last_err = None
        for _ in range(max_retries):
            try:
                if self._use_responses_api():
                    # Responses API: 'system' нет, кладём инструкцию в input
                    payload = {
                        "model": self.model,
                        "input": instruction + "\n\n" + user_part,
                        "temperature": 0.1,
                        "max_output_tokens": 150
                    }
                    r = requests.post(self.responses_url, headers=self._headers(), json=payload,
                                      proxies=self.proxies, timeout=30)
                    if r.status_code != 200:
                        raise RuntimeError(f"Responses {r.status_code}: {r.text}")
                    js = r.json()
                    content = js.get("output_text")
                    if not content and js.get("choices"):
                        content = js["choices"][0].get("message", {}).get("content")
                else:
                    # Chat Completions API
                    payload = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": instruction},
                            {"role": "user", "content": user_part}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 150
                    }
                    r = requests.post(self.chat_url, headers=self._headers(), json=payload,
                                      proxies=self.proxies, timeout=30)
                    if r.status_code != 200:
                        raise RuntimeError(f"Chat {r.status_code}: {r.text}")
                    js = r.json()
                    content = js["choices"][0]["message"]["content"]

                if not content or "|" not in content:
                    raise ValueError("Некорректный формат ответа модели")
                p1, p2 = [p.strip() for p in content.split("|", 1)]
                if not p1 or not p2:
                    raise ValueError("Пустые части ответа модели")
                return p1, p2

            except Exception as e:
                last_err = str(e)
                continue

        raise Exception(f"Ошибка запроса к OpenAI API: {last_err}")
