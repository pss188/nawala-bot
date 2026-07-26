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
# Proxy dengan autentikasi
PROXY_IPS = [
    "193.5.64.205",
    "193.5.64.160", 
    "193.5.64.163",
    "193.5.64.183",
    "193.5.64.101"
]

PROXY_USERNAME = "pulsaslot18880CWCH"
PROXY_PASSWORD = "b7qufiNuAD"
PROXY_PORT_HTTP = "50100"
PROXY_PORT_SOCKS5 = "50101"

# Buat daftar proxy dari IP yang diberikan
def build_proxy_list():
    proxies = []
    for ip in PROXY_IPS:
        # HTTP/HTTPS proxy
        proxies.append((ip, int(PROXY_PORT_HTTP), "http", "transparent"))
        # SOCKS5 proxy
        proxies.append((ip, int(PROXY_PORT_SOCKS5), "socks5", "transparent"))
    return proxies

# Proxy dengan autentikasi untuk digunakan di requests
def get_proxy_url(host, port, protocol):
    """Buat URL proxy dengan autentikasi"""
    if protocol == "http":
        return f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{host}:{port}"
    elif protocol == "socks5":
        return f"socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{host}:{port}"
    else:
        return f"{protocol}://{PROXY_USERNAME}:{PROXY_PASSWORD}@{host}:{port}"

# Global proxy list
PROXY_LIST = build_proxy_list()

def fetch_proxies_from_proxy5(proxy_to_use=None):
    """Ambil daftar proxy dari proxy5.net menggunakan proxy yang diberikan"""
    global PROXY_LIST
    
    try:
        logger.info("🌐 Mengambil daftar proxy dari proxy5.net...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Gunakan proxy yang diberikan
        proxies = None
        if proxy_to_use:
            host, port, protocol, _ = proxy_to_use
            proxy_url = get_proxy_url(host, port, protocol)
            proxies = {'http': proxy_url, 'https': proxy_url}
            logger.info(f"🔗 Menggunakan proxy: {host}:{port} ({protocol})")
        
        response = requests.get(
            "https://proxy5.net/free-proxy/indonesia",
            headers=headers,
            proxies=proxies,
            timeout=20,
            verify=False
        )
        
        if response.status_code != 200:
            logger.warning(f"⚠️ Gagal mengambil proxy: HTTP {response.status_code}")
            return False
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cari tabel proxy
        table = soup.find('table', {'id': 'proxylister-table'})
        if not table:
            tables = soup.find_all('table')
            for t in tables:
                if 'IP Address' in str(t) or 'Port' in str(t):
                    table = t
                    break
        
        if not table:
            logger.warning("⚠️ Tabel proxy tidak ditemukan")
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
        
        for row in rows[1:]:
            cols = row.find_all('td')
            if len(cols) >= 3:
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
                            mapped = protocol_map.get(proto)
                            if mapped and mapped not in protocols:
                                protocols.append(mapped)
                    
                    if not protocols:
                        protocols = ['http']
                    
                    for proto in protocols:
                        proxy_tuple = (ip_text, port, proto, 'transparent')
                        if proxy_tuple not in new_proxies:
                            new_proxies.append(proxy_tuple)
                            
                except (ValueError, IndexError, AttributeError):
                    continue
        
        if new_proxies:
            # Tambahkan proxy baru ke daftar yang sudah ada
            existing_ips = set([p[0] for p in PROXY_LIST])
            for p in new_proxies:
                if p[0] not in existing_ips:
                    PROXY_LIST.append(p)
            
            logger.info(f"✅ Berhasil menambahkan {len(new_proxies)} proxy dari proxy5.net")
            logger.info(f"📊 Total proxy: {len(PROXY_LIST)}")
            
            # Simpan ke cache
            try:
                with open('proxy_cache.json', 'w') as f:
                    json.dump(PROXY_LIST, f)
            except:
                pass
            
            return True
        else:
            logger.warning("⚠️ Tidak ada proxy yang valid ditemukan")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error mengambil proxy: {e}")
        return False

def load_proxy_cache():
    """Muat proxy dari cache"""
    global PROXY_LIST
    
    try:
        if os.path.exists('proxy_cache.json'):
            with open('proxy_cache.json', 'r') as f:
                cached_proxies = json.load(f)
                if cached_proxies and len(cached_proxies) > 0:
                    # Gabungkan dengan proxy yang sudah ada
                    existing_ips = set([p[0] for p in PROXY_LIST])
                    for p in cached_proxies:
                        if p[0] not in existing_ips:
                            PROXY_LIST.append(p)
                    logger.info(f"📂 Memuat {len(cached_proxies)} proxy dari cache")
                    return True
    except Exception as e:
        logger.warning(f"⚠️ Gagal memuat cache: {e}")
    
    return False

def init_proxies():
    """Inisialisasi daftar proxy"""
    global PROXY_LIST
    
    # Proxy dengan autentikasi sudah ada di PROXY_LIST
    logger.info(f"✅ Proxy dengan autentikasi: {len(PROXY_LIST)} proxy")
    
    # Coba ambil tambahan dari proxy5.net
    if PROXY_LIST:
        # Gunakan proxy pertama yang ada
        proxy_to_use = PROXY_LIST[0]
        fetch_proxies_from_proxy5(proxy_to_use)
    
    # Jika masih kurang dari 5 proxy, coba dari cache
    if len(PROXY_LIST) < 5:
        load_proxy_cache()
    
    logger.info(f"📊 Total proxy: {len(PROXY_LIST)}")
    return True

def test_proxy(proxy):
    """Test apakah proxy bekerja"""
    try:
        host, port, protocol, _ = proxy
        proxy_url = get_proxy_url(host, port, protocol)
        proxies = {'http': proxy_url, 'https': proxy_url}
        
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
            return True
    except Exception as e:
        logger.debug(f"Test proxy {proxy[0]}:{proxy[1]} gagal: {str(e)[:50]}")
    return False

class ProxyManager:
    """Manajer proxy dengan rotasi dan failover"""
    
    def __init__(self):
        self.proxies = PROXY_LIST.copy()
        self.working_proxies = []
        self.current_index = 0
        self.failed_proxies = {}
        self.last_refresh = 0
        self.refresh_interval = 1800  # 30 menit
        
        # Inisialisasi
        self._ensure_working_proxies()
    
    def _get_proxy_url_with_auth(self, proxy):
        """Dapatkan URL proxy dengan autentikasi"""
        if not proxy:
            return None
        host, port, protocol, _ = proxy
        return get_proxy_url(host, port, protocol)
    
    def _ensure_working_proxies(self):
        """Pastikan ada proxy yang bekerja"""
        if not self.working_proxies:
            logger.info("🔍 Mencari proxy yang bekerja...")
            # Test semua proxy
            for proxy in self.proxies[:20]:  # Test maksimal 20 proxy
                if test_proxy(proxy):
                    self.working_proxies.append(proxy)
                    logger.info(f"✅ Proxy {proxy[0]}:{proxy[1]} ({proxy[2]}) BEKERJA!")
                    # Jika sudah dapat 3, berhenti
                    if len(self.working_proxies) >= 3:
                        break
                time.sleep(0.5)
            
            if not self.working_proxies:
                # Jika tidak ada yang bekerja, gunakan semua proxy
                self.working_proxies = self.proxies[:5]
                logger.warning(f"⚠️ Tidak ada proxy yang lolos test, menggunakan {len(self.working_proxies)} proxy")
    
    def refresh_proxies_if_needed(self):
        """Refresh proxy jika sudah waktunya"""
        current_time = time.time()
        if current_time - self.last_refresh > self.refresh_interval:
            logger.info("🔄 Refresh proxy...")
            
            # Ambil proxy baru dari proxy5.net
            if self.proxies:
                proxy_to_use = self.proxies[0]
                if fetch_proxies_from_proxy5(proxy_to_use):
                    self.proxies = PROXY_LIST.copy()
                    # Cari yang bekerja
                    self.working_proxies = []
                    for proxy in self.proxies[:10]:
                        if test_proxy(proxy):
                            self.working_proxies.append(proxy)
                            if len(self.working_proxies) >= 3:
                                break
                    if self.working_proxies:
                        logger.info(f"✅ Refresh berhasil: {len(self.working_proxies)} proxy")
                        self.last_refresh = current_time
    
    def get_next_proxy(self):
        """Dapatkan proxy berikutnya"""
        self.refresh_proxies_if_needed()
        
        if not self.working_proxies:
            self._ensure_working_proxies()
        
        if not self.working_proxies:
            # Fallback ke proxy dengan autentikasi
            self.working_proxies = PROXY_LIST[:5]
        
        # Cari proxy yang tidak gagal
        attempts = 0
        while attempts < len(self.working_proxies):
            proxy = self.working_proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.working_proxies)
            
            if proxy in self.failed_proxies:
                if time.time() - self.failed_proxies[proxy] < 60:
                    attempts += 1
                    continue
                else:
                    del self.failed_proxies[proxy]
            
            return proxy
        
        # Jika semua gagal, reset
        self.failed_proxies.clear()
        self._ensure_working_proxies()
        return self.working_proxies[0] if self.working_proxies else PROXY_LIST[0]
    
    def mark_failed(self, proxy):
        """Tandai proxy sebagai gagal"""
        if proxy:
            self.failed_proxies[proxy] = time.time()
            logger.info(f"⚠️ Proxy {proxy[0]}:{proxy[1]} ditandai gagal")
            if proxy in self.working_proxies:
                self.working_proxies.remove(proxy)
    
    def mark_success(self, proxy):
        """Tandai proxy sebagai berhasil"""
        if proxy and proxy in self.failed_proxies:
            del self.failed_proxies[proxy]

class ProxySession:
    """Session dengan dukungan proxy dan autentikasi"""
    
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
    
    def _get_proxies_dict(self, proxy):
        """Dapatkan dictionary proxies dengan autentikasi"""
        if not proxy:
            return {}
        host, port, protocol, _ = proxy
        proxy_url = get_proxy_url(host, port, protocol)
        return {'http': proxy_url, 'https': proxy_url}
    
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
                            logger.error(f"❌ Batch {batch_count} gagal: {e}")
                
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
        
        # Hitung jumlah proxy
        total_proxy = len(PROXY_LIST)
        working_count = len(ProxyManager().working_proxies) if hasattr(ProxyManager(), 'working_proxies') else 0
        
        message = (
            "🤖 *TrustPositif Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Batch:** 5 domain/request\n"
            f"🌐 **Proxy Pool:** {total_proxy} proxy\n"
            f"🔑 **Auth Proxy:** {len(PROXY_IPS)} IP dengan autentikasi\n"
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
    print(f"🔑 Proxy Auth: {PROXY_USERNAME}")
    print(f"🌐 Proxy IPs: {', '.join(PROXY_IPS)}")
    print(f"📡 HTTP/HTTPS Port: {PROXY_PORT_HTTP}")
    print(f"📡 SOCKS5 Port: {PROXY_PORT_SOCKS5}")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info(f"🔑 Proxy dengan autentikasi: {len(PROXY_IPS)} IP")
    
    # Inisialisasi proxy
    init_proxies()
    logger.info(f"✅ {len(PROXY_LIST)} proxy tersedia")
    
    # Kirim status awal
    await kirim_status()
    
    # Setup schedule
    logger.info("Setting up schedule...")
    
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    logger.info("✅ Schedule: Check domains every 15 minutes")
    
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    logger.info("✅ Schedule: Status report every 3 hours")
    
    # Refresh proxy setiap 30 menit
    def refresh_proxy_job():
        logger.info("🔄 Refresh proxy...")
        if PROXY_LIST:
            proxy_to_use = PROXY_LIST[0]
            fetch_proxies_from_proxy5(proxy_to_use)
    schedule.every(30).minutes.do(refresh_proxy_job)
    logger.info("✅ Schedule: Refresh proxy every 30 minutes")
    
    logger.info("Running first check in 5 seconds...")
    await asyncio.sleep(5)
    await cek_domain_job()
    
    logger.info("✅ Bot successfully started!")
    logger.info(f"📍 Proxy pool: {len(PROXY_LIST)} proxies")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Proxy refresh: Every 30 minutes")
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
