# M3UScanner.py — Главный файл запуска
# py M3UScanner.py          — консольный режим (по умолчанию)
# py M3UScanner.py --gui    — графический интерфейс
# py M3UScanner.py --console — консольный режим (явно)

import os
import sys
import time
import re
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# Добавляем текущую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from M3UUtils import M3UParser, QualityAnalyzer
from SearchM3U import NetworkSearcher, PatternMatcher


class OnlineM3UScanner:
    """Основной класс сканера M3U"""

    def __init__(self):
        # Настройки
        self.timeout = 15
        self.playlist_file = "playlist/playlist.m3u"
        self.sites_file = "files/site.txt"
        self.cartolog_file = "files/cartolog.txt"
        self.channels_file = "files/Channels.txt"
        self.max_workers = 10
        self.max_sites_per_search = 20
        self.max_retries = 3
        self.max_check_urls = 50
        self.search_mode = "exact"

        # Настройки форматов (по умолчанию оба)
        self.scan_m3u = True
        self.scan_m3u8 = True

        # Статистика (создаём ДО передачи в другие классы)
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0,
            'quality_checks': 0,
            'failed_quality_checks': 0,
            'm3u_found': 0,
            'm3u8_found': 0
        }

        # Утилиты
        self.network_searcher = NetworkSearcher(
            timeout=self.timeout,
            max_retries=self.max_retries,
            stats=self.stats
        )

        self.quality_analyzer = QualityAnalyzer(
            enable_deep_check=True,
            check_duration=5,
            required_bitrate=500,
            min_resolution=480,
            required_fps=25,
            check_timeout=30
        )

        self.pattern_matcher = PatternMatcher()
        self.m3u_parser = M3UParser()

        # Загрузка файлов
        self.custom_sites = self.load_custom_sites()
        self.channel_categories = self.load_channel_categories()
        self.channels_list = self.load_channels_list()

        # Кэш
        self.channels_cache = {}

    # ============================================================
    # Настройки форматов
    # ============================================================
    def set_scan_formats(self, m3u: bool, m3u8: bool):
        """Установить форматы для сканирования"""
        self.scan_m3u = m3u
        self.scan_m3u8 = m3u8

    def get_format_string(self) -> str:
        """Получить строку с выбранными форматами"""
        formats = []
        if self.scan_m3u:
            formats.append("M3U")
        if self.scan_m3u8:
            formats.append("M3U8")
        return ", ".join(formats) if formats else "НЕ ВЫБРАНЫ"
    def set_search_mode(self, mode: str):
        """Установить режим поиска: exact / broad"""
        self.search_mode = mode
        if mode == "broad":
            print("🔍 Режим: расширенный (поиск всех дублей канала)")
        else:
            print("🔍 Режим: точный (только указанный канал)")

    # ============================================================
    # Загрузка конфигурационных файлов
    # ============================================================
    def load_custom_sites(self):
        """Загрузка списка сайтов из files/site.txt"""
        try:
            if not os.path.exists(self.sites_file):
                print(f"⚠️ Файл {self.sites_file} не найден.")
                os.makedirs(os.path.dirname(self.sites_file), exist_ok=True)
                return []
            with open(self.sites_file, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except Exception as e:
            print(f"❌ Ошибка загрузки site.txt: {e}")
            return []

    def load_channels_list(self):
        """Загрузка списка каналов из files/Channels.txt"""
        try:
            if not os.path.exists(self.channels_file):
                print(f"⚠️ Файл {self.channels_file} не найден.")
                return []
            with open(self.channels_file, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except Exception as e:
            print(f"❌ Ошибка загрузки Channels.txt: {e}")
            return []

    def load_channel_categories(self):
        """Загрузка категорий из files/cartolog.txt"""
        try:
            if not os.path.exists(self.cartolog_file):
                print(f"⚠️ Файл {self.cartolog_file} не найден.")
                return {}
            categories = {}
            current_category = "Без категории"
            with open(self.cartolog_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('#'):
                        current_category = line.lstrip('#').strip()
                    else:
                        categories[line] = current_category
            return categories
        except Exception as e:
            print(f"❌ Ошибка загрузки cartolog.txt: {e}")
            return {}

    def get_channel_category(self, channel_name: str) -> str:
        return self.channel_categories.get(channel_name, "Без категории")

    # ============================================================
    # Проверка сайтов + поиск M3U/M3U8
    # ============================================================
    def check_sites_and_find_m3u(self, threads=20, timeout=10):
        """
        Проверка работоспособности сайтов и поиск M3U/M3U8 плейлистов.
        """
        if not self.scan_m3u and not self.scan_m3u8:
            print("❌ Выберите хотя бы один формат (M3U или M3U8)!")
            return

        sites = self.load_custom_sites()
        if not sites:
            print("❌ Нет сайтов для проверки! Добавьте URL в files/site.txt")
            return

        total = len(sites)
        working = []
        broken = []
        m3u_found = []
        m3u8_found = []

        print(f"\n{'='*60}")
        print(f"🔍 ПРОВЕРКА {total} САЙТОВ + ПОИСК ПЛЕЙЛИСТОВ")
        print(f"{'='*60}")
        print(f"⚡ Потоков: {threads} | Таймаут: {timeout}с")
        print(f"🎯 Форматы: {self.get_format_string()}")
        print(f"{'='*60}\n")

        import requests

        with ThreadPoolExecutor(max_workers=threads) as executor:
            future_to_url = {}
            for url in sites:
                future = executor.submit(
                    self._check_single_site_and_find_m3u,
                    url, timeout, self.scan_m3u, self.scan_m3u8
                )
                future_to_url[future] = url

            done = 0
            for future in as_completed(future_to_url):
                done += 1
                url = future_to_url[future]

                try:
                    result = future.result()
                    is_working = result['is_working']
                    status_info = result['status_info']
                    found_m3u = result.get('m3u_links', [])
                    found_m3u8 = result.get('m3u8_links', [])

                    if is_working:
                        working.append((url, status_info))
                        icon = "✅"
                        extra = ""
                        if found_m3u or found_m3u8:
                            extra = f" | 🔗 M3U:{len(found_m3u)} M3U8:{len(found_m3u8)}"
                            m3u_found.extend([(url, link) for link in found_m3u])
                            m3u8_found.extend([(url, link) for link in found_m3u8])
                            # Показываем первые найденные ссылки
                            for link in found_m3u[:2]:
                                print(f"      📺 M3U: {link[:90]}")
                            for link in found_m3u8[:2]:
                                print(f"      📺 M3U8: {link[:90]}")
                        print(f"{icon} [{done}/{total}] {url[:70]} ({status_info}){extra}")
                    else:
                        broken.append((url, status_info))
                        print(f"❌ [{done}/{total}] {url[:70]} ({status_info})")

                except Exception as e:
                    broken.append((url, str(e)))
                    print(f"❌ [{done}/{total}] {url[:70]} (Ошибка: {e})")

        # Сохраняем результаты
        self._save_site_results(working, broken)
        self._save_m3u_results(m3u_found, m3u8_found)

        self.stats['m3u_found'] = len(m3u_found)
        self.stats['m3u8_found'] = len(m3u8_found)

        print(f"\n{'='*60}")
        print(f"✅ ПРОВЕРКА ЗАВЕРШЕНА!")
        print(f"   Сайтов: {total}")
        print(f"   ✅ Рабочих: {len(working)}")
        print(f"   ❌ Нерабочих: {len(broken)}")
        print(f"   🔗 Найдено M3U: {len(m3u_found)} | M3U8: {len(m3u8_found)}")
        print(f"   💾 Результаты сохранены в results/")
        print(f"{'='*60}")

    def _check_single_site_and_find_m3u(self, url, timeout, scan_m3u=True, scan_m3u8=True):
        """Проверка одного сайта + поиск M3U/M3U8"""
        import requests

        result = {
            'is_working': False,
            'status_info': '',
            'm3u_links': [],
            'm3u8_links': []
        }

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True,
                              headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

            result['is_working'] = resp.status_code < 400
            result['status_info'] = str(resp.status_code)

            if result['is_working']:
                content = resp.text

                # Поиск M3U
                if scan_m3u:
                    m3u_patterns = [
                        r'https?://[^\s<>"\']+\.m3u(?:\?[^\s<>"\']*)?',
                        r'["\']([^"\']*\.m3u[^"\']*)["\']',
                        r'href=["\']([^"\']*\.m3u[^"\']*)["\']',
                    ]
                    for pattern in m3u_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            link = match if match.startswith('http') else urljoin(url, match)
                            if link not in result['m3u_links'] and not link.endswith('.m3u8'):
                                result['m3u_links'].append(link)

                # Поиск M3U8
                if scan_m3u8:
                    m3u8_patterns = [
                        r'https?://[^\s<>"\']+\.m3u8(?:\?[^\s<>"\']*)?',
                        r'["\']([^"\']*\.m3u8[^"\']*)["\']',
                        r'href=["\']([^"\']*\.m3u8[^"\']*)["\']',
                    ]
                    for pattern in m3u8_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            link = match if match.startswith('http') else urljoin(url, match)
                            if link not in result['m3u8_links']:
                                result['m3u8_links'].append(link)

        except Exception as e:
            result['status_info'] = str(e)

        return result

    def _save_site_results(self, working, broken):
        """Сохранение результатов проверки сайтов"""
        Path("results").mkdir(exist_ok=True)

        with open("results/done.txt", 'w', encoding='utf-8') as f:
            f.write(f"# Рабочие сайты ({len(working)})\n")
            f.write(f"# Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for url, status in working:
                f.write(f"{url}  # status: {status}\n")

        with open("results/error.txt", 'w', encoding='utf-8') as f:
            f.write(f"# Нерабочие сайты ({len(broken)})\n")
            f.write(f"# Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for url, error in broken:
                f.write(f"{url}  # error: {error}\n")

    def _save_m3u_results(self, m3u_links, m3u8_links):
        """Сохранение найденных M3U/M3U8 ссылок"""
        Path("results").mkdir(exist_ok=True)

        with open("results/m3u_playlists.txt", 'w', encoding='utf-8') as f:
            f.write(f"# Найденные M3U/M3U8 плейлисты\n")
            f.write(f"# Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Всего M3U: {len(m3u_links)} | M3U8: {len(m3u8_links)}\n\n")

            if m3u_links:
                f.write(f"# ==================== M3U ({len(m3u_links)}) ====================\n")
                for source_url, m3u_url in m3u_links:
                    f.write(f"{m3u_url}  # source: {source_url}\n")
                f.write("\n")

            if m3u8_links:
                f.write(f"# ==================== M3U8 ({len(m3u8_links)}) ====================\n")
                for source_url, m3u8_url in m3u8_links:
                    f.write(f"{m3u8_url}  # source: {source_url}\n")
                f.write("\n")

    # ============================================================
    # Основные методы поиска и обновления каналов
    # ============================================================
    def search_in_online_sources(self, channel_name: str) -> list:
        """Оркестрация поиска: IPTV-источники, поисковые системы, GitHub."""
        print(f"\n{'='*60}")
        print(f"🔍 Поиск канала: {channel_name}")
        print(f"🎯 Форматы: {self.get_format_string()}")
        print(f"{'='*60}")

        all_urls = []

        print("📡 Поиск в IPTV-источниках...")
        custom_urls = self.network_searcher.search_iptv_sources(channel_name, self.custom_sites)
        if custom_urls:
            all_urls.extend(custom_urls)
            print(f"   Найдено: {len(custom_urls)} ссылок")
        else:
            print(f"   Найдено: 0 ссылок")

        print("🌐 Поиск в поисковых системах...")
        search_engines = [
            "https://www.google.com/search?q=",
            "https://search.yahoo.com/search?p="
        ]
        search_urls = self.network_searcher.search_on_search_engines(channel_name, search_engines)
        if search_urls:
            all_urls.extend(search_urls)
            print(f"   Найдено: {len(search_urls)} ссылок")
        else:
            print(f"   Найдено: 0 ссылок")

        if not all_urls:
            print("❌ Ничего не найдено")
            return []

        unique_urls = list(set(all_urls))

        if not self.scan_m3u:
            unique_urls = [u for u in unique_urls if '.m3u' not in u.lower() or '.m3u8' in u.lower()]
        if not self.scan_m3u8:
            unique_urls = [u for u in unique_urls if '.m3u8' not in u.lower()]

        print(f"\n📊 Всего уникальных ссылок: {len(unique_urls)}")
        return unique_urls

    def check_single_stream_improved(self, stream_info: dict) -> dict:
        """Проверка конкретной ссылки через QualityAnalyzer"""
        url = stream_info.get('url', '')
        result = {
            'url': url,
            'name': stream_info.get('name', ''),
            'is_working': False,
            'quality_score': 0,
            'quality_info': {}
        }

        try:
            quality_info = self.quality_analyzer.analyze_stream_quality(url)
            self.stats['quality_checks'] += 1

            if quality_info.get('is_working', False):
                if self.quality_analyzer.check_quality_requirements(quality_info):
                    result['is_working'] = True
                    result['quality_score'] = self.quality_analyzer.calculate_quality_score(quality_info)
                    result['quality_info'] = quality_info
                else:
                    self.stats['failed_quality_checks'] += 1
            else:
                self.stats['failed_quality_checks'] += 1
        except Exception as e:
            print(f"   ⚠️ Ошибка проверки {url}: {e}")

        return result

    def check_streams(self, streams: list, search_name: str) -> list:
        """Проверка всех найденных ссылок с фильтрацией по имени (многопоточно)"""
        print(f"\n🔬 Проверка {len(streams)} потоков для '{search_name}'...")
        search_patterns = self.pattern_matcher.generate_exact_search_patterns(search_name)
        
        # Фильтруем по имени
        filtered_streams = []
        for stream in streams:
            stream_name = stream.get('name', '')
            if self.pattern_matcher.exact_match(stream_name, search_patterns):
                filtered_streams.append(stream)
        
        print(f"   Отфильтровано по имени: {len(filtered_streams)} из {len(streams)}")
        
        valid_streams = []
        
        # Многопоточная проверка (30 потоков)
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = {executor.submit(self.check_single_stream_improved, stream): stream for stream in filtered_streams}
            done = 0
            for future in as_completed(futures):
                done += 1
                try:
                    result = future.result()
                    if result['is_working']:
                        valid_streams.append(result)
                        print(f"   ✅ [{done}/{len(filtered_streams)}] {result['name'][:50]} (score: {result['quality_score']})")
                    else:
                        if done % 10 == 0:  # Показываем прогресс каждые 10
                            print(f"   🔄 Проверено: {done}/{len(filtered_streams)} | Найдено: {len(valid_streams)}")
                except:
                    pass
        
        valid_streams.sort(key=lambda x: x['quality_score'], reverse=True)
        print(f"\n📊 Рабочих потоков: {len(valid_streams)}")
        return valid_streams

    def search_and_update_channel(self, channel_name: str) -> bool:
        try:
            if self.search_mode == "broad":
                # Расширенный поиск
                all_valid = []
                search_terms = [channel_name]
                for suffix in ['HD', 'FHD', 'UHD', '4K', '+2', '+4', '+7', '+8', '-2', '-4', '-7']:
                    search_terms.append(f"{channel_name} {suffix}")
                
                total_terms = len(search_terms)
                for idx, term in enumerate(search_terms, 1):
                    print(f"\n{'='*60}")
                    print(f"🔍 Поиск канала ({idx}/{total_terms}): {term}")
                    print(f"🎯 Форматы: {self.get_format_string()}")
                    print(f"{'='*60}")
                    
                    urls = self.search_in_online_sources(term)
                    if urls:
                        limit = max(5, self.max_check_urls // total_terms)
                        if len(urls) > limit:
                            print(f"   ⚡ Ограничиваем до {limit} ссылок")
                            urls = urls[:limit]
                        streams = [{'url': url, 'name': term} for url in urls]
                        valid = self.check_streams(streams, term)
                        all_valid.extend(valid)
                
                if not all_valid:
                    print(f"❌ Канал '{channel_name}' не найден")
                    return False
                
                print(f"\n📊 Всего найдено рабочих потоков: {len(all_valid)}")
                return self.update_channel_in_playlist(channel_name, all_valid)
            else:
                # Точный поиск
                urls = self.search_in_online_sources(channel_name)
                if not urls:
                    return False
                if len(urls) > self.max_check_urls:
                    print(f"   ⚡ Ограничиваем до {self.max_check_urls} ссылок")
                    urls = urls[:self.max_check_urls]
                streams = [{'url': url, 'name': channel_name} for url in urls]
                valid_streams = self.check_streams(streams, channel_name)
                if not valid_streams:
                    return False
                return self.update_channel_in_playlist(channel_name, valid_streams)
        except Exception as e:
            print(f"💥 Ошибка: {e}")
            return False

    def refresh_all_channels(self):
        """Обновить все каналы из плейлиста"""
        print("\n🔄 ПОЛНОЕ ОБНОВЛЕНИЕ ВСЕХ КАНАЛОВ")
        print(f"🎯 Форматы: {self.get_format_string()}")

        existing_channels = self.load_existing_channels()
        if not existing_channels:
            print("📝 Плейлист пуст. Запуск поиска из Channels.txt...")
            self.search_from_channels_list()
            return

        total = len(existing_channels)
        updated = 0
        failed = 0

        for i, channel_name in enumerate(existing_channels.keys(), 1):
            print(f"\n{'─'*50}")
            print(f"[{i}/{total}] Обновление: {channel_name}")
            if self.search_and_update_channel(channel_name):
                updated += 1
            else:
                failed += 1
            if i < total:
                print("⏳ Пауза 2 сек...")
                time.sleep(2)

        print(f"\n{'='*50}")
        print(f"✅ Обновлено: {updated} | ❌ Ошибок: {failed}")

    def search_from_channels_list(self):
        """Массовый поиск по списку Channels.txt"""
        if not self.channels_list:
            print("❌ Список каналов пуст! Добавьте каналы в files/Channels.txt")
            return

        print(f"\n📋 Загрузка {len(self.channels_list)} каналов из списка...")
        print(f"🎯 Форматы: {self.get_format_string()}")
        found = 0
        not_found = 0

        for i, channel_name in enumerate(self.channels_list, 1):
            print(f"\n{'─'*50}")
            print(f"[{i}/{len(self.channels_list)}] Поиск: {channel_name}")
            if self.search_and_update_channel(channel_name):
                found += 1
            else:
                not_found += 1
            if i < len(self.channels_list):
                print("⏳ Пауза 3 сек...")
                time.sleep(3)

        print(f"\n{'='*50}")
        print(f"✅ Найдено: {found} | ❌ Не найдено: {not_found}")

    # ============================================================
    # Работа с плейлистом
    # ============================================================
    def load_existing_channels(self) -> dict:
        return self.m3u_parser.load_existing_channels(self.playlist_file)

    def save_full_playlist(self, channels_dict: dict) -> bool:
        static = self.m3u_parser.create_default_static_content()
        return self.m3u_parser.save_full_playlist(self.playlist_file, channels_dict, static)

    def update_channel_in_playlist(self, channel_name: str, new_streams: list) -> bool:
        try:
            existing_channels = self.load_existing_channels()
            old_streams = existing_channels.get(channel_name, [])
            merged_streams = self.merge_streams(old_streams, new_streams)
            existing_channels[channel_name] = merged_streams
            return self.save_full_playlist(existing_channels)
        except Exception as e:
            print(f"❌ Ошибка обновления плейлиста: {e}")
            return False

    def merge_streams(self, old_streams: list, new_streams: list) -> list:
        merged = {}
        for stream in old_streams:
            url = stream.get('url', '')
            if url and url not in merged:
                merged[url] = stream
        for stream in new_streams:
            url = stream.get('url', '')
            if url:
                merged[url] = stream
        result = list(merged.values())
        result.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        return result

    # ============================================================
    # Вспомогательные методы
    # ============================================================
    def get_source_name(self, url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or "unknown"

    def show_quality_settings(self):
        print("\n📊 Настройки качества:")
        print(f"   Глубокая проверка: {self.quality_analyzer.enable_deep_check}")
        print(f"   Длительность проверки: {self.quality_analyzer.check_duration} сек")
        print(f"   Мин. битрейт: {self.quality_analyzer.required_bitrate} Kbps")
        print(f"   Мин. разрешение: {self.quality_analyzer.min_video_resolution}p")
        print(f"   Мин. FPS: {self.quality_analyzer.required_fps}")
        print(f"   Таймаут: {self.quality_analyzer.check_timeout} сек")

    def update_quality_settings(self):
        print("\n⚙️ Обновление настроек качества (оставьте пустым для пропуска):")
        try:
            val = input(f"Глубокая проверка (y/n) [{self.quality_analyzer.enable_deep_check}]: ").strip().lower()
            if val == 'y':
                self.quality_analyzer.enable_deep_check = True
            elif val == 'n':
                self.quality_analyzer.enable_deep_check = False

            val = input(f"Длительность проверки (сек) [{self.quality_analyzer.check_duration}]: ").strip()
            if val:
                self.quality_analyzer.check_duration = int(val)

            val = input(f"Мин. битрейт (Kbps) [{self.quality_analyzer.required_bitrate}]: ").strip()
            if val:
                self.quality_analyzer.required_bitrate = int(val)

            val = input(f"Мин. разрешение (p) [{self.quality_analyzer.min_video_resolution}]: ").strip()
            if val:
                self.quality_analyzer.min_video_resolution = int(val)

            val = input(f"Мин. FPS [{self.quality_analyzer.required_fps}]: ").strip()
            if val:
                self.quality_analyzer.required_fps = int(val)

            print("✅ Настройки обновлены!")
        except ValueError:
            print("❌ Ошибка: введите число")

    def show_format_settings(self):
        """Показать текущие настройки форматов"""
        print("\n📋 Настройки форматов:")
        print(f"   M3U:  {'✅ Включено' if self.scan_m3u else '❌ Отключено'}")
        print(f"   M3U8: {'✅ Включено' if self.scan_m3u8 else '❌ Отключено'}")

    def update_format_settings(self):
        """Интерактивное меню выбора форматов"""
        print("\n⚙️ Выбор форматов для поиска:")
        print(f"   [1] M3U  — {'✅ ВКЛ' if self.scan_m3u else '❌ ВЫКЛ'}")
        print(f"   [2] M3U8 — {'✅ ВКЛ' if self.scan_m3u8 else '❌ ВЫКЛ'}")
        print(f"   [3] Включить оба")
        print(f"   [4] Выключить оба")
        print(f"   [0] Назад")

        choice = input("Выберите: ").strip()

        if choice == '1':
            self.scan_m3u = not self.scan_m3u
            print(f"   M3U: {'✅ ВКЛЮЧЕН' if self.scan_m3u else '❌ ВЫКЛЮЧЕН'}")
        elif choice == '2':
            self.scan_m3u8 = not self.scan_m3u8
            print(f"   M3U8: {'✅ ВКЛЮЧЕН' if self.scan_m3u8 else '❌ ВЫКЛЮЧЕН'}")
        elif choice == '3':
            self.scan_m3u = True
            self.scan_m3u8 = True
            print("   ✅ Оба формата включены")
        elif choice == '4':
            self.scan_m3u = False
            self.scan_m3u8 = False
            print("   ❌ Оба формата выключены")
        elif choice == '0':
            return
        else:
            print("   ❌ Неверный выбор")


# ============================================================
# Консольный режим
# ============================================================
def console_mode():
    """Интерактивное меню в консоли"""
    scanner = OnlineM3UScanner()

    while True:
        print(f"\n{'='*50}")
        print("🌐 SMART M3U SCANNER")
        print(f"{'='*50}")
        print(f"🎯 Форматы: {scanner.get_format_string()}")
        print(f"{'='*50}")
        print("1. 🔍 Поиск канала")
        print("2. 📋 Поиск всех каналов (из Channels.txt)")
        print("3. 🔄 Обновить все каналы")
        print("4. 🌐 Проверить сайты + найти M3U/M3U8")
        print("5. 📊 Статистика плейлиста")
        print("6. ⚙️ Настройки качества")
        print("7. 📋 Выбор форматов (M3U/M3U8)")
        print("8. 📁 Открыть папку проекта")
        print("9. ⚡ Макс. ссылок для проверки (сейчас: {})".format(scanner.max_check_urls))
        print("10. 🔍 Режим поиска (сейчас: {})".format(scanner.search_mode))
        print("0. 🚪 Выход")
        print(f"{'='*50}")

        choice = input("Выберите действие: ").strip()

        if choice == '1':
            channel_name = input("Введите название канала: ").strip()
            if channel_name:
                scanner.search_and_update_channel(channel_name)

        elif choice == '2':
            scanner.search_from_channels_list()

        elif choice == '3':
            print("⚠️ Это займёт много времени. Продолжить? (y/n): ", end='')
            if input().strip().lower() == 'y':
                scanner.refresh_all_channels()

        elif choice == '4':
            try:
                threads = input("Количество потоков (по умолчанию 20): ").strip()
                threads = int(threads) if threads else 20
            except ValueError:
                threads = 20
            try:
                timeout = input("Таймаут в секундах (по умолчанию 10): ").strip()
                timeout = int(timeout) if timeout else 10
            except ValueError:
                timeout = 10
            scanner.check_sites_and_find_m3u(threads=threads, timeout=timeout)

        elif choice == '5':
            channels = scanner.load_existing_channels()
            if channels:
                total = sum(len(s) for s in channels.values())
                print(f"\n📊 Статистика плейлиста:")
                print(f"   📺 Каналов: {len(channels)}")
                print(f"   🔗 Всего ссылок: {total}")
                print(f"   📁 Источников (site.txt): {len(scanner.custom_sites)}")
            else:
                print("\n📝 Плейлист пуст")
            print(f"\n📊 Статистика поиска:")
            print(f"   🔗 Найдено M3U: {scanner.stats.get('m3u_found', 0)}")
            print(f"   🔗 Найдено M3U8: {scanner.stats.get('m3u8_found', 0)}")

        elif choice == '6':
            scanner.show_quality_settings()
            scanner.update_quality_settings()

        elif choice == '7':
            scanner.show_format_settings()
            scanner.update_format_settings()

        elif choice == '8':
            try:
                project_dir = os.path.dirname(os.path.abspath(__file__))
                if sys.platform == "win32":
                    os.startfile(project_dir)
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["open", project_dir])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", project_dir])
            except:
                print(f"📁 Папка проекта: {os.path.dirname(os.path.abspath(__file__))}")

        elif choice == '9':
            try:
                val = input(f"Макс. ссылок [{scanner.max_check_urls}]: ").strip()
                if val:
                    scanner.max_check_urls = int(val)
                    print(f"   ✅ Установлено: {scanner.max_check_urls}")
            except ValueError:
                print("   ❌ Введите число")
        elif choice == '10':
            if scanner.search_mode == "exact":
                scanner.set_search_mode("broad")
            else:
                scanner.set_search_mode("exact")

        elif choice == '0':
            print("👋 До свидания!")
            break

        else:
            print("❌ Неверный выбор")

        input("\nНажмите Enter для продолжения...")


# ============================================================
# Точка входа
# ============================================================
def main():
    """
    Точка входа.
    py M3UScanner.py             → консольный режим
    py M3UScanner.py --console   → консольный режим
    py M3UScanner.py --gui       → графический интерфейс
    """
    if "--gui" in sys.argv:
        try:
            from Interface import main as gui_main
            gui_main()
        except ImportError as e:
            print(f"❌ Ошибка импорта Interface.py: {e}")
            print("   Убедитесь, что Interface.py находится в одной папке с M3UScanner.py")
    elif "--console" in sys.argv or len(sys.argv) == 1:
        console_mode()
    else:
        print("Использование:")
        print("  py M3UScanner.py             — консольный режим (по умолчанию)")
        print("  py M3UScanner.py --console   — консольный режим")
        print("  py M3UScanner.py --gui       — графический интерфейс")


if __name__ == "__main__":
    main()