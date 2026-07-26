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
# Default proxy list (akan ditimpa oleh fetch_proxies_from_web jika berhasil)
DEFAULT_PROXY_LIST = [
    ("43.218.124.29", 8090, "http", "transparent"),
    ("34.50.105.1", 80, "http", "transparent"),
    ("114.4.168.140", 80, "http", "transparent"),
]

# Global proxy list yang akan diisi dari web
PROXY_LIST = []

def fetch_proxies_from_web():
    """Ambil daftar proxy dari proxy5.net"""
    global PROXY_LIST
    
    try:
        logger.info("🌐 Mengambil daftar proxy dari proxy5.net...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(
            "https://proxy5.net/free-proxy/indonesia",
            headers=headers,
            timeout=15
        )
        
        if response.status_code != 200:
            logger.warning(f"⚠️ Gagal mengambil proxy: HTTP {response.status_code}")
            return False
        
        # Parse HTML dengan BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cari tabel proxy
        table = soup.find('table')
        if not table:
            logger.warning("⚠️ Tabel proxy tidak ditemukan di halaman")
            return False
        
        # Parse baris tabel
        rows = table.find_all('tr')
        new_proxies = []
        protocol_map = {
            'HTTP': 'http',
            'HTTPS': 'http',
            'SOCKS4': 'socks4',
            'SOCKS5': 'socks5'
        }
        
        for row in rows[1:]:  # Skip header
            cols = row.find_all('td')
            if len(cols) >= 5:
                try:
                    # Ekstrak data
                    ip_text = cols[0].get_text(strip=True)
                    port_text = cols[1].get_text(strip=True)
                    protocol_text = cols[2].get_text(strip=True).upper()
                    anonymity_text = cols[3].get_text(strip=True).lower()
                    
                    # Validasi IP dan port
                    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_text):
                        continue
                    
                    port = int(port_text)
                    if port < 1 or port > 65535:
                        continue
                    
                    # Parse protocols
                    protocols = []
                    for proto in ['HTTP', 'HTTPS', 'SOCKS4', 'SOCKS5']:
                        if proto in protocol_text:
                            protocols.append(protocol_map.get(proto, proto.lower()))
                    
                    if not protocols:
                        protocols = ['http']  # Default ke http
                    
                    # Tambahkan ke daftar
                    for proto in protocols:
                        # Filter proxy yang terlalu lambat (latency > 1000ms) bisa diabaikan
                        # Tapi kita tetap ambil semua
                        new_proxies.append((ip_text, port, proto, anonymity_text))
                        
                except (ValueError, IndexError) as e:
                    continue
        
        if new_proxies:
            # Hapus duplikat
            unique_proxies = list(set(new_proxies))
            PROXY_LIST = unique_proxies
            logger.info(f"✅ Berhasil mengambil {len(PROXY_LIST)} proxy dari proxy5.net")
            
            # Simpan ke file untuk cache
            try:
                with open('proxy_cache.json', 'w') as f:
                    json.dump(PROXY_LIST, f)
                logger.info("💾 Proxy disimpan ke cache")
            except:
                pass
            
            return True
        else:
            logger.warning("⚠️ Tidak ada proxy yang valid ditemukan")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error mengambil proxy dari web: {e}")
        return False

def load_proxy_cache():
    """Muat proxy dari cache jika gagal mengambil dari web"""
    global PROXY_LIST
    
    try:
        if os.path.exists('proxy_cache.json'):
            with open('proxy_cache.json', 'r') as f:
                cached_proxies = json.load(f)
                if cached_proxies:
                    PROXY_LIST = cached_proxies
                    logger.info(f"📂 Memuat {len(PROXY_LIST)} proxy dari cache")
                    return True
    except Exception as e:
        logger.warning(f"⚠️ Gagal memuat cache: {e}")
    
    return False

def init_proxies():
    """Inisialisasi daftar proxy"""
    global PROXY_LIST
    
    # Coba ambil dari web
    if fetch_proxies_from_web():
        return True
    
    # Jika gagal, coba dari cache
    if load_proxy_cache():
        return True
    
    # Jika semua gagal, pakai default
    PROXY_LIST = DEFAULT_PROXY_LIST.copy()
    logger.warning(f"⚠️ Menggunakan {len(PROXY_LIST)} proxy default")
    return False

class ProxyManager:
    """Manajer proxy dengan rotasi dan failover"""
    
    def __init__(self):
        self.proxies = PROXY_LIST.copy()
        self.current_index = 0
        self.failed_proxies = {}
        self.max_failures = 2
        self.reset_time = 120
        self.last_reset = time.time()
        self.working_proxy = None
        self.proxy_stats = {}
        
    def refresh_proxies(self):
        """Refresh daftar proxy dari web"""
        logger.info("🔄 Refresh daftar proxy...")
        if fetch_proxies_from_web():
            self.proxies = PROXY_LIST.copy()
            self.failed_proxies.clear()
            logger.info(f"✅ Proxy di-refresh: {len(self.proxies)} proxy")
            return True
        return False
        
    def get_next_proxy(self):
        """Dapatkan proxy berikutnya dengan rotasi round-robin"""
        self._reset_failed_if_needed()
        
        # Jika daftar proxy kosong, refresh
        if not self.proxies:
            self.refresh_proxies()
            if not self.proxies:
                self.proxies = DEFAULT_PROXY_LIST.copy()
        
        attempts = 0
        while attempts < len(self.proxies):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            
            if proxy in self.failed_proxies:
                if time.time() - self.failed_proxies[proxy] < 30:
                    attempts += 1
                    continue
                else:
                    del self.failed_proxies[proxy]
            
            return proxy
        
        self.failed_proxies.clear()
        return self.proxies[0] if self.proxies else DEFAULT_PROXY_LIST[0]
    
    def _reset_failed_if_needed(self):
        if time.time() - self.last_reset > self.reset_time:
            self.failed_proxies.clear()
            self.last_reset = time.time()
            logger.info("🔄 Reset daftar proxy gagal")
    
    def mark_failed(self, proxy, error=None):
        self.failed_proxies[proxy] = time.time()
        error_type = str(error)[:50] if error else "unknown"
        logger.warning(f"⚠️ Proxy {proxy[0]}:{proxy[1]} ({proxy[2]}) gagal: {error_type}")
        
        if self.working_proxy == proxy:
            self.working_proxy = None
    
    def mark_success(self, proxy):
        if proxy in self.failed_proxies:
            del self.failed_proxies[proxy]
        self.working_proxy = proxy
        
        if proxy not in self.proxy_stats:
            self.proxy_stats[proxy] = {'success': 0, 'fail': 0}
        self.proxy_stats[proxy]['success'] += 1

class ProxySession:
    """Session dengan dukungan proxy dan SSL handling"""
    
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
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })
        
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _get_proxy_url(self, proxy):
        host, port, protocol, _ = proxy
        if protocol == "http":
            return f"http://{host}:{port}"
        elif protocol.startswith("socks"):
            return f"{protocol}://{host}:{port}"
        else:
            return f"http://{host}:{port}"
    
    def _get_proxies_dict(self, proxy):
        proxy_url = self._get_proxy_url(proxy)
        return {'http': proxy_url, 'https': proxy_url}
    
    def get(self, url, **kwargs):
        return self._request('GET', url, **kwargs)
    
    def post(self, url, **kwargs):
        return self._request('POST', url, **kwargs)
    
    def _request(self, method, url, max_retries=2, **kwargs):
        last_error = None
        
        if 'timeout' not in kwargs:
            kwargs['timeout'] = (10, 30)
        kwargs['verify'] = False
        
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        for attempt in range(max_retries):
            proxy = self.proxy_manager.get_next_proxy()
            proxies = self._get_proxies_dict(proxy)
            
            try:
                kwargs['proxies'] = proxies
                
                logger.debug(f"🔗 Menggunakan proxy: {proxy[0]}:{proxy[1]} ({proxy[2]}) - Attempt {attempt + 1}")
                
                if method.upper() == 'GET':
                    response = self.session.get(url, **kwargs)
                else:
                    response = self.session.post(url, **kwargs)
                
                if response.status_code < 400:
                    self.proxy_manager.mark_success(proxy)
                    self.current_proxy = proxy
                    return response
                else:
                    try:
                        error_preview = response.text[:100]
                        logger.warning(f"⚠️ Proxy {proxy[0]}:{proxy[1]} - HTTP {response.status_code}: {error_preview}")
                    except:
                        logger.warning(f"⚠️ Proxy {proxy[0]}:{proxy[1]} - HTTP {response.status_code}")
                    
                    self.proxy_manager.mark_failed(proxy, f"HTTP {response.status_code}")
                    
                    if response.status_code in [400, 502, 503, 504]:
                        logger.info(f"⏭️ Skip proxy {proxy[0]}:{proxy[1]} - HTTP {response.status_code}")
                        continue
                    
            except requests.exceptions.ProxyError as e:
                error_msg = str(e)[:100]
                logger.warning(f"❌ Proxy error dengan {proxy[0]}:{proxy[1]} - {error_msg}")
                self.proxy_manager.mark_failed(proxy, "ProxyError")
                last_error = e
                
            except requests.exceptions.SSLError as e:
                logger.warning(f"🔒 SSL error dengan {proxy[0]}:{proxy[1]} - {str(e)[:100]}")
                self.proxy_manager.mark_failed(proxy, "SSLError")
                last_error = e
                
            except requests.exceptions.Timeout:
                logger.warning(f"⏱️ Timeout dengan proxy {proxy[0]}:{proxy[1]}")
                self.proxy_manager.mark_failed(proxy, "Timeout")
                last_error = "Timeout"
                
            except requests.exceptions.ConnectionError as e:
                error_msg = str(e)[:100]
                logger.warning(f"🔌 Connection error dengan {proxy[0]}:{proxy[1]} - {error_msg}")
                self.proxy_manager.mark_failed(proxy, "ConnectionError")
                last_error = e
                
            except Exception as e:
                error_msg = str(e)[:100]
                logger.warning(f"❌ Error dengan proxy {proxy[0]}:{proxy[1]} - {error_msg}")
                self.proxy_manager.mark_failed(proxy, "UnknownError")
                last_error = e
            
            if attempt < max_retries - 1:
                time.sleep(1)
        
        # Fallback tanpa proxy
        try:
            logger.info("🔄 Mencoba tanpa proxy (fallback)...")
            kwargs.pop('proxies', None)
            if method.upper() == 'GET':
                response = self.session.get(url, **kwargs)
            else:
                response = self.session.post(url, **kwargs)
            
            if response.status_code < 400:
                logger.info("✅ Berhasil tanpa proxy")
                return response
        except Exception as e:
            logger.warning(f"⚠️ Fallback tanpa proxy juga gagal: {str(e)[:100]}")
        
        raise Exception(f"Semua proxy gagal setelah {max_retries} percobaan. Error terakhir: {last_error}")

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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
                    domain_index = html_lower.find(domain_lower)
                    start = max(0, domain_index - 100)
                    end = min(len(html_lower), domain_index + 150)
                    context = html_lower[start:end]
                    
                    if 'tidak ada' in context:
                        logger.info(f"✅ HTML: {domain} aman")
                    else:
                        if f'<td>{domain_lower}</td>' in html_lower:
                            import re
                            pattern = f'<td>{domain_lower}</td>.*?<td>(.*?)</td>'
                            match = re.search(pattern, html_lower, re.DOTALL)
                            if match:
                                status = match.group(1).strip()
                                if status != 'tidak ada':
                                    blocked_domains.append(f"{domain} ({status})")
                                    logger.warning(f"🚫 HTML: {domain} -> {status}")
                                else:
                                    logger.info(f"✅ HTML: {domain} aman")
                        else:
                            blocked_domains.append(f"{domain} (terdeteksi)")
                            logger.warning(f"⚠️ HTML: {domain} terdeteksi tapi status tidak jelas")
                else:
                    logger.info(f"✅ {domain}: Tidak ditemukan dalam response (asumsi aman)")
        
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
                
                max_retries = 2
                for retry in range(max_retries):
                    try:
                        blocked_batch = self.check_batch_5_domains(batch)
                        all_blocked.extend(blocked_batch)
                        break
                    except Exception as e:
                        if retry < max_retries - 1:
                            logger.warning(f"⚠️ Batch {batch_count} gagal, retry {retry + 2}/{max_retries}...")
                            time.sleep(2)
                        else:
                            logger.error(f"❌ Batch {batch_count} gagal setelah {max_retries} percobaan: {e}")
                
                if i + batch_size < len(domains):
                    delay = 2
                    logger.info(f"⏳ Menunggu {delay} detik sebelum batch berikutnya...")
                    time.sleep(delay)
            
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
            f"🌐 **Proxy Pool:** {len(PROXY_LIST)} proxy (auto-update dari proxy5.net)\n"
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
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"📤 Laporan aman: {total_domains} domain")
            
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
            
            if len(message) > 4096:
                await kirim_pesan_terbagi(blocked_domains, total_domains)
            else:
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"📤 Laporan terblokir: {blocked_count} domain")
            
    except Exception as e:
        logger.error(f"❌ Gagal kirim laporan: {e}")

async def kirim_pesan_terbagi(blocked_domains, total_domains):
    try:
        blocked_count = len(blocked_domains)
        chunk_size = 20
        chunks = [blocked_domains[i:i + chunk_size] for i in range(0, len(blocked_domains), chunk_size)]
        
        for i, chunk in enumerate(chunks, 1):
            domain_list = ""
            for j, domain_info in enumerate(chunk, 1):
                domain_list += f"{(i-1)*chunk_size + j}. 🚫 `{domain_info}`\n"
            
            message = (
                f"🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {i}/{len(chunks)})*\n\n"
                f"{domain_list}\n"
            )
            
            if i == len(chunks):
                message += (
                    f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                    f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                    "_Sumber: trustpositif.komdigi.go.id_"
                )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            
            if i < len(chunks):
                await asyncio.sleep(1)
        
        logger.info(f"📤 Laporan terbagi: {blocked_count} domain dalam {len(chunks)} pesan")
        
    except Exception as e:
        logger.error(f"❌ Gagal kirim pesan terbagi: {e}")

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

async def test_koneksi():
    try:
        logger.info("🔗 Testing koneksi ke trustpositif.komdigi.go.id dengan proxy...")
        
        proxy_session = ProxySession()
        
        response = proxy_session.get(
            "https://trustpositif.komdigi.go.id/",
            timeout=10
        )
        
        if response.status_code == 200:
            if 'TrustPositif' in response.text:
                logger.info("✅ Koneksi BERHASIL - TrustPositif terdeteksi")
                return True
            else:
                logger.warning("⚠️ Koneksi OK tapi halaman tidak sesuai")
                return False
        else:
            logger.warning(f"⚠️ HTTP Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test koneksi GAGAL: {e}")
        return False

async def main():
    print("\n" + "=" * 60)
    print("🚀 TRUSTPOSITIF KOMINFO DOMAIN MONITORING BOT")
    print("=" * 60)
    
    # Inisialisasi proxy
    print("🌐 Menginisialisasi daftar proxy...")
    if init_proxies():
        print(f"✅ {len(PROXY_LIST)} proxy siap digunakan")
    else:
        print("⚠️ Menggunakan proxy default")
    
    print(f"🔒 SSL Verification: Disabled")
    print("=" * 60)
    
    logger.info("Bot starting...")
    
    # Test koneksi
    logger.info("Testing connection with proxy rotation...")
    if not await test_koneksi():
        logger.warning("⚠️ Koneksi bermasalah, bot tetap berjalan...")
    else:
        logger.info("✅ Koneksi OK")
    
    await kirim_status()
    
    logger.info("Setting up schedule...")
    
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    logger.info("✅ Schedule: Check domains every 15 minutes")
    
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    logger.info("✅ Schedule: Status report every 3 hours")
    
    # Refresh proxy setiap 6 jam
    def refresh_proxy_job():
        logger.info("🔄 Menjadwalkan refresh proxy...")
        fetch_proxies_from_web()
    schedule.every(6).hours.do(refresh_proxy_job)
    logger.info("✅ Schedule: Refresh proxy every 6 hours")
    
    logger.info("Running first check in 5 seconds...")
    await asyncio.sleep(5)
    await cek_domain_job()
    
    logger.info("✅ Bot successfully started!")
    logger.info(f"📍 Proxy pool: {len(PROXY_LIST)} proxies (auto-update from proxy5.net)")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Proxy refresh: Every 6 hours")
    logger.info("📍 Batch size: 5 domains per request")
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
