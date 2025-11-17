#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import os
from typing import Optional, List
from datetime import datetime


class DatabaseManager:
    """Менеджер для работы с базами данных контрагентов"""
    
    def __init__(self, db_folder: str = "database"):
        self.db_folder = db_folder
        self.kadis_db_path = os.path.join(db_folder, "kadis_counterparties.csv")
        self.uri_db_path = os.path.join(db_folder, "uri_counterparties.csv")
        
        # Колонки для базы данных
        self.columns = [
            "Название организации",
            "Поставщик",
            "Количество",
            "ИНН",
            "КПП",
            "Идентификатор участника ЭДО",
            "Статус",
            "Дата изменения статуса",
            "ID организации",
            "ID ящика"
        ]
    
    
    def _load_csv(self, csv_path: str):
        """Пытается прочитать CSV с разными кодировками и разделителями. Возвращает DataFrame с dtype=str."""
        import pandas as pd
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
    
    def create_database_from_csv(self, csv_path: str, company: str) -> bool:
        """Создает базу данных из CSV (только 3 столбца: Название организации, ИНН, КПП). Дубликаты по ИНН удаляются."""
        try:
            import pandas as pd
            df = self._load_csv(csv_path)

            # Допускаем различные вариации названия 1-го столбца
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

            # Приводим ИНН/КПП к строке и чистим формат
            df['ИНН'] = df['ИНН'].apply(self._fix_inn_format)
            if 'КПП' in df.columns:
                df['КПП'] = df['КПП'].apply(lambda x: self._fix_inn_format(x) if str(x).strip() else "")

            # Убираем пустые ИНН и дубли по ИНН
            df = df[df['ИНН'].astype(str).str.len() > 0]
            df = df.drop_duplicates(subset=['ИНН'], keep='first')

            # Сохраняем как БД выбранной компании (может содержать только эти 3 колонки — это нормально)
            db_path = self.kadis_db_path if company == "КАДИС" else self.uri_db_path
            # Если нужен полный набор колонок — расширим пустыми перед сохранением
            out = pd.DataFrame(columns=self.columns)
            if not df.empty:
                out = df.merge(out, how='right', right_index=True, left_index=True)  # ensure columns exist
                # Более простой способ — совместить: 
                out = pd.concat([df, pd.DataFrame(columns=[c for c in self.columns if c not in df.columns])], axis=1)
                out = out[self.columns] if all(c in out.columns for c in self.columns) else out
            out.to_csv(db_path, index=False, encoding='utf-8-sig')
            return True
        except Exception as e:
            raise Exception(f"Ошибка создания базы данных: {str(e)}")
        
    def _fix_inn_format(self, inn) -> str:
        """Исправляет формат ИНН из научной нотации"""
        if not inn or pd.isna(inn):
            return ""
        
        # Если уже строка
        inn_str = str(inn).strip()
        
        # Убираем пробелы
        inn_str = inn_str.replace(' ', '')
        
        # Если пусто
        if not inn_str:
            return ""
        
        # Если в научной нотации (7,84806E+11 или 7.84806E+11)
        if 'E' in inn_str.upper() or 'e' in inn_str:
            try:
                # Заменяем запятую на точку и преобразуем
                inn_str = inn_str.replace(',', '.')
                inn_float = float(inn_str)
                inn_int = int(inn_float)
                return str(inn_int)
            except:
                return inn_str
        
        # Если есть .0 в конце
        if inn_str.endswith('.0'):
            inn_str = inn_str[:-2]
        
        # Убираем все нецифровые символы
        inn_clean = ''.join(c for c in inn_str if c.isdigit())
        
        return inn_clean if inn_clean else ""
    
    def check_inn_exists(self, inn: str, company: str) -> bool:
        """
        Проверяет существует ли ИНН в базе данных
        
        Args:
            inn: ИНН для проверки
            company: название компании
            
        Returns:
            True если существует, False если нет
        """
        db_path = self.kadis_db_path if company == "КАДИС" else self.uri_db_path
        
        if not os.path.exists(db_path):
            return False
        
        try:
            df = pd.read_csv(db_path, encoding='utf-8-sig', dtype={'ИНН': str})
            df['ИНН'] = df['ИНН'].apply(self._fix_inn_format)
            inn_fixed = self._fix_inn_format(inn)
            return inn_fixed in df['ИНН'].values
        except Exception as e:
            raise Exception(f"Ошибка проверки ИНН в базе: {str(e)}")
    
    def add_counterparty(self, data: dict, company: str) -> bool:
        """
        Добавляет контрагента в базу данных
        
        Args:
            data: словарь с данными контрагента
            company: название компании
            
        Returns:
            True если успешно
        """
        db_path = self.kadis_db_path if company == "КАДИС" else self.uri_db_path
        
        try:
            # Читаем существующую БД или создаем новую
            if os.path.exists(db_path):
                df = pd.read_csv(db_path, encoding='utf-8-sig', dtype={'ИНН': str, 'КПП': str})
            else:
                df = pd.DataFrame(columns=self.columns)
            
            # Добавляем новую запись
            new_row = pd.DataFrame([data])
            for col in self.columns:
            	if col not in df.columns:
            		df[col] = ''
            for col in self.columns:
            	if col not in new_row.columns:
            		new_row[col] = ''
            df = pd.concat([df[self.columns], new_row[self.columns]], ignore_index=True)
            
            # Сохраняем
            df.to_csv(db_path, index=False, encoding='utf-8-sig')
            return True
        except Exception as e:
            raise Exception(f"Ошибка добавления контрагента в БД: {str(e)}")
    
    def get_new_counterparties(self, csv_path: str, company: str) -> List[dict]:
        """
        Получает список новых контрагентов (которых нет в БД)
        
        Args:
            csv_path: путь к CSV файлу с контрагентами
            company: название компании
            
        Returns:
            Список словарей с данными новых контрагентов
        """
        try:
            # Пробуем разные кодировки и разделители
            df = None
            for encoding in ['cp1251', 'windows-1251', 'utf-8-sig', 'utf-8', 'latin1']:
                for sep in [';', ',', '\t']:
                    try:
                        # Читаем всё как строки
                        df = pd.read_csv(csv_path, encoding=encoding, sep=sep, dtype=str, keep_default_na=False)
                        if len(df.columns) > 1:
                            break
                    except:
                        continue
                if df is not None and len(df.columns) > 1:
                    break
            
            if df is None or len(df.columns) <= 1:
                raise Exception("Не удалось прочитать CSV файл. Проверьте формат и кодировку.")
            
            # Исправляем формат ИНН
            if 'ИНН' in df.columns:
                df['ИНН'] = df['ИНН'].apply(self._fix_inn_format)
            
            # Исправляем формат КПП
            if 'КПП' in df.columns:
                df['КПП'] = df['КПП'].apply(lambda x: self._fix_inn_format(x) if x and str(x).strip() else "")
            
            # Фильтруем только новые
            new_counterparties = []
            for _, row in df.iterrows():
                inn = row.get('ИНН', '')
                if inn and not self.check_inn_exists(inn, company):
                    new_counterparties.append(row.to_dict())
            
            return new_counterparties
        except Exception as e:
            raise Exception(f"Ошибка получения новых контрагентов: {str(e)}")
    
    def database_exists(self, company: str) -> bool:
        """Проверяет существует ли база данных для компании"""
        db_path = self.kadis_db_path if company == "КАДИС" else self.uri_db_path
        return os.path.exists(db_path)
