# SearchM3U.py
import urllib.request
import urllib.error
import re
import ssl
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

class NetworkSearcher:
    """Поиск M3U-плейлистов в интернете"""
    
    def __init__(self, timeout=15, max_retries=3, stats=None):
        self.timeout = timeout
        self.max_retries = max_retries
        self.stats = stats or {}
        self.ssl_context = ssl._create_unverified_context()
    
    def search_iptv_sources(self, channel_name: str, custom_sites: list) -> list:
        """Сканирует сайты из site.txt и ищет m3u/m3u8 ссылки (многопоточно)"""
        found_urls = []
        
        def scan_site(site):
            results = []
            if not site.startswith('http'):
                site = 'https://' + site
            try:
                resp = requests.get(site, timeout=self.timeout, allow_redirects=True,
                                  headers={'User-Agent': 'Mozilla/5.0'})
                if resp.status_code < 400:
                    content = resp.text
                    patterns = [
                        r'https?://[^\s<>"\']+\.m3u[8]?(?:\?[^\s<>"\']*)?',
                        r'["\']([^"\']*\.m3u[8]?[^"\']*)["\']',
                        r'https?://[^\s<>"\']+/playlist[^\s<>"\']*\.m3u[8]?[^\s<>"\']*',
                    ]
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            link = match if match.startswith('http') else urljoin(site, match)
                            if link not in results:
                                results.append(link)
            except:
                pass
            return results
        
        # Многопоточное сканирование (20 потоков)
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(scan_site, site): site for site in custom_sites}
            for future in as_completed(futures):
                try:
                    site_results = future.result()
                    found_urls.extend(site_results)
                except:
                    continue
        
        return list(set(found_urls))
    
    def search_on_search_engines(self, channel_name: str, search_engines: list) -> list:
        """Поиск через поисковые системы"""
        found_urls = []
        query = f"{channel_name}+m3u8+playlist+iptv"
        
        for engine in search_engines:
            try:
                search_url = f"{engine}{urllib.request.quote(query)}"
                resp = requests.get(search_url, timeout=self.timeout,
                                  headers={'User-Agent': 'Mozilla/5.0'})
                if resp.status_code < 400:
                    content = resp.text
                    patterns = [r'https?://[^\s<>"\']+\.m3u[8]?(?:\?[^\s<>"\']*)?']
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            if match not in found_urls:
                                found_urls.append(match)
            except:
                continue
        
        return found_urls


class PatternMatcher:
    """Генерация поисковых паттернов и нечеткое сравнение"""
    
    @staticmethod
    def generate_exact_search_patterns(channel_name: str) -> list:
        name = channel_name.lower().strip()
        patterns = [name]
        if ' ' in name:
            patterns.append(name.replace(' ', ''))
            patterns.append(name.replace(' ', '-'))
            patterns.append(name.replace(' ', '_'))
        return patterns
    
    @staticmethod
    def exact_match(channel_title: str, search_patterns: list) -> bool:
        if not channel_title or not search_patterns:
            return False
        title_lower = channel_title.lower().strip()
        for pattern in search_patterns:
            if pattern in title_lower:
                return True
        return False
    
    @staticmethod
    def fuzzy_match(text: str, pattern: str) -> bool:
        return pattern.lower() in text.lower()
    
    @staticmethod
    def is_high_quality_channel(channel_info: dict) -> bool:
        name = channel_info.get('tvg_name', '') or channel_info.get('title', '')
        skip_words = ['test', 'xxx', '18+', 'adult', 'shop', 'barker']
        return not any(word in name.lower() for word in skip_words)
    
    @staticmethod
    def calculate_channel_quality_score(channel_info: dict) -> int:
        name = channel_info.get('tvg_name', '') or channel_info.get('title', '')
        score = 5
        name_lower = name.lower()
        if 'uhd' in name_lower or '4k' in name_lower:
            score += 3
        if 'hd' in name_lower:
            score += 2
        if 'fhd' in name_lower:
            score += 2
        return min(10, score)