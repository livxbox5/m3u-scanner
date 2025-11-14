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
        self.timeout = 10
        self.playlist_file = "playlist/playlist.m3u"
        self.sites_file = "files/site.txt"
        self.cartolog_file = "files/cartolog.txt"
        self.channels_file = "files/Channels.txt"  # Файл со списком каналов для поиска
        self.max_workers = 5
        self.max_sites_per_search = 15

        # Улучшенные источники для поиска
        self.search_sources = [
            "https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u",
            "https://raw.githubusercontent.com/iptv-org/iptv/master/channels/ru.m3u",
            "https://iptv-org.github.io/iptv/countries/ru.m3u",
            "https://raw.githubusercontent.com/Free-IPTV/Countries/master/RU.m3u",
            "https://raw.githubusercontent.com/gglabs/iptv/master/index.m3u",
            "https://raw.githubusercontent.com/ivanskod/iptv/main/iptv.m3u",
        ]

        # Загружаем сайты из файла
        self.custom_sites = self.load_custom_sites()

        # Загружаем категории из файла
        self.channel_categories = self.load_channel_categories()

        # Загружаем список каналов для поиска
        self.channels_list = self.load_channels_list()

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

    def load_channels_list(self):
        """Загружает список каналов из файла Channels.txt"""
        channels = []
        if os.path.exists(self.channels_file):
            try:
                with open(self.channels_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        channel = line.strip()
                        if channel and not channel.startswith('#'):
                            channels.append(channel)
                print(f"📁 Загружено {len(channels)} каналов из {self.channels_file}")
            except Exception as e:
                print(f"❌ Ошибка загрузки каналов: {e}")
        else:
            print(f"📝 Файл {self.channels_file} не найден, создаем базовый...")
            self.create_default_channels_file()
            channels = self.load_channels_list()
        return channels

    def create_default_channels_file(self):
        """Создает файл с каналами по умолчанию"""
        default_channels = [
            "Первый",
            "Россия",
            "НТВ",
            "СТС",
            "ТНТ",
            "РЕН ТВ",
            "Пятый канал",
            "Мир",
            "Культура",
            "ОТР"
        ]
        try:
            os.makedirs(os.path.dirname(self.channels_file), exist_ok=True)
            with open(self.channels_file, 'w', encoding='utf-8') as f:
                f.write("# Список каналов для поиска\n")
                for channel in default_channels:
                    f.write(f"{channel}\n")
            print(f"✅ Создан файл {self.channels_file} с {len(default_channels)} каналами")
        except Exception as e:
            print(f"❌ Ошибка создания файла каналов: {e}")

    def create_default_sites_file(self):
        """Создает файл с сайтами по умолчанию"""
        default_sites = [
            "https://github.com/",
            "https://yandex.ru/",
            "https://google.com/",
            "https://vk.com/",
            "https://ok.ru/",
            "https://dzen.ru/",
            "https://rambler.ru/",
            "https://mail.ru/",
        ]
        try:
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
                                channel, category = line.split(':', 1)
                                categories[channel.strip()] = category.strip()
                            else:
                                categories[line] = line
                print(f"📁 Загружено категорий: {len(categories)} из {self.cartolog_file}")
            except Exception as e:
                print(f"❌ Ошибка загрузки категорий: {e}")
        else:
            print(f"📝 Файл {self.cartolog_file} не найден, создаем базовый...")
            self.create_default_cartolog_file()
            categories = self.load_channel_categories()

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
        ]

        try:
            os.makedirs(os.path.dirname(self.cartolog_file), exist_ok=True)
            with open(self.cartolog_file, 'w', encoding='utf-8') as f:
                for line in default_content:
                    f.write(f"{line}\n")
            print(f"✅ Создан файл {self.cartolog_file} с категориями")
        except Exception as e:
            print(f"❌ Ошибка создания файла категорий: {e}")

    def get_channel_category(self, channel_name):
        """Определяет категорию для канала"""
        if channel_name in self.channel_categories:
            return self.channel_categories[channel_name]

        for channel_pattern, category in self.channel_categories.items():
            if channel_pattern in channel_name or channel_name in channel_pattern:
                return category

        return "Общие"

    def make_request(self, url, method='GET', max_retries=3):
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

        sites_to_search = self.custom_sites[:self.max_sites_per_search]

        for site in sites_to_search:
            try:
                print(f"   🔍 Проверяем: {site}")

                if any(engine in site for engine in ['yandex.ru', 'google.com', 'youtube.com', 'rutube.ru']):
                    search_urls = self.search_on_engine(site, channel_name)
                    found_urls.update(search_urls)
                else:
                    m3u_urls = self.scan_site_for_m3u(site, channel_name)
                    found_urls.update(m3u_urls)

                time.sleep(0.5)

            except Exception as e:
                continue

        return list(found_urls)[:50]

    def search_on_engine(self, engine_url, channel_name):
        """Ищет на поисковых системах и видео платформах"""
        found_urls = set()

        try:
            if 'yandex.ru' in engine_url:
                search_url = f"https://yandex.ru/search/?text={quote(channel_name + ' m3u8 live stream')}"
                response = self.make_request(search_url)
                if response:
                    content = response.read().decode('utf-8', errors='ignore')
                    m3u_urls = re.findall(r'https?://[^\s"<>]+\.m3u8?', content)
                    found_urls.update(m3u_urls)

            elif 'google.com' in engine_url:
                search_url = f"https://www.google.com/search?q={quote(channel_name + ' m3u8 iptv live')}"
                response = self.make_request(search_url)
                if response:
                    content = response.read().decode('utf-8', errors='ignore')
                    m3u_urls = re.findall(r'https?://[^\s"<>]+\.m3u8?', content)
                    found_urls.update(m3u_urls)

            elif 'youtube.com' in engine_url:
                search_url = f"https://www.youtube.com/results?search_query={quote(channel_name + ' live stream')}"
                response = self.make_request(search_url)
                if response:
                    content = response.read().decode('utf-8', errors='ignore')
                    video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', content)
                    for video_id in video_ids[:3]:
                        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                        found_urls.add(youtube_url)

        except Exception as e:
            pass

        return list(found_urls)

    def scan_site_for_m3u(self, site_url, channel_name):
        """Сканирует сайт на наличие M3U и M3U8 плейлистов"""
        found_urls = set()

        try:
            response = self.make_request(site_url)
            if response:
                content = response.read().decode('utf-8', errors='ignore')

                # Ищем прямые M3U8 ссылки
                m3u8_urls = re.findall(r'https?://[^\s"\'<>]+\.m3u8', content)
                found_urls.update(m3u8_urls)

                # Ищем прямые M3U ссылки
                m3u_urls = re.findall(r'https?://[^\s"\'<>]+\.m3u', content)
                found_urls.update(m3u_urls)

                # Ищем ссылки на плейлисты в href
                playlist_urls = re.findall(r'href="([^"]+\.m3u8?)"', content, re.IGNORECASE)
                for url in playlist_urls:
                    if url.startswith('/'):
                        full_url = urljoin(site_url, url)
                        found_urls.add(full_url)
                    elif url.startswith('http'):
                        found_urls.add(url)

        except Exception as e:
            pass

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
            "https://raw.githubusercontent.com/Free-IPTV/Countries/master/RU.m3u",
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
        """Улучшенный поиск канала в интернете"""
        print(f"🌐 Запуск расширенного поиска для канала: '{channel_name}'")
        all_streams = []

        # 1. Проверка базовых источников
        print("   📡 Этап 1/3: Проверка базовых источников...")
        for i, source_url in enumerate(self.search_sources, 1):
            try:
                print(f"      🔍 Проверяем источник {i}/{len(self.search_sources)}: {source_url}")
                playlist_content = self.download_playlist(source_url)
                if playlist_content:
                    found_streams = self.extract_channels_from_playlist(playlist_content, channel_name)
                    all_streams.extend(found_streams)
                    print(f"      ✅ Найдено {len(found_streams)} потоков")
                else:
                    print(f"      ❌ Источник недоступен")
            except Exception as e:
                print(f"      💥 Ошибка: {e}")
                continue

        # 2. Поиск в специализированных IPTV источниках
        print("   🔍 Этап 2/3: Поиск в IPTV источниках...")
        iptv_streams = self.search_iptv_sources(channel_name)
        all_streams.extend(iptv_streams)
        print(f"      ✅ Найдено {len(iptv_streams)} IPTV потоков")

        # 3. Поиск на пользовательских сайтах
        print("   🌐 Этап 3/3: Поиск на пользовательских сайтах...")
        custom_urls = self.search_custom_sites(channel_name)
        valid_streams = self.quick_check_urls(custom_urls, channel_name)
        all_streams.extend(valid_streams)
        print(f"      ✅ Найдено {len(valid_streams)} потоков с сайтов")

        print(f"   📊 ИТОГО: найдено {len(all_streams)} потенциальных потоков")

        return all_streams

    def quick_check_urls(self, urls, channel_name):
        """Улучшенная быстрая проверка URL"""
        valid_streams = []

        def check_url(url):
            try:
                # Для YouTube ссылок
                if 'youtube.com/watch' in url or 'youtu.be' in url:
                    return {
                        'name': f"{channel_name}",
                        'url': url,
                        'source': 'youtube',
                        'group': 'YouTube'
                    }

                # Для M3U8 ссылок
                elif '.m3u8' in url.lower():
                    response = self.make_request(url, 'HEAD')
                    if response and response.getcode() == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if any(ct in content_type.lower() for ct in ['video', 'application', 'octet-stream', 'mpegurl']):
                            return {
                                'name': f"{channel_name}",
                                'url': url,
                                'source': 'm3u8',
                                'group': 'M3U8'
                            }

                # Для M3U ссылок
                elif '.m3u' in url.lower():
                    response = self.make_request(url, 'GET')
                    if response and response.getcode() == 200:
                        content = response.read(1024).decode('utf-8', errors='ignore')
                        if '#EXTM3U' in content:
                            return {
                                'name': f"{channel_name}",
                                'url': url,
                                'source': 'm3u',
                                'group': 'M3U'
                            }

                return None
            except:
                return None

        # Проверяем URL параллельно
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(check_url, url) for url in urls[:50]]

            for future in as_completed(futures):
                result = future.result()
                if result:
                    valid_streams.append(result)

        return valid_streams

    def extract_channels_from_playlist(self, playlist_content, channel_name):
        """Извлекает каналы из плейлиста с ТОЧНЫМ поиском"""
        streams = []
        lines = playlist_content.split('\n')

        # ТОЧНЫЕ поисковые паттерны
        search_patterns = self.generate_exact_search_patterns(channel_name)

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if line.startswith('#EXTINF:'):
                channel_info = self.parse_extinf_line(line)
                channel_title = channel_info.get('name', '').lower()

                # ТОЧНЫЙ поиск с учетом границ слов
                if self.exact_match(channel_title, search_patterns):
                    if i + 1 < len(lines):
                        url = lines[i + 1].strip()
                        if url and not url.startswith('#') and url.startswith('http'):
                            # Проверяем качество канала перед добавлением
                            if self.is_high_quality_channel(channel_info):
                                streams.append({
                                    'name': channel_info.get('name', channel_name),
                                    'url': url,
                                    'source': 'playlist',
                                    'group': channel_info.get('group-title', 'Общие'),
                                    'tvg_id': channel_info.get('tvg-id', ''),
                                    'tvg_logo': channel_info.get('tvg-logo', ''),
                                    'quality_score': self.calculate_quality_score(channel_info)
                                })
                                i += 1
            i += 1

        # Сортируем по качеству (лучшие первыми)
        streams.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        return streams

    def exact_match(self, channel_title, search_patterns):
        """Точное совпадение с учетом границ слов"""
        channel_title = channel_title.lower().strip()

        # Убираем лишние символы
        channel_title = re.sub(r'[^\w\s]', ' ', channel_title)
        channel_title = re.sub(r'\s+', ' ', channel_title).strip()

        for pattern in search_patterns:
            pattern = pattern.lower().strip()

            # Точное совпадение
            if channel_title == pattern:
                return True

            # Совпадение с границами слов
            if re.search(r'\b' + re.escape(pattern) + r'\b', channel_title):
                return True

            # Совпадение без учета регистра и с учетом опечаток
            if self.fuzzy_match(channel_title, pattern):
                return True

        return False

    def fuzzy_match(self, text, pattern):
        """Нечеткое сравнение для учета опечаток"""
        text = text.lower()
        pattern = pattern.lower()

        # Если паттерн короткий, требуем точное совпадение
        if len(pattern) < 4:
            return pattern in text

        # Проверяем различные варианты
        variations = [
            pattern,
            pattern.replace(' ', ''),
            pattern.replace(' ', '.'),
            pattern.replace(' ', '-'),
            pattern.replace('тв', 'tv'),
            pattern.replace('tv', 'тв'),
        ]

        for var in variations:
            if var in text and len(var) > 2:
                return True

        return False

    def generate_exact_search_patterns(self, channel_name):
        """Генерирует ТОЧНЫЕ варианты для поиска"""
        name_lower = channel_name.lower().strip()

        # Основные точные паттерны
        patterns = [
            name_lower,
            name_lower + ' hd',
            name_lower + ' fhd',
            name_lower + ' fullhd',
            name_lower + ' 1080p',
            name_lower + ' 720p',
        ]

        # Добавляем варианты без пробелов и с разными разделителями
        patterns.extend([
            name_lower.replace(' ', ''),
            name_lower.replace(' ', '.'),
            name_lower.replace(' ', '-'),
            name_lower.replace(' ', '_'),
        ])

        # Добавляем варианты с TV/TВ
        patterns.extend([
            name_lower.replace('тв', 'tv'),
            name_lower.replace('tv', 'тв'),
            name_lower + ' tv',
            name_lower + ' тв',
        ])

        # Убираем "канал" и "channel" для более точного поиска
        if 'канал' in name_lower:
            without_channel = name_lower.replace('канал', '').strip()
            if without_channel:
                patterns.append(without_channel)

        if 'channel' in name_lower:
            without_channel = name_lower.replace('channel', '').strip()
            if without_channel:
                patterns.append(without_channel)

        return list(set([p for p in patterns if p and len(p) > 1]))

    def is_high_quality_channel(self, channel_info):
        """Проверяет, является ли канал качественным"""
        name = channel_info.get('name', '').lower()

        # Признаки некачественных каналов
        low_quality_indicators = [
            'test', 'тест', 'demo', 'демо', 'sample', 'пример',
            'low', 'низк', 'bad', 'плох', 'fake', 'фейк',
            'offline', 'оффлайн', 'not working', 'не работает'
        ]

        for indicator in low_quality_indicators:
            if indicator in name:
                return False

        return True

    def calculate_quality_score(self, channel_info):
        """Рассчитывает оценку качества канала"""
        score = 0
        name = channel_info.get('name', '').lower()

        # Бонусы за качество в названии
        quality_indicators = {
            'hd': 10,
            'fhd': 15,
            'fullhd': 15,
            '1080p': 15,
            '720p': 10,
            '4k': 20,
            'uhd': 20,
            'high': 5,
            'качеств': 5
        }

        for indicator, points in quality_indicators.items():
            if indicator in name:
                score += points

        # Бонус за наличие логотипа
        if channel_info.get('tvg-logo'):
            score += 5

        # Бонус за ID канала
        if channel_info.get('tvg-id'):
            score += 3

        return score

    def parse_extinf_line(self, extinf_line):
        """Парсит строку EXTINF и извлекает все атрибуты"""
        info = {}

        attributes = re.findall(r'(\w+)=["\']([^"\']*)["\']', extinf_line)
        for key, value in attributes:
            info[key] = value

        if ',' in extinf_line:
            name = extinf_line.split(',')[-1].strip()
            info['name'] = re.sub(r'["\'<>]', '', name)

        return info

    def check_stream_with_ffmpeg(self, url):
        """Проверяет поток с помощью ffmpeg"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
            if result.returncode != 0:
                return None

            cmd = [
                'ffmpeg',
                '-i', url,
                '-t', '5',
                '-f', 'null',
                '-',
                '-hide_banner',
                '-loglevel', 'error'
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=10)
            return result.returncode == 0

        except:
            return None

    def check_single_stream(self, stream_info):
        """Проверяет работоспособность ссылки с улучшенной проверкой"""
        try:
            url = stream_info['url']

            if not url.startswith('http'):
                return None

            print(f"    🔧 Проверка: {stream_info.get('name', 'Unknown')} - {url[:50]}...")

            # Для YouTube ссылок - считаем рабочими
            if 'youtube.com/watch' in url or 'youtu.be' in url:
                return {**stream_info, 'working': True, 'status': 'YouTube', 'quality': 'high'}

            # Пробуем проверку через ffmpeg
            ffmpeg_result = self.check_stream_with_ffmpeg(url)
            if ffmpeg_result:
                return {**stream_info, 'working': True, 'status': 'FFmpeg проверен', 'quality': 'high'}

            # Для M3U8 ссылок - улучшенная проверка
            if url.endswith('.m3u8') or 'm3u8' in url:
                response = self.make_request(url, 'HEAD')
                if response and response.getcode() == 200:
                    content_length = response.headers.get('Content-Length')
                    # Если контент слишком маленький - вероятно, это не рабочий поток
                    if content_length and int(content_length) > 1000:
                        return {**stream_info, 'working': True, 'status': 'M3U8 доступен', 'quality': 'medium'}
                    else:
                        return {**stream_info, 'working': True, 'status': 'M3U8 (малый размер)', 'quality': 'low'}

            # Для M3U ссылок
            elif url.endswith('.m3u') or 'm3u' in url:
                response = self.make_request(url, 'GET')
                if response and response.getcode() == 200:
                    content = response.read(1024).decode('utf-8', errors='ignore')
                    if '#EXTM3U' in content:
                        return {**stream_info, 'working': True, 'status': 'M3U валидный', 'quality': 'medium'}

            # Общая проверка с таймаутом
            response = self.make_request(url, 'HEAD')
            if response and response.getcode() == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                if any(ct in content_type for ct in ['video/', 'audio/', 'application/']):
                    return {**stream_info, 'working': True, 'status': 'Поток доступен', 'quality': 'medium'}

            return {**stream_info, 'working': False, 'status': 'Не доступен', 'quality': 'none'}

        except Exception as e:
            return {**stream_info, 'working': False, 'status': f'Ошибка: {str(e)}', 'quality': 'none'}

    def check_streams(self, streams):
        """Проверяет все найденные ссылки с приоритетом качества"""
        working_streams = []
        total = len(streams)

        if total == 0:
            return []

        print(f"🔧 Проверка {total} найденных ссылок...")

        # Сортируем потоки по оценке качества перед проверкой
        sorted_streams = sorted(streams, key=lambda x: x.get('quality_score', 0), reverse=True)

        # Используем многопоточность для проверки
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_stream = {executor.submit(self.check_single_stream, stream): stream for stream in sorted_streams}

            for i, future in enumerate(as_completed(future_to_stream), 1):
                result = future.result()
                if result:
                    if result['working']:
                        working_streams.append(result)
                        quality_icon = '🔴' if result.get('quality') == 'low' else '🟡' if result.get('quality') == 'medium' else '🟢'
                        print(f"  [{i}/{total}] ✅ {quality_icon} РАБОТАЕТ - {result['status']}")
                    else:
                        print(f"  [{i}/{total}] ❌ Не работает - {result['status']}")

        # Сортируем рабочие потоки по качеству
        working_streams.sort(key=lambda x: {'high': 3, 'medium': 2, 'low': 1}.get(x.get('quality', 'low'), 1), reverse=True)
        return working_streams

    def search_and_update_channel(self, channel_name):
        """Поиск и обновление канала в плейлисте с умным объединением"""
        print(f"\n🚀 Запуск ТОЧНОГО поиска: '{channel_name}'")
        print("⏳ Это может занять 1-2 минуты...")

        # Загружаем существующие каналы ДО поиска
        existing_channels = self.load_existing_channels()

        # Ищем точное совпадение названия (с учетом регистра)
        exact_match = None
        similar_matches = []

        for existing_name in existing_channels.keys():
            if existing_name.lower() == channel_name.lower():
                exact_match = existing_name
            elif channel_name.lower() in existing_name.lower() or existing_name.lower() in channel_name.lower():
                similar_matches.append(existing_name)

        # Если есть точное совпадение, используем его
        if exact_match:
            print(f"🔍 Найден существующий канал: '{exact_match}'")
            final_channel_name = exact_match
            category = self.get_channel_category(final_channel_name)
            # Сохраняем старые рабочие ссылки на случай, если новые не найдутся
            old_streams = existing_channels[final_channel_name].copy()
        else:
            final_channel_name = channel_name
            category = self.get_channel_category(final_channel_name)
            old_streams = []

        # Показываем похожие каналы
        if similar_matches and not exact_match:
            print(f"💡 Похожие каналы в плейлисте: {', '.join(similar_matches)}")
            choice = input("Использовать одно из этих названий? (y/n): ").strip().lower()
            if choice == 'y':
                for i, name in enumerate(similar_matches, 1):
                    print(f"{i}. {name}")
                try:
                    idx = int(input("Выберите номер: ")) - 1
                    if 0 <= idx < len(similar_matches):
                        final_channel_name = similar_matches[idx]
                        category = self.get_channel_category(final_channel_name)
                        old_streams = existing_channels[final_channel_name].copy()
                except:
                    pass

        start_time = time.time()
        all_streams = self.search_in_online_sources(final_channel_name)

        if not all_streams:
            print("❌ Не найдено ни одной новой ссылки для проверки")
            if old_streams:
                print("💡 Сохранены существующие рабочие ссылки")
                return True
            return False

        # Проверяем работоспособность новых ссылок
        working_streams = self.check_streams(all_streams)
        search_time = time.time() - start_time

        if working_streams:
            # Добавляем категорию к новым стримам
            for stream in working_streams:
                stream['group'] = category

            # ОБЪЕДИНЯЕМ старые и новые ссылки (убираем дубликаты URL)
            combined_streams = self.merge_streams(old_streams, working_streams)

            # Фильтруем только качественные потоки (максимум 5 лучших)
            high_quality_streams = [s for s in combined_streams if s.get('quality') in ['high', 'medium']]
            if len(high_quality_streams) > 5:
                combined_streams = high_quality_streams[:5]

            print("\n🎉" + "=" * 50)
            print(f"✅ НАЙДЕНО РАБОЧИХ ССЫЛОК: {len(working_streams)}")
            print(f"🎯 КАЧЕСТВЕННЫХ ПОТОКОВ: {len([s for s in combined_streams if s.get('quality') in ['high', 'medium']])}")
            if old_streams:
                print(f"💾 СТАРЫХ ССЫЛОК: {len(old_streams)}")
                print(f"🔗 ВСЕГО ПОСЛЕ ОБЪЕДИНЕНИЯ: {len(combined_streams)}")
            print(f"📂 Категория: {category}")
            print(f"⏱️  Время поиска: {search_time:.1f} секунд")
            print("=" * 50)

            # Обновляем канал в плейлисте
            success = self.update_channel_in_playlist(final_channel_name, combined_streams)

            if success:
                print(f"\n🔄 КАНАЛ ОБНОВЛЕН: {final_channel_name}")
                print(f"📂 Категория: {category}")
                print(f"📺 Всего ссылок: {len(combined_streams)}")
                print(f"🎯 Качественных: {len([s for s in combined_streams if s.get('quality') in ['high', 'medium']])}")
            return True

        else:
            print(f"\n❌ Для канала '{final_channel_name}' не найдено новых рабочих ссылок")
            if old_streams:
                print("💡 Сохранены существующие рабочие ссылки")
                return True
            else:
                # Удаляем канал только если нет вообще рабочих ссылок
                self.update_channel_in_playlist(final_channel_name, [])
                return False

    def merge_streams(self, old_streams, new_streams):
        """Объединяет старые и новые ссылки, убирая дубликаты"""
        merged = []
        seen_urls = set()

        # Сначала добавляем новые качественные ссылки (приоритет)
        for stream in new_streams:
            if stream['url'] not in seen_urls and stream.get('working', True):
                merged.append(stream)
                seen_urls.add(stream['url'])

        # Затем добавляем старые качественные ссылки, которых нет в новых
        for stream in old_streams:
            if (stream['url'] not in seen_urls and
                stream.get('working', True) and
                stream.get('quality') in ['high', 'medium']):
                merged.append(stream)
                seen_urls.add(stream['url'])

        return merged

    def update_channel_in_playlist(self, channel_name, new_streams):
        """Обновляет канал в плейлисте с проверкой на пустые списки"""
        existing_channels = self.load_existing_channels()

        if new_streams:
            existing_channels[channel_name] = new_streams
            print(f"🔄 Обновлен канал: {channel_name} ({len(new_streams)} ссылок)")
        else:
            # Удаляем канал только если явно передали пустой список
            if channel_name in existing_channels:
                del existing_channels[channel_name]
                print(f"🗑️ Удален канал: {channel_name} (нет рабочих ссылок)")

        return self.save_full_playlist(existing_channels)

    def load_existing_channels(self):
        """Загружает существующие каналы из плейлиста"""
        channels = {}
        if os.path.exists(self.playlist_file):
            try:
                with open(self.playlist_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                parts = content.split('#############################')
                if len(parts) > 1:
                    channels_content = parts[1]
                    lines = channels_content.split('\n')

                    i = 0
                    current_stream = None

                    while i < len(lines):
                        line = lines[i].strip()

                        if line.startswith('#EXTINF:'):
                            channel_info = self.parse_extinf_line(line)
                            current_stream = channel_info

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
                                        'quality': 'medium'  # По умолчанию
                                    })
                                    i += 1
                        i += 1

            except Exception as e:
                print(f"❌ Ошибка загрузки плейлиста: {e}")

        return channels

    def save_full_playlist(self, channels_dict):
        """Сохраняет полный плейлист БЕЗ информационных каналов"""
        try:
            os.makedirs(os.path.dirname(self.playlist_file), exist_ok=True)

            with open(self.playlist_file, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                f.write(f"# Обновлен: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Всего каналов: {len(channels_dict)}\n")
                f.write(f"# Всего ссылок: {sum(len(streams) for streams in channels_dict.values())}\n\n")

                f.write('#############################\n\n')

                for channel_name, streams in channels_dict.items():
                    for stream in streams:
                        extinf_parts = ['#EXTINF:-1']

                        if stream.get('tvg_id'):
                            extinf_parts.append(f'tvg-id="{stream["tvg_id"]}"')
                        if stream.get('tvg_logo'):
                            extinf_parts.append(f'tvg-logo="{stream["tvg_logo"]}"')
                        if stream.get('group'):
                            extinf_parts.append(f'group-title="{stream["group"]}"')

                        # Добавляем информацию о качестве
                        quality = stream.get('quality', '')
                        if quality:
                            extinf_parts.append(f'quality="{quality}"')

                        extinf_parts.append(f', {stream["name"]}')
                        f.write(' '.join(extinf_parts) + '\n')
                        f.write(f'{stream["url"]}\n')

            print(f"💾 Плейлист сохранен: {self.playlist_file}")
            print(f"📊 Всего каналов: {len(channels_dict)}")
            return True

        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    def refresh_all_channels(self):
        """Обновляет все каналы в плейлисте"""
        print("🔄 ЗАПУСК ПОЛНОГО ОБНОВЛЕНИЯ ВСЕХ КАНАЛОВ...")

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
                    category = "Общие"
                    if existing_channels[channel_name]:
                        category = existing_channels[channel_name][0].get('group', 'Общие')

                    for stream in working_streams:
                        stream['group'] = category

                    existing_channels[channel_name] = working_streams
                    updated_count += 1
                    print(f"✅ ОБНОВЛЕН: {channel_name} ({len(working_streams)} ссылок)")
                else:
                    del existing_channels[channel_name]
                    failed_count += 1
                    print(f"❌ УДАЛЕН: {channel_name} (нет рабочих ссылок)")

                time.sleep(1)

            except Exception as e:
                print(f"💥 ОШИБКА при обновлении {channel_name}: {e}")
                failed_count += 1
                continue

        if self.save_full_playlist(existing_channels):
            print(f"\n🎉 ОБНОВЛЕНИЕ ЗАВЕРШЕНО!")
            print(f"✅ Обновлено каналов: {updated_count}")
            print(f"❌ Удалено каналов: {failed_count}")
        else:
            print("❌ Ошибка сохранения обновленного плейлиста")

    def search_channel_online(self, channel_name):
        """Основной поиск канала в интернете"""
        print(f"🎯 ТОЧНЫЙ поиск канала: '{channel_name}'")

        all_streams = self.search_in_online_sources(channel_name)

        unique_streams = []
        seen_urls = set()
        for stream in all_streams:
            if stream['url'] not in seen_urls:
                unique_streams.append(stream)
                seen_urls.add(stream['url'])

        print(f"\n📊 Всего найдено ссылок: {len(unique_streams)}")

        if not unique_streams:
            return []

        working_streams = self.check_streams(unique_streams)
        return working_streams

    def search_from_channels_list(self):
        """Поиск каналов из списка в файле Channels.txt"""
        if not self.channels_list:
            print("❌ Список каналов пуст. Добавьте каналы в файл Channels.txt")
            return

        print(f"🎯 ЗАПУСК ПОИСКА ПО СПИСКУ ИЗ {len(self.channels_list)} КАНАЛОВ...")
        print("⏳ Это может занять продолжительное время...")

        success_count = 0
        failed_count = 0

        for i, channel_name in enumerate(self.channels_list, 1):
            print(f"\n{'='*70}")
            print(f"📺 [{i}/{len(self.channels_list)}] ПОИСК: {channel_name}")
            print(f"{'='*70}")

            try:
                if self.search_and_update_channel(channel_name):
                    success_count += 1
                    print(f"✅ УСПЕХ: {channel_name}")
                else:
                    failed_count += 1
                    print(f"❌ НЕ УДАЛОСЬ: {channel_name}")

                # Пауза между запросами
                if i < len(self.channels_list):
                    print(f"⏳ Ожидание 3 секунды перед следующим каналом...")
                    time.sleep(3)

            except Exception as e:
                print(f"💥 ОШИБКА при поиске {channel_name}: {e}")
                failed_count += 1
                continue

        print(f"\n🎉 ПОИСК ПО СПИСКУ ЗАВЕРШЕН!")
        print(f"✅ Успешно найдено: {success_count} каналов")
        print(f"❌ Не найдено: {failed_count} каналов")
        print(f"📊 Общее качество плейлиста улучшено!")

def interactive_mode():
    """Интерактивный режим работы"""
    scanner = OnlineM3UScanner()

    print("🎬" + "=" * 70)
    print("🌐 SMART M3U SCANNER - ТОЧНАЯ ВЕРСИЯ")
    print("🎯 УЛУЧШЕННЫЙ ПОИСК КАЧЕСТВЕННЫХ КАНАЛОВ")
    print("🎬" + "=" * 70)
    print("📡 Поиск рабочих M3U и M3U8 потоков")
    print(f"📁 Источники: {len(scanner.custom_sites)} сайтов")
    print(f"📂 Категории: {len(scanner.channel_categories)}")
    print(f"📺 Каналы для поиска: {len(scanner.channels_list)}")
    print(f"💾 Результаты: {scanner.playlist_file}")
    print("💡 ТОЧНЫЙ поиск с фильтрацией качества")
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

    existing_channels = scanner.load_existing_channels()
    if existing_channels:
        total_streams = sum(len(streams) for streams in existing_channels.values())
        high_quality = sum(1 for streams in existing_channels.values() for s in streams if s.get('quality') in ['high', 'medium'])
        print(f"📊 В плейлисте: {len(existing_channels)} каналов, {total_streams} ссылок")
        print(f"🎯 Качественных потоков: {high_quality}")
    else:
        print("📝 Плейлист будет создан при первом поиске")

    while True:
        print("\n" + "🎯" + "=" * 60)
        print("1. 🔍 Поиск и обновление одного канала")
        print("2. 📋 Поиск по списку из файла Channels.txt")
        print("3. 🔄 Полное обновление всех каналов")
        print("4. 📊 Статистика плейлиста")
        print("5. 🚪 Выход")

        choice = input("\nВыберите действие (1-5): ").strip()

        if choice == '1':
            channel_name = input("📺 Введите название телеканала: ").strip()
            if channel_name:
                scanner.search_and_update_channel(channel_name)
            else:
                print("⚠️  Пожалуйста, введите название канала")

        elif choice == '2':
            if scanner.channels_list:
                confirm = input("⚠️  Запустить поиск по списку из файла? Это может занять много времени (y/n): ").strip().lower()
                if confirm == 'y':
                    scanner.search_from_channels_list()
            else:
                print("❌ Файл Channels.txt пуст или не найден")

        elif choice == '3':
            confirm = input("⚠️  Вы уверены? Это может занять много времени (y/n): ").strip().lower()
            if confirm == 'y':
                scanner.refresh_all_channels()

        elif choice == '4':
            existing_channels = scanner.load_existing_channels()
            if existing_channels:
                total_streams = sum(len(streams) for streams in existing_channels.values())
                high_quality = sum(1 for streams in existing_channels.values() for s in streams if s.get('quality') in ['high', 'medium'])
                print(f"\n📊 СТАТИСТИКА ПЛЕЙЛИСТА:")
                print(f"📁 Каналов: {len(existing_channels)}")
                print(f"🔗 Всего ссылок: {total_streams}")
                print(f"🎯 Качественных потоков: {high_quality}")
                print(f"📈 Эффективность: {(high_quality/total_streams*100 if total_streams > 0 else 0):.1f}%")
            else:
                print("📝 Плейлист пуст")

        elif choice == '5' or choice.lower() == 'exit':
            print("👋 Выход из программы...")
            break

        else:
            print("⚠️  Неверный выбор, попробуйте снова")

def main():
    if len(sys.argv) == 1:
        # Консольный режим
        interactive_mode()
    elif len(sys.argv) > 1 and sys.argv[1] == "--gui":
        # Графический режим
        try:
            from Interface import main as gui_main
            gui_main()
        except ImportError as e:
            print(f"❌ Не удалось запустить графический интерфейс: {e}")
            print("📝 Убедитесь, что файл Interface.py находится в той же папке")
    else:
        print("🌐 Smart M3U Scanner - Точная версия")
        print("Использование:")
        print("  python M3UScanner.py          - Консольный режим")
        print("  python M3UScanner.py --gui    - Графический интерфейс")

if __name__ == "__main__":
    main()
