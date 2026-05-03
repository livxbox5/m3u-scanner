import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def load_sites(filename="sites/site.txt"):
    """Читает список сайтов из файла, пропускает пустые строки и комментарии (#)."""
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Файл {filename} не найден")
    with open(path, "r", encoding="utf-8") as f:
        sites = []
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                sites.append(line)
    return sites

def load_sites_with_comments(filename="sites/site.txt"):
    """
    Читает файл и возвращает список строк в исходном порядке.
    Нужно для сохранения структуры комментариев при записи результатов.
    """
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Файл {filename} не найден")
    with open(path, "r", encoding="utf-8") as f:
        return [line.rstrip('\n\r') for line in f]

def check_site(url, timeout=5):
    """
    Проверяет один сайт.
    Возвращает кортеж: (url, is_working, status_or_error).
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code < 400:
            return url, True, resp.status_code
        else:
            return url, False, f"HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return url, False, str(e)

def check_all_sites(filename="sites/site.txt", timeout=5, max_workers=10):
    """
    Проверяет все сайты многопоточно.
    Возвращает: working, broken (списки кортежей (url, info)).
    Используется для консольного режима.
    """
    sites = load_sites(filename)
    if not sites:
        return [], []

    working = []
    broken = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(check_site, url, timeout): url
            for url in sites
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                url_checked, ok, info = future.result()
                if ok:
                    working.append((url_checked, info))
                else:
                    broken.append((url_checked, info))
            except Exception as e:
                broken.append((url, f"Exception: {e}"))

    return working, broken

def save_results(working, broken,
                 done_file="results/done.txt",
                 error_file="results/error.txt",
                 source_file="sites/site.txt"):
    """
    Сохраняет результаты в файлы с сохранением исходной структуры комментариев.
    Формат как в site.txt: секции с заголовками #, сайты с пометками статуса.
    """
    Path("results").mkdir(exist_ok=True)

    # Создаём словари для быстрого поиска результатов
    working_dict = {url: status for url, status in working}
    broken_dict = {url: error for url, error in broken}

    # Читаем исходный файл для сохранения структуры
    try:
        original_lines = load_sites_with_comments(source_file)
    except FileNotFoundError:
        original_lines = []

    done_lines = []
    error_lines = []

    current_section = ""
    done_has_section = False
    error_has_section = False

    for line in original_lines:
        stripped = line.strip()

        # Сохраняем заголовки секций
        if stripped.startswith("#"):
            current_section = line
            done_lines.append(line)
            error_lines.append(line)
            done_has_section = False
            error_has_section = False
            continue

        # Пустые строки
        if not stripped:
            done_lines.append(line)
            error_lines.append(line)
            continue

        # Это URL — проверяем его статус
        if stripped in working_dict:
            status = working_dict[stripped]
            done_lines.append(f"{stripped}  # status: {status}")
            done_has_section = True
        elif stripped in broken_dict:
            err = broken_dict[stripped]
            error_lines.append(f"{stripped}  # error: {err}")
            error_has_section = True
        else:
            # Сайт был в исходном файле, но по какой-то причине не проверен
            done_lines.append(f"{stripped}  # not checked")
            error_lines.append(f"{stripped}  # not checked")

    # Убираем пустые секции (где нет рабочих/нерабочих сайтов)
    done_lines = remove_empty_sections(done_lines)
    error_lines = remove_empty_sections(error_lines)

    # Добавляем сводку в начало файла
    done_header = [
        f"# ==================== РАБОЧИЕ САЙТЫ ({len(working)}) ====================",
        f"# Проверено: {len(working) + len(broken)} сайтов",
        f"# Рабочих: {len(working)} | Нерабочих: {len(broken)}",
        "# =======================================================================",
        ""
    ]

    error_header = [
        f"# ==================== НЕРАБОЧИЕ САЙТЫ ({len(broken)}) ====================",
        f"# Проверено: {len(working) + len(broken)} сайтов",
        f"# Рабочих: {len(working)} | Нерабочих: {len(broken)}",
        "# =======================================================================",
        ""
    ]

    with open(done_file, "w", encoding="utf-8") as f:
        f.write('\n'.join(done_header) + '\n')
        f.write('\n'.join(done_lines) + '\n')

    with open(error_file, "w", encoding="utf-8") as f:
        f.write('\n'.join(error_header) + '\n')
        f.write('\n'.join(error_lines) + '\n')


def remove_empty_sections(lines):
    """
    Убирает секции, в которых нет ни одного URL (только заголовок и пустые строки).
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Если это заголовок секции
        if stripped.startswith("#") and not stripped.startswith("# "):
            # Смотрим, есть ли дальше URL до следующего заголовка
            has_urls = False
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line.startswith("#") and not next_line.startswith("# "):
                    break  # Следующая секция
                if next_line and not next_line.startswith("#"):
                    has_urls = True
                    break
                j += 1

            if has_urls:
                result.append(line)
            # Если нет URL — пропускаем заголовок и следующую пустую строку
            else:
                if i + 1 < len(lines) and not lines[i + 1].strip():
                    i += 1  # Пропускаем пустую строку после заголовка
        else:
            result.append(line)
        i += 1

    # Убираем пустые строки в начале
    while result and not result[0].strip():
        result.pop(0)
    # Убираем пустые строки в конце
    while result and not result[-1].strip():
        result.pop()

    return result