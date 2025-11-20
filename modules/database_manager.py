#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import pandas as pd
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер для работы с SQLite базой данных контрагентов"""

    def __init__(self, db_folder: str = "database"):
        self.db_folder = db_folder
        os.makedirs(db_folder, exist_ok=True)
        self.db_path = os.path.join(db_folder, "counterparties.db")

        # Колонки для базы данных
        self.core_columns = ["Название организации", "ИНН", "КПП", "Дата изменения статуса"]
        self.full_columns = [
            "Название организации", "ИНН", "КПП", "Идентификатор участника ЭДО",
            "Статус", "Дата изменения статуса", "ID организации", "ID ящика"
        ]

        self._init_database()

    def _init_database(self):
        """Инициализация SQLite базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Таблица для КАДИС
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS kadis_counterparties (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        org_name TEXT NOT NULL,
                        inn TEXT UNIQUE NOT NULL,
                        kpp TEXT,
                        status_date TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица для ЮрРегионИнформ
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS uri_counterparties (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        org_name TEXT NOT NULL,
                        inn TEXT UNIQUE NOT NULL,
                        kpp TEXT,
                        status_date TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Индексы для быстрого поиска
                conn.execute('CREATE INDEX IF NOT EXISTS idx_kadis_inn ON kadis_counterparties(inn)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_uri_inn ON uri_counterparties(inn)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_kadis_status_date ON kadis_counterparties(status_date)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_uri_status_date ON uri_counterparties(status_date)')

                conn.commit()
                logger.info("База данных SQLite инициализирована")

        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {str(e)}")
            raise

    def _get_table_name(self, company: str) -> str:
        """Возвращает имя таблицы для компании"""
        if company == "КАДИС":
            return "kadis_counterparties"
        elif company == "ЮрРегионИнформ":
            return "uri_counterparties"
        else:
            raise ValueError(f"Неизвестная компания: {company}")

    def _load_csv(self, csv_path: str) -> pd.DataFrame:
        """Пытается прочитать CSV с разными кодировками и разделителями."""
        df = None
        for encoding in ['cp1251', 'windows-1251', 'utf-8-sig', 'utf-8', 'latin1']:
            for sep in [';', ',', '\t']:
                try:
                    df = pd.read_csv(csv_path, encoding=encoding, sep=sep, dtype=str, keep_default_na=False)
                    if len(df.columns) > 1 or (len(df.columns) == 1 and df.shape[0] > 0):
                        break
                except Exception:
                    continue
            if df is not None and (len(df.columns) > 1 or (len(df.columns) == 1 and df.shape[0] > 0)):
                break

        if df is None:
            raise Exception("Не удалось прочитать CSV файл. Проверьте формат и кодировку.")
        return df

    def _fix_inn_format(self, inn) -> str:
        """Исправляет формат ИНН из научной нотации"""
        if not inn or pd.isna(inn):
            return ""

        inn_str = str(inn).strip().replace(' ', '')

        if not inn_str:
            return ""

        # Обработка научной нотации
        if 'E' in inn_str.upper() or 'e' in inn_str:
            try:
                inn_str = inn_str.replace(',', '.')
                inn_float = float(inn_str)
                inn_int = int(inn_float)
                return str(inn_int)
            except:
                return inn_str

        # Убираем .0 в конце
        if inn_str.endswith('.0'):
            inn_str = inn_str[:-2]

        # Оставляем только цифры
        inn_clean = ''.join(c for c in inn_str if c.isdigit())

        return inn_clean if inn_clean else ""

    def create_database_from_csv(self, csv_path: str, company: str) -> bool:
        """Создает базу данных из CSV (только 3 столбца). Дубликаты по ИНН игнорируются."""
        try:
            df = self._load_csv(csv_path)

            # Допускаем различные вариации названия столбцов
            rename_map = {
                'Юр.лицо': 'Название организации',
                'Юр. лицо': 'Название организации',
                'Название': 'Название организации',
                'Организация': 'Название организации',
            }

            for k, v in rename_map.items():
                if k in df.columns and 'Название организации' not in df.columns:
                    df.rename(columns={k: v}, inplace=True)

            # Оставляем только нужные колонки
            keep = ['Название организации', 'ИНН', 'КПП']
            for col in keep:
                if col not in df.columns:
                    df[col] = ""

            df = df[keep]

            # Чистим формат ИНН/КПП
            df['ИНН'] = df['ИНН'].apply(self._fix_inn_format)
            if 'КПП' in df.columns:
                df['КПП'] = df['КПП'].apply(lambda x: self._fix_inn_format(x) if str(x).strip() else "")

            # Убираем пустые ИНН
            df = df[df['ИНН'].astype(str).str.len() > 0]

            # Вставляем в SQLite (дубликаты ИНН будут проигнорированы благодаря UNIQUE constraint)
            table_name = self._get_table_name(company)
            with sqlite3.connect(self.db_path) as conn:
                for _, row in df.iterrows():
                    try:
                        conn.execute(
                            f'INSERT INTO {table_name} (org_name, inn, kpp) VALUES (?, ?, ?)',
                            (row['Название организации'], row['ИНН'], row.get('КПП', ''))
                        )
                    except sqlite3.IntegrityError:
                        # Игнорируем дубликаты ИНН
                        continue

                conn.commit()

            logger.info(f"База данных для {company} создана из CSV. Добавлено записей: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания базы данных: {str(e)}")
            raise Exception(f"Ошибка создания базы данных: {str(e)}")

    def check_inn_exists(self, inn: str, company: str) -> bool:
        """Проверяет существует ли ИНН в базе данных"""
        try:
            table_name = self._get_table_name(company)
            inn_fixed = self._fix_inn_format(inn)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    f'SELECT 1 FROM {table_name} WHERE inn = ? LIMIT 1',
                    (inn_fixed,)
                )
                return cursor.fetchone() is not None

        except Exception as e:
            logger.error(f"Ошибка проверки ИНН в БД: {str(e)}")
            raise Exception(f"Ошибка проверки ИНН в базе: {str(e)}")

    def add_counterparty(self, data: dict, company: str) -> bool:
        """Добавляет контрагента в базу данных"""
        try:
            table_name = self._get_table_name(company)

            # Извлекаем только нужные поля
            org_name = data.get('Название организации', '')
            inn = self._fix_inn_format(data.get('ИНН', ''))
            kpp = self._fix_inn_format(data.get('КПП', '')) if data.get('КПП') else ''
            status_date = data.get('Дата изменения статуса', '')

            if not inn:
                raise ValueError("ИНН не может быть пустым")

            with sqlite3.connect(self.db_path) as conn:
                # Используем INSERT OR REPLACE для обновления существующих записей
                conn.execute(
                    f'''INSERT OR REPLACE INTO {table_name} 
                        (org_name, inn, kpp, status_date, updated_at) 
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)''',
                    (org_name, inn, kpp, status_date)
                )
                conn.commit()

            return True

        except Exception as e:
            logger.error(f"Ошибка добавления контрагента в БД: {str(e)}")
            raise Exception(f"Ошибка добавления контрагента в БД: {str(e)}")

    def get_new_counterparties(self, csv_path: str, company: str, date_from: str = None, date_to: str = None) -> List[
        dict]:
        """
        Получает список новых контрагентов (которых нет в БД ИЛИ с датой в указанном периоде)

        Args:
            csv_path: путь к CSV файлу с контрагентами
            company: название компании
            date_from: начальная дата периода (dd.mm.yyyy)
            date_to: конечная дата периода (dd.mm.yyyy)

        Returns:
            Список словарей с данными новых контрагентов
        """
        try:
            df = self._load_csv(csv_path)

            # ДИАГНОСТИКА: выведем какие колонки есть в CSV
            logger.info(f"Колонки в CSV файле: {list(df.columns)}")
            logger.info(f"Всего строк в CSV: {len(df)}")

            # Стандартизируем названия колонок
            column_mapping = {
                'Юр.лицо': 'Название организации',
                'Юр. лицо': 'Название организации',
                'Название': 'Название организации',
                'Организация': 'Название организации',
                'Дата изменения': 'Дата изменения статуса',
                'Дата': 'Дата изменения статуса',
                'ДатаСтатуса': 'Дата изменения статуса',
            }

            for old_col, new_col in column_mapping.items():
                if old_col in df.columns and new_col not in df.columns:
                    df.rename(columns={old_col: new_col}, inplace=True)
                    logger.info(f"Переименована колонка: '{old_col}' -> '{new_col}'")

            # Обеспечиваем наличие обязательных колонок
            required_cols = ['Название организации', 'ИНН']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = ""
                    logger.warning(f"Колонка '{col}' отсутствует в CSV, создана пустая")

            # Чистим формат
            df['ИНН'] = df['ИНН'].apply(self._fix_inn_format)
            if 'КПП' in df.columns:
                df['КПП'] = df['КПП'].apply(lambda x: self._fix_inn_format(x) if str(x).strip() else "")

            # ДИАГНОСТИКА: покажем несколько ИНН из CSV
            logger.info(f"Примеры ИНН из CSV: {df['ИНН'].head(5).tolist()}")

            # Функция для фильтрации по дате (берет только дату без времени)
            def date_in_period(date_str):
                if not date_str or not str(date_str).strip():
                    return True  # Если даты нет - включаем в обработку
                try:
                    # Берем только часть до пробела (дату без времени)
                    date_only = str(date_str).strip().split()[0] if ' ' in str(date_str) else str(date_str).strip()

                    # Пробуем разные форматы дат
                    date_formats = ['%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%d.%m.%y']
                    for fmt in date_formats:
                        try:
                            date_obj = datetime.strptime(date_only, fmt).date()
                            return date_from_obj.date() <= date_obj <= date_to_obj.date()
                        except:
                            continue
                    return False
                except:
                    return True  # При ошибке парсинга включаем в обработку

            # Фильтруем по периоду если указаны даты
            if date_from and date_to:
                if 'Дата изменения статуса' in df.columns:
                    try:
                        # Конвертируем даты для сравнения
                        date_from_obj = datetime.strptime(date_from, '%d.%m.%Y')
                        date_to_obj = datetime.strptime(date_to, '%d.%m.%Y')

                        # Применяем фильтрацию
                        before_count = len(df)
                        df = df[df['Дата изменения статуса'].apply(date_in_period)]
                        after_count = len(df)

                        logger.info(f"Фильтрация по дате: {before_count} -> {after_count} строк")

                        # ДИАГНОСТИКА: покажем примеры обработки дат
                        if len(df) > 0:
                            sample_dates = df['Дата изменения статуса'].head(3).tolist()
                            processed_samples = []
                            for date_str in sample_dates:
                                if date_str and ' ' in str(date_str):
                                    processed_samples.append(f"'{date_str}' -> '{date_str.split()[0]}'")
                                else:
                                    processed_samples.append(f"'{date_str}'")

                            logger.info(f"Примеры обработки дат: {', '.join(processed_samples)}")

                    except Exception as e:
                        logger.warning(f"Ошибка фильтрации по дате: {e}. Будут обработаны все контрагенты.")
                else:
                    logger.warning(
                        "Колонка 'Дата изменения статуса' не найдена в CSV. Фильтрация по дате не применяется.")
            else:
                logger.info("Даты периода не указаны, фильтрация по дате не применяется")

            # Фильтруем только те, которых нет в БД
            new_counterparties = []
            found_in_db = 0

            for _, row in df.iterrows():
                inn = row.get('ИНН', '')
                if inn:
                    if not self.check_inn_exists(inn, company):
                        counterparty_data = {
                            'Название организации': row.get('Название организации', ''),
                            'ИНН': inn,
                            'КПП': row.get('КПП', ''),
                            'Дата изменения статуса': row.get('Дата изменения статуса', '')
                        }
                        new_counterparties.append(counterparty_data)
                    else:
                        found_in_db += 1

            logger.info(f"Найдено новых контрагентов: {len(new_counterparties)}")
            logger.info(f"Уже есть в БД: {found_in_db}")
            logger.info(f"Всего обработано: {len(new_counterparties) + found_in_db}")

            return new_counterparties

        except Exception as e:
            logger.error(f"Ошибка получения новых контрагентов: {str(e)}")
            raise Exception(f"Ошибка получения новых контрагентов: {str(e)}")

    def database_exists(self, company: str) -> bool:
        """Проверяет существует ли база данных для компании"""
        try:
            table_name = self._get_table_name(company)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                return cursor.fetchone() is not None
        except:
            return False

    def export_to_csv(self, company: str, output_path: str = None) -> str:
        """Экспортирует базу данных в CSV для просмотра"""
        try:
            table_name = self._get_table_name(company)

            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

            if output_path is None:
                output_path = os.path.join(self.db_folder, f"{company}_counterparties.csv")

            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            return output_path

        except Exception as e:
            logger.error(f"Ошибка экспорта в CSV: {str(e)}")
            raise