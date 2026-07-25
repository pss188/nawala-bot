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
        
        # Headers lengkap seperti browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
        }
    
    def check_single_domain(self, domain):
        """Cek 1 domain secara individual dengan submit form"""
        try:
            logger.info(f"🔍 Checking domain: {domain}")
            
            # Kirim POST request dengan form data
            form_data = {
                'domain': domain,
                'domains': domain,
            }
            
            response = self.session.post(
                self.base_url,
                data=form_data,
                headers={
                    **self.headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=30,
                verify=False,
                allow_redirects=True
            )
            
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response URL: {response.url}")
            
            if response.status_code == 200:
                return self._parse_result(response.text, domain)
            else:
                logger.warning(f"⚠️ Response status: {response.status_code}")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error checking domain {domain}: {e}")
            return None
    
    def _parse_result(self, html, domain):
        """Parse hasil dari HTML response"""
        try:
            # Cari status di HTML
            patterns = [
                # Pattern untuk status Nawala
                r'Status Nawala:\s*<span[^>]*>(.*?)</span>',
                r'Status Nawala[^<]*</h3>\s*<p[^>]*>(.*?)</p>',
                r'<div[^>]*class="[^"]*red[^"]*"[^>]*>.*?NAWALA.*?</div>',
                r'<span[^>]*class="[^"]*text-red[^"]*"[^>]*>(.*?)</span>',
                # Pattern untuk status di card
                r'<h3[^>]*class="[^"]*font-semibold[^"]*"[^>]*>.*?Status Nawala[^:]*:\s*<span[^>]*>(.*?)</span>',
                r'<p[^>]*class="[^"]*text-xs[^"]*"[^>]*>.*?(terblokir|diblokir|NAWALA|blocked).*?</p>',
                # Pattern untuk div hasil
                r'<div[^>]*class="[^"]*border-red[^"]*"[^>]*>.*?(NAWALA|terblokir|diblokir|blocked).*?</div>',
                r'<div[^>]*class="[^"]*bg-red[^"]*"[^>]*>.*?(NAWALA|terblokir|diblokir|blocked).*?</div>',
            ]
            
            html_lower = html.lower()
            domain_lower = domain.lower()
            
            # Cek apakah domain ada di response
            if domain_lower not in html_lower:
                logger.info(f"✅ {domain}: Domain tidak ditemukan di response (asumsi aman)")
                return False
            
            # Cari status
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                if match:
                    status_text = match.group(1).strip().lower() if match.groups() else match.group(0).strip().lower()
                    logger.debug(f"Status pattern found: {status_text}")
                    
                    # Cek indikasi terblokir
                    if 'nawala' in status_text or 'terblokir' in status_text or 'diblokir' in status_text or 'blocked' in status_text:
                        logger.warning(f"🚫 {domain}: TERBLOKIR (NAWALA)")
                        return True
                    elif 'aman' in status_text or 'safe' in status_text or 'allowed' in status_text:
                        logger.info(f"✅ {domain}: AMAN")
                        return False
            
            # Cek langsung di HTML untuk kata kunci
            # Cari div dengan status
            status_div_pattern = r'<div[^>]*class="[^"]*(?:red|danger|error)[^"]*"[^>]*>(.*?)</div>'
            matches = re.findall(status_div_pattern, html, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                if domain_lower in match.lower():
                    if 'nawala' in match.lower() or 'terblokir' in match.lower() or 'diblokir' in match.lower():
                        logger.warning(f"🚫 {domain}: TERBLOKIR (NAWALA)")
                        return True
            
            # Cek apakah ada teks "NAWALA" di dekat domain
            domain_index = html_lower.find(domain_lower)
            if domain_index != -1:
                start = max(0, domain_index - 500)
                end = min(len(html_lower), domain_index + 500)
                context = html_lower[start:end]
                
                if 'nawala' in context or 'terblokir' in context or 'diblokir' in context:
                    logger.warning(f"🚫 {domain}: TERBLOKIR (NAWALA terdeteksi di konteks)")
                    return True
                elif 'aman' in context or 'safe' in context:
                    logger.info(f"✅ {domain}: AMAN")
                    return False
            
            # Default: aman
            logger.info(f"✅ {domain}: Tidak terdeteksi blokir (asumsi aman)")
            return False
            
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return None
    
    def check_all_domains(self, domains):
        """Cek semua domain satu per satu"""
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
                    time.sleep(2)
                    is_blocked = self.check_single_domain(domain)
                    if is_blocked is True:
                        all_blocked.append(domain)
                        logger.warning(f"🚫 {domain}: TERBLOKIR (setelah retry)")
                    else:
                        logger.info(f"✅ {domain}: AMAN (setelah retry)")
                
                logger.info("-" * 40)
                
                # Delay antar domain
                if i < total:
                    delay = 2
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
            f"🔢 **Mode:** 1 domain/request\n"
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
        logger.info("🔄 Mode: 1 domain per request")
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
    print("📌 Mode: 1 domain per request")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: trustpositif.infonawala.com")
    logger.info("📌 Mode: 1 domain per request")
    
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
    logger.info("📍 Delay antar domain: 2 detik")
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
