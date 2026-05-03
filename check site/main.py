import sys
from pathlib import Path
from logic import check_all_sites, save_results

def console_mode(threads=10):
    print("=== Проверка сайтов ===")
    try:
        # Создаём папку sites если её нет
        Path("sites").mkdir(exist_ok=True)

        site_file = "sites/site.txt"
        if not Path(site_file).exists():
            print(f"❌ Файл {site_file} не найден!")
            print("   Поместите site.txt в папку sites/ или создайте его.")
            return

        print(f"📂 Чтение списка из: {site_file}")
        print(f"⚡ Потоков: {threads}\n")

        working, broken = check_all_sites(site_file, max_workers=threads)
        save_results(working, broken, source_file=site_file)

        print(f"\n{'='*60}")
        print(f"✅ Рабочие сайты ({len(working)}):")
        for url, status in working:
            print(f"  ✓ {url}  (status: {status})")

        print(f"\n❌ Нерабочие сайты ({len(broken)}):")
        for url, error in broken:
            print(f"  ✗ {url}  (error: {error})")

        print(f"\n{'='*60}")
        print("💾 Результаты сохранены:")
        print("   ✅ results/done.txt  — рабочие сайты")
        print("   ❌ results/error.txt — нерабочие сайты")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    if "-interface" in sys.argv or "--interface" in sys.argv:
        from interface import run_gui
        run_gui()
    else:
        threads = 10
        if "-threads" in sys.argv:
            idx = sys.argv.index("-threads")
            if idx + 1 < len(sys.argv):
                threads = int(sys.argv[idx + 1])
        elif "-t" in sys.argv:
            idx = sys.argv.index("-t")
            if idx + 1 < len(sys.argv):
                threads = int(sys.argv[idx + 1])

        console_mode(threads)