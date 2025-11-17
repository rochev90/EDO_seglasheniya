#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Добавляем путь к модулям
sys.path.append(os.path.dirname(__file__))

from modules.database_manager import DatabaseManager
from modules.agreement_processor import AgreementProcessor


class AgreementGeneratorGUI:
    """Главное окно приложения"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Генератор соглашений ЭДО")
        self.root.geometry("1200x700")
        self.root.resizable(True, True)
        
        # Настройки
        self.config_file = "config.json"
        self.load_config()
        
        # OpenAI API Key
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        
        # OpenAI модель
        self.openai_model = self.config.get("openai_model", "gpt-4o-mini")
        
        # Менеджер БД
        self.db_manager = DatabaseManager()
        
        # Процессор
        self.processor = AgreementProcessor(
            openai_api_key=self.openai_api_key,
            output_folder=self.config["output_folder"]
        )
        self.processor.set_progress_callback(self.update_log)
        self.processor.set_error_callback(self.handle_error)
        
        # Переменные
        self.selected_company = tk.StringVar(value="КАДИС")
        self.processing = False
        # Период по умолчанию: месяц назад по сегодня
        from datetime import datetime, timedelta
        today = datetime.now()
        month_ago = today - timedelta(days=30)
        self.date_from_var = tk.StringVar(value=month_ago.strftime('%d.%m.%Y'))
        self.date_to_var = tk.StringVar(value=today.strftime('%d.%m.%Y'))
        
        # Создаем интерфейс
        self.create_ui()
    
    def load_config(self):
        """Загружает конфигурацию"""
        self.config = {
            "output_folder": "Соглашения",
            "openai_model": "gpt-4o-mini"
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
            except:
                pass
    
    def save_config(self):
        """Сохраняет конфигурацию"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def create_ui(self):
        """Создает интерфейс"""
        # Стили
        style = ttk.Style()
        style.theme_use('clam')
        
        # Настройка цветов
        bg_color = "#f0f0f0"
        self.root.configure(bg=bg_color)
        
        # Главный контейнер
        main_frame = tk.Frame(self.root, bg=bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Левая панель - управление
        left_frame = tk.Frame(main_frame, bg=bg_color, width=500)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        left_frame.pack_propagate(False)
        
        # Правая панель - логи
        right_frame = tk.Frame(main_frame, bg=bg_color)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # === ЛЕВАЯ ПАНЕЛЬ ===
        
        # Заголовок
        title_label = tk.Label(
            left_frame,
            text="Генератор соглашений ЭДО",
            font=("Arial", 18, "bold"),
            bg=bg_color,
            fg="#2c3e50"
        )
        title_label.pack(pady=(0, 30))
        
        # Выбор компании и генерация
        generate_frame = tk.LabelFrame(
            left_frame,
            text="Генерация соглашений",
            font=("Arial", 12, "bold"),
            bg=bg_color,
            fg="#2c3e50",
            padx=20,
            pady=15
        )
        generate_frame.pack(fill=tk.X, pady=(0, 20))
        
        
        # Верхняя строка с выбором компании (слева) и периодом (справа)
        top_row = tk.Frame(generate_frame, bg=bg_color)
        top_row.pack(fill=tk.X)

        # Левая часть — компания
        left_col = tk.Frame(top_row, bg=bg_color)
        left_col.pack(side=tk.LEFT, anchor=tk.NW)

        company_label = tk.Label(left_col, text="Выберите компанию:", bg=bg_color, font=("Arial", 11, "bold"))
        company_label.pack(anchor=tk.W, pady=(0, 10))

        kadis_radio = tk.Radiobutton(left_col, text="КАДИС", variable=self.selected_company, value="КАДИС", bg=bg_color, font=("Arial", 11), selectcolor=bg_color)
        kadis_radio.pack(anchor=tk.W, pady=2)

        uri_radio = tk.Radiobutton(left_col, text="ЮрРегионИнформ", variable=self.selected_company, value="ЮрРегионИнформ", bg=bg_color, font=("Arial", 11), selectcolor=bg_color)
        uri_radio.pack(anchor=tk.W, pady=2)

        # Правая часть — период
        right_col = tk.Frame(top_row, bg=bg_color)
        right_col.pack(side=tk.RIGHT, anchor=tk.NE, padx=(20,0))

        period_lbl = tk.Label(right_col, text="Период (дата изменения статуса):", bg=bg_color, font=("Arial", 11, "bold"))
        period_lbl.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0,4))

        tk.Label(right_col, text="с", bg=bg_color).grid(row=1, column=0, sticky="e")
        self.date_from_entry = tk.Entry(right_col, width=12, textvariable=self.date_from_var)
        self.date_from_entry.grid(row=1, column=1, sticky="w", padx=(4,10))

        tk.Label(right_col, text="по", bg=bg_color).grid(row=1, column=2, sticky="e")
        self.date_to_entry = tk.Entry(right_col, width=12, textvariable=self.date_to_var)
        self.date_to_entry.grid(row=1, column=3, sticky="w", padx=(4,0))

# Кнопка генерации
        self.generate_btn = tk.Button(
            generate_frame,
            text="📄 Сформировать соглашения",
            command=self.start_processing,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 13, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=12,
            cursor="hand2"
        )
        self.generate_btn.pack(pady=(15, 0))
        
        # Настройки
        settings_frame = tk.LabelFrame(
            left_frame,
            text="Настройки",
            font=("Arial", 12, "bold"),
            bg=bg_color,
            fg="#2c3e50",
            padx=20,
            pady=15
        )
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        # Модель OpenAI
        tk.Label(
            settings_frame,
            text="Модель OpenAI:",
            bg=bg_color,
            font=("Arial", 10, "bold")
        ).pack(anchor=tk.W, pady=(0, 5))
        
        model_frame = tk.Frame(settings_frame, bg=bg_color)
        model_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.model_entry = tk.Entry(model_frame, font=("Arial", 10))
        self.model_entry.insert(0, self.openai_model)
        self.model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        save_model_btn = tk.Button(
            model_frame,
            text="✓",
            command=self.save_model,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            width=3,
            relief=tk.FLAT
        )
        save_model_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        tk.Label(
            settings_frame,
            text="Примеры: gpt-4o, gpt-4o-mini, gpt-5-nano",
            bg=bg_color,
            font=("Arial", 8),
            fg="#7f8c8d"
        ).pack(anchor=tk.W, pady=(0, 15))
        
        # Путь сохранения
        tk.Label(
            settings_frame,
            text="Папка для соглашений:",
            bg=bg_color,
            font=("Arial", 10, "bold")
        ).pack(anchor=tk.W, pady=(0, 5))
        
        output_folder_frame = tk.Frame(settings_frame, bg=bg_color)
        output_folder_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.output_folder_entry = tk.Entry(output_folder_frame, font=("Arial", 9))
        self.output_folder_entry.insert(0, self.config["output_folder"])
        self.output_folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        browse_output_btn = tk.Button(
            output_folder_frame,
            text="...",
            command=self.browse_output_folder,
            width=3
        )
        browse_output_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        save_paths_btn = tk.Button(
            settings_frame,
            text="Сохранить настройки",
            command=self.save_settings,
            bg="#3498db",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            padx=15,
            pady=8
        )
        save_paths_btn.pack(pady=(5, 15))
        
        # Кнопка создания БД
        create_db_btn = tk.Button(
            settings_frame,
            text="Создать БД из CSV",
            command=self.create_database,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.FLAT,
            padx=15,
            pady=6
        )
        create_db_btn.pack()
        
        # === ПРАВАЯ ПАНЕЛЬ - ЛОГИ ===
        
        logs_label = tk.Label(
            right_frame,
            text="Журнал работы",
            font=("Arial", 14, "bold"),
            bg=bg_color,
            fg="#2c3e50"
        )
        logs_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Текстовое поле для логов
        self.log_text = scrolledtext.ScrolledText(
            right_frame,
            font=("Consolas", 9),
            bg="#2c3e50",
            fg="#ecf0f1",
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Кнопки управления логами
        log_buttons_frame = tk.Frame(right_frame, bg=bg_color)
        log_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        clear_log_btn = tk.Button(
            log_buttons_frame,
            text="Очистить журнал",
            command=self.clear_logs,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 9),
            relief=tk.FLAT,
            padx=15,
            pady=5
        )
        clear_log_btn.pack(side=tk.LEFT)
    
    def save_model(self):
        """Сохраняет модель OpenAI"""
        new_model = self.model_entry.get().strip()
        if not new_model:
            messagebox.showerror("Ошибка", "Введите название модели")
            return
        
        self.openai_model = new_model
        self.config["openai_model"] = new_model
        self.save_config()
        
        # Пересоздаем процессор с новой моделью
        self.processor = AgreementProcessor(
            openai_api_key=self.openai_api_key,
            output_folder=self.output_folder_entry.get().strip()
        )
        self.processor.openai_processor.model = new_model
        self.processor.set_progress_callback(self.update_log)
        self.processor.set_error_callback(self.handle_error)
        
        messagebox.showinfo("Успех", f"Модель изменена на: {new_model}")
        self.log_message(f"Модель OpenAI изменена на: {new_model}")
    
    def browse_output_folder(self):
        """Выбор папки для сохранения"""
        folder = filedialog.askdirectory(title="Выберите папку для соглашений")
        if folder:
            self.output_folder_entry.delete(0, tk.END)
            self.output_folder_entry.insert(0, folder)
    
    def save_settings(self):
        """Сохраняет все настройки"""
        self.config["output_folder"] = self.output_folder_entry.get().strip()
        self.config["openai_model"] = self.model_entry.get().strip()
        self.save_config()
        
        # Обновляем процессор с новыми настройками
        self.processor.doc_processor.output_folder = self.config["output_folder"]
        
        messagebox.showinfo("Успех", "Настройки сохранены")
        self.log_message("Настройки сохранены")
    
    def create_database(self):
        """Создает базу данных из CSV"""
        company = self.selected_company.get()
        
        csv_path = filedialog.askopenfilename(
            title=f"Выберите CSV файл для создания БД {company}",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
        )
        
        if not csv_path:
            return
        
        try:
            self.db_manager.create_database_from_csv(csv_path, company)
            messagebox.showinfo("Успех", f"База данных для {company} создана")
            self.log_message(f"База данных для {company} создана из CSV")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать БД:\n{str(e)}")
            self.log_message(f"ОШИБКА создания БД: {str(e)}", "error")
    
    def start_processing(self):
        """Начинает обработку контрагентов"""
        if self.processing:
            messagebox.showwarning("Предупреждение", "Обработка уже выполняется")
            return
        
        company = self.selected_company.get()
        
        csv_path = filedialog.askopenfilename(
            title=f"Выберите CSV файл с контрагентами для {company}",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
        )
        
        if not csv_path:
            return
        
        # Автоматически создаем БД если её нет
        if not self.db_manager.database_exists(company):
            self.log_message(f"База данных для {company} не найдена. Создаю новую...")
            try:
                # Создаем пустую БД
                import pandas as pd
                columns = [
                    "Название организации", "Поставщик", "Количество", "ИНН", "КПП",
                    "Идентификатор участника ЭДО", "Статус", "Дата изменения статуса",
                    "ID организации", "ID ящика"
                ]
                df = pd.DataFrame(columns=columns)
                db_path = self.db_manager.kadis_db_path if company == "КАДИС" else self.db_manager.uri_db_path
                df.to_csv(db_path, index=False, encoding='utf-8-sig')
                self.log_message(f"База данных для {company} создана")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать БД:\n{str(e)}")
                return
        
        # Запускаем обработку в отдельном потоке
        self.processing = True
        self.generate_btn.config(state=tk.DISABLED, text="⏳ Обработка...")

        date_from = self.date_from_var.get().strip()
        date_to = self.date_to_var.get().strip()

        thread = threading.Thread(
            target=self.process_thread,
            args=(csv_path, company, date_from, date_to),
            daemon=True
        )
        thread.start()
    
    def process_thread(self, csv_path: str, company: str, date_from: str, date_to: str):
        """Поток обработки контрагентов"""
        try:
            # Обработка по периоду
            created = self.processor.process_by_period(company, csv_path, date_from, date_to)
            total = created
            self.root.after(0, lambda: self.processing_complete(created, total))
        except Exception as e:
            self.root.after(0, lambda: self.processing_error(str(e)))
    
    def processing_complete(self, processed: int, total: int):
        """Вызывается после завершения обработки"""
        self.processing = False
        self.generate_btn.config(state=tk.NORMAL, text="📄 Сформировать соглашения")
        
        messagebox.showinfo(
            "Обработка завершена",
            f"Успешно обработано: {processed} из {total}\n\nСоглашения сохранены в папке '{self.config['output_folder']}'"
        )
        self.log_message(f"\n{'='*60}")
        self.log_message(f"ОБРАБОТКА ЗАВЕРШЕНА")
        self.log_message(f"Успешно: {processed}/{total}")
        self.log_message(f"{'='*60}\n")
    
    def processing_error(self, error_msg: str):
        """Вызывается при ошибке обработки"""
        self.processing = False
        self.generate_btn.config(state=tk.NORMAL, text="📄 Сформировать соглашения")
        
        messagebox.showerror("Ошибка", f"Произошла ошибка:\n{error_msg}")
        self.log_message(f"КРИТИЧЕСКАЯ ОШИБКА: {error_msg}", "error")
    
    def handle_error(self, error_type: str, error_details: str) -> str:
        """
        Обработчик ошибок с выбором действия пользователя
        
        Returns:
            'abort', 'retry' или 'skip'
        """
        # Это вызывается из другого потока, поэтому используем root.after
        result = {"action": "abort"}
        
        def show_dialog():
            dialog = tk.Toplevel(self.root)
            dialog.title("Ошибка обработки")
            dialog.geometry("500x250")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Центрируем окно
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            
            tk.Label(
                dialog,
                text=error_type,
                font=("Arial", 12, "bold"),
                fg="#e74c3c"
            ).pack(pady=(20, 10))
            
            text_frame = tk.Frame(dialog)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
            
            text_widget = tk.Text(text_frame, height=5, wrap=tk.WORD, font=("Arial", 9))
            text_widget.insert(1.0, error_details)
            text_widget.config(state=tk.DISABLED)
            text_widget.pack(fill=tk.BOTH, expand=True)
            
            buttons_frame = tk.Frame(dialog)
            buttons_frame.pack(pady=(0, 20))
            
            def set_action(action):
                result["action"] = action
                dialog.destroy()
            
            tk.Button(
                buttons_frame,
                text="Прервать",
                command=lambda: set_action("abort"),
                bg="#e74c3c",
                fg="white",
                font=("Arial", 10, "bold"),
                width=12,
                pady=5
            ).pack(side=tk.LEFT, padx=5)
            
            tk.Button(
                buttons_frame,
                text="Повторить",
                command=lambda: set_action("retry"),
                bg="#3498db",
                fg="white",
                font=("Arial", 10, "bold"),
                width=12,
                pady=5
            ).pack(side=tk.LEFT, padx=5)
            
            tk.Button(
                buttons_frame,
                text="Пропустить",
                command=lambda: set_action("skip"),
                bg="#95a5a6",
                fg="white",
                font=("Arial", 10, "bold"),
                width=12,
                pady=5
            ).pack(side=tk.LEFT, padx=5)
            
            dialog.wait_window()
        
        self.root.after(0, show_dialog)
        
        # Ждем пока пользователь не выберет действие
        while result["action"] == "abort" and self.processing:
            self.root.update()
            import time
            time.sleep(0.1)
        
        return result["action"]
    
    def log_message(self, message: str, level: str = "info"):
        """Добавляет сообщение в журнал"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if level == "error":
            prefix = "❌ [ОШИБКА]"
        elif level == "warning":
            prefix = "⚠️  [ВНИМАНИЕ]"
        else:
            prefix = "ℹ️"
        
        log_entry = f"[{timestamp}] {prefix} {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def update_log(self, message: str):
        """Обновляет журнал (вызывается из процессора)"""
        self.root.after(0, lambda: self.log_message(message))
    
    def clear_logs(self):
        """Очищает журнал"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)


def main():
    root = tk.Tk()
    app = AgreementGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
