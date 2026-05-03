import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from logic import check_site, load_sites, save_results
from pathlib import Path
import threading
import queue

class App:
    def __init__(self, root):
        self.root = root
        root.title("Проверка сайтов")
        root.geometry("800x600")

        # Создаём папки при старте
        Path("sites").mkdir(exist_ok=True)
        Path("results").mkdir(exist_ok=True)

        # Фрейм выбора файла
        frame = tk.Frame(root)
        frame.pack(pady=5, fill=tk.X, padx=10)

        self.file_path = tk.StringVar(value="sites/site.txt")
        tk.Label(frame, text="Файл со списком:").pack(side=tk.LEFT)
        tk.Entry(frame, textvariable=self.file_path, width=40).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Обзор", command=self.browse).pack(side=tk.LEFT)

        # Количество потоков
        frame2 = tk.Frame(root)
        frame2.pack(pady=5, fill=tk.X, padx=10)
        tk.Label(frame2, text="Потоков:").pack(side=tk.LEFT)
        self.threads_var = tk.StringVar(value="10")
        tk.Entry(frame2, textvariable=self.threads_var, width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(frame2, text="(1-50)").pack(side=tk.LEFT, padx=5)

        # Кнопки
        frame3 = tk.Frame(root)
        frame3.pack(pady=5, fill=tk.X, padx=10)
        self.run_btn = tk.Button(frame3, text="▶ Начать проверку", command=self.start_check,
                                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.run_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = tk.Button(frame3, text="■ Стоп", command=self.stop_check,
                                  bg="#f44336", fg="white", state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Статистика
        self.stats_label = tk.Label(root, text="Готов к проверке", fg="blue", font=("Arial", 9))
        self.stats_label.pack(pady=2)

        # Окно вывода
        self.output = scrolledtext.ScrolledText(root, width=90, height=25, state="normal")
        self.output.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # Цветовые теги
        self.output.tag_config("working", foreground="green")
        self.output.tag_config("broken", foreground="red")
        self.output.tag_config("header", foreground="blue", font=("Arial", 10, "bold"))
        self.output.tag_config("info", foreground="gray")

        # Очередь для реального времени
        self.result_queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.checking = False

        self.root.after(100, self.process_queue)

    def browse(self):
        filename = filedialog.askopenfilename(
            title="Выберите файл site.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir="sites"
        )
        if filename:
            self.file_path.set(filename)

    def start_check(self):
        if self.checking:
            return
        self.checking = True
        self.stop_flag.clear()
        self.run_btn.config(state="disabled", text="⏳ Проверка...")
        self.stop_btn.config(state="normal")
        self.output.delete(1.0, tk.END)
        self.stats_label.config(text="Загрузка списка сайтов...")

        try:
            threads = int(self.threads_var.get())
            if threads < 1:
                threads = 1
            elif threads > 50:
                threads = 50
        except ValueError:
            threads = 10

        threading.Thread(target=self._check, args=(threads,), daemon=True).start()

    def stop_check(self):
        self.stop_flag.set()
        self.stats_label.config(text="Остановка проверки...", fg="orange")
        self.stop_btn.config(state="disabled")

    def _check(self, threads):
        try:
            filename = self.file_path.get()
            sites = load_sites(filename)
            total = len(sites)
            done = 0
            working_count = 0
            broken_count = 0

            self.result_queue.put(("header", f"=== Найдено {total} сайтов для проверки ===\n"))
            self.result_queue.put(("info", f"Запущено потоков: {threads}\n\n"))

            self.working_list = []
            self.broken_list = []

            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=threads) as executor:
                future_to_url = {
                    executor.submit(check_site, url): url
                    for url in sites
                }

                for future in as_completed(future_to_url):
                    if self.stop_flag.is_set():
                        for f in future_to_url:
                            f.cancel()
                        self.result_queue.put(("info", "\n⏹ Проверка остановлена пользователем\n"))
                        break

                    done += 1
                    url = future_to_url[future]
                    try:
                        url_checked, ok, info = future.result()
                        if ok:
                            working_count += 1
                            self.working_list.append((url_checked, info))
                            self.result_queue.put(("working",
                                f"✓ [{done}/{total}] {url_checked}  (status: {info})\n"))
                        else:
                            broken_count += 1
                            self.broken_list.append((url_checked, info))
                            self.result_queue.put(("broken",
                                f"✗ [{done}/{total}] {url_checked}  (error: {info})\n"))
                    except Exception as e:
                        broken_count += 1
                        self.broken_list.append((url, str(e)))
                        self.result_queue.put(("broken",
                            f"✗ [{done}/{total}] {url}  (error: {e})\n"))

                    self.result_queue.put(("stats",
                        f"Прогресс: {done}/{total} | ✓ Рабочих: {working_count} | ✗ Нерабочих: {broken_count}"))

            # Сохраняем результаты в формате site.txt
            if not self.stop_flag.is_set():
                save_results(self.working_list, self.broken_list, source_file=filename)
                self.result_queue.put(("header", f"\n✅ Проверка завершена! Всего: {total}\n"))
                self.result_queue.put(("header", f"Рабочих: {working_count} | Нерабочих: {broken_count}\n"))
                self.result_queue.put(("info", "Результаты сохранены:\n"))
                self.result_queue.put(("info", "  ✅ results/done.txt\n"))
                self.result_queue.put(("info", "  ❌ results/error.txt\n"))
            else:
                save_results(self.working_list, self.broken_list, source_file=filename)
                self.result_queue.put(("info", "\nРезультаты сохранены (проверка прервана)\n"))

        except Exception as e:
            self.result_queue.put(("broken", f"\n❌ Ошибка: {e}\n"))
        finally:
            self.result_queue.put(("done", ""))

    def process_queue(self):
        try:
            while True:
                msg = self.result_queue.get_nowait()
                if msg[0] == "working":
                    self.output.insert(tk.END, msg[1], "working")
                elif msg[0] == "broken":
                    self.output.insert(tk.END, msg[1], "broken")
                elif msg[0] == "header":
                    self.output.insert(tk.END, msg[1], "header")
                elif msg[0] == "info":
                    self.output.insert(tk.END, msg[1], "info")
                elif msg[0] == "stats":
                    self.stats_label.config(text=msg[1])
                elif msg[0] == "done":
                    self.checking = False
                    self.run_btn.config(state="normal", text="▶ Начать проверку")
                    self.stop_btn.config(state="disabled")
                    self.stats_label.config(text="Готово ✓", fg="green")

                self.output.see(tk.END)

        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)

def run_gui():
    root = tk.Tk()
    App(root)
    root.mainloop()