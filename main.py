import os
import sys
import time
import requests
import asyncio
import logging
import schedule
import json
import random
import re
from telegram.ext import Application
from datetime import datetime
from urllib.parse import urlparse
import ssl
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# ============= PROXY CONFIGURATION =============
# Hanya digunakan untuk bootstrap (ambil proxy pertama kali)
BOOTSTRAP_PROXIES = [
    ("43.218.124.29", 8090, "http", "transparent"),
    ("34.50.105.1", 80, "http", "transparent"),
    ("114.4.168.140", 80, "http", "transparent"),
    ("43.218.124.29", 28950, "http", "transparent"),
    ("108.136.140.236", 14043, "http", "transparent"),
]

# Global proxy list - akan diisi dari web
PROXY_LIST = []
PROXY_SOURCES = [
    "https://proxy5.net/free-proxy/indonesia",
    "https://free-proxy-list.net/",
    "https://www.sslproxies.org/",
    "https://www.us-proxy.org/",
]

def fetch_proxies_from_web(proxy_to_use=None):
    """Ambil daftar proxy dari berbagai sumber"""
    global PROXY_LIST
    
    all_new_proxies = []
    
    for source_url in PROXY_SOURCES:
        try:
            logger.info(f"🌐 Mencoba mengambil proxy dari {source_url}...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
            }
            
            proxies = {}
            if proxy_to_use:
                proxy_url = f"{proxy_to_use[2]}://{proxy_to_use[0]}:{proxy_to_use[1]}"
                proxies = {'http': proxy_url, 'https': proxy_url}
                logger.info(f"🔗 Menggunakan proxy {proxy_to_use[0]}:{proxy_to_use[1]}")
            
            response = requests.get(
                source_url,
                headers=headers,
                proxies=proxies if proxy_to_use else None,
                timeout=30,
                verify=False
            )
            
            if response.status_code != 200:
                logger.warning(f"⚠️ Gagal mengambil dari {source_url}: HTTP {response.status_code}")
                continue
            
            # Parse berdasarkan sumber
            if 'proxy5.net' in source_url:
                proxies = parse_proxy5_html(response.text)
            elif 'free-proxy-list.net' in source_url:
                proxies = parse_free_proxy_list(response.text)
            else:
                proxies = parse_generic_proxy_table(response.text)
            
            if proxies:
                all_new_proxies.extend(proxies)
                logger.info(f"✅ Mendapat {len(proxies)} proxy dari {source_url}")
                break  # Berhenti jika berhasil dapat proxy
                
        except Exception as e:
            logger.warning(f"⚠️ Error dari {source_url}: {e}")
            continue
    
    if all_new_proxies:
        # Hapus duplikat
        unique_proxies = list(set(all_new_proxies))
        PROXY_LIST = unique_proxies
        logger.info(f"✅ Total {len(PROXY_LIST)} proxy berhasil diambil")
        
        # Simpan ke cache
        try:
            with open('proxy_cache.json', 'w') as f:
                json.dump(PROXY_LIST, f)
            logger.info("💾 Proxy disimpan ke cache")
        except:
            pass
        
        return True
    
    # Jika semua sumber gagal, coba ambil dari cache
    if load_proxy_cache():
        return True
    
    return False

def parse_proxy5_html(html):
    """Parse HTML dari proxy5.net"""
    proxies = []
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Cari tabel
        table = None
        for selector in ['table', 'table.table', 'table.proxy-table']:
            try:
                table = soup.select_one(selector)
                if table:
                    break
            except:
                continue
        
        if not table:
            tables = soup.find_all('table')
            for t in tables:
                if 'IP Address' in str(t) or 'Port' in str(t):
                    table = t
                    break
        
        if not table:
            return proxies
        
        rows = table.find_all('tr')
        protocol_map = {
            'HTTP': 'http',
            'HTTPS': 'http',
            'SOCKS4': 'socks4',
            'SOCKS5': 'socks5'
        }
        
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) >= 5:
                try:
                    ip_text = cols[0].get_text(strip=True)
                    port_text = cols[1].get_text(strip=True)
                    protocol_text = cols[2].get_text(strip=True).upper()
                    
                    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_text):
                        continue
                    
                    port = int(port_text)
                    if port < 1 or port > 65535:
                        continue
                    
                    protocols = []
                    for proto in ['HTTP', 'HTTPS', 'SOCKS4', 'SOCKS5']:
                        if proto in protocol_text:
                            protocols.append(protocol_map.get(proto, proto.lower()))
                    
                    if not protocols:
                        protocols = ['http']
                    
                    for proto in protocols:
                        proxy_tuple = (ip_text, port, proto, 'transparent')
                        if proxy_tuple not in proxies:
                            proxies.append(proxy_tuple)
                            
                except (ValueError, IndexError):
                    continue
                    
    except Exception as e:
        logger.error(f"Error parsing proxy5: {e}")
    
    return proxies

def parse_free_proxy_list(html):
    """Parse HTML dari free-proxy-list.net"""
    proxies = []
    try:
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', {'id': 'proxylisttable'})
        
        if not table:
            return proxies
        
        rows = table.find_all('tr')
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) >= 8:
                try:
                    ip_text = cols[0].get_text(strip=True)
                    port_text = cols[1].get_text(strip=True)
                    protocol_text = cols[6].get_text(strip=True).upper()
                    
                    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_text):
                        continue
                    
                    port = int(port_text)
                    if port < 1 or port > 65535:
                        continue
                    
                    protocol = 'http' if protocol_text == 'HTTP' else 'socks5'
                    proxy_tuple = (ip_text, port, protocol, 'transparent')
                    if proxy_tuple not in proxies:
                        proxies.append(proxy_tuple)
                        
                except (ValueError, IndexError):
                    continue
                    
    except Exception as e:
        logger.error(f"Error parsing free-proxy-list: {e}")
    
    return proxies

def parse_generic_proxy_table(html):
    """Parse HTML dari tabel proxy generic"""
    proxies = []
    try:
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        
        if not table:
            return proxies
        
        rows = table.find_all('tr')
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) >= 4:
                try:
                    ip_text = cols[0].get_text(strip=True)
                    port_text = cols[1].get_text(strip=True)
                    
                    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_text):
                        continue
                    
                    port = int(port_text)
                    if port < 1 or port > 65535:
                        continue
                    
                    protocol = 'http'  # Default
                    proxy_tuple = (ip_text, port, protocol, 'transparent')
                    if proxy_tuple not in proxies:
                        proxies.append(proxy_tuple)
                        
                except (ValueError, IndexError):
                    continue
                    
    except Exception as e:
        logger.error(f"Error parsing generic table: {e}")
    
    return proxies

def load_proxy_cache():
    """Muat proxy dari cache"""
    global PROXY_LIST
    
    try:
        if os.path.exists('proxy_cache.json'):
            with open('proxy_cache.json', 'r') as f:
                cached_proxies = json.load(f)
                if cached_proxies and len(cached_proxies) > 0:
                    PROXY_LIST = cached_proxies
                    logger.info(f"📂 Memuat {len(PROXY_LIST)} proxy dari cache")
                    return True
    except Exception as e:
        logger.warning(f"⚠️ Gagal memuat cache: {e}")
    
    return False

def find_working_proxy():
    """Cari proxy yang bekerja dengan mencoba semua proxy yang ada"""
    global PROXY_LIST
    
    if not PROXY_LIST:
        logger.error("❌ Tidak ada proxy untuk diuji!")
        return None
    
    logger.info(f"🔍 Menguji {len(PROXY_LIST)} proxy untuk mencari yang bekerja...")
    
    # Acak urutan proxy
    test_proxies = PROXY_LIST.copy()
    random.shuffle(test_proxies)
    
    working_proxies = []
    
    for proxy in test_proxies[:50]:  # Batasi 50 proxy untuk testing
        try:
            host, port, protocol, _ = proxy
            proxy_url = f"{protocol}://{host}:{port}"
            proxies = {'http': proxy_url, 'https': proxy_url}
            
            logger.info(f"🧪 Menguji {host}:{port} ({protocol})...")
            
            # Test dengan trustpositif
            response = requests.get(
                "https://trustpositif.komdigi.go.id/",
                proxies=proxies,
                timeout=10,
                verify=False,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            if response.status_code == 200 and 'TrustPositif' in response.text:
                logger.info(f"✅ Proxy {host}:{port} BEKERJA!")
                working_proxies.append(proxy)
                break  # Cukup satu yang bekerja
                
        except Exception as e:
            logger.debug(f"❌ Proxy {proxy[0]}:{proxy[1]} gagal: {str(e)[:50]}")
            continue
    
    if working_proxies:
        # Update PROXY_LIST dengan yang bekerja
        PROXY_LIST = working_proxies
        return working_proxies[0]
    
    logger.warning("⚠️ Tidak ada proxy yang bekerja dari daftar saat ini")
    return None

def fetch_and_test_proxies():
    """Ambil proxy dari web dan uji sampai dapat yang bekerja"""
    global PROXY_LIST
    
    max_attempts = 5
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        logger.info(f"🔄 Percobaan {attempt}/{max_attempts} mendapatkan proxy...")
        
        # Coba dengan proxy yang sudah ada (jika ada)
        proxy_to_use = None
        if PROXY_LIST:
            # Gunakan proxy acak dari yang sudah ada
            proxy_to_use = random.choice(PROXY_LIST)
            logger.info(f"🔑 Menggunakan proxy existing: {proxy_to_use[0]}:{proxy_to_use[1]}")
        
        # Ambil proxy dari web
        if fetch_proxies_from_web(proxy_to_use):
            logger.info(f"✅ Mendapat {len(PROXY_LIST)} proxy, mencari yang bekerja...")
            
            # Cari proxy yang bekerja
            working_proxy = find_working_proxy()
            if working_proxy:
                logger.info(f"🎯 Proxy bekerja ditemukan: {working_proxy[0]}:{working_proxy[1]}")
                return True
        
        # Jika gagal, tunggu sebentar sebelum mencoba lagi
        if attempt < max_attempts:
            wait_time = 5 * attempt
            logger.info(f"⏳ Menunggu {wait_time} detik sebelum percobaan berikutnya...")
            time.sleep(wait_time)
    
    logger.error("❌ Gagal mendapatkan proxy yang bekerja setelah beberapa percobaan")
    return False

class ProxyManager:
    """Manajer proxy dengan rotasi dan failover"""
    
    def __init__(self):
        self.proxies = []
        self.current_index = 0
        self.failed_proxies = {}
        self.last_refresh = 0
        self.refresh_interval = 3600  # 1 jam
        
        # Inisialisasi - cari proxy sampai dapat
        self._ensure_proxies()
    
    def _ensure_proxies(self):
        """Pastikan ada proxy yang tersedia"""
        if not self.proxies:
            logger.info("🔍 Mencari proxy yang bekerja...")
            if fetch_and_test_proxies():
                self.proxies = PROXY_LIST.copy()
                logger.info(f"✅ {len(self.proxies)} proxy siap digunakan")
            else:
                logger.error("❌ Tidak ada proxy yang tersedia!")
                # Terus mencoba setiap 30 detik
                while not self.proxies:
                    logger.info("🔄 Mencoba lagi dalam 30 detik...")
                    time.sleep(30)
                    if fetch_and_test_proxies():
                        self.proxies = PROXY_LIST.copy()
    
    def refresh_proxies_if_needed(self):
        """Refresh proxy jika sudah waktunya"""
        current_time = time.time()
        if current_time - self.last_refresh > self.refresh_interval:
            logger.info("🔄 Refresh proxy (jadwal)...")
            if fetch_and_test_proxies():
                self.proxies = PROXY_LIST.copy()
                self.failed_proxies.clear()
                logger.info(f"✅ Proxy di-refresh: {len(self.proxies)} proxy")
                self.last_refresh = current_time
            else:
                # Jika gagal refresh, tetap pakai yang lama
                logger.warning("⚠️ Refresh proxy gagal, tetap menggunakan yang ada")
    
    def get_next_proxy(self):
        """Dapatkan proxy berikutnya"""
        # Refresh jika perlu
        self.refresh_proxies_if_needed()
        
        # Pastikan ada proxy
        self._ensure_proxies()
        
        if not self.proxies:
            return None
        
        # Cari proxy yang tidak gagal
        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            
            if proxy in self.failed_proxies:
                if time.time() - self.failed_proxies[proxy] < 60:
                    attempts += 1
                    continue
                else:
                    del self.failed_proxies[proxy]
            
            return proxy
        
        # Jika semua proxy gagal, reset dan refresh
        self.failed_proxies.clear()
        self.proxies = PROXY_LIST.copy()
        return self.proxies[0] if self.proxies else None
    
    def mark_failed(self, proxy):
        """Tandai proxy sebagai gagal"""
        if proxy:
            self.failed_proxies[proxy] = time.time()
            logger.info(f"⚠️ Proxy {proxy[0]}:{proxy[1]} ditandai gagal")
    
    def mark_success(self, proxy):
        """Tandai proxy sebagai berhasil"""
        if proxy and proxy in self.failed_proxies:
            del self.failed_proxies[proxy]

class ProxySession:
    """Session dengan dukungan proxy"""
    
    def __init__(self):
        self.proxy_manager = ProxyManager()
        self.session = requests.Session()
        self.current_proxy = None
        self._setup_session()
    
    def _setup_session(self):
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
        })
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _get_proxy_url(self, proxy):
        if not proxy:
            return None
        host, port, protocol, _ = proxy
        return f"{protocol}://{host}:{port}"
    
    def _get_proxies_dict(self, proxy):
        proxy_url = self._get_proxy_url(proxy)
        if proxy_url:
            return {'http': proxy_url, 'https': proxy_url}
        return {}
    
    def get(self, url, **kwargs):
        return self._request('GET', url, **kwargs)
    
    def post(self, url, **kwargs):
        return self._request('POST', url, **kwargs)
    
    def _request(self, method, url, max_retries=3, **kwargs):
        last_error = None
        
        if 'timeout' not in kwargs:
            kwargs['timeout'] = (15, 30)
        kwargs['verify'] = False
        
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        for attempt in range(max_retries):
            proxy = self.proxy_manager.get_next_proxy()
            if not proxy:
                logger.error("❌ Tidak ada proxy tersedia!")
                time.sleep(5)
                continue
            
            proxies = self._get_proxies_dict(proxy)
            
            try:
                kwargs['proxies'] = proxies
                
                logger.debug(f"🔗 Menggunakan proxy: {proxy[0]}:{proxy[1]} ({proxy[2]})")
                
                if method.upper() == 'GET':
                    response = self.session.get(url, **kwargs)
                else:
                    response = self.session.post(url, **kwargs)
                
                if response.status_code < 400:
                    self.proxy_manager.mark_success(proxy)
                    self.current_proxy = proxy
                    return response
                else:
                    logger.warning(f"⚠️ Proxy {proxy[0]}:{proxy[1]} - HTTP {response.status_code}")
                    self.proxy_manager.mark_failed(proxy)
                    
            except Exception as e:
                error_msg = str(e)[:100]
                logger.warning(f"❌ Error dengan proxy {proxy[0]}:{proxy[1]} - {error_msg}")
                self.proxy_manager.mark_failed(proxy)
                last_error = e
            
            if attempt < max_retries - 1:
                time.sleep(1)
        
        raise Exception(f"Semua proxy gagal. Error terakhir: {last_error}")

class TrustPositifChecker:
    def __init__(self):
        self.proxy_session = ProxySession()
        self.base_url = "https://trustpositif.komdigi.go.id"
        self.csrf_token = "3835f8d38d9c0a271d2d782a70113bc2"
        self.api_url = f"{self.base_url}/Rest_server/getrecordsname_home"
    
    def check_batch_5_domains(self, domains):
        try:
            if len(domains) > 5:
                domains = domains[:5]
            
            domains_text = "\n".join(domains)
            logger.info(f"🔍 Mengecek batch: {', '.join(domains)}")
            
            data = {
                'csrf_token': self.csrf_token,
                'name': domains_text
            }
            
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': f'{self.base_url}/',
                'Origin': self.base_url,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            }
            
            response = self.proxy_session.post(
                self.api_url,
                data=data,
                headers=headers
            )
            
            logger.info(f"📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                return self.parse_api_response(response.text, domains)
            else:
                logger.error(f"❌ HTTP Error {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error checking batch: {e}")
            return []
    
    def parse_api_response(self, response_text, original_domains):
        blocked_domains = []
        
        try:
            try:
                result = json.loads(response_text)
                
                if 'values' in result:
                    domain_status_map = {}
                    
                    for item in result['values']:
                        if isinstance(item, dict):
                            domain = item.get('Domain', '').strip().lower()
                            status = item.get('Status', '').strip()
                            if domain:
                                domain_status_map[domain] = status
                    
                    for domain in original_domains:
                        domain_lower = domain.lower()
                        status = domain_status_map.get(domain_lower, '')
                        
                        if status == 'Tidak Ada':
                            logger.info(f"✅ {domain}: Aman")
                        elif status:
                            blocked_domains.append(f"{domain} ({status})")
                            logger.warning(f"🚫 {domain}: {status}")
                        else:
                            logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
                
                return blocked_domains
                
            except json.JSONDecodeError:
                logger.warning("⚠️ Response bukan JSON, mencoba parse HTML")
                return self.parse_html_response(response_text, original_domains)
                
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return []
    
    def parse_html_response(self, html, domains):
        blocked_domains = []
        
        try:
            html_lower = html.lower()
            
            for domain in domains:
                domain_lower = domain.lower()
                
                if domain_lower in html_lower:
                    if 'tidak ada' in html_lower:
                        logger.info(f"✅ HTML: {domain} aman")
                    else:
                        blocked_domains.append(f"{domain} (terdeteksi)")
                        logger.warning(f"⚠️ HTML: {domain} terdeteksi")
                else:
                    logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
        
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
        
        return blocked_domains
    
    def check_all_domains(self, domains):
        try:
            if not domains:
                return []
            
            all_blocked = []
            batch_size = 5
            batch_count = 0
            
            for i in range(0, len(domains), batch_size):
                batch = domains[i:i + batch_size]
                batch_count += 1
                
                logger.info(f"📦 Batch {batch_count}: {len(batch)} domain")
                
                blocked_batch = self.check_batch_5_domains(batch)
                all_blocked.extend(blocked_batch)
                
                if i + batch_size < len(domains):
                    time.sleep(2)
            
            logger.info(f"📊 Total batch diproses: {batch_count}")
            return all_blocked
            
        except Exception as e:
            logger.error(f"❌ Error checking all domains: {e}")
            return []

def baca_domain():
    try:
        if not os.path.exists("domain.txt"):
            logger.error("❌ File domain.txt tidak ditemukan!")
            with open("domain.txt", "w") as f:
                f.write("# Daftar domain untuk dicek\n")
                f.write("# Satu domain per baris\n")
                f.write("google.com\n")
                f.write("facebook.com\n")
            logger.info("✅ File domain.txt dibuat dengan contoh")
            return []
        
        domains = []
        with open("domain.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    line = line.lower()
                    for prefix in ['http://', 'https://', 'www.']:
                        if line.startswith(prefix):
                            line = line[len(prefix):]
                    line = line.rstrip('/')
                    if '.' in line and len(line) > 3:
                        domains.append(line)
        
        logger.info(f"📖 Membaca {len(domains)} domain dari domain.txt")
        return domains
        
    except Exception as e:
        logger.error(f"❌ Error membaca domain: {e}")
        return []

async def kirim_status():
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        domain_count = len(domains)
        
        message = (
            "🤖 *TrustPositif Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Batch:** 5 domain/request\n"
            f"🌐 **Proxy Pool:** {len(PROXY_LIST)} proxy (auto-update)\n"
            f"🔄 **SSL Verify:** Disabled\n\n"
            "_Bot akan mengecek domain setiap 15 menit_"
        )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("📤 Status bot terkirim")
        
    except Exception as e:
        logger.error(f"❌ Gagal kirim status: {e}")

async def kirim_laporan(blocked_domains, total_domains):
    try:
        blocked_count = len(blocked_domains)
        
        if blocked_count == 0:
            message = (
                "✅ *LAPORAN NAWALA*\n\n"
                "**SEMUA DOMAIN AMAN!** 🎉\n\n"
                f"📊 **Total Domain:** {total_domains}\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "Tidak ada domain yang nawala."
            )
        else:
            domain_list = ""
            for i, domain_info in enumerate(blocked_domains, 1):
                domain_list += f"{i}. 🚫 `{domain_info}`\n"
            
            message = (
                "🚨 *LAPORAN DOMAIN TERBLOKIR*\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
            )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"📤 Laporan terkirim: {blocked_count} domain terblokir")
            
    except Exception as e:
        logger.error(f"❌ Gagal kirim laporan: {e}")

async def cek_domain_job():
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF KOMINFO")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = TrustPositifChecker()
        
        start_time = time.time()
        blocked_domains = checker.check_all_domains(domains)
        elapsed_time = time.time() - start_time
        
        logger.info(f"⏱️ Waktu pemrosesan: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {len(blocked_domains)} dari {len(domains)} domain terblokir")
        
        await kirim_laporan(blocked_domains, len(domains))
        
        logger.info("✅ Pemeriksaan selesai")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error dalam cek_domain_job: {e}")
        import traceback
        logger.error(traceback.format_exc())

def run_async_job(job_func):
    asyncio.create_task(job_func())

async def schedule_runner():
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Schedule runner dihentikan")
            break
        except Exception as e:
            logger.error(f"❌ Error dalam schedule runner: {e}")
            await asyncio.sleep(5)

async def main():
    print("\n" + "=" * 60)
    print("🚀 TRUSTPOSITIF KOMINFO DOMAIN MONITORING BOT")
    print("=" * 60)
    print("🌐 Mencari proxy yang bekerja... (ini mungkin memakan waktu)")
    print("=" * 60)
    
    logger.info("Bot starting...")
    
    # Cari proxy sampai dapat
    proxy_manager = ProxyManager()
    
    # Kirim status awal jika ada proxy
    if proxy_manager.proxies:
        logger.info(f"✅ Bot siap dengan {len(proxy_manager.proxies)} proxy")
        await kirim_status()
    else:
        logger.error("❌ Bot gagal mendapatkan proxy!")
        return
    
    # Setup schedule
    logger.info("Setting up schedule...")
    
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    logger.info("✅ Schedule: Check domains every 15 minutes")
    
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    logger.info("✅ Schedule: Status report every 3 hours")
    
    # Refresh proxy setiap 2 jam
    def refresh_proxy_job():
        logger.info("🔄 Menjadwalkan refresh proxy...")
        fetch_and_test_proxies()
    schedule.every(2).hours.do(refresh_proxy_job)
    logger.info("✅ Schedule: Refresh proxy every 2 hours")
    
    logger.info("Running first check in 5 seconds...")
    await asyncio.sleep(5)
    await cek_domain_job()
    
    logger.info("✅ Bot successfully started!")
    logger.info(f"📍 Proxy pool: {len(PROXY_LIST)} proxies")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Proxy refresh: Every 2 hours")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    await schedule_runner()

if __name__ == "__main__":
    try:
        import schedule
        import requests
        from telegram import __version__
        import bs4
        logger.info(f"✅ Dependencies: requests, schedule, python-telegram-bot v{__version__}, beautifulsoup4")
        
        try:
            import requests.socks
            logger.info("✅ SOCKS support available")
        except ImportError:
            logger.warning("⚠️ SOCKS support not available. Install with: pip install requests[socks]")
            
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install -r requirements.txt")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
