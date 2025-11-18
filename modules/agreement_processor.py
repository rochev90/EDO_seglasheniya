#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from typing import Optional, Tuple, Callable
from datetime import datetime

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from modules.database_manager import DatabaseManager
from modules.openai_processor import OpenAIProcessor
from modules.document_processor import DocumentProcessor
from modules.logger_manager import LoggerManager
from modules.contur_focus import get_head_by_inn
from modules.diadoc_sender import DiadocClient  # Добавлен импорт


class AgreementProcessor:
    """Главный процессор для обработки соглашений"""

    def __init__(self, openai_api_key: str, output_folder: str = "Соглашения"):
        self.db_manager = DatabaseManager()
        self.openai_processor = OpenAIProcessor(openai_api_key)
        self.doc_processor = DocumentProcessor(output_folder=output_folder)
        self.logger = LoggerManager()
        self.diadoc_client = DiadocClient()  # Добавлен клиент Диадок

        # Callback для обновления GUI
        self.progress_callback: Optional[Callable[[str], None]] = None
        self.error_callback: Optional[Callable[[str, str], str]] = None

    def set_progress_callback(self, callback: Callable[[str], None]):
        """Устанавливает callback для обновления прогресса в GUI"""
        self.progress_callback = callback

    def set_error_callback(self, callback: Callable[[str, str], str]):
        """Устанавливает callback для обработки ошибок в GUI"""
        self.error_callback = callback

    def _log_and_update(self, message: str, level: str = "info"):
        """Логирует сообщение и обновляет GUI"""
        if level == "info":
            self.logger.info(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "warning":
            self.logger.warning(message)

        if self.progress_callback:
            self.progress_callback(message)

    def _get_head_info(self, inn: str, max_retries: int = 3) -> Optional[Tuple[str, str]]:
        """
        Получает информацию о руководителе через contur_focus

        Returns:
            Tuple[position, fio] или None при ошибке
        """
        for attempt in range(max_retries):
            try:
                position, fio = get_head_by_inn(inn)
                self._log_and_update(f"Получена информация о руководителе: {position} {fio}")
                return (position, fio)

            except Exception as e:
                self._log_and_update(
                    f"Ошибка при получении данных руководителя (попытка {attempt + 1}/{max_retries}): {str(e)}",
                    "error")

                if attempt < max_retries - 1:
                    continue

        return None

    def _send_to_diadoc(self, document_path: str, company: str, to_inn: str, to_kpp: str = "") -> bool:
        """
        Отправляет документ через Диадок

        Args:
            document_path: путь к документу
            company: компания отправителя
            to_inn: ИНН получателя
            to_kpp: КПП получателя

        Returns:
            True если успешно, False если ошибка
        """
        try:
            # Определяем ИНН отправителя в зависимости от компании
            if company == "КАДИС":
                from_inn = "7827004830"
            else:  # ЮрРегионИнформ
                from_inn = "7839305479"

            # Форматируем дату
            document_date = datetime.now().strftime("%d.%m.%Y")

            self._log_and_update(f"Отправка документа через Диадок...")
            self._log_and_update(f"От: {from_inn} (компания: {company})")
            self._log_and_update(f"Кому: ИНН {to_inn}" + (f", КПП {to_kpp}" if to_kpp else ""))

            # Отправляем документ
            result = self.diadoc_client.send_document(
                from_inn=from_inn,
                to_inn=to_inn,
                document_path=document_path,
                to_kpp=to_kpp,
                comment="Соглашение об ЭДО",
                document_date=document_date,
                need_recipient_signature=True
            )

            self._log_and_update(f"✅ Документ успешно отправлен через Диадок")
            self._log_and_update(f"ID сообщения: {result.get('MessageId', 'неизвестно')}")
            return True

        except Exception as e:
            self._log_and_update(f"❌ Ошибка отправки через Диадок: {str(e)}", "error")

            # Обработка ошибки через callback
            if self.error_callback:
                action = self.error_callback(
                    "Ошибка отправки через Диадок",
                    f"Не удалось отправить документ через Диадок.\n\nОшибка: {str(e)}"
                )

                if action == "abort":
                    return False
                elif action == "retry":
                    return self._send_to_diadoc(document_path, company, to_inn, to_kpp)
                elif action == "skip":
                    self._log_and_update("Пропуск отправки через Диадок", "warning")
                    return True

            return False

    def _process_ip(self, counterparty: dict, company: str) -> bool:
        """
        Обрабатывает ИП

        Returns:
            True если успешно, False если ошибка
        """
        inn = counterparty['ИНН']
        org_name = counterparty.get('Название организации', '')

        self._log_and_update(f"Обработка ИП: {org_name} (ИНН: {inn})")

        # Получаем данные руководителя
        head_info = self._get_head_info(inn)

        if not head_info:
            # Обработка ошибки через callback
            if self.error_callback:
                action = self.error_callback(
                    "Не удалось получить данные о руководителе",
                    f"ИНН: {inn}\nОрганизация: {org_name}"
                )

                if action == "abort":
                    return False
                elif action == "retry":
                    return self._process_ip(counterparty, company)
                elif action == "skip":
                    self._log_and_update(f"Пропуск ИП {org_name} (нет данных о руководителе)", "warning")
                    return True
            return False

        position, fio = head_info

        if position != "ИП":
            self._log_and_update(f"Ошибка: ожидался ИП, получено {position}", "error")
            return False

        # Формируем полное название ИП
        ip_full_name = f"ИП {fio}"

        # Заполняем документ
        try:
            output_path = self.doc_processor.fill_ip_template(
                company=company,
                ip_name=ip_full_name,
                ip_inn=inn,
                fio=fio
            )
            self._log_and_update(f"Создан документ: {output_path}")
        except Exception as e:
            self._log_and_update(f"Ошибка при создании документа: {str(e)}", "error")

            if self.error_callback:
                action = self.error_callback(
                    "Не удалось заполнить шаблон",
                    f"Ошибка: {str(e)}\n\n"
                )

                if action == "abort":
                    return False
                elif action == "retry":
                    return self._process_ip(counterparty, company)
            return False

        # Отправляем через Диадок
        if not self._send_to_diadoc(output_path, company, inn):
            return False

        # Добавляем в базу данных
        db_data = {
            "Название организации": ip_full_name,
            "Поставщик": counterparty.get("Поставщик", ""),
            "Количество": counterparty.get("Количество", ""),
            "ИНН": inn,
            "КПП": "",
            "Идентификатор участника ЭДО": "",
            "Статус": "Отправлено через Диадок",
            "Дата изменения статуса": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "ID организации": "",
            "ID ящика": ""
        }

        self.db_manager.add_counterparty(db_data, company)
        self._log_and_update(f"ИП {ip_full_name} добавлен в базу данных")

        return True

    def _process_ul(self, counterparty: dict, company: str) -> bool:
        """
        Обрабатывает юридическое лицо

        Returns:
            True если успешно, False если ошибка
        """
        inn = counterparty['ИНН']
        kpp = counterparty.get('КПП', '')
        org_name = counterparty.get('Название организации', '')

        self._log_and_update(f"Обработка ЮЛ: {org_name} (ИНН: {inn})")

        # Получаем данные руководителя
        head_info = self._get_head_info(inn)

        if not head_info:
            # Обработка ошибки через callback
            if self.error_callback:
                action = self.error_callback(
                    "Не удалось получить данные о руководителе",
                    f"ИНН: {inn}\nОрганизация: {org_name}"
                )

                if action == "abort":
                    return False
                elif action == "retry":
                    return self._process_ul(counterparty, company)
                elif action == "skip":
                    self._log_and_update(f"Пропуск {org_name} (нет данных о руководителе)", "warning")
                    return True
            return False

        position, fio = head_info

        if position == "ИП":
            self._log_and_update(f"Ошибка: ожидалось ЮЛ, получен ИП", "error")
            return False

        # Преобразуем в родительный падеж через OpenAI
        position_gen = None
        fio_gen = None

        try:
            position_gen, fio_gen = self.openai_processor.convert_to_genitive(position, fio)
            self._log_and_update(f"Преобразовано в родительный падеж: {position_gen} {fio_gen}")
        except Exception as e:
            self._log_and_update(f"Ошибка OpenAI API: {str(e)}", "error")

            if self.error_callback:
                action = self.error_callback(
                    "Ошибка OpenAI API",
                    f"Не удалось преобразовать в родительный падеж.\nОшибка: {str(e)}"
                )

                if action == "abort":
                    return False
                elif action == "retry":
                    return self._process_ul(counterparty, company)
                elif action == "skip":
                    # Используем именительный падеж
                    position_gen = position.lower()
                    fio_gen = fio
                    self._log_and_update(f"Используется именительный падеж (пропуск OpenAI)", "warning")

        # Заполняем документ
        try:
            output_path = self.doc_processor.fill_ul_template(
                company=company,
                org_name=org_name,
                inn=inn,
                kpp=kpp,
                position=position,
                fio=fio,
                post_fixed=position_gen,
                fio_fixed=fio_gen
            )
            self._log_and_update(f"Создан документ: {output_path}")
        except Exception as e:
            self._log_and_update(f"Ошибка при создании документа: {str(e)}", "error")

            if self.error_callback:
                action = self.error_callback(
                    "Не удалось заполнить шаблон",
                    f"Ошибка: {str(e)}\n\n"
                )

                if action == "abort":
                    return False
                elif action == "retry":
                    return self._process_ul(counterparty, company)
            return False

        # Отправляем через Диадок
        if not self._send_to_diadoc(output_path, company, inn, kpp):
            return False

        # Добавляем в базу данных
        db_data = {
            "Название организации": org_name,
            "Поставщик": counterparty.get("Поставщик", ""),
            "Количество": counterparty.get("Количество", ""),
            "ИНН": inn,
            "КПП": kpp,
            "Идентификатор участника ЭДО": "",
            "Статус": "Отправлено через Диадок",
            "Дата изменения статуса": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "ID организации": "",
            "ID ящика": ""
        }

        self.db_manager.add_counterparty(db_data, company)
        self._log_and_update(f"{org_name} добавлен в базу данных")

        return True

    def process_counterparties(self, csv_path: str, company: str) -> Tuple[int, int]:
        """
        Обрабатывает контрагентов из CSV файла

        Args:
            csv_path: путь к CSV файлу
            company: КАДИС или ЮрРегионИнформ

        Returns:
            Tuple[успешно обработано, всего новых]
        """
        self._log_and_update(f"Начало обработки контрагентов для компании {company}")
        self._log_and_update(f"Загрузка файла: {csv_path}")

        # Получаем новых контрагентов
        try:
            new_counterparties = self.db_manager.get_new_counterparties(csv_path, company)
            total = len(new_counterparties)

            if total == 0:
                self._log_and_update("Новых контрагентов не найдено")
                return (0, 0)

            self._log_and_update(f"Найдено новых контрагентов: {total}")

        except Exception as e:
            self._log_and_update(f"Ошибка при загрузке контрагентов: {str(e)}", "error")
            return (0, 0)

        # Обрабатываем каждого контрагента
        processed = 0
        for i, counterparty in enumerate(new_counterparties, 1):
            self._log_and_update(f"\n{'=' * 60}")
            self._log_and_update(f"Обработка {i}/{total}")

            inn = counterparty.get('ИНН', '')

            # Определяем тип: ИП или ЮЛ через длину ИНН
            if len(inn) == 12:
                # ИП
                success = self._process_ip(counterparty, company)
            else:
                # ЮЛ
                success = self._process_ul(counterparty, company)

            if success:
                processed += 1
            else:
                # Если abort, прерываем обработку
                break

        self._log_and_update(f"\n{'=' * 60}")
        self._log_and_update(f"Обработка завершена. Успешно: {processed}/{total}")

        return (processed, total)

    def process_by_period(self, company: str, csv_path: str, date_from: str, date_to: str) -> int:
        """Добавляет недостающих в БД и формирует соглашения только за период.
        date_from/date_to: 'dd.mm.yyyy' включительно.
        Возвращает число созданных документов.
        """
        from datetime import datetime
        import pandas as pd
        # загрузим CSV так же, как при создании БД
        df = self.db_manager._load_csv(csv_path)
        for col in self.db_manager.columns:
            if col not in df.columns:
                df[col] = ""
        df['ИНН'] = df['ИНН'].apply(self.db_manager._fix_inn_format)
        if 'КПП' in df.columns:
            df['КПП'] = df['КПП'].apply(self.db_manager._fix_inn_format)

        # добавить недостающих в БД
        for _, row in df.iterrows():
            inn = row.get('ИНН', '')
            if inn and not self.db_manager.check_inn_exists(inn, company):
                self.db_manager.add_counterparty({c: row.get(c, '') for c in self.db_manager.columns}, company)

        def parse_date(v):
            s = str(v).strip()
            if not s:
                return None
            d = s.split()[0]
            try:
                return datetime.strptime(d, "%d.%m.%Y").date()
            except Exception:
                return None

        d_from = datetime.strptime(date_from, "%d.%m.%Y").date()
        d_to = datetime.strptime(date_to, "%d.%m.%Y").date()

        created = 0
        for _, row in df.iterrows():
            d = parse_date(row.get('Дата изменения статуса', ''))
            if d and d_from <= d <= d_to:
                inn = row.get('ИНН', '')
                name = row.get('Название организации', '')
                kpp = row.get('КПП', '')
                if len(inn) == 12:
                    ok = self._process_ip({"ИНН": inn, "Название организации": name}, company)
                elif len(inn) == 10:
                    ok = self._process_ul({"ИНН": inn, "КПП": kpp, "Название организации": name}, company)
                else:
                    ok = False
                if ok:
                    created += 1
        return created