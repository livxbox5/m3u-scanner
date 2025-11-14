import urllib.request
import urllib.error
import re
import time
import sys
import os
import ssl
from urllib.parse import urlparse, urljoin, quote
import random
import json
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# Отключаем SSL проверку
ssl._create_default_https_context = ssl._create_unverified_context

class OnlineM3UScanner:
    def __init__(self):
        self.timeout = 15
        self.playlist_file = "playlist/playlist.m3u"
        self.sites_file = "files/site.txt"
        self.cartolog_file = "files/cartolog.txt"
        self.max_workers = 3
        self.max_sites_per_search = 10

        # Базовые источники для поиска
        self.search_sources = [
            "https://raw.githubusercontent.com/iptv-org/iptv/master/channels/ru.m3u",
            "https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u",
            "https://iptv-org.github.io/iptv/countries/ru.m3u",
        ]

        # Загружаем сайты из файла
        self.custom_sites = self.load_custom_sites()

        # Загружаем категории из файла
        self.channel_categories = self.load_channel_categories()

        # Кэш для хранения найденных каналов
        self.channels_cache = {}

    def load_custom_sites(self):
        """Загружает список сайтов из файла site.txt"""
        sites = []
        if os.path.exists(self.sites_file):
            try:
                with open(self.sites_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        site = line.strip()
                        if site and not site.startswith('#'):
                            sites.append(site)
                print(f"📁 Загружено {len(sites)} сайтов из {self.sites_file}")
            except Exception as e:
                print(f"❌ Ошибка загрузки сайтов: {e}")
        else:
            print(f"📝 Файл {self.sites_file} не найден, создаем базовый...")
            self.create_default_sites_file()
            sites = self.load_custom_sites()
        return sites

    def create_default_sites_file(self):
        """Создает файл с сайтами по умолчанию"""
        default_sites = [
            "https://github.com/",
            "https://yandex.ru/",
            "https://google.com/",
            "https://rutube.ru/",
            "https://youtube.com/",
            "https://vk.com/",
            "https://ok.ru/",
            "https://dzen.ru/",
            "https://rambler.ru/",
            "https://mail.ru/",
        ]
        try:
            # Создаем папку files если её нет
            os.makedirs(os.path.dirname(self.sites_file), exist_ok=True)

            with open(self.sites_file, 'w', encoding='utf-8') as f:
                f.write("# Список сайтов для поиска M3U плейлистов\n")
                for site in default_sites:
                    f.write(f"{site}\n")
            print(f"✅ Создан файл {self.sites_file} с {len(default_sites)} сайтами")
        except Exception as e:
            print(f"❌ Ошибка создания файла: {e}")

    def load_channel_categories(self):
        """Загружает категории каналов из файла cartolog.txt"""
        categories = {}
        default_categories = ["Все каналы", "Общие", "Развлекательные", "Музыкальные", "Детские", "Кино"]

        if os.path.exists(self.cartolog_file):
            try:
                with open(self.cartolog_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if ':' in line:
                                # Формат: канал:категория
                                channel, category = line.split(':', 1)
                                categories[channel.strip()] = category.strip()
                            else:
                                # Просто категория
                                categories[line] = line
                print(f"📁 Загружено категорий: {len(categories)} из {self.cartolog_file}")
            except Exception as e:
                print(f"❌ Ошибка загрузки категорий: {e}")
        else:
            print(f"📝 Файл {self.cartolog_file} не найден, создаем базовый...")
            self.create_default_cartolog_file()
            categories = self.load_channel_categories()

        # Добавляем категории по умолчанию если их нет
        for cat in default_categories:
            if cat not in categories.values():
                categories[cat] = cat

        return categories

    def create_default_cartolog_file(self):
        """Создает файл с категориями по умолчанию"""
        default_content = [
            "# Словарь категорий для автоматической группировки каналов",
            "# Формат: название_канала:категория",
            "",
            "# Примеры категорий:",
            "Все каналы",
            "Общие",
            "Развлекательные",
            "Музыкальные",
            "Детские",
            "Кино",
            "Новостные",
            "Спортивные",
            "Познавательные",
            "Региональные",
            "",
            "# Примеры привязки каналов:",
            "# Первый канал:Новостные",
            "# Россия 1:Общие",
            "# НТВ:Развлекательные"
        ]

        try:
            # Создаем папку files если её нет
            os.makedirs(os.path.dirname(self.cartolog_file), exist_ok=True)

            with open(self.cartolog_file, 'w', encoding='utf-8') as f:
                for line in default_content:
                    f.write(f"{line}\n")
            print(f"✅ Создан файл {self.cartolog_file} с категориями")
        except Exception as e:
            print(f"❌ Ошибка создания файла категорий: {e}")

    def get_channel_category(self, channel_name):
        """Определяет категорию для канала"""
        # Сначала ищем точное совпадение
        if channel_name in self.channel_categories:
            return self.channel_categories[channel_name]

        # Ищем частичное совпадение
        for channel_pattern, category in self.channel_categories.items():
            if channel_pattern in channel_name or channel_name in channel_pattern:
                return category

        # Категория по умолчанию
        return "Общие"

    def interactive_category_selection(self, channel_name):
        """Интерактивный выбор категории для канала"""
        print(f"\n🎯 Выбор категории для канала: '{channel_name}'")

        # Получаем существующие категории
        existing_categories = list(set(self.channel_categories.values()))
        existing_categories.sort()

        if existing_categories:
            print("\n📋 Существующие категории:")
            for i, category in enumerate(existing_categories, 1):
                print(f"{i}. {category}")

        print("\n💡 Варианты:")
        print("0. Создать новую категорию")
        print("00. Пропустить (категория 'Общие')")

        while True:
            choice = input("\nВыберите категорию (номер или новое название): ").strip()

            if choice == '00':
                return "Общие"
            elif choice == '0':
                new_category = input("Введите название новой категории: ").strip()
                if new_category:
                    return new_category
                else:
                    print("⚠️  Название категории не может быть пустым")
            elif choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(existing_categories):
                    return existing_categories[index]
                else:
                    print("⚠️  Неверный номер категории")
            else:
                # Пользователь ввел новое название
                return choice

    def make_request(self, url, method='GET', max_retries=2):
        """Выполняет HTTP запрос с повторными попытками"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        }

        for attempt in range(max_retries):
            try:
                if method.upper() == 'HEAD':
                    req = urllib.request.Request(url, headers=headers, method='HEAD')
                else:
                    req = urllib.request.Request(url, headers=headers)

                response = urllib.request.urlopen(req, timeout=self.timeout)
                return response
            except Exception as e:
                if attempt == max_retries - 1:
                    return None
                time.sleep(1)
        return None

    def search_custom_sites(self, channel_name):
        """Ищет M3U и M3U8 плейлисты на пользовательских сайтах"""
        print("🌐 Поиск на пользовательских сайтах...")

        found_urls = set()

        # Ограничиваем количество сайтов для поиска
        sites_to_search = self.custom_sites[:self.max_sites_per_search]

        for site in sites_to_search:
            try:
                print(f"   🔍 Проверяем: {site}")

                # Для поисковых систем - используем поисковые запросы
                if any(engine in site for engine in ['yandex.ru', 'google.com', 'youtube.com', 'rutube.ru']):
                    search_urls = self.search_on_engine(site, channel_name)
                    found_urls.update(search_urls)
                else:
                    # Для обычных сайтов - ищем M3U/M3U8 ссылки
                    m3u_urls = self.scan_site_for_m3u(site, channel_name)
                    found_urls.update(m3u_urls)

                time.sleep(1)  # Задержка между запросами

            except Exception as e:
                print(f"   💥 Ошибка на {site}: {e}")
                continue

        return list(found_urls)[:30]  # Ограничиваем количество

    def search_on_engine(self, engine_url, channel_name):
        """Ищет на поисковых системах и видео платформах"""
        found_urls = set()

        try:
            if 'yandex.ru' in engine_url:
                # Поиск через Yandex
                search_url = f"https://yandex.ru/search/?text={quote(channel_name + ' m3u8 m3u live stream')}"
                response = self.make_request(search_url)
                if response:
                    content = response.read().decode('utf-8', errors='ignore')
                    # Ищем M3U8 и M3U ссылки
                    m3u_urls = re.findall(r'https?://[^\s"<>]+\.m3u8?', content)
                    found_urls.update(m3u_urls)

            elif 'google.com' in engine_url:
                # Поиск через Google
                search_url = f"https://www.google.com/search?q={quote(channel_name + ' m3u8 m3u iptv')}"
                response = self.make_request(search_url)
                if response:
                    content = response.read().decode('utf-8', errors='ignore')
                    m3u_urls = re.findall(r'https?://[^\s"<>]+\.m3u8?', content)
                    found_urls.update(m3u_urls)

            elif 'youtube.com' in engine_url:
                # Поиск на YouTube
                search_url = f"https://www.youtube.com/results?search_query={quote(channel_name + ' live stream')}"
                response = self.make_request(search_url)
                if response:
                    content = response.read().decode('utf-8', errors='ignore')
                    video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', content)
                    for video_id in video_ids[:5]:
                        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                        found_urls.add(youtube_url)

            elif 'rutube.ru' in engine_url:
                # Поиск на RUTube
                search_url = f"https://rutube.ru/api/search/video/?query={quote(channel_name)}"
                response = self.make_request(search_url)
                if response:
                    content = response.read().decode('utf-8', errors='ignore')
                    try:
                        data = json.loads(content)
                        if 'results' in data:
                            for video in data['results'][:5]:
                                video_url = f"https://rutube.ru/video/{video.get('id', '')}/"
                                found_urls.add(video_url)
                    except:
                        video_ids = re.findall(r'href="/video/([a-zA-Z0-9_-]+)/"', content)
                        for video_id in video_ids[:5]:
                            rutube_url = f"https://rutube.ru/video/{video_id}/"
                            found_urls.add(rutube_url)

        except Exception as e:
            print(f"      Ошибка поиска на {engine_url}: {e}")

        return list(found_urls)

    def scan_site_for_m3u(self, site_url, channel_name):
        """Сканирует сайт на наличие M3U и M3U8 плейлистов"""
        found_urls = set()

        try:
            response = self.make_request(site_url)
            if response:
                content = response.read().decode('utf-8', errors='ignore')

                # Ищем прямые M3U8 ссылки (приоритет)
                m3u8_urls = re.findall(r'https?://[^\s"\'<>]+\.m3u8', content)
                found_urls.update(m3u8_urls)

                # Ищем прямые M3U ссылки
                m3u_urls = re.findall(r'https?://[^\s"\'<>]+\.m3u', content)
                found_urls.update(m3u_urls)

                # Ищем ссылки на плейлисты в href
                playlist_urls = re.findall(r'href="([^"]+\.m3u8?)"', content, re.IGNORECASE)
                for url in playlist_urls:
                    if url.startswith('/'):
                        # Относительная ссылка
                        full_url = urljoin(site_url, url)
                        found_urls.add(full_url)
                    elif url.startswith('http'):
                        found_urls.add(url)

                # Ищем страницы с упоминанием канала
                if channel_name.lower() in content.lower():
                    # На странице есть упоминание канала, ищем все возможные ссылки
                    all_urls = re.findall(r'href="([^"]+)"', content)
                    for url in all_urls:
                        if any(keyword in url.lower() for keyword in ['tv', 'stream', 'live', 'channel', 'iptv', 'm3u']):
                            if url.startswith('/'):
                                full_url = urljoin(site_url, url)
                                found_urls.add(full_url)
                            elif url.startswith('http'):
                                found_urls.add(url)

        except Exception as e:
            print(f"      Ошибка сканирования {site_url}: {e}")

        return list(found_urls)

    def search_github_simple(self, channel_name):
        """Упрощенный поиск на GitHub"""
        print("🐙 Быстрый поиск на GitHub...")

        found_urls = set()

        # Прямые ссылки на популярные IPTV репозитории
        github_urls = [
            "https://raw.githubusercontent.com/iptv-org/iptv/master/channels/ru.m3u",
            "https://raw.githubusercontent.com/Free-IPTV/Countries/master/Russia.m3u",
            "https://raw.githubusercontent.com/gglabs/iptv/master/index.m3u",
        ]

        for url in github_urls:
            try:
                content = self.download_playlist(url)
                if content:
                    # Ищем канал в плейлисте
                    streams = self.extract_channels_from_playlist(content, channel_name)
                    for stream in streams:
                        found_urls.add(stream['url'])
            except:
                continue

        return list(found_urls)

    def download_playlist(self, url):
        """Скачивает плейлист с источника"""
        try:
            response = self.make_request(url, 'GET')
            if response and response.getcode() == 200:
                content = response.read().decode('utf-8', errors='ignore')
                return content
            return None
        except Exception as e:
            return None

    def search_iptv_sources(self, channel_name):
        """Поиск в специализированных IPTV источниках"""
        iptv_sources = [
            "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
            "https://iptv-org.github.io/iptv/categories/news.m3u",
            "https://iptv-org.github.io/iptv/categories/sports.m3u",
            "https://raw.githubusercontent.com/Free-IPTV/Countries/master/Russia.m3u",
            "https://raw.githubusercontent.com/ivanskod/iptv/main/iptv.m3u",
        ]

        streams = []
        for source in iptv_sources:
            try:
                content = self.download_playlist(source)
                if content:
                    found = self.extract_channels_from_playlist(content, channel_name)
                    streams.extend(found)
            except:
                continue
        return streams

    def search_in_online_sources(self, channel_name):
        """Улучшенный поиск канала в интернете с акцентом на M3U/M3U8"""
        print("🌐 Запуск расширенного поиска...")
        all_streams = []

        # 1. Поиск на пользовательских сайтах
        print("   🌐 Этап 1/4: Поиск на пользовательских сайтах...")
        custom_urls = self.search_custom_sites(channel_name)
        print(f"      Найдено: {len(custom_urls)} URL")

        # 2. Поиск на GitHub
        print("   🐙 Этап 2/4: Поиск на GitHub...")
        github_urls = self.search_github_simple(channel_name)
        print(f"      Найдено: {len(github_urls)} URL")

        # 3. Проверка базовых источников
        print("   📡 Этап 3/4: Проверка базовых источников...")
        for source_url in self.search_sources:
            try:
                playlist_content = self.download_playlist(source_url)
                if playlist_content:
                    found_streams = self.extract_channels_from_playlist(playlist_content, channel_name)
                    all_streams.extend(found_streams)
            except:
                continue

        # 4. Поиск в специализированных IPTV источниках
        print("   🔍 Этап 4/4: Поиск в IPTV источниках...")
        iptv_streams = self.search_iptv_sources(channel_name)
        all_streams.extend(iptv_streams)

        # Объединяем все URL
        all_urls = list(set(custom_urls + github_urls))
        print(f"   📊 Всего уникальных URL: {len(all_urls)}")

        # Быстрая проверка URL
        print("   🔧 Быстрая проверка URL...")
        valid_streams = self.quick_check_urls(all_urls, channel_name)

        all_streams.extend(valid_streams)
        return all_streams

    def quick_check_urls(self, urls, channel_name):
        """Улучшенная быстрая проверка URL"""
        valid_streams = []

        def check_url(url):
            try:
                # Для YouTube и RUTube ссылок
                if any(platform in url for platform in ['youtube.com/watch', 'youtu.be', 'rutube.ru/video']):
                    return {
                        'name': f"{channel_name}",
                        'url': url,
                        'source': 'video_platform',
                        'group': 'Видеоплатформы'
                    }

                # Для M3U8 ссылок - приоритет
                elif '.m3u8' in url.lower():
                    response = self.make_request(url, 'HEAD')
                    if response and response.getcode() == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if any(ct in content_type.lower() for ct in ['video', 'audio', 'application', 'octet-stream', 'mpegurl']):
                            return {
                                'name': f"{channel_name}",
                                'url': url,
                                'source': 'm3u8',
                                'group': 'M3U8 потоки'
                            }

                # Для M3U ссылок
                elif '.m3u' in url.lower():
                    response = self.make_request(url, 'HEAD')
                    if response and response.getcode() == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if any(ct in content_type.lower() for ct in ['video', 'audio', 'application', 'octet-stream', 'mpegurl']):
                            return {
                                'name': f"{channel_name}",
                                'url': url,
                                'source': 'm3u',
                                'group': 'M3U плейлисты'
                            }

                # Для других ссылок - пробуем GET
                else:
                    response = self.make_request(url, 'GET', max_retries=1)
                    if response and response.getcode() == 200:
                        return {
                            'name': f"{channel_name}",
                            'url': url,
                            'source': 'web',
                            'group': 'Веб-ссылки'
                        }

                return None
            except:
                return None

        # Проверяем URL параллельно с ограничением
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(check_url, url) for url in urls[:30]]

            for future in as_completed(futures):
                result = future.result()
                if result:
                    valid_streams.append(result)

        return valid_streams

    def extract_channels_from_playlist(self, playlist_content, channel_name):
        """Извлекает каналы из плейлиста"""
        streams = []
        lines = playlist_content.split('\n')

        # Генерируем варианты для поиска
        search_patterns = self.generate_search_patterns(channel_name)

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if line.startswith('#EXTINF:'):
                # Извлекаем атрибуты из строки EXTINF
                channel_info = self.parse_extinf_line(line)

                # Проверяем совпадение по названию
                channel_title = channel_info.get('name', '').lower()
                if any(pattern in channel_title for pattern in search_patterns):
                    # Следующая строка должна быть URL
                    if i + 1 < len(lines):
                        url = lines[i + 1].strip()
                        if url and not url.startswith('#') and url.startswith('http'):
                            streams.append({
                                'name': channel_info.get('name', channel_name),
                                'url': url,
                                'source': 'playlist',
                                'group': channel_info.get('group', 'Общие'),
                                'tvg_id': channel_info.get('tvg_id', ''),
                                'tvg_logo': channel_info.get('tvg_logo', ''),
                                'catchup': channel_info.get('catchup', ''),
                                'catchup_days': channel_info.get('catchup_days', ''),
                                'user_agent': channel_info.get('user_agent', '')
                            })
                            i += 1
            i += 1

        return streams

    def parse_extinf_line(self, extinf_line):
        """Парсит строку EXTINF и извлекает все атрибуты"""
        info = {}

        # Извлекаем атрибуты в формате key="value"
        attributes = re.findall(r'(\w+)=["\']([^"\']*)["\']', extinf_line)
        for key, value in attributes:
            info[key] = value

        # Извлекаем название канала (после последней запятой)
        if ',' in extinf_line:
            name = extinf_line.split(',')[-1].strip()
            info['name'] = re.sub(r'["\'<>]', '', name)

        return info

    def generate_search_patterns(self, channel_name):
        """Генерирует варианты для поиска"""
        name_lower = channel_name.lower()

        patterns = [
            name_lower,
            name_lower.replace(' ', ''),
            name_lower.replace(' ', '.'),
            name_lower.replace(' ', '-'),
            name_lower.replace('тв', 'tv'),
            name_lower.replace('tv', 'тв'),
        ]

        # Убираем пустые и дубликаты
        return list(set([p for p in patterns if p and len(p) > 1]))

    def check_stream_with_ffmpeg(self, url):
        """Проверяет поток с помощью ffmpeg (если установлен)"""
        try:
            # Проверяем наличие ffmpeg
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
            if result.returncode != 0:
                return None

            # Пробуем получить информацию о потоке
            cmd = [
                'ffmpeg',
                '-i', url,
                '-t', '10',  # Только 10 секунд
                '-f', 'null',
                '-',
                '-hide_banner',
                '-loglevel', 'error'
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=15)

            # Если нет критических ошибок, считаем поток рабочим
            if result.returncode == 0 or "Invalid data found" not in result.stderr.decode():
                return True
            return False

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return None

    def check_single_stream(self, stream_info):
        """Проверяет работоспособность ссылки с улучшенной проверкой"""
        try:
            url = stream_info['url']

            if not url.startswith('http'):
                return None

            print(f"    🔧 Проверка: {url[:60]}...")

            # Для YouTube и RUTube ссылок - считаем рабочими без проверки
            if 'youtube.com/watch' in url or 'youtu.be' in url or 'rutube.ru/video' in url:
                return {**stream_info, 'working': True, 'status': 'Видео платформа'}

            # Пробуем проверку через ffmpeg сначала
            ffmpeg_result = self.check_stream_with_ffmpeg(url)
            if ffmpeg_result:
                return {**stream_info, 'working': True, 'status': 'FFmpeg проверен'}
            elif ffmpeg_result is False:
                return {**stream_info, 'working': False, 'status': 'FFmpeg ошибка'}

            # Для M3U8 ссылок - углубленная проверка
            if url.endswith('.m3u8') or 'm3u8' in url:
                return self.check_m3u8_stream(url, stream_info)

            # Для M3U ссылок
            elif url.endswith('.m3u') or 'm3u' in url:
                return self.check_m3u_stream(url, stream_info)

            # Для других типов ссылок
            else:
                return self.check_generic_stream(url, stream_info)

        except Exception as e:
            return {**stream_info, 'working': False, 'status': f'Ошибка: {str(e)}'}

    def check_m3u8_stream(self, url, stream_info):
        """Углубленная проверка M3U8 потоков"""
        try:
            # Сначала пробуем HEAD запрос
            response = self.make_request(url, 'HEAD')
            if response and response.getcode() == 200:
                content_type = response.headers.get('Content-Type', '')
                if any(t in content_type.lower() for t in ['video', 'application', 'octet-stream', 'mpegurl']):
                    return {**stream_info, 'working': True, 'status': 'M3U8 доступен'}

            # Затем GET запрос для анализа содержимого
            response = self.make_request(url, 'GET')
            if response and response.getcode() == 200:
                content = response.read(10000).decode('utf-8', errors='ignore')

                # Проверяем валидность M3U8 содержимого
                if self.is_valid_m3u8_content(content):
                    return {**stream_info, 'working': True, 'status': 'M3U8 валидный'}

                # Если это плейлист плейлистов, проверяем первый суб-поток
                if '#EXT-X-STREAM-INF' in content:
                    base_url = '/'.join(url.split('/')[:-1]) + '/' if '/' in url else ''
                    sub_streams = re.findall(r'[^\s]+\.m3u8', content)
                    if sub_streams:
                        first_sub = sub_streams[0]
                        if not first_sub.startswith('http'):
                            first_sub = base_url + first_sub
                        sub_response = self.make_request(first_sub, 'HEAD')
                        if sub_response and sub_response.getcode() == 200:
                            return {**stream_info, 'working': True, 'status': 'M3U8 мастер-плейлист'}

            return {**stream_info, 'working': False, 'status': 'M3U8 невалидный'}

        except Exception as e:
            return {**stream_info, 'working': False, 'status': f'M3U8 ошибка'}

    def check_m3u_stream(self, url, stream_info):
        """Проверка M3U плейлистов"""
        try:
            response = self.make_request(url, 'GET')
            if response and response.getcode() == 200:
                content = response.read(10000).decode('utf-8', errors='ignore')

                # Проверяем валидность M3U содержимого
                if '#EXTM3U' in content and '#EXTINF' in content:
                    return {**stream_info, 'working': True, 'status': 'M3U валидный'}

            return {**stream_info, 'working': False, 'status': 'M3U невалидный'}

        except Exception as e:
            return {**stream_info, 'working': False, 'status': f'M3U ошибка'}

    def is_valid_m3u8_content(self, content):
        """Проверяет валидность M3U8 содержимого"""
        valid_indicators = [
            '#EXTM3U',
            '#EXT-X-VERSION',
            '#EXT-X-TARGETDURATION',
            '#EXTINF',
            '#EXT-X-STREAM-INF',
            '.ts',  # TS сегменты
        ]

        return any(indicator in content for indicator in valid_indicators)

    def check_generic_stream(self, url, stream_info):
        """Проверка общих типов потоков"""
        try:
            # Пробуем HEAD запрос
            response = self.make_request(url, 'HEAD')
            if response and response.getcode() == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                content_length = response.headers.get('Content-Length')

                # Принимаем различные видео/аудио форматы
                valid_content_types = [
                    'video/', 'audio/', 'application/', 'octet-stream',
                    'x-mpegurl', 'vnd.apple.mpegurl'
                ]

                if any(ct in content_type for ct in valid_content_types):
                    return {**stream_info, 'working': True, 'status': 'Поток доступен'}

                # Если Content-Length большой, возможно это поток
                if content_length and int(content_length) > 1000000:  # > 1MB
                    return {**stream_info, 'working': True, 'status': 'Большой поток'}

            # Пробуем GET запрос с ограничением по размеру
            response = self.make_request(url, 'GET')
            if response and response.getcode() == 200:
                # Читаем только первые 1024 байта для проверки
                data = response.read(1024)
                if len(data) > 100:  # Если получили данные
                    return {**stream_info, 'working': True, 'status': 'Данные получены'}

            return {**stream_info, 'working': False, 'status': 'Не доступен'}

        except Exception as e:
            return {**stream_info, 'working': False, 'status': f'Ошибка проверки'}

    def check_streams(self, streams):
        """Проверяет все найденные ссылки с улучшенной логикой"""
        working_streams = []
        total = len(streams)

        if total == 0:
            return []

        print(f"🔧 Проверка {total} найденных ссылок...")
        print("💡 Используется улучшенная проверка...")

        # Разделяем потоки по типам для приоритетной проверки
        priority_streams = []
        other_streams = []

        for stream in streams:
            url = stream['url']
            if any(ext in url.lower() for ext in ['.m3u8', 'youtube', 'rutube']):
                priority_streams.append(stream)
            else:
                other_streams.append(stream)

        # Проверяем приоритетные потоки сначала
        all_streams_to_check = priority_streams + other_streams

        # Используем многопоточность для проверки
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_stream = {executor.submit(self.check_single_stream, stream): stream for stream in all_streams_to_check}

            for i, future in enumerate(as_completed(future_to_stream), 1):
                result = future.result()
                if result:
                    if result['working']:
                        working_streams.append(result)
                        print(f"  [{i}/{total}] ✅ РАБОТАЕТ - {result['status']}")
                    else:
                        print(f"  [{i}/{total}] ❌ Не работает - {result['status']}")

                # Добавляем небольшую задержку между проверками
                if i % 5 == 0:
                    time.sleep(1)

        # Сортируем рабочие потоки по качеству
        working_streams.sort(key=lambda x: (
            0 if 'youtube' in x['url'] else
            1 if 'rutube' in x['url'] else
            2 if '.m3u8' in x['url'] else
            3 if '.m3u' in x['url'] else 4
        ))

        return working_streams

    def search_and_update_channel(self, channel_name):
        """Поиск и обновление канала в плейлисте с улучшенной проверкой"""
        print(f"\n🚀 Запуск поиска: '{channel_name}'")
        print("⏳ Это может занять 2-3 минуты...")
        print("💡 Используется улучшенная система проверки...")

        # Определяем категорию
        category = self.get_channel_category(channel_name)
        if category == "Общие":
            # Если категория не определена, предлагаем выбрать
            category = self.interactive_category_selection(channel_name)
            if category and category != "Общие":
                self.save_channel_category(channel_name, category)

        start_time = time.time()
        all_streams = self.search_in_online_sources(channel_name)

        if not all_streams:
            print("❌ Не найдено ни одной ссылки для проверки")
            return False

        # Проверяем работоспособность
        working_streams = self.check_streams(all_streams)
        search_time = time.time() - start_time

        if working_streams:
            # Добавляем категорию к каждому стриму
            for stream in working_streams:
                stream['group'] = category

            print("\n🎉" + "=" * 50)
            print(f"✅ НАЙДЕНО РАБОЧИХ ССЫЛОК: {len(working_streams)}")
            print(f"📂 Категория: {category}")
            print(f"⏱️  Время поиска: {search_time:.1f} секунд")
            print("🎉" + "=" * 50)

            # Показываем найденные рабочие ссылки
            print(f"\n📺 Рабочие ссылки:")
            for i, stream in enumerate(working_streams, 1):
                print(f"{i}. {stream['name']}")
                print(f"   📂 {stream['group']}")
                print(f"   🔗 {stream['url'][:80]}...")
                print(f"   🏷️  {stream['status']}")

            # Обновляем канал в плейлисте
            success = self.update_channel_in_playlist(channel_name, working_streams)

            if success:
                print(f"\n🔄 КАНАЛ ОБНОВЛЕН: {channel_name}")
                print(f"📂 Категория: {category}")
                print(f"📺 Рабочих ссылок: {len(working_streams)}")
            else:
                print("❌ Ошибка при обновлении плейлиста")

        else:
            print(f"\n❌ Для канала '{channel_name}' не найдено рабочих ссылок")
            print("💡 Советы по улучшению поиска:")
            print("   - Добавьте больше сайтов в files/site.txt")
            print("   - Используйте точное название канала")
            print("   - Проверьте наличие ffmpeg для лучшей проверки")
            print("   - Попробуйте английское название канала")

            # Удаляем канал из плейлиста если нет рабочих ссылок
            self.update_channel_in_playlist(channel_name, [])

        return len(working_streams) > 0

    def save_channel_category(self, channel_name, category):
        """Сохраняет категорию для канала в файл"""
        try:
            # Обновляем в памяти
            self.channel_categories[channel_name] = category

            # Читаем существующий файл
            lines = []
            if os.path.exists(self.cartolog_file):
                with open(self.cartolog_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

            # Удаляем старую запись если есть
            lines = [line for line in lines if not line.startswith(f"{channel_name}:")]

            # Добавляем новую запись
            lines.append(f"{channel_name}:{category}\n")

            # Сохраняем обратно
            with open(self.cartolog_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            print(f"💾 Категория сохранена: {channel_name} -> {category}")
            return True

        except Exception as e:
            print(f"❌ Ошибка сохранения категории: {e}")
            return False

    def update_channel_in_playlist(self, channel_name, new_streams):
        """Обновляет канал в плейлисте"""
        # Загружаем существующие каналы
        existing_channels = self.load_existing_channels()

        # Обновляем канал
        if new_streams:
            existing_channels[channel_name] = new_streams
            print(f"🔄 Обновлен канал: {channel_name} ({len(new_streams)} ссылок)")
        else:
            # Если нет рабочих ссылок, удаляем канал
            if channel_name in existing_channels:
                del existing_channels[channel_name]
                print(f"🗑️  Удален канал: {channel_name} (нет рабочих ссылок)")

        # Сохраняем обновленный плейлист
        return self.save_full_playlist(existing_channels)

    def load_existing_channels(self):
        """Загружает существующие каналы из плейлиста (только после разделителя)"""
        channels = {}
        if os.path.exists(self.playlist_file):
            try:
                with open(self.playlist_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Находим разделитель #############################
                parts = content.split('#############################')
                if len(parts) > 1:
                    # Берем только часть после разделителя
                    channels_content = parts[1]
                    lines = channels_content.split('\n')

                    i = 0
                    current_stream = None

                    while i < len(lines):
                        line = lines[i].strip()

                        if line.startswith('#EXTINF:'):
                            # Парсим информацию о канале
                            channel_info = self.parse_extinf_line(line)
                            current_stream = channel_info

                            # Следующая строка должна быть URL
                            if i + 1 < len(lines):
                                url_line = lines[i + 1].strip()
                                if url_line.startswith('http'):
                                    channel_name = current_stream.get('name', 'Unknown')
                                    if channel_name not in channels:
                                        channels[channel_name] = []

                                    channels[channel_name].append({
                                        'name': current_stream.get('name', 'Unknown'),
                                        'url': url_line,
                                        'group': current_stream.get('group-title', 'Общие'),
                                        'tvg_id': current_stream.get('tvg-id', ''),
                                        'tvg_logo': current_stream.get('tvg-logo', ''),
                                        'catchup': current_stream.get('catchup', ''),
                                        'catchup_days': current_stream.get('catchup-days', ''),
                                        'user_agent': current_stream.get('user-agent', '')
                                    })
                                    i += 1  # Пропускаем URL строку
                        i += 1

            except Exception as e:
                print(f"❌ Ошибка загрузки плейлиста: {e}")

        return channels

    def save_full_playlist(self, channels_dict):
        """Сохраняет полный плейлист с вашим кастомным шаблоном"""
        try:
            # Создаем папку playlist если её нет
            os.makedirs(os.path.dirname(self.playlist_file), exist_ok=True)

            with open(self.playlist_file, 'w', encoding='utf-8') as f:
                # Ваш кастомный шаблон
                f.write('#EXTM3U url-tvg="https://iptvx.one/EPG,https://api.catcast.tv/api/timetable/epg.xml?channel_ids=40783"\n')
                f.write(f"# Обновлен: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Всего каналов: {len(channels_dict)}\n")
                f.write(f"# Всего ссылок: {sum(len(streams) for streams in channels_dict.values())}\n\n")

                # Ваши информационные каналы
                f.write('#EXTINF:-1 group-title="Общие" , Ссылка на плейлист устарела\n')
                f.write('https://raw.githubusercontent.com/livxbox5/m3u-scanner/refs/heads/main/m3u-scanner/playlist/playlist.m3u\n')
                f.write('#EXTINF:-1 group-title="Общие" , ссылка https://raw.githubusercontent.com/livxbox5/m3u-scanner/refs/heads/main/m3u-scanner/playlist/playlist.m3u\n')
                f.write('https://raw.githubusercontent.com/livxbox5/m3u-scanner/refs/heads/main/m3u-scanner/playlist/playlist.m3u\n')
                f.write('#EXTINF:-1 group-title="Общие" , Telegram-канал https://t.me/NexusIPTVGroups\n')
                f.write('#EXTINF:-1 group-title="Общие" , Telegram-чат https://t.me/NexusIPTVGroups\n')
                f.write('#EXTINF:-1 group-title="Общие" , Telegram-резерв https://t.me/NexusIPTVGroups\n')
                f.write('#############################\n\n')

                # Сохраняем все каналы (только после разделителя)
                for channel_name, streams in channels_dict.items():
                    for stream in streams:
                        # Формируем строку EXTINF с атрибутами
                        extinf_parts = ['#EXTINF:-1']

                        # Добавляем атрибуты
                        if stream.get('tvg_id'):
                            extinf_parts.append(f'tvg-id="{stream["tvg_id"]}"')
                        if stream.get('tvg_logo'):
                            extinf_parts.append(f'tvg-logo="{stream["tvg_logo"]}"')
                        if stream.get('group'):
                            extinf_parts.append(f'group-title="{stream["group"]}"')
                        if stream.get('catchup'):
                            extinf_parts.append(f'catchup="{stream["catchup"]}"')
                        if stream.get('catchup_days'):
                            extinf_parts.append(f'catchup-days="{stream["catchup_days"]}"')

                        # Добавляем название канала
                        extinf_parts.append(f', {stream["name"]}')

                        f.write(' '.join(extinf_parts) + '\n')

                        # Добавляем user-agent если есть
                        if stream.get('user_agent'):
                            f.write(f'#EXTVLCOPT:http-user-agent={stream["user_agent"]}\n')

                        # Добавляем URL
                        f.write(f'{stream["url"]}\n')

            print(f"💾 Плейлист сохранен: {self.playlist_file}")
            print(f"📊 Всего каналов: {len(channels_dict)}")
            print(f"📺 Всего ссылок: {sum(len(streams) for streams in channels_dict.values())}")
            return True

        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    def refresh_all_channels(self):
        """Обновляет все каналы в плейлисте"""
        print("🔄 ЗАПУСК ПОЛНОГО ОБНОВЛЕНИЯ ВСЕХ КАНАЛОВ...")

        # Загружаем существующие каналы (только после разделителя)
        existing_channels = self.load_existing_channels()

        if not existing_channels:
            print("❌ В плейлисте нет каналов для обновления")
            return

        print(f"📊 Найдено каналов для обновления: {len(existing_channels)}")

        updated_count = 0
        failed_count = 0

        for channel_name in list(existing_channels.keys()):
            print(f"\n{'='*60}")
            print(f"🔄 ОБНОВЛЕНИЕ: {channel_name}")
            print(f"{'='*60}")

            try:
                working_streams = self.search_channel_online(channel_name)

                if working_streams:
                    # Сохраняем категорию из существующего канала
                    category = "Общие"
                    if existing_channels[channel_name]:
                        category = existing_channels[channel_name][0].get('group', 'Общие')

                    # Добавляем категорию к новым стримам
                    for stream in working_streams:
                        stream['group'] = category

                    existing_channels[channel_name] = working_streams
                    updated_count += 1
                    print(f"✅ ОБНОВЛЕН: {channel_name} ({len(working_streams)} ссылок)")
                else:
                    # Удаляем канал если нет рабочих ссылок
                    del existing_channels[channel_name]
                    failed_count += 1
                    print(f"❌ УДАЛЕН: {channel_name} (нет рабочих ссылок)")

                # Пауза между каналами
                time.sleep(2)

            except Exception as e:
                print(f"💥 ОШИБКА при обновлении {channel_name}: {e}")
                failed_count += 1
                continue

        # Сохраняем обновленный плейлист
        if self.save_full_playlist(existing_channels):
            print(f"\n🎉 ОБНОВЛЕНИЕ ЗАВЕРШЕНО!")
            print(f"✅ Обновлено каналов: {updated_count}")
            print(f"❌ Удалено каналов: {failed_count}")
            print(f"📊 Итого в плейлисте: {len(existing_channels)} каналов")
        else:
            print("❌ Ошибка сохранения обновленного плейлиста")

    def search_channel_online(self, channel_name):
        """Основной поиск канала в интернете"""
        print(f"🎯 Поиск канала: '{channel_name}'")

        # Ищем в онлайн источниках
        all_streams = self.search_in_online_sources(channel_name)

        # Убираем дубликаты
        unique_streams = []
        seen_urls = set()
        for stream in all_streams:
            if stream['url'] not in seen_urls:
                unique_streams.append(stream)
                seen_urls.add(stream['url'])

        print(f"\n📊 Всего найдено ссылок: {len(unique_streams)}")

        if not unique_streams:
            print("❌ Ссылки не найдены в интернете")
            return []

        # Проверяем работоспособность
        working_streams = self.check_streams(unique_streams)

        # Добавляем нумерацию к каналам
        numbered_streams = self.add_numbering_to_channels(working_streams)

        return numbered_streams

    def add_numbering_to_channels(self, streams):
        """Добавляет нумерацию к каналам с одинаковыми названиями"""
        name_count = {}
        numbered_streams = []

        for stream in streams:
            original_name = stream['name']

            # Считаем количество каналов с таким названием
            if original_name not in name_count:
                name_count[original_name] = 0
            name_count[original_name] += 1

            # Если это первый канал с таким названием, оставляем без номера
            if name_count[original_name] == 1:
                numbered_name = original_name
            else:
                # Добавляем номер к названию
                numbered_name = f"{original_name} #{name_count[original_name]}"

            # Создаем новый stream с пронумерованным названием
            numbered_stream = stream.copy()
            numbered_stream['name'] = numbered_name
            numbered_streams.append(numbered_stream)

        return numbered_streams

    def show_categories_statistics(self):
        """Показывает статистику по категориям"""
        existing_channels = self.load_existing_channels()

        if not existing_channels:
            print("📝 Плейлист пуст")
            return

        category_stats = {}
        for channel_name, streams in existing_channels.items():
            if streams:
                category = streams[0].get('group', 'Общие')
                if category not in category_stats:
                    category_stats[category] = []
                category_stats[category].append(channel_name)

        print(f"\n📊 СТАТИСТИКА ПО КАТЕГОРИЯМ:")
        print(f"📁 Всего категорий: {len(category_stats)}")

        for category, channels in sorted(category_stats.items()):
            print(f"\n📂 {category}: {len(channels)} каналов")
            for channel in sorted(channels)[:10]:
                print(f"   📺 {channel}")
            if len(channels) > 10:
                print(f"   ... и еще {len(channels) - 10} каналов")

def interactive_mode():
    """Интерактивный режим работы с улучшенным интерфейсом"""
    scanner = OnlineM3UScanner()

    print("🎬" + "=" * 70)
    print("🌐 SMART M3U SCANNER - УЛУЧШЕННАЯ ВЕРСИЯ")
    print("🎬" + "=" * 70)
    print("📡 Поиск M3U и M3U8 плейлистов с улучшенной проверкой")
    print(f"📁 Источники: {len(scanner.custom_sites)} сайтов")
    print(f"📂 Категории: {len(scanner.channel_categories)}")
    print(f"💾 Результаты: {scanner.playlist_file}")
    print("💡 Теперь с поддержкой M3U/M3U8 и улучшенной проверкой потоков")
    print("=" * 70)

    # Проверяем наличие ffmpeg
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode == 0:
            print("✅ FFmpeg обнаружен - используется улучшенная проверка")
        else:
            print("ℹ️  FFmpeg не найден - используется базовая проверка")
    except:
        print("ℹ️  FFmpeg не найден - используется базовая проверка")

    # Статистика плейлиста
    existing_channels = scanner.load_existing_channels()
    if existing_channels:
        total_streams = sum(len(streams) for streams in existing_channels.values())
        print(f"📊 В плейлисте: {len(existing_channels)} каналов, {total_streams} ссылок")
    else:
        print("📝 Плейлист будет создан при первом поиске")

    while True:
        print("\n" + "🎯" + "=" * 60)
        print("1. 🔍 Поиск и обновление одного канала")
        print("2. 🔄 Полное обновление всех каналов")
        print("3. 📊 Статистика плейлиста")
        print("4. 📂 Статистика по категориям")
        print("5. ⚙️  Проверка системы")
        print("6. 🚪 Выход")

        choice = input("\nВыберите действие (1-6): ").strip()

        if choice == '1':
            channel_name = input("📺 Введите название телеканала: ").strip()
            if channel_name:
                scanner.search_and_update_channel(channel_name)
            else:
                print("⚠️  Пожалуйста, введите название канала")

        elif choice == '2':
            confirm = input("⚠️  Вы уверены? Это может занять много времени (y/n): ").strip().lower()
            if confirm == 'y':
                scanner.refresh_all_channels()

        elif choice == '3':
            existing_channels = scanner.load_existing_channels()
            if existing_channels:
                total_streams = sum(len(streams) for streams in existing_channels.values())
                print(f"\n📊 СТАТИСТИКА ПЛЕЙЛИСТА:")
                print(f"📁 Каналов: {len(existing_channels)}")
                print(f"🔗 Ссылок: {total_streams}")
                print(f"\n📺 Список каналов:")
                for i, channel_name in enumerate(existing_channels.keys(), 1):
                    category = existing_channels[channel_name][0].get('group', 'Общие') if existing_channels[channel_name] else 'Общие'
                    print(f"{i}. {channel_name} ({len(existing_channels[channel_name])} ссылок) - {category}")
            else:
                print("📝 Плейлист пуст")

        elif choice == '4':
            scanner.show_categories_statistics()

        elif choice == '5':
            print("\n🔧 ПРОВЕРКА СИСТЕМЫ:")
            # Проверка ffmpeg
            try:
                result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
                if result.returncode == 0:
                    print("✅ FFmpeg: установлен")
                else:
                    print("❌ FFmpeg: не установлен")
            except:
                print("❌ FFmpeg: не установлен")

            # Проверка файлов
            print(f"📁 Файл сайтов: {'✅ существует' if os.path.exists(scanner.sites_file) else '❌ отсутствует'}")
            print(f"📁 Файл категорий: {'✅ существует' if os.path.exists(scanner.cartolog_file) else '❌ отсутствует'}")
            print(f"📁 Плейлист: {'✅ существует' if os.path.exists(scanner.playlist_file) else '❌ отсутствует'}")

        elif choice == '6' or choice.lower() == 'exit':
            print("👋 Выход из программы...")
            break

        else:
            print("⚠️  Неверный выбор, попробуйте снова")

def main():
    if len(sys.argv) == 1:
        interactive_mode()
    else:
        print("🌐 Smart M3U Scanner - Автоматическое обновление плейлиста")
        print("Использование: python M3UScanner.py")
        print("Поиск и обновление M3U/M3U8 плейлистов на пользовательских сайтах")

if __name__ == "__main__":
    main()