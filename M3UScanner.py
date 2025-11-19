import urllib.request
import urllib.error
import re
import time
import sys
import os
import ssl
from urllib.parse import urlparse, urljoin, quote
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
        self.channels_file = "files/Channels.txt"
        self.max_workers = 3
        self.max_sites_per_search = 20  # Увеличил для большего охвата
        self.max_retries = 3

        # Автоматически добавляем ffmpeg в PATH
        self.setup_ffmpeg_path()

        # Загружаем данные из файлов
        self.custom_sites = self.load_custom_sites()
        self.channel_categories = self.load_channel_categories()
        self.channels_list = self.load_channels_list()

        # Кэш для хранения найденных каналов
        self.channels_cache = {}

        # Статистика
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0
        }

    def setup_ffmpeg_path(self):
        """Автоматически добавляет ffmpeg в PATH если он есть в папке проекта"""
        ffmpeg_paths = [
            os.path.join(os.path.dirname(__file__), 'ffmpeg', 'bin'),
            os.path.join(os.path.dirname(__file__), 'ffmpeg-2025-11-17-git-e94439e49b-full_build', 'bin'),
        ]

        for path in ffmpeg_paths:
            if os.path.exists(path):
                os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
                print(f"✅ FFmpeg добавлен в PATH: {path}")
                return
        print("ℹ️  FFmpeg не найден в папке проекта")

    def find_ffmpeg(self):
        """Автоматически ищет ffmpeg в различных местах"""
        possible_paths = [
            "./ffmpeg/bin/ffmpeg.exe",
            "./ffmpeg-2025-11-17-git-e94439e49b-full_build/bin/ffmpeg.exe",
            "./ffmpeg.exe",
            "ffmpeg"
        ]

        for path in possible_paths:
            try:
                result = subprocess.run([path, '-version'], capture_output=True, timeout=5)
                if result.returncode == 0:
                    print(f"✅ FFmpeg найден: {path}")
                    return path
            except:
                continue
        print("❌ FFmpeg не найден")
        return None

    def load_custom_sites(self):
        """Загружает список сайтов из files/site.txt"""
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
            print(f"❌ Файл {self.sites_file} не найден!")
            self.create_default_sites_file()
        return sites

    def load_channels_list(self):
        """Загружает список каналов из files/Channels.txt"""
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
            print(f"❌ Файл {self.channels_file} не найден!")
        return channels

    def create_default_sites_file(self):
        """Создает файл с сайтами по умолчанию"""
        default_sites = [
            "# IPTV источники",
            "https://github.com/iptv-org/iptv",
            "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
            "https://raw.githubusercontent.com/iptv-org/iptv/master/categories/",
            "",
            "# Поисковые системы",
            "https://yandex.ru/",
            "https://google.com/",
            "",
            "# Видео платформы",
            "https://youtube.com/",
            "https://rutube.ru/",
            "",
            "# Социальные сети",
            "https://vk.com/",
            "https://ok.ru/",
        ]
        try:
            os.makedirs(os.path.dirname(self.sites_file), exist_ok=True)
            with open(self.sites_file, 'w', encoding='utf-8') as f:
                f.write("# Список сайтов для поиска M3U плейлистов\n")
                for site in default_sites:
                    f.write(f"{site}\n")
            print(f"✅ Создан файл {self.sites_file}")
        except Exception as e:
            print(f"❌ Ошибка создания файла: {e}")

    def load_channel_categories(self):
        """Загружает категории каналов из files/cartolog.txt"""
        categories = {}
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
            print(f"❌ Файл {self.cartolog_file} не найден!")
        return categories

    def get_channel_category(self, channel_name):
        """Определяет категорию для канала из cartolog.txt"""
        if channel_name in self.channel_categories:
            return self.channel_categories[channel_name]

        for channel_pattern, category in self.channel_categories.items():
            if channel_pattern in channel_name or channel_name in channel_pattern:
                return category

        return "Общие"

    def make_request(self, url, method='GET', max_retries=None):
        """HTTP запрос с повторными попытками"""
        if max_retries is None:
            max_retries = self.max_retries

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        }

        for attempt in range(max_retries):
            self.stats['total_requests'] += 1
            start_time = time.time()

            try:
                if method.upper() == 'HEAD':
                    req = urllib.request.Request(url, headers=headers, method='HEAD')
                else:
                    req = urllib.request.Request(url, headers=headers)

                current_timeout = min(self.timeout * (attempt + 1), 30)
                response = urllib.request.urlopen(req, timeout=current_timeout)
                response_time = time.time() - start_time

                self.stats['successful_requests'] += 1
                self.stats['avg_response_time'] = (
                    self.stats['avg_response_time'] * (self.stats['successful_requests'] - 1) + response_time
                ) / self.stats['successful_requests']

                return response

            except Exception as e:
                if attempt == max_retries - 1:
                    self.stats['failed_requests'] += 1
                    return None
                time.sleep(1)

        return None

    def search_iptv_sources(self, channel_name):
        """Поиск в IPTV источниках из site.txt"""
        print("   📡 Поиск в IPTV источниках...")
        streams = []

        # Фильтруем IPTV источники
        iptv_sources = []
        for site in self.custom_sites:
            if any(keyword in site.lower() for keyword in [
                'iptv', 'm3u', 'github.com/iptv', 'stream', 'live',
                'iptv-org', 'raw.githubusercontent.com', '.m3u'
            ]):
                iptv_sources.append(site)

        iptv_sources = iptv_sources[:15]  # Ограничиваем количество

        print(f"      📊 Обрабатываем {len(iptv_sources)} IPTV источников")

        for source in iptv_sources:
            try:
                source_name = self.get_source_name(source)
                print(f"      🔍 Проверяем: {source_name}")

                # Прямые M3U ссылки
                if any(ext in source.lower() for ext in ['.m3u', '.m3u8']):
                    content = self.download_playlist(source)
                    if content:
                        found = self.extract_channels_from_playlist(content, channel_name)
                        streams.extend(found)
                        if found:
                            print(f"      ✅ Найдено {len(found)} потоков")

                # GitHub репозитории
                elif 'github.com' in source.lower():
                    github_urls = self.scan_github_for_m3u(source, channel_name)
                    for m3u_url in github_urls:
                        content = self.download_playlist(m3u_url)
                        if content:
                            found = self.extract_channels_from_playlist(content, channel_name)
                            streams.extend(found)
                            if found:
                                print(f"      ✅ Найдено в {m3u_url.split('/')[-1]}")

                # Другие IPTV сайты
                elif any(keyword in source.lower() for keyword in ['iptv', 'stream']):
                    m3u_urls = self.scan_site_for_m3u(source, channel_name)
                    valid_streams = self.quick_check_urls(m3u_urls, channel_name)
                    streams.extend(valid_streams)
                    if valid_streams:
                        print(f"      ✅ Найдено {len(valid_streams)} потоков")

                time.sleep(0.5)

            except Exception as e:
                continue

        return streams

    def search_on_search_engines(self, channel_name):
        """Поиск через поисковые системы из site.txt"""
        search_urls = []

        search_engines = [
            site for site in self.custom_sites
            if any(engine in site for engine in [
                'yandex.ru', 'google.com', 'bing.com', 'duckduckgo.com'
            ])
        ]

        for engine in search_engines[:2]:
            try:
                if 'yandex.ru' in engine:
                    search_url = f"https://yandex.ru/search/?text={quote(channel_name + ' m3u8 live stream')}"
                    response = self.make_request(search_url)
                    if response:
                        content = response.read().decode('utf-8', errors='ignore')
                        m3u_urls = re.findall(r'https?://[^\s"<>]+\.m3u8?', content)
                        search_urls.extend(m3u_urls[:3])

                elif 'google.com' in engine:
                    search_url = f"https://www.google.com/search?q={quote(channel_name + ' m3u8 iptv live')}"
                    response = self.make_request(search_url)
                    if response:
                        content = response.read().decode('utf-8', errors='ignore')
                        m3u_urls = re.findall(r'https?://[^\s"<>]+\.m3u8?', content)
                        search_urls.extend(m3u_urls[:3])

            except Exception as e:
                continue

        return search_urls

    def search_in_online_sources(self, channel_name):
        """Основной поиск канала по всем источникам из site.txt"""
        print(f"🌐 Поиск канала: '{channel_name}'")
        all_streams = []

        # 1. Поиск в IPTV источниках
        print("   🔍 Этап 1: IPTV источники...")
        iptv_streams = self.search_iptv_sources(channel_name)
        all_streams.extend(iptv_streams)
        print(f"      ✅ Найдено {len(iptv_streams)} IPTV потоков")

        # 2. Поиск в поисковых системах
        print("   🔎 Этап 2: Поисковые системы...")
        search_urls = self.search_on_search_engines(channel_name)
        search_streams = self.quick_check_urls(search_urls, channel_name)
        all_streams.extend(search_streams)
        print(f"      ✅ Найдено {len(search_streams)} потоков с поисковиков")

        # 3. Поиск на остальных сайтах
        print("   🌐 Этап 3: Общие сайты...")
        other_sites = [
            site for site in self.custom_sites
            if not any(keyword in site.lower() for keyword in [
                'iptv', 'm3u', 'github.com/iptv', 'yandex.ru', 'google.com'
            ])
        ][:10]  # Ограничиваем количество

        for site in other_sites:
            try:
                m3u_urls = self.scan_site_for_m3u(site, channel_name)
                valid_streams = self.quick_check_urls(m3u_urls, channel_name)
                all_streams.extend(valid_streams)
                if valid_streams:
                    print(f"      ✅ Найдено на {self.get_source_name(site)}")
                time.sleep(1)
            except:
                continue

        print(f"   📊 ИТОГО: {len(all_streams)} потенциальных потоков")
        return all_streams

    def get_source_name(self, url):
        """Получает читаемое имя источника"""
        try:
            clean_url = re.sub(r'^https?://(www\.)?', '', url)
            parts = clean_url.split('/')
            if len(parts) > 1:
                if 'github.com' in url and len(parts) >= 3:
                    return f"github.com/{parts[1]}/{parts[2]}"
                domain = parts[0]
                if len(parts) > 1 and parts[1]:
                    return f"{domain}/{parts[1]}"
                return domain
            return clean_url
        except:
            return url[:30] + "..." if len(url) > 30 else url

    def scan_site_for_m3u(self, site_url, channel_name):
        """Сканирует сайт на наличие M3U плейлистов"""
        found_urls = set()
        try:
            response = self.make_request(site_url)
            if response:
                content = response.read().decode('utf-8', errors='ignore')

                # Ищем M3U8 ссылки
                m3u8_urls = re.findall(r'https?://[^\s"\'<>]+\.m3u8', content)
                found_urls.update(m3u8_urls[:10])

                # Ищем M3U ссылки
                m3u_urls = re.findall(r'https?://[^\s"\'<>]+\.m3u', content)
                found_urls.update(m3u_urls[:10])

                # Ищем ссылки в href
                playlist_urls = re.findall(r'href="([^"]+\.m3u8?)"', content, re.IGNORECASE)
                for url in playlist_urls[:10]:
                    if url.startswith('/'):
                        full_url = urljoin(site_url, url)
                        found_urls.add(full_url)
                    elif url.startswith('http'):
                        found_urls.add(url)

        except Exception as e:
            pass

        return list(found_urls)

    def download_playlist(self, url):
        """Скачивает плейлист"""
        try:
            response = self.make_request(url, 'GET', max_retries=2)
            if response and response.getcode() == 200:
                return response.read().decode('utf-8', errors='ignore')
            return None
        except:
            return None

    def scan_github_for_m3u(self, github_url, channel_name):
        """Сканирует GitHub на наличие M3U файлов"""
        m3u_urls = []
        try:
            # Прямые ссылки на M3U
            if github_url.endswith('.m3u') or github_url.endswith('.m3u8'):
                m3u_urls.append(github_url)

            # GitHub pages IPTV-org
            elif 'iptv-org.github.io' in github_url:
                categories = ['news', 'sports', 'entertainment', 'kids', 'music', 'movies']
                for category in categories:
                    m3u_urls.append(f"https://iptv-org.github.io/iptv/categories/{category}.m3u")

            # GitHub raw content
            elif 'raw.githubusercontent.com' in github_url:
                m3u_urls.append(github_url)

            # GitHub blob URLs
            elif 'github.com' in github_url and '/blob/' in github_url:
                raw_url = github_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
                if raw_url.endswith(('.m3u', '.m3u8')):
                    m3u_urls.append(raw_url)

        except:
            pass

        return m3u_urls[:10]

    def quick_check_urls(self, urls, channel_name):
        """Быстрая проверка URL"""
        valid_streams = []

        def check_url(url):
            try:
                # YouTube ссылки
                if 'youtube.com/watch' in url or 'youtu.be' in url:
                    return {
                        'name': channel_name,
                        'url': url,
                        'source': 'youtube',
                        'group': 'YouTube',
                        'stability_score': 8
                    }

                # M3U8 ссылки
                elif '.m3u8' in url.lower():
                    response = self.make_request(url, 'HEAD', max_retries=1)
                    if response and response.getcode() == 200:
                        return {
                            'name': channel_name,
                            'url': url,
                            'source': 'm3u8',
                            'group': 'M3U8',
                            'stability_score': 6
                        }

                # M3U ссылки
                elif '.m3u' in url.lower():
                    response = self.make_request(url, 'GET', max_retries=1)
                    if response and response.getcode() == 200:
                        content = response.read(1024).decode('utf-8', errors='ignore')
                        if '#EXTM3U' in content:
                            return {
                                'name': channel_name,
                                'url': url,
                                'source': 'm3u',
                                'group': 'M3U',
                                'stability_score': 5
                            }

                return None
            except:
                return None

        # Проверяем URL параллельно
        urls_to_check = urls[:15]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(check_url, url) for url in urls_to_check]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    valid_streams.append(result)

        return valid_streams

    def extract_channels_from_playlist(self, playlist_content, channel_name):
        """Извлекает каналы из плейлиста"""
        streams = []
        lines = playlist_content.split('\n')
        search_patterns = self.generate_exact_search_patterns(channel_name)

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXTINF:'):
                channel_info = self.parse_extinf_line(line)
                channel_title = channel_info.get('name', '').lower()

                if self.exact_match(channel_title, search_patterns):
                    if i + 1 < len(lines):
                        url = lines[i + 1].strip()
                        if url and not url.startswith('#') and url.startswith('http'):
                            if self.is_high_quality_channel(channel_info):
                                stability_score = self.calculate_stability_score(channel_info, url)
                                streams.append({
                                    'name': channel_name,
                                    'url': url,
                                    'source': 'playlist',
                                    'group': channel_info.get('group-title', 'Общие'),
                                    'tvg_id': channel_info.get('tvg-id', ''),
                                    'tvg_logo': channel_info.get('tvg-logo', ''),
                                    'quality_score': self.calculate_quality_score(channel_info),
                                    'stability_score': stability_score
                                })
                                i += 1
            i += 1

        streams.sort(key=lambda x: (x.get('stability_score', 0), x.get('quality_score', 0)), reverse=True)
        return streams[:10]

    def exact_match(self, channel_title, search_patterns):
        """Точное совпадение канала"""
        channel_title = channel_title.lower().strip()
        channel_title = re.sub(r'[^\w\s]', ' ', channel_title)
        channel_title = re.sub(r'\s+', ' ', channel_title).strip()

        for pattern in search_patterns:
            pattern = pattern.lower().strip()
            if channel_title == pattern:
                return True
            if re.search(r'\b' + re.escape(pattern) + r'\b', channel_title):
                return True
            if self.fuzzy_match(channel_title, pattern):
                return True
        return False

    def fuzzy_match(self, text, pattern):
        """Нечеткое сравнение"""
        text = text.lower()
        pattern = pattern.lower()
        if len(pattern) < 4:
            return pattern in text

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
        """Генерирует паттерны для поиска"""
        name_lower = channel_name.lower().strip()
        patterns = [
            name_lower,
            name_lower + ' hd',
            name_lower + ' fhd',
            name_lower + ' 1080p',
            name_lower + ' 720p',
            name_lower.replace(' ', ''),
            name_lower.replace(' ', '.'),
            name_lower.replace(' ', '-'),
            name_lower.replace('тв', 'tv'),
            name_lower.replace('tv', 'тв'),
            name_lower + ' tv',
            name_lower + ' тв',
        ]

        # Убираем "канал" и "channel"
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
        """Проверяет качество канала"""
        name = channel_info.get('name', '').lower()
        low_quality_indicators = [
            'test', 'тест', 'demo', 'демо', 'sample', 'пример',
            'low', 'низк', 'bad', 'плох', 'fake', 'фейк',
            'offline', 'оффлайн', 'not working', 'не работает'
        ]
        return not any(indicator in name for indicator in low_quality_indicators)

    def calculate_stability_score(self, channel_info, url):
        """Рассчитывает стабильность"""
        score = 5
        name = channel_info.get('name', '').lower()
        url_lower = url.lower()

        stable_indicators = {
            'github.com': 3, 'raw.githubusercontent.com': 3,
            'iptv-org.github.io': 3, 'youtube.com': 2, 'youtu.be': 2
        }
        unstable_indicators = {
            'test': -3, 'тест': -3, 'temp': -2, 'localhost': -5
        }

        for domain, points in stable_indicators.items():
            if domain in url_lower:
                score += points
        for indicator, penalty in unstable_indicators.items():
            if indicator in name:
                score += penalty

        return max(1, min(10, score))

    def calculate_quality_score(self, channel_info):
        """Рассчитывает качество"""
        score = 0
        name = channel_info.get('name', '').lower()

        quality_indicators = {
            'hd': 10, 'fhd': 15, 'fullhd': 15, '1080p': 15,
            '720p': 10, '4k': 20, 'uhd': 20
        }

        for indicator, points in quality_indicators.items():
            if indicator in name:
                score += points

        if channel_info.get('tvg-logo'):
            score += 5
        if channel_info.get('tvg-id'):
            score += 3

        return score

    def parse_extinf_line(self, extinf_line):
        """Парсит строку EXTINF"""
        info = {}
        attributes = re.findall(r'(\w+)=["\']([^"\']*)["\']', extinf_line)
        for key, value in attributes:
            info[key] = value

        if ',' in extinf_line:
            name = extinf_line.split(',')[-1].strip()
            info['name'] = re.sub(r'["\'<>]', '', name)

        return info

    def check_single_stream_improved(self, stream_info):
        """Проверка работоспособности ссылки"""
        try:
            url = stream_info['url']
            channel_name = stream_info.get('name', 'Unknown')

            if not url.startswith('http'):
                return None

            print(f"    🔧 Проверка: {channel_name} - {url[:60]}...")

            # YouTube ссылки
            if 'youtube.com/watch' in url or 'youtu.be' in url:
                response = self.make_request(url, 'HEAD', max_retries=1)
                if response and response.getcode() == 200:
                    return {**stream_info, 'working': True, 'status': 'YouTube доступен', 'quality': 'high', 'stable': True}
                else:
                    return {**stream_info, 'working': False, 'status': 'YouTube недоступен', 'quality': 'none', 'stable': False}

            # M3U8 ссылки
            elif '.m3u8' in url.lower():
                response = self.make_request(url, 'HEAD')
                if response and response.getcode() == 200:
                    # Проверка через FFmpeg если доступен
                    ffmpeg_path = self.find_ffmpeg()
                    if ffmpeg_path:
                        try:
                            cmd = [ffmpeg_path, '-i', url, '-t', '3', '-f', 'null', '-', '-hide_banner', '-loglevel', 'error']
                            result = subprocess.run(cmd, capture_output=True, timeout=10)
                            if result.returncode == 0:
                                return {**stream_info, 'working': True, 'status': 'FFmpeg проверен', 'quality': 'high', 'stable': True}
                        except:
                            pass

                    # Базовая проверка
                    content_type = response.headers.get('Content-Type', '').lower()
                    if any(ct in content_type for ct in ['video', 'application', 'mpegurl']):
                        return {**stream_info, 'working': True, 'status': 'M3U8 доступен', 'quality': 'medium', 'stable': True}

            # M3U ссылки
            elif '.m3u' in url.lower() and not url.endswith('.m3u8'):
                response = self.make_request(url, 'GET')
                if response and response.getcode() == 200:
                    content = response.read(2048).decode('utf-8', errors='ignore')
                    if '#EXTM3U' in content:
                        return {**stream_info, 'working': True, 'status': 'M3U валидный', 'quality': 'medium', 'stable': True}

            # Общая проверка
            response = self.make_request(url, 'HEAD')
            if response and response.getcode() == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                if any(ct in content_type for ct in ['video/', 'audio/', 'application/']):
                    return {**stream_info, 'working': True, 'status': 'Поток доступен', 'quality': 'medium', 'stable': False}

            return {**stream_info, 'working': False, 'status': 'Не доступен', 'quality': 'none', 'stable': False}

        except Exception as e:
            return {**stream_info, 'working': False, 'status': f'Ошибка: {str(e)}', 'quality': 'none', 'stable': False}

    def check_streams(self, streams):
        """Проверяет все найденные ссылки"""
        if not streams:
            return []

        print(f"🔧 Проверка {len(streams)} найденных ссылок...")
        working_streams = []

        # Сортируем по стабильности
        sorted_streams = sorted(streams, key=lambda x: x.get('stability_score', 0), reverse=True)

        for i, stream in enumerate(sorted_streams, 1):
            result = self.check_single_stream_improved(stream)
            if result:
                if result['working']:
                    working_streams.append(result)
                    stability_icon = '🟢' if result.get('stable') else '🟡'
                    quality_icon = '🟢' if result.get('quality') == 'high' else '🟡' if result.get('quality') == 'medium' else '🔴'
                    print(f"  [{i}/{len(streams)}] ✅ {quality_icon}{stability_icon} РАБОТАЕТ - {result['status']}")
                else:
                    print(f"  [{i}/{len(streams)}] ❌ Не работает - {result['status']}")

            if i < len(streams):
                time.sleep(1)

        # Фильтруем стабильные потоки
        stable_working = [s for s in working_streams if s.get('stable', False)]
        if stable_working:
            return stable_working[:5]
        else:
            return working_streams[:3]

    def search_and_update_channel(self, channel_name):
        """Поиск и обновление канала"""
        print(f"\n🚀 Поиск: '{channel_name}'")
        print("⏳ Это может занять 1-2 минуты...")

        # Загружаем существующие каналы
        existing_channels = self.load_existing_channels()

        # Ищем существующий канал
        final_channel_name = channel_name
        old_streams = []

        for existing_name in existing_channels.keys():
            if existing_name.lower() == channel_name.lower():
                final_channel_name = existing_name
                old_streams = existing_channels[final_channel_name].copy()
                break

        category = self.get_channel_category(final_channel_name)

        # Поиск новых ссылок
        start_time = time.time()
        all_streams = self.search_in_online_sources(final_channel_name)

        if not all_streams:
            print("❌ Не найдено новых ссылок для проверки")
            if old_streams:
                print("💡 Сохранены существующие рабочие ссылки")
                return True
            return False

        # Проверка работоспособности
        working_streams = self.check_streams(all_streams)
        search_time = time.time() - start_time

        if working_streams:
            # Добавляем категорию
            for stream in working_streams:
                stream['group'] = category

            # Объединяем старые и новые ссылки
            combined_streams = self.merge_streams(old_streams, working_streams)

            print("\n🎉" + "=" * 50)
            print(f"✅ НАЙДЕНО РАБОЧИХ ССЫЛОК: {len(working_streams)}")
            print(f"🎯 СТАБИЛЬНЫХ ПОТОКОВ: {len([s for s in working_streams if s.get('stable')])}")
            print(f"📂 Категория: {category}")
            print(f"⏱️  Время поиска: {search_time:.1f} секунд")
            print("=" * 50)

            # Обновляем канал
            success = self.update_channel_in_playlist(final_channel_name, combined_streams)

            if success:
                print(f"\n🔄 КАНАЛ ОБНОВЛЕН: {final_channel_name}")
                print(f"📺 Всего ссылок: {len(combined_streams)}")
            return True

        else:
            print(f"\n❌ Для канала '{final_channel_name}' не найдено рабочих ссылок")
            if old_streams:
                print("💡 Сохранены существующие рабочие ссылки")
                return True
            else:
                self.update_channel_in_playlist(final_channel_name, [])
                return False

    def merge_streams(self, old_streams, new_streams):
        """Объединяет ссылки"""
        merged = []
        seen_urls = set()

        # Сначала новые
        for stream in new_streams:
            if stream['url'] not in seen_urls and stream.get('working', True):
                merged.append(stream)
                seen_urls.add(stream['url'])

        # Затем старые стабильные
        for stream in old_streams:
            if (stream['url'] not in seen_urls and
                stream.get('working', True) and
                stream.get('stable', False)):
                merged.append(stream)
                seen_urls.add(stream['url'])

        return merged

    def update_channel_in_playlist(self, channel_name, new_streams):
        """Обновляет канал в плейлисте"""
        existing_channels = self.load_existing_channels()

        if new_streams:
            existing_channels[channel_name] = new_streams
            print(f"🔄 Обновлен канал: {channel_name} ({len(new_streams)} ссылок)")
        else:
            if channel_name in existing_channels:
                del existing_channels[channel_name]
                print(f"🗑️ Удален канал: {channel_name}")

        return self.save_full_playlist(existing_channels)

    def load_existing_channels(self):
        """Загружает существующие каналы"""
        channels = {}
        if os.path.exists(self.playlist_file):
            try:
                with open(self.playlist_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Динамическая часть (после разделителя)
                parts = content.split('#############################')
                if len(parts) > 2:
                    dynamic_content = parts[2]
                    lines = dynamic_content.split('\n')

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
                                        'quality': 'medium'
                                    })
                                    i += 1
                        i += 1

            except Exception as e:
                print(f"❌ Ошибка загрузки плейлиста: {e}")

        return channels

    def save_full_playlist(self, channels_dict):
        """Сохраняет плейлист"""
        try:
            os.makedirs(os.path.dirname(self.playlist_file), exist_ok=True)

            # Статическая часть
            static_content = ""
            if os.path.exists(self.playlist_file):
                with open(self.playlist_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    parts = content.split('#############################')
                    if len(parts) >= 2:
                        static_content = '#############################'.join(parts[:2]) + '#############################\n\n'
                    else:
                        static_content = self.create_default_static_content()
            else:
                static_content = self.create_default_static_content()

            # Записываем плейлист
            with open(self.playlist_file, 'w', encoding='utf-8') as f:
                f.write(static_content)
                for channel_name, streams in channels_dict.items():
                    for stream in streams:
                        extinf_parts = ['#EXTINF:-1']
                        if stream.get('tvg_id'):
                            extinf_parts.append(f'tvg-id="{stream["tvg_id"]}"')
                        if stream.get('tvg_logo'):
                            extinf_parts.append(f'tvg-logo="{stream["tvg_logo"]}"')
                        if stream.get('group'):
                            extinf_parts.append(f'group-title="{stream["group"]}"')
                        if stream.get('quality'):
                            extinf_parts.append(f'quality="{stream["quality"]}"')
                        if stream.get('stable'):
                            extinf_parts.append(f'stable="{stream["stable"]}"')
                        extinf_parts.append(f', {stream["name"]}')
                        f.write(' '.join(extinf_parts) + '\n')
                        f.write(f'{stream["url"]}\n')

            print(f"💾 Плейлист сохранен: {self.playlist_file}")
            print(f"📊 Всего каналов: {len(channels_dict)}")
            return True

        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    def create_default_static_content(self):
        """Создает статическую часть плейлиста"""
        return f'''#EXTM3U
# Обновлен: {time.strftime('%Y-%m-%d %H:%M:%S')}
# Статическая часть - НЕ ИЗМЕНЯТЬ!
# Динамическая часть ниже

#############################
#EXTINF:-1 group-title="Информационные" quality="high", ТГ канал https://t.me/NexusIPTVGroups
https://edge1.1internet.tv/
#EXTINF:-1 group-title="Информационные" quality="high", Поддержка проекта
https://edge1.1internet.tv/
#EXTINF:-1 group-title="Информационные" quality="high", GitHub проекта
https://edge1.1internet.tv/
#############################

'''

    def refresh_all_channels(self):
        """Обновляет все каналы"""
        print("🔄 ОБНОВЛЕНИЕ ВСЕХ КАНАЛОВ...")
        existing_channels = self.load_existing_channels()

        if not existing_channels:
            print("❌ Нет каналов для обновления")
            return

        print(f"📊 Найдено каналов: {len(existing_channels)}")
        updated_count = 0
        failed_count = 0

        for channel_name in list(existing_channels.keys()):
            print(f"\n{'='*60}")
            print(f"🔄 ОБНОВЛЕНИЕ: {channel_name}")
            print(f"{'='*60}")

            try:
                # Сохраняем оригинальную информацию
                original_name = channel_name
                original_category = "Общие"
                original_tvg_id = ""
                original_tvg_logo = ""

                if existing_channels[channel_name]:
                    original_category = existing_channels[channel_name][0].get('group', 'Общие')
                    original_tvg_id = existing_channels[channel_name][0].get('tvg_id', '')
                    original_tvg_logo = existing_channels[channel_name][0].get('tvg_logo', '')

                working_streams = self.search_channel_online(channel_name)

                if working_streams:
                    # Восстанавливаем оригинальную информацию
                    for stream in working_streams:
                        stream['name'] = original_name
                        stream['group'] = original_category
                        if original_tvg_id:
                            stream['tvg_id'] = original_tvg_id
                        if original_tvg_logo:
                            stream['tvg_logo'] = original_tvg_logo

                    existing_channels[channel_name] = working_streams
                    updated_count += 1
                    print(f"✅ ОБНОВЛЕН: {original_name}")
                else:
                    del existing_channels[channel_name]
                    failed_count += 1
                    print(f"❌ УДАЛЕН: {channel_name}")

                time.sleep(2)

            except Exception as e:
                print(f"💥 ОШИБКА: {e}")
                failed_count += 1
                continue

        if self.save_full_playlist(existing_channels):
            print(f"\n🎉 ОБНОВЛЕНИЕ ЗАВЕРШЕНО!")
            print(f"✅ Обновлено: {updated_count}")
            print(f"❌ Удалено: {failed_count}")

    def search_channel_online(self, channel_name):
        """Поиск канала"""
        print(f"🎯 Поиск: '{channel_name}'")
        all_streams = self.search_in_online_sources(channel_name)

        unique_streams = []
        seen_urls = set()
        for stream in all_streams:
            if stream['url'] not in seen_urls:
                stream['name'] = channel_name
                unique_streams.append(stream)
                seen_urls.add(stream['url'])

        print(f"📊 Найдено ссылок: {len(unique_streams)}")
        if not unique_streams:
            return []

        working_streams = self.check_streams(unique_streams)
        for stream in working_streams:
            stream['name'] = channel_name

        return working_streams

    def search_from_channels_list(self):
        """Поиск по списку из Channels.txt"""
        if not self.channels_list:
            print("❌ Файл Channels.txt пуст или не найден")
            return

        print(f"🎯 ПОИСК ПО СПИСКУ ИЗ {len(self.channels_list)} КАНАЛОВ...")
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

                if i < len(self.channels_list):
                    time.sleep(3)

            except Exception as e:
                print(f"💥 ОШИБКА: {e}")
                failed_count += 1
                continue

        print(f"\n🎉 ПОИСК ЗАВЕРШЕН!")
        print(f"✅ Найдено: {success_count} каналов")
        print(f"❌ Не найдено: {failed_count} каналов")

def interactive_mode():
    """Интерактивный режим"""
    scanner = OnlineM3UScanner()

    print("🎬" + "=" * 70)
    print("🌐 SMART M3U SCANNER")
    print("🎯 РАБОТАЕТ С ФАЙЛАМИ:")
    print(f"   📁 {scanner.sites_file} - источники для поиска")
    print(f"   📁 {scanner.cartolog_file} - категории каналов")  # ИСПРАВЛЕНО: cartolog.txt -> cartolog_file
    print(f"   📁 {scanner.channels_file} - список каналов для поиска")
    print("🎬" + "=" * 70)

    # Проверяем файлы
    if not scanner.custom_sites:
        print("❌ Нет сайтов для поиска! Добавьте URLs в files/site.txt")
        return

    if not scanner.channels_list:
        print("❌ Нет каналов для поиска! Добавьте каналы в files/Channels.txt")
        return

    print(f"📊 Загружено:")
    print(f"   🌐 {len(scanner.custom_sites)} сайтов из site.txt")
    print(f"   📂 {len(scanner.channel_categories)} категорий из cartolog.txt")
    print(f"   📺 {len(scanner.channels_list)} каналов из Channels.txt")

    # Проверяем ffmpeg
    ffmpeg_path = scanner.find_ffmpeg()
    if ffmpeg_path:
        print("✅ FFmpeg обнаружен")
    else:
        print("ℹ️  FFmpeg не найден - используется базовая проверка")

    existing_channels = scanner.load_existing_channels()
    if existing_channels:
        total_streams = sum(len(streams) for streams in existing_channels.values())
        print(f"📊 В плейлисте: {len(existing_channels)} каналов, {total_streams} ссылок")
    else:
        print("📝 Плейлист будет создан при первом поиске")
    while True:
        print("\n" + "🎯" + "=" * 60)
        print("1. 🔍 Поиск одного канала")
        print("2. 📋 Поиск по списку из Channels.txt")
        print("3. 🔄 Обновить все каналы")
        print("4. 📊 Статистика")
        print("5. 🚪 Выход")

        choice = input("\nВыберите действие (1-5): ").strip()

        if choice == '1':
            channel_name = input("📺 Введите название канала: ").strip()
            if channel_name:
                scanner.search_and_update_channel(channel_name)
            else:
                print("⚠️  Введите название канала")

        elif choice == '2':
            confirm = input("⚠️  Запустить поиск по списку? (y/n): ").strip().lower()
            if confirm == 'y':
                scanner.search_from_channels_list()

        elif choice == '3':
            confirm = input("⚠️  Обновить все каналы? (y/n): ").strip().lower()
            if confirm == 'y':
                scanner.refresh_all_channels()

        elif choice == '4':
            existing_channels = scanner.load_existing_channels()
            if existing_channels:
                total_streams = sum(len(streams) for streams in existing_channels.values())
                high_quality = sum(1 for streams in existing_channels.values() for s in streams if s.get('quality') in ['high', 'medium'])
                print(f"\n📊 СТАТИСТИКА:")
                print(f"   📁 Каналов: {len(existing_channels)}")
                print(f"   🔗 Ссылок: {total_streams}")
                print(f"   🎯 Качественных: {high_quality}")
            else:
                print("📝 Плейлист пуст")

        elif choice == '5':
            print("👋 Выход...")
            break

        else:
            print("⚠️  Неверный выбор")

# Настройка FFmpeg
def setup_global_ffmpeg_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_paths = [
        os.path.join(base_dir, 'ffmpeg', 'bin'),
        os.path.join(base_dir, 'ffmpeg-2025-11-17-git-e94439e49b-full_build', 'bin'),
    ]
    for path in ffmpeg_paths:
        if os.path.exists(path):
            os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
            return True
    return False

setup_global_ffmpeg_path()

def main():
    if len(sys.argv) == 1:
        interactive_mode()
    elif len(sys.argv) > 1 and sys.argv[1] == "--gui":
        try:
            from Interface import main as gui_main
            gui_main()
        except ImportError:
            print("❌ Графический интерфейс не найден")
    else:
        print("🌐 Smart M3U Scanner")
        print("Использование:")
        print("  python M3UScanner.py          - Консольный режим")
        print("  python M3UScanner.py --gui    - Графический интерфейс")

if __name__ == "__main__":
    main()
