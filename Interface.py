import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import sys
import os
import time
import subprocess
import io
from contextlib import redirect_stdout

# Добавляем путь к текущей директории для импорта M3UScanner
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from M3UScanner import OnlineM3UScanner
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    sys.exit(1)

class RealTimeLogger:
    """Класс для перехвата вывода в реальном времени"""
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        # Отправляем каждую завершенную строку
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line.strip():
                self.log_callback(line.strip())

    def flush(self):
        if self.buffer.strip():
            self.log_callback(self.buffer.strip())
            self.buffer = ""

class M3UScannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🌐 Smart M3U Scanner - Графический интерфейс")
        self.root.geometry("900x700")
        self.root.configure(bg='#2b2b2b')

        self.scanner = OnlineM3UScanner()
        self.is_scanning = False
        self.realtime_logger = None

        self.setup_ui()
        self.update_stats()

    def setup_ui(self):
        # Стиль
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#2b2b2b')
        style.configure('TLabel', background='#2b2b2b', foreground='white', font=('Arial', 10))
        style.configure('TButton', font=('Arial', 10), padding=5)
        style.configure('TEntry', font=('Arial', 10), padding=5)
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'), foreground='#4CAF50')

        # Главный фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Заголовок
        header_label = ttk.Label(main_frame, text="🌐 SMART M3U SCANNER", style='Header.TLabel')
        header_label.pack(pady=(0, 10))

        # Фрейм статистики
        stats_frame = ttk.LabelFrame(main_frame, text="📊 Статистика", padding="10")
        stats_frame.pack(fill=tk.X, pady=5)

        self.stats_label = ttk.Label(stats_frame, text="Загрузка...")
        self.stats_label.pack(anchor=tk.W)

        # Фрейм поиска канала
        search_frame = ttk.LabelFrame(main_frame, text="🔍 Поиск канала", padding="10")
        search_frame.pack(fill=tk.X, pady=5)

        ttk.Label(search_frame, text="Название канала:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.channel_entry = ttk.Entry(search_frame, width=50)
        self.channel_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        self.channel_entry.bind('<Return>', lambda e: self.search_channel())

        search_btn = ttk.Button(search_frame, text="🔍 Найти и обновить", command=self.search_channel)
        search_btn.grid(row=0, column=2, padx=5, pady=5)

        # Фрейм управления
        control_frame = ttk.LabelFrame(main_frame, text="🔄 Управление", padding="10")
        control_frame.pack(fill=tk.X, pady=5)

        ttk.Button(control_frame, text="🔄 Обновить все каналы",
                  command=self.refresh_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="📊 Обновить статистику",
                  command=self.update_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="📁 Открыть папку плейлиста",
                  command=self.open_playlist_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="❌ Остановить сканирование",
                  command=self.stop_scanning).pack(side=tk.LEFT, padx=5)

        # Прогресс бар
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=5)

        # Лог
        log_frame = ttk.LabelFrame(main_frame, text="📝 Лог выполнения", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, width=80,
                                                 bg='#1e1e1e', fg='white',
                                                 font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Кнопка очистки лога
        clear_btn = ttk.Button(log_frame, text="🧹 Очистить лог", command=self.clear_log)
        clear_btn.pack(side=tk.BOTTOM, pady=5)

        # Статус бар
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(5, 0))

        # Настройка весов строк и колонок
        search_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)

    def log_message(self, message):
        """Добавляет сообщение в лог в реальном времени"""
        def update_log():
            timestamp = time.strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}\n"

            self.log_text.insert(tk.END, formatted_message)
            self.log_text.see(tk.END)
            self.root.update_idletasks()

        # Выполняем в основном потоке GUI
        self.root.after(0, update_log)

    def clear_log(self):
        """Очищает лог"""
        self.log_text.delete(1.0, tk.END)

    def update_stats(self):
        """Обновляет статистику плейлиста"""
        try:
            existing_channels = self.scanner.load_existing_channels()
            if existing_channels:
                total_streams = sum(len(streams) for streams in existing_channels.values())
                stats_text = f"📊 Каналов: {len(existing_channels)} | 📺 Ссылок: {total_streams} | 📁 Источников: {len(self.scanner.custom_sites)}"
            else:
                stats_text = "📝 Плейлист пуст | 📁 Источников: 0"

            self.stats_label.config(text=stats_text)
        except Exception as e:
            self.log_message(f"❌ Ошибка обновления статистики: {e}")

    def search_channel(self):
        """Запускает поиск канала в отдельном потоке"""
        if self.is_scanning:
            messagebox.showwarning("Внимание", "Сканирование уже выполняется!")
            return

        channel_name = self.channel_entry.get().strip()
        if not channel_name:
            messagebox.showwarning("Внимание", "Введите название канала!")
            return

        self.is_scanning = True
        self.progress.start()
        self.status_var.set(f"🔍 Поиск канала: {channel_name}")
        self.log_message(f"🚀 Начало поиска канала: {channel_name}")

        thread = threading.Thread(target=self._search_channel_thread, args=(channel_name,))
        thread.daemon = True
        thread.start()

    def _search_channel_thread(self, channel_name):
        """Поток для поиска канала с перехватом вывода в реальном времени"""
        try:
            # Создаем логгер для реального времени
            self.realtime_logger = RealTimeLogger(self.log_message)

            # Перехватываем stdout
            old_stdout = sys.stdout
            sys.stdout = self.realtime_logger

            # Выполняем поиск
            success = self.scanner.search_and_update_channel(channel_name)

            # Восстанавливаем stdout
            sys.stdout = old_stdout
            self.realtime_logger.flush()  # Отправляем оставшиеся данные

            if success:
                self.log_message(f"✅ Канал '{channel_name}' успешно обновлен!")
            else:
                self.log_message(f"❌ Не удалось обновить канал '{channel_name}'")

        except Exception as e:
            self.log_message(f"💥 Ошибка при поиске: {e}")
        finally:
            self.is_scanning = False
            self.progress.stop()
            self.status_var.set("Готов к работе")
            self.update_stats()
            self.realtime_logger = None

    def refresh_all(self):
        """Обновляет все каналы"""
        if self.is_scanning:
            messagebox.showwarning("Внимание", "Сканирование уже выполняется!")
            return

        result = messagebox.askyesno(
            "Подтверждение",
            "⚠️  Полное обновление всех каналов может занять много времени.\nПродолжить?"
        )

        if not result:
            return

        self.is_scanning = True
        self.progress.start()
        self.status_var.set("🔄 Полное обновление всех каналов...")
        self.log_message("🔄 ЗАПУСК ПОЛНОГО ОБНОВЛЕНИЯ ВСЕХ КАНАЛОВ...")

        thread = threading.Thread(target=self._refresh_all_thread)
        thread.daemon = True
        thread.start()

    def _refresh_all_thread(self):
        """Поток для полного обновления с перехватом вывода в реальном времени"""
        try:
            # Создаем логгер для реального времени
            self.realtime_logger = RealTimeLogger(self.log_message)

            # Перехватываем stdout
            old_stdout = sys.stdout
            sys.stdout = self.realtime_logger

            # Выполняем обновление
            self.scanner.refresh_all_channels()

            # Восстанавливаем stdout
            sys.stdout = old_stdout
            self.realtime_logger.flush()  # Отправляем оставшиеся данные

            self.log_message("✅ Полное обновление завершено!")

        except Exception as e:
            self.log_message(f"💥 Ошибка при обновлении: {e}")
        finally:
            self.is_scanning = False
            self.progress.stop()
            self.status_var.set("Готов к работе")
            self.update_stats()
            self.realtime_logger = None

    def stop_scanning(self):
        """Останавливает сканирование"""
        if self.is_scanning:
            self.is_scanning = False
            self.progress.stop()
            self.status_var.set("Сканирование остановлено")
            self.log_message("⏹️ Сканирование остановлено пользователем")

            # Восстанавливаем stdout если был перехвачен
            if self.realtime_logger:
                sys.stdout = sys.__stdout__
                self.realtime_logger = None
        else:
            messagebox.showinfo("Информация", "Сканирование не выполняется")

    def open_playlist_folder(self):
        """Открывает папку с плейлистом"""
        playlist_dir = os.path.dirname(self.scanner.playlist_file)
        if not os.path.exists(playlist_dir):
            os.makedirs(playlist_dir, exist_ok=True)

        try:
            if sys.platform == "win32":
                os.startfile(playlist_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", playlist_dir])
            else:
                subprocess.Popen(["xdg-open", playlist_dir])
            self.log_message(f"📁 Открыта папка: {playlist_dir}")
        except Exception as e:
            self.log_message(f"❌ Не удалось открыть папку: {e}")

def main():
    root = tk.Tk()
    app = M3UScannerGUI(root)

    # Центрирование окна
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 2
    root.geometry(f"+{x}+{y}")

    root.mainloop()

if __name__ == "__main__":
    main()