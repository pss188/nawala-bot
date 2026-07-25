import os
import sys
import time
import requests
import asyncio
import logging
import schedule
import json
import re
from telegram.ext import Application
from datetime import datetime
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup logging dengan lebih detail
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Set ke DEBUG untuk melihat lebih detail
)
logger = logging.getLogger(__name__)

# Config
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# Bot setup
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

class TrustPositifChecker:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://trustpositif.infonawala.com"
        
        # Headers lengkap seperti browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
        }
        
        # Ambil CSRF token dan form data dari halaman
        self.csrf_token = None
        self.form_data = {}
        self._fetch_page_data()
    
    def _fetch_page_data(self):
        """Ambil data dari halaman (CSRF token, dll)"""
        try:
            logger.info("🔄 Mengambil data dari halaman...")
            response = self.session.get(
                self.base_url,
                headers=self.headers,
                timeout=20,
                verify=False
            )
            
            if response.status_code == 200:
                html = response.text
                
                # Cari CSRF token di HTML
                csrf_patterns = [
                    r'csrfToken["\']?\s*[:=]\s*["\']([^"\']+)',
                    r'<input[^>]*name=["\']csrfToken["\'][^>]*value=["\']([^"\']+)',
                    r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)',
                    r'_csrf["\']?\s*[:=]\s*["\']([^"\']+)',
                    r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)',
                ]
                
                for pattern in csrf_patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        self.csrf_token = match.group(1)
                        logger.info(f"✅ CSRF token ditemukan: {self.csrf_token[:20]}...")
                        break
                
                # Cari form action
                form_action = re.search(r'<form[^>]*action=["\']([^"\']+)["\']', html, re.IGNORECASE)
                if form_action:
                    self.form_action = form_action.group(1)
                    logger.info(f"✅ Form action: {self.form_action}")
                else:
                    self.form_action = self.base_url
                
                # Cari input hidden lainnya
                hidden_inputs = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']+)["\']', html, re.IGNORECASE)
                for name, value in hidden_inputs:
                    self.form_data[name] = value
                    logger.debug(f"Hidden input: {name} = {value[:20]}...")
                
                logger.info(f"✅ Data halaman berhasil diambil")
                return True
            else:
                logger.warning(f"⚠️ Gagal mengambil halaman: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error fetching page: {e}")
            return False
    
    def check_single_domain(self, domain):
        """Cek 1 domain secara individual dengan debug"""
        try:
            logger.info(f"🔍 Checking domain: {domain}")
            
            # Refresh data halaman setiap kali (untuk token terbaru)
            self._fetch_page_data()
            
            # Coba berbagai pendekatan
            approaches = [
                self._check_via_form_submit,
                self._check_via_api_json,
                self._check_via_api_form,
                self._check_via_get,
            ]
            
            for approach in approaches:
                try:
                    result = approach(domain)
                    if result is not None:
                        return result
                except Exception as e:
                    logger.debug(f"Pendekatan {approach.__name__} gagal: {e}")
                    continue
            
            logger.warning(f"⚠️ Semua pendekatan gagal untuk {domain}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error checking domain {domain}: {e}")
            return None
    
    def _check_via_form_submit(self, domain):
        """Coba submit form seperti di browser"""
        try:
            # Data form yang mungkin
            form_data = {
                'domain': domain,
                'domains': domain,
                'url': domain,
                'q': domain,
                'check': domain,
            }
            
            # Tambahkan CSRF token jika ada
            if self.csrf_token:
                form_data['csrfToken'] = self.csrf_token
                form_data['_csrf'] = self.csrf_token
                form_data['csrf_token'] = self.csrf_token
            
            # Tambahkan hidden inputs dari halaman
            form_data.update(self.form_data)
            
            logger.debug(f"Form data: {form_data}")
            
            # Submit ke form action
            response = self.session.post(
                self.form_action,
                data=form_data,
                headers={
                    **self.headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=20,
                verify=False,
                allow_redirects=True
            )
            
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response URL: {response.url}")
            
            if response.status_code in [200, 302, 303]:
                # Coba parse response
                return self._parse_response(response, domain)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Form submit error: {e}")
            return None
    
    def _check_via_api_json(self, domain):
        """Coba dengan JSON ke API endpoint"""
        try:
            # Endpoint API yang mungkin
            api_endpoints = [
                f"{self.base_url}/api/check",
                f"{self.base_url}/api/domains",
                f"{self.base_url}/api/nawala",
                f"{self.base_url}/api/trustpositif",
                f"{self.base_url}/api/scan",
                f"{self.base_url}/api/cek",
            ]
            
            payloads = [
                {'domain': domain},
                {'domains': [domain]},
                {'url': domain},
                {'q': domain},
                {'query': domain},
                {'data': domain},
                {'text': domain},
            ]
            
            for endpoint in api_endpoints:
                for payload in payloads:
                    try:
                        # Tambahkan token jika ada
                        if self.csrf_token:
                            payload['csrfToken'] = self.csrf_token
                            payload['_csrf'] = self.csrf_token
                        
                        response = self.session.post(
                            endpoint,
                            json=payload,
                            headers={
                                **self.headers,
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                            timeout=20,
                            verify=False
                        )
                        
                        logger.debug(f"API JSON response status: {response.status_code}")
                        
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                logger.debug(f"API JSON response: {json.dumps(data, indent=2)[:500]}")
                                return self._parse_json_response(data, domain)
                            except:
                                # Jika bukan JSON, coba parse HTML
                                return self._parse_html_response(response.text, domain)
                                
                    except Exception as e:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ API JSON error: {e}")
            return None
    
    def _check_via_api_form(self, domain):
        """Coba dengan form data ke API endpoint"""
        try:
            api_endpoints = [
                f"{self.base_url}/api/check",
                f"{self.base_url}/api/domains",
            ]
            
            form_data = {
                'domain': domain,
                'domains': domain,
                'url': domain,
            }
            
            if self.csrf_token:
                form_data['csrfToken'] = self.csrf_token
            
            for endpoint in api_endpoints:
                try:
                    response = self.session.post(
                        endpoint,
                        data=form_data,
                        headers={
                            **self.headers,
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        timeout=20,
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            return self._parse_json_response(data, domain)
                        except:
                            return self._parse_html_response(response.text, domain)
                            
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ API Form error: {e}")
            return None
    
    def _check_via_get(self, domain):
        """Coba dengan GET request"""
        try:
            params_list = [
                {'domain': domain},
                {'q': domain},
                {'url': domain},
                {'check': domain},
                {'cek': domain},
            ]
            
            for params in params_list:
                try:
                    response = self.session.get(
                        self.base_url,
                        params=params,
                        headers=self.headers,
                        timeout=20,
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        return self._parse_html_response(response.text, domain)
                        
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ GET error: {e}")
            return None
    
    def _parse_response(self, response, domain):
        """Parse response dari berbagai format"""
        try:
            content_type = response.headers.get('Content-Type', '')
            
            if 'application/json' in content_type:
                try:
                    data = response.json()
                    return self._parse_json_response(data, domain)
                except:
                    pass
            
            # Coba parse HTML
            return self._parse_html_response(response.text, domain)
            
        except Exception as e:
            logger.error(f"❌ Parse response error: {e}")
            return None
    
    def _parse_json_response(self, data, domain):
        """Parse JSON response dengan lebih detail"""
        try:
            logger.debug(f"Parsing JSON untuk {domain}")
            domain_lower = domain.lower()
            
            # Cek apakah domain ada di response
            json_str = json.dumps(data).lower()
            if domain_lower not in json_str:
                logger.info(f"✅ {domain}: Tidak ditemukan di response (asumsi aman)")
                return False
            
            # Cari status domain
            if isinstance(data, dict):
                # Cek berbagai struktur response yang mungkin
                structures = [
                    ['data', 'domains'],
                    ['result', 'domains'],
                    ['results', 'domains'],
                    ['domains'],
                    ['data'],
                    ['result'],
                    ['results'],
                    ['status'],
                    ['blocked'],
                ]
                
                for path in structures:
                    current = data
                    for key in path:
                        if key in current:
                            current = current[key]
                        else:
                            current = None
                            break
                    
                    if current is not None:
                        if isinstance(current, list):
                            for item in current:
                                if isinstance(item, dict):
                                    item_domain = str(item.get('domain', '')).lower()
                                    if item_domain == domain_lower or domain_lower in item_domain:
                                        status = str(item.get('status', '')).lower()
                                        blocked = item.get('blocked', False)
                                        is_blocked = item.get('is_blocked', False)
                                        
                                        logger.debug(f"Domain ditemukan: {item_domain}, status: {status}, blocked: {blocked}")
                                        
                                        if blocked or is_blocked or status in ['blocked', 'terblokir', 'true', '1']:
                                            return True
                                        elif status in ['clean', 'ok', 'allowed', 'aman', 'false', '0', 'tidak ada']:
                                            return False
                                        
                        elif isinstance(current, dict):
                            for d, value in current.items():
                                if d.lower() == domain_lower or domain_lower in d.lower():
                                    if isinstance(value, dict):
                                        status = str(value.get('status', '')).lower()
                                        blocked = value.get('blocked', False)
                                        if blocked or status in ['blocked', 'terblokir']:
                                            return True
                                    elif str(value).lower() in ['blocked', 'terblokir', 'true', '1']:
                                        return True
                                    elif str(value).lower() in ['clean', 'ok', 'allowed', 'false', '0']:
                                        return False
            
            # Cek di JSON string dengan konteks
            domain_index = json_str.find(domain_lower)
            if domain_index != -1:
                start = max(0, domain_index - 200)
                end = min(len(json_str), domain_index + 200)
                context = json_str[start:end]
                
                logger.debug(f"Context: {context}")
                
                if 'blocked' in context or 'terblokir' in context:
                    if 'allowed' in context or 'aman' in context or 'clean' in context:
                        # Ada keduanya, cek yang mana lebih dekat dengan domain
                        blocked_pos = context.find('blocked')
                        allowed_pos = context.find('allowed')
                        if blocked_pos != -1 and (allowed_pos == -1 or blocked_pos < allowed_pos):
                            return True
                        return False
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ JSON parse error: {e}")
            return None
    
    def _parse_html_response(self, html, domain):
        """Parse HTML response dengan lebih detail"""
        try:
            html_lower = html.lower()
            domain_lower = domain.lower()
            
            # Cari domain dalam HTML
            if domain_lower not in html_lower:
                logger.info(f"✅ {domain}: Tidak ditemukan di HTML (asumsi aman)")
                return False
            
            # Cari konteks
            domain_index = html_lower.find(domain_lower)
            start = max(0, domain_index - 500)
            end = min(len(html_lower), domain_index + 500)
            context = html_lower[start:end]
            
            logger.debug(f"HTML Context: {context[:200]}...")
            
            # Indikasi terblokir
            blocked_patterns = [
                r'terblokir',
                r'diblokir',
                r'blocked',
                r'class=["\'][^"\']*(blocked|block|red|danger|error)[^"\']*["\']',
                r'data-status=["\'](blocked|terblokir)["\']',
                r'bg-red',
                r'text-red',
                r'border-red',
                r'status.*?(blocked|terblokir)',
                r'<td[^>]*>.*?(blocked|terblokir).*?</td>',
                r'<span[^>]*>.*?(blocked|terblokir).*?</span>',
                r'<div[^>]*>.*?(blocked|terblokir).*?</div>',
            ]
            
            # Indikasi aman
            safe_patterns = [
                r'aman',
                r'safe',
                r'allowed',
                r'tidak ada',
                r'tidak ditemukan',
                r'class=["\'][^"\']*(success|green|safe|allowed)[^"\']*["\']',
                r'data-status=["\'](clean|ok|allowed|aman)["\']',
                r'bg-green',
                r'text-green',
                r'border-green',
                r'status.*?(clean|ok|allowed|aman)',
            ]
            
            # Cek blokir di konteks
            for pattern in blocked_patterns:
                if re.search(pattern, context, re.IGNORECASE):
                    logger.warning(f"🚫 {domain}: Terdeteksi terblokir")
                    return True
            
            # Cek aman di konteks
            for pattern in safe_patterns:
                if re.search(pattern, context, re.IGNORECASE):
                    logger.info(f"✅ {domain}: Terdeteksi aman")
                    return False
            
            # Default: aman
            logger.info(f"✅ {domain}: Tidak terdeteksi blokir (asumsi aman)")
            return False
            
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
            return None
    
    def check_all_domains(self, domains):
        """Cek semua domain satu per satu dengan debug"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            total = len(domains)
            
            for i, domain in enumerate(domains, 1):
                logger.info(f"📌 [{i}/{total}] Memeriksa: {domain}")
                logger.info("-" * 40)
                
                # Cek domain
                is_blocked = self.check_single_domain(domain)
                
                if is_blocked is True:
                    all_blocked.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                elif is_blocked is False:
                    logger.info(f"✅ {domain}: AMAN")
                else:
                    logger.warning(f"⚠️ {domain}: TIDAK DIKETAHUI - coba lagi")
                    time.sleep(3)
                    is_blocked = self.check_single_domain(domain)
                    if is_blocked is True:
                        all_blocked.append(domain)
                        logger.warning(f"🚫 {domain}: TERBLOKIR (setelah retry)")
                    else:
                        logger.info(f"✅ {domain}: AMAN (setelah retry)")
                
                logger.info("-" * 40)
                
                # Delay antar domain
                if i < total:
                    delay = 3
                    logger.info(f"⏳ Menunggu {delay} detik...")
                    time.sleep(delay)
            
            return all_blocked
            
        except Exception as e:
            logger.error(f"❌ Error checking all domains: {e}")
            return []

def baca_domain():
    """Baca domain dari file domain.txt"""
    try:
        if not os.path.exists("domain.txt"):
            logger.error("❌ File domain.txt tidak ditemukan!")
            with open("domain.txt", "w") as f:
                f.write("# Daftar domain untuk dicek\n")
                f.write("# Satu domain per baris\n")
                f.write("google.com\n")
                f.write("facebook.com\n")
                f.write("twitter.com\n")
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

# ============================================
# FUNGSI TELEGRAM
# ============================================

async def kirim_status():
    """Kirim status bot"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        domain_count = len(domains)
        
        message = (
            "🤖 *TrustPositif Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** 1 domain/request (debug mode)\n"
            f"🌐 **Sumber:** trustpositif.infonawala.com\n\n"
            "_Bot akan mengecek domain satu per satu setiap 15 menit_"
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
    """Kirim laporan hasil pengecekan"""
    try:
        blocked_count = len(blocked_domains)
        
        if blocked_count == 0:
            message = (
                "✅ *LAPORAN CEK TRUSTPOSITIF*\n\n"
                "**SEMUA DOMAIN AMAN!** 🎉\n\n"
                f"📊 **Total Domain:** {total_domains}\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "Tidak ada domain yang terblokir."
            )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"📤 Laporan aman: {total_domains} domain")
            
        else:
            domain_list = ""
            for i, domain in enumerate(blocked_domains, 1):
                domain_list += f"{i}. 🚫 `{domain}`\n"
            
            message = (
                "❌❌❌❌❌❌❌❌❌\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: trustpositif.infonawala.com_"
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
    """Kirim pesan terbagi jika terlalu panjang"""
    try:
        blocked_count = len(blocked_domains)
        chunk_size = 20
        chunks = [blocked_domains[i:i + chunk_size] for i in range(0, len(blocked_domains), chunk_size)]
        
        for i, chunk in enumerate(chunks, 1):
            domain_list = ""
            for j, domain in enumerate(chunk, 1):
                domain_list += f"{(i-1)*chunk_size + j}. 🚫 `{domain}`\n"
            
            message = (
                f"🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {i}/{len(chunks)})*\n\n"
                f"{domain_list}\n"
            )
            
            if i == len(chunks):
                message += (
                    f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                    f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                    "_Sumber: trustpositif.infonawala.com_"
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
    """Job untuk mengecek domain satu per satu"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.INFONAWALA.COM")
        logger.info("🔄 Mode: 1 domain per request (DEBUG)")
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
    """Wrapper untuk menjalankan async job dari schedule"""
    asyncio.create_task(job_func())

async def schedule_runner():
    """Menjalankan schedule dalam loop asyncio"""
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
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 TRUSTPOSITIF.INFONAWALA.COM DOMAIN MONITORING BOT")
    print("📌 Mode: 1 domain per request (DEBUG)")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: trustpositif.infonawala.com")
    logger.info("📌 Mode: 1 domain per request (debug mode)")
    
    await kirim_status()
    
    logger.info("Setting up schedule...")
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    logger.info("✅ Schedule: Check domains every 15 minutes")
    
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    logger.info("✅ Schedule: Status report every 3 hours")
    
    logger.info("Running first check in 5 seconds...")
    await asyncio.sleep(5)
    await cek_domain_job()
    
    logger.info("✅ Bot successfully started!")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Mode: 1 domain per request")
    logger.info("📍 Delay antar domain: 3 detik")
    logger.info("📍 Source: trustpositif.infonawala.com")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    await schedule_runner()

if __name__ == "__main__":
    try:
        import schedule
        import requests
        from telegram import __version__
        logger.info(f"✅ Dependencies: requests, schedule, python-telegram-bot v{__version__}")
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
