# Interface.py — Smart M3U Scanner Pro GUI
# Полный GUI с раздельными кнопками, умными категориями из cartolog.txt

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import sys
import os
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import re
from urllib.parse import urljoin

# Добавляем путь к текущей директории для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from M3UScanner import OnlineM3UScanner
except ImportError as e:
    print(f"Ошибка импорта M3UScanner: {e}")
    OnlineM3UScanner = None


class SmartM3UScannerGUI:
    """Полностью переработанный GUI с раздельными кнопками и умными категориями"""

    def __init__(self, root):
        self.root = root
        self.root.title("🌐 Smart M3U Scanner Pro")
        self.root.geometry("1050x850")
        self.root.minsize(900, 700)
        self.root.configure(bg='#1a1a2e')

        # Переменные состояния
        self.is_scanning = False
        self.auto_refresh_active = False
        self.stop_requested = False
        self.result_queue = queue.Queue()
        self.working_list = []
        self.broken_list = []

        # Кэш категорий
        self.category_map = {}
        self.categories_list = []

        # Настройки по умолчанию
        self.settings = {
            'threads': 20,
            'timeout': 10,
            'auto_refresh_interval': 30,
            'site_file': 'files/site.txt',
            'cartolog_file': 'files/cartolog.txt',
            'channels_file': 'files/Channels.txt',
            'scan_m3u': True,
            'scan_m3u8': True,
            'last_channel': '',
            'last_category': '',
        }

        # Инициализация сканера
        self.scanner = None
        if OnlineM3UScanner:
            try:
                self.scanner = OnlineM3UScanner()
            except Exception as e:
                print(f"Ошибка инициализации сканера: {e}")

        # Загружаем сохранённые настройки
        self.max_urls_var = tk.StringVar(value=str(self.settings.get('max_check_urls', 50)))
        self.search_mode_var = tk.StringVar(value="exact")
        self.load_settings()

        # Создаём папки
        Path("results").mkdir(exist_ok=True)
        Path("files").mkdir(exist_ok=True)
        Path("playlist").mkdir(exist_ok=True)

        # Настраиваем UI
        self.setup_ui()

        # Загружаем категории
        self.reload_category_map()

        self.update_stats()
        self.load_categories_into_combobox()

        # Запускаем обработчик очереди
        self.root.after(100, self.process_queue)
    
    # ============================================================
    # УМНЫЕ КАТЕГОРИИ
    # ============================================================
    def reload_category_map(self):
        """
        Загружает карту категорий из cartolog.txt.
        """
        self.category_map = {}
        self.categories_list = []

        cartolog_file = self.settings.get('cartolog_file', 'files/cartolog.txt')
        path = Path(cartolog_file)

        if not path.exists():
            self._create_default_cartolog()
            path = Path(cartolog_file)

        try:
            current_category = None
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith('#'):
                        cat = line.lstrip('#').strip()
                        if cat:
                            current_category = cat
                            if cat not in self.categories_list:
                                self.categories_list.append(cat)
                    elif current_category:
                        channel_lower = line.lower()
                        if channel_lower not in self.category_map:
                            self.category_map[channel_lower] = current_category

            if not self.categories_list:
                self.categories_list = [
                    "Без категории",
                    "Общие", "Спорт", "Фильмы", "Сериалы",
                    "Новости", "Музыка", "Детские", "Познавательные",
                    "Региональные", "HD каналы", "4K каналы"
                ]

            print(f"📁 Загружено категорий: {len(self.categories_list)} | Каналов в карте: {len(self.category_map)}")

        except Exception as e:
            print(f"⚠️ Ошибка чтения категорий: {e}")
            self.categories_list = ["Без категории"]

    def _create_default_cartolog(self):
        """Создаёт cartolog.txt с базовыми категориями"""
        path = Path(self.settings.get('cartolog_file', 'files/cartolog.txt'))
        Path(path.parent).mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()  # просто создаём пустой файл

    def smart_detect_category(self, channel_name: str) -> str:
        """Умное определение категории по названию канала."""
        if not channel_name:
            return "Без категории"

        name_lower = channel_name.lower().strip()

        # 1. Точное совпадение
        if name_lower in self.category_map:
            return self.category_map[name_lower]

        # 2. Частичное совпадение
        sorted_keys = sorted(self.category_map.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in name_lower:
                return self.category_map[key]

        # 3. Эвристики
        if any(word in name_lower for word in ['муз', 'music', 'radio', 'радио', 'fm', 'хит', 'hit', 'шансон', 'rock', 'jazz', 'rap', 'hip hop', 'pop', 'dance', 'metal', 'trance', 'techno', 'house']):
            return "Музыкальные"
        if any(word in name_lower for word in ['спорт', 'футбол', 'хоккей', 'теннис', 'баскет', 'sport', 'матч', 'fight', 'khl', 'nhl', 'nba', 'ufc', 'f1', 'формула']):
            return "Спортивные"
        if any(word in name_lower for word in ['фильм', 'кино', 'сериал', 'movie', 'film', 'cinema', 'боевик', 'комедия', 'ужас', 'драма', 'tv1000', 'amedia', 'paramount', 'fox', 'sony', 'universal']):
            return "Кино"
        if any(word in name_lower for word in ['новост', 'news', 'вести', 'rt', 'rbc', 'life', 'euronews', 'cnn', 'bbc', 'sky']):
            return "Новостные"
        if any(word in name_lower for word in ['дет', 'карусель', 'мульт', 'disney', 'cartoon', 'nick', 'аниме', 'kids', 'child']):
            return "Детские"
        if any(word in name_lower for word in ['познав', 'наук', 'истор', 'природ', 'живот', 'путеш', 'discovery', 'national geographic', 'viasat', 'охота', 'техно', 'доктор', 'здоров', 'кухн', 'еда']):
            return "Познавательные"
        if any(word in name_lower for word in ['hd', 'uhd', '4k', 'full hd', 'fhd']):
            return "HD каналы"
        if any(word in name_lower for word in ['развлек', 'пятниц', 'суббот', 'домашн', 'love', 'ю ', 'канал ю', 'тнт4', 'че', 'тв3', '2x2', 'развлекат']):
            return "Развлекательные"

        return "Без категории"

    def load_categories_into_combobox(self):
        """Загружает категории в выпадающий список"""
        self.reload_category_map()
        self.category_combo['values'] = self.categories_list
        last_cat = self.settings.get('last_category', '')
        if last_cat and last_cat in self.categories_list:
            self.category_var.set(last_cat)

    def reload_categories(self):
        """Перезагружает категории и обновляет UI"""
        self.reload_category_map()
        self.load_categories_into_combobox()
        self.log("🔄 Категории перезагружены из cartolog.txt", "info")

    # ============================================================
    # UI
    # ============================================================
    def setup_ui(self):
        """Полная настройка интерфейса"""
        style = ttk.Style()
        style.theme_use('clam')

        bg_dark = '#1a1a2e'
        bg_medium = '#16213e'
        accent_green = '#4CAF50'
        text_light = '#ffffff'
        text_gray = '#a0a0a0'

        style.configure('Dark.TFrame', background=bg_dark)
        style.configure('Medium.TFrame', background=bg_medium)
        style.configure('Dark.TLabel', background=bg_dark, foreground=text_light, font=('Segoe UI', 10))
        style.configure('Medium.TLabel', background=bg_medium, foreground=text_light, font=('Segoe UI', 10))
        style.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'), foreground=accent_green)
        style.configure('Stats.TLabel', font=('Segoe UI', 9), foreground=text_gray)
        style.configure('Dark.TButton', font=('Segoe UI', 9), padding=6)
        style.configure('Accent.TButton', font=('Segoe UI', 9, 'bold'), padding=6)
        style.configure('Stop.TButton', font=('Segoe UI', 9, 'bold'), padding=6)
        style.configure('Search.TButton', font=('Segoe UI', 10, 'bold'), padding=8)
        style.configure('Update.TButton', font=('Segoe UI', 10, 'bold'), padding=8)
        style.configure('TEntry', font=('Segoe UI', 10), padding=5)
        style.configure('TCombobox', font=('Segoe UI', 10), padding=3)
        style.configure('TLabelframe', background=bg_dark, foreground=text_light)
        style.configure('TLabelframe.Label', background=bg_dark, foreground=accent_green, font=('Segoe UI', 10, 'bold'))
        style.configure('TCheckbutton', background=bg_medium, foreground=text_light)

        main_frame = ttk.Frame(self.root, style='Dark.TFrame', padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Заголовок
        header_frame = ttk.Frame(main_frame, style='Dark.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="🌐 SMART M3U SCANNER PRO", style='Header.TLabel').pack(side=tk.LEFT)
        self.auto_indicator = tk.Canvas(header_frame, width=12, height=12, bg=bg_dark, highlightthickness=0)
        self.auto_indicator.pack(side=tk.RIGHT, padx=5)
        self.auto_indicator.create_oval(2, 2, 10, 10, fill='gray', tags='indicator')
        ttk.Label(header_frame, text="Авто", style='Stats.TLabel').pack(side=tk.RIGHT)

        # Верхняя панель
        top_panel = ttk.Frame(main_frame, style='Dark.TFrame')
        top_panel.pack(fill=tk.X, pady=5)

        stats_frame = ttk.LabelFrame(top_panel, text="📊 Статистика", padding="8")
        stats_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.stats_text = tk.StringVar(value="Загрузка статистики...")
        ttk.Label(stats_frame, textvariable=self.stats_text, style='Medium.TLabel').pack(anchor=tk.W)

        settings_frame = ttk.LabelFrame(top_panel, text="⚙️ Настройки", padding="8")
        settings_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))

        row1 = ttk.Frame(settings_frame, style='Dark.TFrame')
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Потоков:", style='Medium.TLabel').pack(side=tk.LEFT, padx=2)
        self.threads_var = tk.StringVar(value=str(self.settings['threads']))
        ttk.Entry(row1, textvariable=self.threads_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(row1, text="Таймаут:", style='Medium.TLabel').pack(side=tk.LEFT, padx=2)
        self.timeout_var = tk.StringVar(value=str(self.settings['timeout']))
        ttk.Entry(row1, textvariable=self.timeout_var, width=6).pack(side=tk.LEFT, padx=2)

        row2 = ttk.Frame(settings_frame, style='Dark.TFrame')
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Авто-интервал (мин):", style='Medium.TLabel').pack(side=tk.LEFT, padx=2)
        self.auto_interval_var = tk.StringVar(value=str(self.settings['auto_refresh_interval']))
        ttk.Entry(row2, textvariable=self.auto_interval_var, width=6).pack(side=tk.LEFT, padx=2)

        row3 = ttk.Frame(settings_frame, style='Dark.TFrame')
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Формат:", style='Medium.TLabel').pack(side=tk.LEFT, padx=2)
        self.scan_m3u_var = tk.BooleanVar(value=self.settings.get('scan_m3u', True))
        self.cb_m3u = ttk.Checkbutton(row3, text="M3U", variable=self.scan_m3u_var, command=self.save_settings)
        self.cb_m3u.pack(side=tk.LEFT, padx=2)
        self.scan_m3u8_var = tk.BooleanVar(value=self.settings.get('scan_m3u8', True))
        self.cb_m3u8 = ttk.Checkbutton(row3, text="M3U8", variable=self.scan_m3u8_var, command=self.save_settings)
        self.cb_m3u8.pack(side=tk.LEFT, padx=2)

        row4 = ttk.Frame(settings_frame, style='Dark.TFrame')
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="Макс. ссылок:", style='Medium.TLabel').pack(side=tk.LEFT, padx=2)
        ttk.Entry(row4, textvariable=self.max_urls_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Entry(row4, textvariable=self.max_urls_var, width=6).pack(side=tk.LEFT, padx=2)

        row5 = ttk.Frame(settings_frame, style='Dark.TFrame')
        row5.pack(fill=tk.X, pady=2)
        ttk.Label(row5, text="Режим поиска:", style='Medium.TLabel').pack(side=tk.LEFT, padx=2)
        self.search_mode_var = tk.StringVar(value="exact")
        ttk.Combobox(row5, textvariable=self.search_mode_var, values=["exact", "broad"], 
                     width=8, state='readonly').pack(side=tk.LEFT, padx=2)

        # БЛОК 1: ПОИСК КАНАЛА
        search_block = ttk.LabelFrame(main_frame, text="🔍 ПОИСК КАНАЛА", padding="10")
        search_block.pack(fill=tk.X, pady=5)

        input_row = ttk.Frame(search_block, style='Dark.TFrame')
        input_row.pack(fill=tk.X, pady=5)
        ttk.Label(input_row, text="Название канала:", style='Medium.TLabel', width=18).pack(side=tk.LEFT, padx=2)
        self.channel_name_var = tk.StringVar(value=self.settings.get('last_channel', ''))
        self.channel_entry = ttk.Entry(input_row, textvariable=self.channel_name_var, width=30)
        self.channel_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        self.channel_entry.bind('<Return>', lambda e: self.find_channel())
        self.channel_entry.bind('<KeyRelease>', self._on_channel_name_change)

        ttk.Label(input_row, text="Категория:", style='Medium.TLabel', width=10).pack(side=tk.LEFT, padx=(10, 2))
        self.category_var = tk.StringVar(value=self.settings.get('last_category', ''))
        self.category_combo = ttk.Combobox(input_row, textvariable=self.category_var, width=25)
        self.category_combo.pack(side=tk.LEFT, padx=2)
        self.category_combo.bind('<Return>', lambda e: self.find_channel())

        ttk.Button(input_row, text="🤖 Авто", command=self._auto_detect_category_for_input,
                   style='Dark.TButton', width=6).pack(side=tk.LEFT, padx=2)

        btn_row = ttk.Frame(search_block, style='Dark.TFrame')
        btn_row.pack(fill=tk.X, pady=(8, 0))
        self.search_btn = ttk.Button(btn_row, text="🔍 НАЙТИ КАНАЛ", command=self.find_channel, style='Search.TButton')
        self.search_btn.pack(side=tk.LEFT, padx=3)
        self.update_btn = ttk.Button(btn_row, text="🔄 ОБНОВИТЬ КАНАЛЫ", command=self.update_channels, style='Update.TButton')
        self.update_btn.pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="📋 Список каналов", command=self.edit_channels_file, style='Dark.TButton').pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_row, text="📁 Категории", command=self.edit_cartolog_file, style='Dark.TButton').pack(side=tk.LEFT, padx=3)

        # БЛОК 2: ПРОВЕРКА САЙТОВ
        sites_block = ttk.LabelFrame(main_frame, text="🌐 ПРОВЕРКА САЙТОВ И ПОИСК M3U/M3U8", padding="10")
        sites_block.pack(fill=tk.X, pady=5)

        file_row = ttk.Frame(sites_block, style='Dark.TFrame')
        file_row.pack(fill=tk.X, pady=5)
        ttk.Label(file_row, text="Файл сайтов:", style='Medium.TLabel', width=14).pack(side=tk.LEFT, padx=2)
        self.site_file_var = tk.StringVar(value=self.settings['site_file'])
        ttk.Entry(file_row, textvariable=self.site_file_var, width=50).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(file_row, text="📂 Обзор", command=self.browse_site_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_row, text="✏️ Ред.", command=self.edit_site_file).pack(side=tk.LEFT, padx=2)

        ctrl_row = ttk.Frame(sites_block, style='Dark.TFrame')
        ctrl_row.pack(fill=tk.X, pady=(8, 0))
        self.start_btn = ttk.Button(ctrl_row, text="▶ ПРОВЕРИТЬ САЙТЫ + НАЙТИ M3U/M3U8",
                                     command=self.start_check, style='Accent.TButton')
        self.start_btn.pack(side=tk.LEFT, padx=3)
        self.stop_btn = ttk.Button(ctrl_row, text="■ СТОП", command=self.stop_check,
                                    style='Stop.TButton', state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=3)
        self.auto_btn = ttk.Button(ctrl_row, text="🔄 АВТО-ПРОВЕРКА", command=self.toggle_auto_refresh, style='Dark.TButton')
        self.auto_btn.pack(side=tk.LEFT, padx=3)
        ttk.Button(ctrl_row, text="📊 Статистика", command=self.update_stats, style='Dark.TButton').pack(side=tk.LEFT, padx=3)
        ttk.Button(ctrl_row, text="📁 Результаты", command=self.open_results_folder, style='Dark.TButton').pack(side=tk.LEFT, padx=3)

        progress_row = ttk.Frame(sites_block, style='Dark.TFrame')
        progress_row.pack(fill=tk.X, pady=(8, 0))
        self.progress = ttk.Progressbar(progress_row, mode='determinate', length=100)
        self.progress.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.progress_label = ttk.Label(progress_row, text="0%", style='Stats.TLabel', width=6)
        self.progress_label.pack(side=tk.RIGHT, padx=(5, 0))
        self.status_var = tk.StringVar(value="🟢 Готов к работе")
        ttk.Label(sites_block, textvariable=self.status_var, style='Medium.TLabel').pack(anchor=tk.W, pady=(5, 0))

                # БЛОК 3: ЛОГ
        log_frame = ttk.LabelFrame(main_frame, text="📝 ЛОГ ВЫПОЛНЕНИЯ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = tk.Text(log_frame, height=12, width=80, bg='#0d1117', fg='#c9d1d9',
                                font=('Consolas', 9), wrap=tk.WORD, state='normal')
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.tag_config("success", foreground="#4CAF50")
        self.log_text.tag_config("error", foreground="#f44336")
        self.log_text.tag_config("warning", foreground="#ff9800")
        self.log_text.tag_config("info", foreground="#2196F3")
        self.log_text.tag_config("header", foreground="#e94560", font=('Consolas', 10, 'bold'))
        self.log_text.tag_config("stats", foreground="#a0a0a0", font=('Consolas', 8))
        self.log_text.tag_config("m3u_link", foreground="#00BCD4")
        self.log_text.tag_config("channel", foreground="#FFD700", font=('Consolas', 9, 'bold'))

        log_btn_row = ttk.Frame(log_frame, style='Dark.TFrame')
        log_btn_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        ttk.Button(log_btn_row, text="🧹 Очистить лог", command=self.clear_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(log_btn_row, text="💾 Сохранить лог", command=self.save_log).pack(side=tk.LEFT, padx=2)

        # Адаптивность — теперь все переменные созданы
        main_frame.columnconfigure(0, weight=1)
        #main_frame.rowconfigure(0, weight=0)
        main_frame.rowconfigure(1, weight=0)
        main_frame.rowconfigure(2, weight=0)
        main_frame.rowconfigure(3, weight=0)
        main_frame.rowconfigure(4, weight=1)

        search_block.columnconfigure(0, weight=1)
        sites_block.columnconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        #log_frame.rowconfigure(0, weight=1)

    # ============================================================
    # АВТО-ОПРЕДЕЛЕНИЕ КАТЕГОРИИ
    # ============================================================
    def _on_channel_name_change(self, event=None):
        channel_name = self.channel_name_var.get().strip()
        if len(channel_name) >= 2:
            detected = self.smart_detect_category(channel_name)
            if detected != "Без категории":
                self.category_var.set(detected)

    def _auto_detect_category_for_input(self):
        channel_name = self.channel_name_var.get().strip()
        if not channel_name:
            messagebox.showwarning("⚠️ Внимание", "Сначала введите название канала!")
            return
        detected = self.smart_detect_category(channel_name)
        self.category_var.set(detected)
        self.log(f"🤖 Авто-категория для '{channel_name}': {detected}", "info")

    # ============================================================
    # ПОИСК КАНАЛА
    # ============================================================
    def find_channel(self):
        if self.is_scanning:
            messagebox.showwarning("⚠️ Внимание", "Сканирование уже выполняется!")
            return

        channel_name = self.channel_name_var.get().strip()
        if not channel_name:
            messagebox.showwarning("⚠️ Внимание", "Введите название канала!")
            self.channel_entry.focus()
            return

        category = self.category_var.get().strip()
        if not category:
            category = self.smart_detect_category(channel_name)
            self.category_var.set(category)

        self.settings['last_channel'] = channel_name
        self.settings['last_category'] = category
        self.save_settings()

        self.is_scanning = True
        self.stop_requested = False
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.search_btn.config(state='disabled', text="⏳ ПОИСК...")
        self.update_btn.config(state='disabled')
        self.progress.start()
        self.status_var.set(f"🔍 Поиск канала: {channel_name}")

        self.log("=" * 60, "header")
        self.log(f"🔍 ПОИСК КАНАЛА: {channel_name}", "channel")
        self.log(f"📁 Категория: {category} (авто-определение)", "info")
        self.log("=" * 60, "header")

        thread = threading.Thread(target=self._find_channel_thread, args=(channel_name, category), daemon=True)
        thread.start()

    def _find_channel_thread(self, channel_name, category):
        try:
            if self.scanner:
                self.scanner.set_scan_formats(self.scan_m3u_var.get(), self.scan_m3u8_var.get())
                try:
                    self.scanner.max_check_urls = int(self.max_urls_var.get())
                except:
                    pass
                try:
                    self.scanner.search_mode = self.search_mode_var.get()
                except:
                    pass
                old_stdout = sys.stdout

                class QueueStream:
                    def __init__(self, queue):
                        self.queue = queue
                    def write(self, text):
                        if text.strip():
                            self.queue.put(("log", (text.strip(), "info")))
                    def flush(self):
                        pass

                sys.stdout = QueueStream(self.result_queue)
                success = self.scanner.search_and_update_channel(channel_name)
                sys.stdout = old_stdout

                if success:
                    self.result_queue.put(("log", (f"✅ Канал '{channel_name}' найден и обновлён в категории '{category}'!", "success")))
                else:
                    self.result_queue.put(("log", (f"❌ Канал '{channel_name}' не найден", "error")))
            else:
                self.result_queue.put(("log", ("❌ Сканер не инициализирован.", "error")))
        except Exception as e:
            self.result_queue.put(("log", (f"💥 Ошибка: {e}", "error")))
        finally:
            self.result_queue.put(("finish_operation", None))

    # ============================================================
    # ОБНОВЛЕНИЕ КАНАЛОВ
    # ============================================================
    def update_channels(self):
        if self.is_scanning:
            messagebox.showwarning("⚠️ Внимание", "Сканирование уже выполняется!")
            return

        result = messagebox.askyesno("Подтверждение",
                                      "⚠️ Обновление всех каналов в M3U и M3U8 плейлистах может занять время.\n\nПродолжить?")
        if not result:
            return

        self.is_scanning = True
        self.stop_requested = False
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.search_btn.config(state='disabled')
        self.update_btn.config(state='disabled', text="⏳ ОБНОВЛЕНИЕ...")
        self.progress.start()
        self.status_var.set("🔄 Обновление всех каналов в M3U/M3U8...")

        self.log("=" * 60, "header")
        self.log("🔄 ОБНОВЛЕНИЕ ВСЕХ КАНАЛОВ", "header")
        self.log("=" * 60, "header")

        thread = threading.Thread(target=self._update_channels_thread, daemon=True)
        thread.start()

    def _update_channels_thread(self):
        try:
            if self.scanner:
                self.scanner.set_scan_formats(self.scan_m3u_var.get(), self.scan_m3u8_var.get())
                old_stdout = sys.stdout

                class QueueStream:
                    def __init__(self, queue):
                        self.queue = queue
                    def write(self, text):
                        if text.strip():
                            self.queue.put(("log", (text.strip(), "info")))
                    def flush(self):
                        pass

                sys.stdout = QueueStream(self.result_queue)
                self.scanner.refresh_all_channels()
                sys.stdout = old_stdout
                self.result_queue.put(("log", ("✅ Обновление каналов завершено!", "success")))
        except Exception as e:
            self.result_queue.put(("log", (f"💥 Ошибка: {e}", "error")))
        finally:
            self.result_queue.put(("finish_operation", None))

    # ============================================================
    # ПРОВЕРКА САЙТОВ
    # ============================================================
    def start_check(self):
        if self.is_scanning:
            messagebox.showwarning("⚠️ Внимание", "Сканирование уже выполняется!")
            return
        try:
            threads = int(self.threads_var.get())
            timeout = int(self.timeout_var.get())
        except ValueError:
            messagebox.showerror("❌ Ошибка", "Некорректные настройки!")
            return

        self.stop_requested = False
        self.is_scanning = True
        self.working_list = []
        self.broken_list = []

        self.start_btn.config(state='disabled', text="⏳ ПРОВЕРКА...")
        self.stop_btn.config(state='normal')
        self.search_btn.config(state='disabled')
        self.update_btn.config(state='disabled')
        self.progress['value'] = 0
        self.progress_label.config(text="0%")
        self.status_var.set("🟡 Проверка сайтов...")

        self.log("=" * 60, "header")
        self.log("🚀 ПРОВЕРКА САЙТОВ + ПОИСК M3U/M3U8", "header")
        self.log(f"⚡ Потоков: {threads} | Таймаут: {timeout}с", "info")
        self.log("=" * 60, "header")

        thread = threading.Thread(target=self._check_sites_thread, args=(threads, timeout), daemon=True)
        thread.start()

    def stop_check(self):
        if self.is_scanning:
            self.stop_requested = True
            self.status_var.set("🟠 Остановка...")
            self.log("⏹ Остановка...", "warning")

    def _check_sites_thread(self, threads, timeout):
        try:
            import requests
            site_file = self.site_file_var.get()
            sites = self._load_sites(site_file)

            if not sites:
                self.result_queue.put(("log", ("❌ Нет сайтов!", "error")))
                self.result_queue.put(("finish_sites", None))
                return

            total = len(sites)
            scan_m3u = self.scan_m3u_var.get()
            scan_m3u8 = self.scan_m3u8_var.get()

            if not scan_m3u and not scan_m3u8:
                self.result_queue.put(("log", ("❌ Выберите формат!", "error")))
                self.result_queue.put(("finish_sites", None))
                return

            self.result_queue.put(("log", (f"📋 Сайтов: {total}", "info")))
            self.result_queue.put(("progress_max", total))

            done = 0
            m3u_found = []
            m3u8_found = []

            with ThreadPoolExecutor(max_workers=threads) as executor:
                future_to_url = {}
                for url in sites:
                    if self.stop_requested:
                        break
                    future = executor.submit(self._check_site_and_find_m3u, url, timeout, scan_m3u, scan_m3u8)
                    future_to_url[future] = url

                for future in as_completed(future_to_url):
                    if self.stop_requested:
                        for f in future_to_url:
                            f.cancel()
                        self.result_queue.put(("log", ("⏹ Остановлено", "warning")))
                        break

                    done += 1
                    url = future_to_url[future]

                    try:
                        result = future.result()
                        is_working = result['is_working']
                        status_info = result['status_info']
                        found_m3u = result.get('m3u_links', [])
                        found_m3u8 = result.get('m3u8_links', [])

                        if is_working:
                            self.working_list.append((url, status_info))
                            msg = f"✅ [{done}/{total}] {url[:70]} (OK)"
                            if found_m3u or found_m3u8:
                                msg += f" | M3U:{len(found_m3u)} M3U8:{len(found_m3u8)}"
                                m3u_found.extend([(url, link) for link in found_m3u])
                                m3u8_found.extend([(url, link) for link in found_m3u8])
                            self.result_queue.put(("log", (msg, "success")))
                        else:
                            self.broken_list.append((url, status_info))
                            self.result_queue.put(("log", (f"❌ [{done}/{total}] {url[:70]} ({status_info})", "error")))
                    except Exception as e:
                        self.broken_list.append((url, str(e)))
                        self.result_queue.put(("log", (f"❌ [{done}/{total}] {url[:70]} ({e})", "error")))

                    self.result_queue.put(("progress", done))

            if not self.stop_requested:
                self._save_results()
                self._save_m3u_results(m3u_found, m3u8_found)
                self.result_queue.put(("log", ("=" * 60, "header")))
                self.result_queue.put(("log", (f"✅ ГОТОВО! Рабочих: {len(self.working_list)} | Нерабочих: {len(self.broken_list)} | M3U:{len(m3u_found)} M3U8:{len(m3u8_found)}", "header")))
            else:
                self._save_results()
                self._save_m3u_results(m3u_found, m3u8_found)

        except Exception as e:
            self.result_queue.put(("log", (f"💥 ОШИБКА: {e}", "error")))
        finally:
            self.result_queue.put(("finish_sites", None))

    def _check_site_and_find_m3u(self, url, timeout, scan_m3u=True, scan_m3u8=True):
        import requests
        result = {'is_working': False, 'status_info': '', 'm3u_links': [], 'm3u8_links': []}
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True,
                                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            result['is_working'] = resp.status_code < 400
            result['status_info'] = str(resp.status_code)
            if result['is_working']:
                content = resp.text
                if scan_m3u:
                    for pattern in [r'https?://[^\s<>"\']+\.m3u(?:\?[^\s<>"\']*)?',
                                    r'["\']([^"\']*\.m3u[^"\']*)["\']',
                                    r'href=["\']([^"\']*\.m3u[^"\']*)["\']']:
                        for match in re.findall(pattern, content, re.IGNORECASE):
                            link = match if match.startswith('http') else urljoin(url, match)
                            if link not in result['m3u_links'] and not link.endswith('.m3u8'):
                                result['m3u_links'].append(link)
                if scan_m3u8:
                    for pattern in [r'https?://[^\s<>"\']+\.m3u8(?:\?[^\s<>"\']*)?',
                                    r'["\']([^"\']*\.m3u8[^"\']*)["\']',
                                    r'href=["\']([^"\']*\.m3u8[^"\']*)["\']']:
                        for match in re.findall(pattern, content, re.IGNORECASE):
                            link = match if match.startswith('http') else urljoin(url, match)
                            if link not in result['m3u8_links']:
                                result['m3u8_links'].append(link)
        except requests.exceptions.RequestException as e:
            result['status_info'] = str(e)
        return result

    def _load_sites(self, filename):
        path = Path(filename)
        if not path.exists():
            return []
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

    def _save_results(self):
        Path("results").mkdir(exist_ok=True)
        with open("results/done.txt", 'w', encoding='utf-8') as f:
            f.write(f"# Рабочие сайты ({len(self.working_list)})\n")
            f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for url, status in self.working_list:
                f.write(f"{url}  # status: {status}\n")
        with open("results/error.txt", 'w', encoding='utf-8') as f:
            f.write(f"# Нерабочие сайты ({len(self.broken_list)})\n")
            f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for url, error in self.broken_list:
                f.write(f"{url}  # error: {error}\n")

    def _save_m3u_results(self, m3u_links, m3u8_links):
        Path("results").mkdir(exist_ok=True)
        with open("results/m3u_playlists.txt", 'w', encoding='utf-8') as f:
            f.write(f"# M3U/M3U8 плейлисты\n")
            f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# M3U: {len(m3u_links)} | M3U8: {len(m3u8_links)}\n\n")
            if m3u_links:
                f.write(f"# === M3U ({len(m3u_links)}) ===\n")
                for source_url, m3u_url in m3u_links:
                    f.write(f"{m3u_url}  # source: {source_url}\n")
                f.write("\n")
            if m3u8_links:
                f.write(f"# === M3U8 ({len(m3u8_links)}) ===\n")
                for source_url, m3u8_url in m3u8_links:
                    f.write(f"{m3u8_url}  # source: {source_url}\n")
                f.write("\n")

    # ============================================================
    # АВТООБНОВЛЕНИЕ
    # ============================================================
    def toggle_auto_refresh(self):
        if self.auto_refresh_active:
            self.auto_refresh_active = False
            self.auto_btn.config(text="🔄 АВТО-ПРОВЕРКА")
            self.auto_indicator.itemconfig('indicator', fill='gray')
            self.log("🔄 Авто-проверка ОТКЛЮЧЕНА", "warning")
        else:
            try:
                interval = int(self.auto_interval_var.get())
                if interval < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror("❌ Ошибка", "Некорректный интервал!")
                return
            self.auto_refresh_active = True
            self.settings['auto_refresh_interval'] = interval
            self.auto_btn.config(text="🔄 АВТО-ПРОВЕРКА (ВКЛ)")
            self.auto_indicator.itemconfig('indicator', fill='#4CAF50')
            self.log(f"🔄 Авто-проверка ВКЛЮЧЕНА (каждые {interval} мин)", "success")
            self.save_settings()
            self.root.after(1000, self._auto_refresh_cycle)

    def _auto_refresh_cycle(self):
        if not self.auto_refresh_active:
            return
        if not self.is_scanning:
            self.log(f"🔄 [АВТО] Запуск проверки...", "info")
            self.start_check()
        interval_ms = self.settings['auto_refresh_interval'] * 60 * 1000
        self.root.after(interval_ms, self._auto_refresh_cycle)

    # ============================================================
    # ОБРАБОТКА ОЧЕРЕДИ
    # ============================================================
    def process_queue(self):
        try:
            while True:
                msg = self.result_queue.get_nowait()
                msg_type = msg[0]
                if msg_type == "log":
                    message, tag = msg[1]
                    self.log(message, tag)
                elif msg_type == "progress":
                    done = msg[1]
                    if hasattr(self, '_total_sites'):
                        self.progress['value'] = done
                        pct = int(done / self._total_sites * 100) if self._total_sites else 0
                        self.progress_label.config(text=f"{pct}%")
                        self.status_var.set(f"🟡 Проверка: {done}/{self._total_sites} | ✅ {len(self.working_list)} | ❌ {len(self.broken_list)}")
                elif msg_type == "progress_max":
                    total = msg[1]
                    self._total_sites = total
                    self.progress['maximum'] = total
                    self.progress['value'] = 0
                elif msg_type in ("finish_operation", "finish_sites"):
                    self.is_scanning = False
                    self.start_btn.config(state='normal', text="▶ ПРОВЕРИТЬ САЙТЫ + НАЙТИ M3U/M3U8")
                    self.stop_btn.config(state='disabled')
                    self.search_btn.config(state='normal', text="🔍 НАЙТИ КАНАЛ")
                    self.update_btn.config(state='normal', text="🔄 ОБНОВИТЬ КАНАЛЫ")
                    self.progress.stop()
                    if hasattr(self, '_total_sites'):
                        self.progress['value'] = self.progress['maximum']
                        self.progress_label.config(text="100%")
                        del self._total_sites
                    self.status_var.set("🟢 Готов к работе")
                    self.update_stats()
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    # ============================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ============================================================
    def log(self, message, tag="info"):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] ", "stats")
        self.log_text.insert(tk.END, f"{message}\n", tag)
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self.log("Лог очищен", "info")

    def save_log(self):
        filename = filedialog.asksaveasfilename(defaultextension=".txt",
                                                 filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                                                 initialdir="results")
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.log_text.get(1.0, tk.END))
            self.log(f"Лог сохранён: {filename}", "success")

    def edit_channels_file(self):
        path = Path(self.settings.get('channels_file', 'files/Channels.txt'))
        self._open_file_in_editor(path)

    def edit_cartolog_file(self):
        path = Path(self.settings.get('cartolog_file', 'files/cartolog.txt'))
        self._open_file_in_editor(path)
        self.root.after(2000, self.reload_categories)

    def _open_file_in_editor(self, path):
        if not path.exists():
            Path(path.parent).mkdir(parents=True, exist_ok=True)
            path.touch()
        try:
            os.startfile(str(path))
        except:
            subprocess.Popen(['notepad.exe', str(path)])

    def browse_site_file(self):
        filename = filedialog.askopenfilename(title="Выберите файл site.txt",
                                               filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                                               initialdir="files")
        if filename:
            self.site_file_var.set(filename)
            self.settings['site_file'] = filename
            self.save_settings()
            self.log(f"📁 Выбран файл: {filename}", "info")
            self.update_stats()

    def edit_site_file(self):
        site_file = self.site_file_var.get()
        path = Path(site_file)
        self._open_file_in_editor(path)

    def open_results_folder(self):
        Path("results").mkdir(exist_ok=True)
        try:
            os.startfile("results")
        except:
            subprocess.Popen(['explorer', 'results'])

    def update_stats(self):
        try:
            site_file = self.site_file_var.get()
            sites = self._load_sites(site_file) if Path(site_file).exists() else []
            done_count = 0
            error_count = 0
            channels_count = 0
            if Path("results/done.txt").exists():
                with open("results/done.txt", 'r', encoding='utf-8') as f:
                    done_count = len([l for l in f if l.strip() and not l.startswith('#')])
            if Path("results/error.txt").exists():
                with open("results/error.txt", 'r', encoding='utf-8') as f:
                    error_count = len([l for l in f if l.strip() and not l.startswith('#')])
            if Path("playlist/playlist.m3u").exists():
                with open("playlist/playlist.m3u", 'r', encoding='utf-8') as f:
                    channels_count = len(re.findall(r'#EXTINF:', f.read()))
            stats = (f"📋 Сайтов: {len(sites)} | ✅ Рабочих: {done_count} | ❌ Нерабочих: {error_count} | 📺 Каналов: {channels_count} | 📁 Категорий: {len(self.categories_list)}")
            self.stats_text.set(stats)
        except Exception as e:
            self.stats_text.set(f"Ошибка: {e}")

    def load_settings(self):
        try:
            if Path("settings.txt").exists():
                with open("settings.txt", 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            key, val = line.strip().split('=', 1)
                            if key in self.settings:
                                try:
                                    if key in ['scan_m3u', 'scan_m3u8']:
                                        self.settings[key] = val.lower() == 'true'
                                    elif key in ['threads', 'timeout', 'auto_refresh_interval']:
                                        self.settings[key] = int(val)
                                    else:
                                        self.settings[key] = val
                                except:
                                    pass
        except:
            pass

    def save_settings(self):
        try:
            try:
                self.settings['threads'] = int(self.threads_var.get())
            except:
                pass
            try:
                self.settings['timeout'] = int(self.timeout_var.get())
            except:
                pass
            try:
                self.settings['max_check_urls'] = int(self.max_urls_var.get())
            except:
                 pass
            try:
                self.settings['auto_refresh_interval'] = int(self.auto_interval_var.get())
            except:
                pass
            self.settings['site_file'] = self.site_file_var.get()
            self.settings['scan_m3u'] = self.scan_m3u_var.get()
            self.settings['scan_m3u8'] = self.scan_m3u8_var.get()
            self.settings['last_channel'] = self.channel_name_var.get()
            self.settings['last_category'] = self.category_var.get()
            with open("settings.txt", 'w', encoding='utf-8') as f:
                for key, val in self.settings.items():
                    f.write(f"{key}={val}\n")
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")


def main():
    root = tk.Tk()
    app = SmartM3UScannerGUI(root)
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 2
    root.geometry(f"+{x}+{y}")
    root.protocol("WM_DELETE_WINDOW", lambda: (app.save_settings(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()