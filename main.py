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
        
        # Headers untuk meniru browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
        }
    
    def check_batch_5_domains(self, domains):
        """Cek domain menggunakan trustpositif.infonawala.com"""
        try:
            if len(domains) > 5:
                domains = domains[:5]
            
            logger.info(f"🔍 Checking batch: {', '.join(domains)}")
            
            # Format domains: satu per baris atau dipisahkan koma
            domains_text_comma = ", ".join(domains)
            domains_text_newline = "\n".join(domains)
            
            # Coba berbagai pendekatan
            
            # Pendekatan 1: POST dengan form data ke root
            result = self._check_via_form(domains, domains_text_comma)
            if result is not None:
                return result
            
            # Pendekatan 2: POST dengan JSON
            result = self._check_via_json(domains)
            if result is not None:
                return result
            
            # Pendekatan 3: GET dengan query parameter
            result = self._check_via_get(domains)
            if result is not None:
                return result
            
            logger.error("❌ Semua pendekatan gagal")
            return []
            
        except Exception as e:
            logger.error(f"❌ Error checking batch: {e}")
            return []
    
    def _check_via_form(self, domains, domains_text):
        """Coba dengan form data"""
        try:
            # Payload yang umum digunakan untuk form
            payloads = [
                {'domain': domains_text},
                {'domains': domains_text},
                {'domain[]': domains},
                {'domains[]': domains},
                {'url': domains_text},
                {'urls': domains_text},
                {'check': domains_text},
                {'query': domains_text},
                {'q': domains_text},
                {'action': 'check', 'domain': domains_text},
            ]
            
            for payload in payloads:
                try:
                    response = self.session.post(
                        self.base_url,
                        data=payload,
                        headers={
                            **self.headers,
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        timeout=20,
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        result = self._parse_html_response(response.text, domains)
                        if result:
                            logger.info(f"✅ Form success with payload: {payload}")
                            return result
                            
                except Exception as e:
                    continue
            
            # Coba ke endpoint /check
            for payload in payloads:
                try:
                    response = self.session.post(
                        f"{self.base_url}/check",
                        data=payload,
                        headers={
                            **self.headers,
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        timeout=20,
                        verify=False
                    )
                    
                    if response.status_code == 200:
                        result = self._parse_html_response(response.text, domains)
                        if result:
                            logger.info(f"✅ /check success with payload: {payload}")
                            return result
                            
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Form check error: {e}")
            return None
    
    def _check_via_json(self, domains):
        """Coba dengan JSON payload"""
        try:
            payloads = [
                {'domains': domains},
                {'domain': domains[0] if domains else ''},
                {'urls': domains},
                {'list': domains},
                {'items': domains},
                {'data': domains},
            ]
            
            endpoints = [
                self.base_url,
                f"{self.base_url}/api",
                f"{self.base_url}/api/check",
                f"{self.base_url}/check",
                f"{self.base_url}/scan",
            ]
            
            for endpoint in endpoints:
                for payload in payloads:
                    try:
                        response = self.session.post(
                            endpoint,
                            json=payload,
                            headers={
                                **self.headers,
                                'Content-Type': 'application/json',
                                'Accept': 'application/json',
                            },
                            timeout=20,
                            verify=False
                        )
                        
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                result = self._parse_json_response(data, domains)
                                if result:
                                    logger.info(f"✅ JSON success: {endpoint}")
                                    return result
                            except:
                                # Jika bukan JSON, coba parse HTML
                                result = self._parse_html_response(response.text, domains)
                                if result:
                                    logger.info(f"✅ JSON endpoint returned HTML: {endpoint}")
                                    return result
                                    
                    except Exception as e:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ JSON check error: {e}")
            return None
    
    def _check_via_get(self, domains):
        """Coba dengan GET request"""
        try:
            for domain in domains:
                params_list = [
                    {'domain': domain},
                    {'q': domain},
                    {'url': domain},
                    {'check': domain},
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
                            result = self._parse_html_response(response.text, [domain])
                            if result:
                                logger.info(f"✅ GET success with params: {params}")
                                return result
                                
                    except Exception as e:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ GET check error: {e}")
            return None
    
    def _parse_html_response(self, html, domains):
        """Parse HTML response untuk mencari status blokir"""
        blocked_domains = []
        
        try:
            html_lower = html.lower()
            
            # Pola-pola yang menunjukkan domain terblokir
            blocked_patterns = [
                r'terblokir',
                r'diblokir',
                r'blocked',
                r'nawala',
                r'positif',
                r'terindikasi',
                r'berbahaya',
                r'ilegal',
                r'pornografi',
                r'perjudian',
                r'status["\']?\s*[:=]\s*["\']?(blocked|terblokir)',
                r'<span[^>]*class=["\'].*?blocked.*?["\'][^>]*>',
                r'<td[^>]*>.*?(blocked|terblokir).*?</td>',
            ]
            
            # Pola-pola yang menunjukkan domain aman
            allowed_patterns = [
                r'aman',
                r'safe',
                r'allowed',
                r'tidak ada',
                r'tidak ditemukan',
                r'status["\']?\s*[:=]\s*["\']?(clean|ok|allowed)',
            ]
            
            for domain in domains:
                domain_lower = domain.lower()
                domain_escaped = re.escape(domain_lower)
                
                # Cari domain dalam HTML
                domain_patterns = [
                    rf'{domain_escaped}',
                    rf'<td[^>]*>{domain_escaped}</td>',
                    rf'<span[^>]*>{domain_escaped}</span>',
                    rf'<div[^>]*>{domain_escaped}</div>',
                    rf'"{domain_escaped}"',
                    rf"'{domain_escaped}'",
                ]
                
                found = False
                is_blocked = False
                
                for pattern in domain_patterns:
                    match = re.search(pattern, html_lower, re.IGNORECASE)
                    if match:
                        found = True
                        # Ambil konteks di sekitar domain
                        start = max(0, match.start() - 200)
                        end = min(len(html_lower), match.end() + 200)
                        context = html_lower[start:end]
                        
                        # Cek apakah ada indikasi blokir
                        for blocked_pattern in blocked_patterns:
                            if re.search(blocked_pattern, context, re.IGNORECASE):
                                is_blocked = True
                                break
                        
                        # Jika tidak ada indikasi blokir, cek apakah ada indikasi aman
                        if not is_blocked:
                            for allowed_pattern in allowed_patterns:
                                if re.search(allowed_pattern, context, re.IGNORECASE):
                                    is_blocked = False
                                    break
                        
                        break
                
                if found and is_blocked:
                    blocked_domains.append(f"{domain} (terdeteksi terblokir)")
                    logger.warning(f"🚫 {domain}: Terdeteksi terblokir")
                elif found:
                    logger.info(f"✅ {domain}: Ditemukan tapi tidak terblokir (asumsi aman)")
                else:
                    logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
            return []
    
    def _parse_json_response(self, data, domains):
        """Parse JSON response"""
        blocked_domains = []
        
        try:
            if isinstance(data, dict):
                # Cari di berbagai field
                fields_to_check = ['data', 'result', 'results', 'domains', 'status', 'blocked', 'list', 'items']
                
                for field in fields_to_check:
                    if field in data:
                        if isinstance(data[field], list):
                            for item in data[field]:
                                if isinstance(item, dict):
                                    domain = self._extract_domain(item)
                                    status = str(item.get('status', '')).lower()
                                    blocked = item.get('blocked', False) or item.get('is_blocked', False)
                                    
                                    if domain and (blocked or status in ['blocked', 'terblokir']):
                                        blocked_domains.append(f"{domain} (terblokir)")
                                        logger.warning(f"🚫 {domain}: Terblokir")
                                        
                        elif isinstance(data[field], dict):
                            for domain, status in data[field].items():
                                if str(status).lower() in ['blocked', 'terblokir', 'true', '1']:
                                    blocked_domains.append(f"{domain} (terblokir)")
                                    logger.warning(f"🚫 {domain}: Terblokir")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ JSON parse error: {e}")
            return []
    
    def _extract_domain(self, item):
        """Extract domain dari berbagai format"""
        for key in ['domain', 'name', 'url', 'host', 'target', 'item']:
            if key in item:
                return str(item[key]).strip().lower()
        return ''
    
    def check_all_domains(self, domains):
        """Cek semua domain dengan batch 5"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            batch_size = 5
            
            for i in range(0, len(domains), batch_size):
                batch = domains[i:i + batch_size]
                blocked_batch = self.check_batch_5_domains(batch)
                all_blocked.extend(blocked_batch)
                
                if i + batch_size < len(domains):
                    logger.info("⏳ Menunggu 3 detik sebelum batch berikutnya...")
                    time.sleep(3)
            
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
            f"🔢 **Batch:** 5 domain/request\n"
            f"🌐 **Sumber:** trustpositif.infonawala.com\n\n"
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
            for i, domain_info in enumerate(blocked_domains, 1):
                domain_list += f"{i}. 🚫 `{domain_info}`\n"
            
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
    """Job untuk mengecek domain"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.INFONAWALA.COM")
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
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: trustpositif.infonawala.com")
    
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
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Batch size: 5 domains per request")
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
