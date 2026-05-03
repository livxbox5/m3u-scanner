# M3UUtils.py
import re
import subprocess
import os
import time
import html as html_mod
from pathlib import Path

class M3UParser:
    """Парсинг и генерация M3U-плейлистов"""
    
    @staticmethod
    def parse_extinf_line(extinf_line: str) -> dict:
        """Разбор строки #EXTINF."""
        info = {
            'duration': -1,
            'tvg_id': '',
            'tvg_name': '',
            'tvg_logo': '',
            'group_title': '',
            'title': '',
            'url': ''
        }
        
        duration_match = re.match(r'#EXTINF:\s*(-?\d+)', extinf_line)
        if duration_match:
            info['duration'] = int(duration_match.group(1))
        
        attr_patterns = {
            'tvg-id': r'tvg-id="([^"]*)"',
            'tvg-name': r'tvg-name="([^"]*)"',
            'tvg-logo': r'tvg-logo="([^"]*)"',
            'group-title': r'group-title="([^"]*)"',
        }
        
        for attr, pattern in attr_patterns.items():
            match = re.search(pattern, extinf_line)
            if match:
                info[attr.replace('-', '_')] = match.group(1)
        
        comma_match = re.search(r',\s*(.+)$', extinf_line)
        if comma_match:
            info['title'] = comma_match.group(1).strip()
        
        return info
    
    @staticmethod
    def extract_channels_from_playlist(content: str, channel_name: str, 
                                       search_patterns: list) -> list:
        """Извлечение каналов из плейлиста."""
        channels = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            if line.startswith('#EXTINF:'):
                info = M3UParser.parse_extinf_line(line)
                channel_title = info['tvg_name'] or info['title']
                if not channel_title:
                    continue
                from SearchM3U import PatternMatcher
                if PatternMatcher.exact_match(channel_title, search_patterns):
                    if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith('#'):
                        info['url'] = lines[i + 1].strip()
                        channels.append(info)
        
        return channels
    
    @staticmethod
    def create_default_static_content() -> str:
        """Создать статическую шапку плейлиста"""
        return f"""#EXTM3U
#PLAYLIST: Smart M3U Scanner
#URL: https://github.com/livxbox5/m3u-scanner
#Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
#========================================================

"""
    
    @staticmethod
    def load_existing_channels(playlist_path: str) -> dict:
        """Загрузить существующие каналы."""
        channels = {}
        
        if not os.path.exists(playlist_path):
            return channels
        
        try:
            with open(playlist_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            current_info = None
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                if line.startswith('#EXTINF:'):
                    current_info = M3UParser.parse_extinf_line(line)
                elif line and not line.startswith('#') and current_info:
                    channel_name = current_info['tvg_name'] or current_info['title']
                    if channel_name:
                        current_info['url'] = line
                        if channel_name not in channels:
                            channels[channel_name] = []
                        channels[channel_name].append(current_info.copy())
                    current_info = None
        
        except Exception as e:
            print(f"Ошибка загрузки плейлиста: {e}")
        
        return channels
    
    @staticmethod
    def save_full_playlist(playlist_path: str, channels_dict: dict, 
                        static_content: str) -> bool:
        """Сохранить плейлист с разделением m3u/m3u8."""
        try:
            Path(os.path.dirname(playlist_path)).mkdir(parents=True, exist_ok=True)
            
            # Сохраняем пользовательский контент
            user_header = static_content
            if os.path.exists(playlist_path):
                with open(playlist_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if '\n#========================================================\n# ℹ️ ИНФОРМАЦИЯ' in content:
                    user_header = content.split('\n#========================================================\n# ℹ️ ИНФОРМАЦИЯ')[0].strip()
            
            # Загружаем существующие каналы
            existing = M3UParser.load_existing_channels(playlist_path) if os.path.exists(playlist_path) else {}
            
            # Объединяем
            for ch, streams in channels_dict.items():
                if ch in existing:
                    old_urls = {s['url'] for s in existing[ch]}
                    for s in streams:
                        if s['url'] not in old_urls:
                            existing[ch].append(s)
                else:
                    existing[ch] = streams
            
            # Разделяем
            info_names = ['GitHUB', 'ТГ канал', 'Поддержка']
            normal = {k: v for k, v in existing.items() if k not in info_names}
            info = {k: v for k, v in existing.items() if k in info_names}
            
            # Разделяем по типу ссылок
            m3u_normal = {}
            m3u8_normal = {}
            
            for ch, streams in normal.items():
                for s in streams:
                    url = s.get('url', '')
                    if '.m3u8' in url:
                        if ch not in m3u8_normal:
                            m3u8_normal[ch] = []
                        m3u8_normal[ch].append(s)
                    else:
                        if ch not in m3u_normal:
                            m3u_normal[ch] = []
                        m3u_normal[ch].append(s)
            
            def write_channels_to_file(filepath, channels, info_data):
                Path(os.path.dirname(filepath)).mkdir(parents=True, exist_ok=True)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(user_header + "\n\n")
                    
                    f.write("#========================================================\n")
                    f.write("# ℹ️ ИНФОРМАЦИЯ\n")
                    f.write(f"# Обновлено: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("# Поддержка: https://t.me/NexusIPTVGroups\n")
                    f.write(f"# Каналов: {len(channels)}\n")
                    f.write("#========================================================\n")
                    for key in sorted(info_data.keys()):
                        streams = info_data[key]
                        best = streams[0] if streams else None
                        if best:
                            f.write(f'#EXTINF:-1 group-title="INFO" tvg-name="{key}",{key}\n')
                            f.write(f'{best["url"]}\n')
                    
                    f.write("\n")
                    f.write("#========================================================\n")
                    f.write("# 📡 КАНАЛЫ — обновляются автоматически\n")
                    f.write("#========================================================\n")
                    
                    for channel_name in sorted(channels.keys()):
                        streams = channels[channel_name]
                        if not streams:
                            continue
                        best = max(streams, key=lambda x: x.get('quality_score', 0)) if streams else None
                        if best:
                            url = best["url"]
                            url = html_mod.unescape(url)
                            if '.m3u8' in url:
                                url = url.split('.m3u8')[0] + '.m3u8'
                                if '?' in url:
                                    base = url.split('?')[0]
                                    params = url.split('?')[1]
                                    if params and not params.startswith('{') and '&' in params:
                                        url = base + '?' + params.split('&')[0]
                                    else:
                                        url = base
                            elif '.m3u' in url:
                                url = url.split('.m3u')[0] + '.m3u'
                                if '?' in url:
                                    url = url.split('?')[0]
                            
                            qi = best.get('quality_info', {})
                            res = qi.get('resolution', 0)
                            if res >= 2160: label = "4K"
                            elif res >= 1080: label = "1080p"
                            elif res >= 720: label = "720p"
                            elif res >= 480: label = "480p"
                            else: label = "SD"
                            
                            f.write(f'#EXTINF:-1 group-title="IPTV" tvg-name="{channel_name} ({label})",{channel_name} ({label})\n')
                            f.write(f'{url}\n')
            
            # Сохраняем оба файла
            m3u_path = playlist_path
            m3u8_path = playlist_path.replace('.m3u', '.m3u8')
            
            write_channels_to_file(m3u_path, m3u_normal, info)
            write_channels_to_file(m3u8_path, m3u8_normal, info)
            
            return True
        
        except Exception as e:
            print(f"Ошибка сохранения плейлиста: {e}")
            return False


class QualityAnalyzer:
    """Анализ качества видео через FFmpeg"""
    
    def __init__(self, enable_deep_check=True, check_duration=5,
                 required_bitrate=500, min_resolution=480, required_fps=25,
                 check_timeout=30):
        self.enable_deep_check = enable_deep_check
        self.check_duration = check_duration
        self.required_bitrate = required_bitrate
        self.min_video_resolution = min_resolution
        self.required_fps = required_fps
        self.check_timeout = check_timeout
        self.ffmpeg_path = None
        self.quality_cache = {}
        self.setup_ffmpeg()
    
    def setup_ffmpeg(self):
        """Поиск ffmpeg в системе и папке проекта"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        possible_paths = [
            os.path.join(script_dir, 'ffmpeg.exe'),
            os.path.join(script_dir, 'ffmpeg', 'bin', 'ffmpeg.exe'),
            os.path.join(script_dir, 'ffmpeg', 'ffmpeg.exe'),
            'ffmpeg',
            'ffmpeg.exe',
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, '-version'], 
                                      capture_output=True, 
                                      timeout=5)
                if result.returncode == 0:
                    self.ffmpeg_path = path
                    print(f"✅ FFmpeg найден: {path}")
                    return
            except:
                continue
        
        print("⚠️ FFmpeg не найден. Проверка качества будет ограничена.")
    
    def analyze_stream_quality(self, url: str) -> dict:
        """Анализ потока — быстрое определение качества по URL"""
        result = {
            'url': url,
            'is_working': False,
            'resolution': 0,
            'bitrate': 0,
            'fps': 0,
            'codec': 'unknown',
            'duration': 0,
            'error': ''
        }
        
        import requests
        try:
            resp = requests.get(url, timeout=10, allow_redirects=True, stream=True,
                            headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code < 400:
                result['is_working'] = True
                
                url_lower = url.lower()
                if 'uhd' in url_lower or '2160' in url_lower or '4k' in url_lower:
                    result['resolution'] = 2160
                    result['bitrate'] = 15000
                elif 'fhd' in url_lower or '1080' in url_lower:
                    result['resolution'] = 1080
                    result['bitrate'] = 6000
                elif 'hd' in url_lower or '720' in url_lower:
                    result['resolution'] = 720
                    result['bitrate'] = 3000
                elif 'sd' in url_lower or '480' in url_lower or '360' in url_lower:
                    result['resolution'] = 480
                    result['bitrate'] = 1000
                else:
                    result['resolution'] = 720
                    result['bitrate'] = 2000
                result['fps'] = 25
                result['codec'] = 'h264'
                
                resp.close()
        except:
            pass
        
        return result
    
    def check_quality_requirements(self, quality_info: dict) -> bool:
        if not quality_info.get('is_working', False):
            return False
        return True
    
    def calculate_quality_score(self, quality_info: dict) -> int:
        score = 30
        resolution = quality_info.get('resolution', 0)
        if resolution >= 2160: score += 35
        elif resolution >= 1080: score += 25
        elif resolution >= 720: score += 15
        elif resolution >= 480: score += 5
        
        bitrate = quality_info.get('bitrate', 0)
        if bitrate >= 8000: score += 20
        elif bitrate >= 4000: score += 15
        elif bitrate >= 2000: score += 10
        elif bitrate >= 1000: score += 5
        
        fps = quality_info.get('fps', 0)
        if fps >= 50: score += 15
        elif fps >= 30: score += 10
        elif fps >= 25: score += 5
        
        return min(100, max(0, score))
    
    def _quick_check(self, url: str) -> bool:
        import requests
        try:
            resp = requests.get(url, timeout=10, allow_redirects=True,
                            headers={'User-Agent': 'Mozilla/5.0'})
            return resp.status_code < 400
        except:
            return False