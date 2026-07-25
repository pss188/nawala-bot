import os
import sys
import time
import asyncio
import logging
import schedule
import re
from telegram.ext import Application
from datetime import datetime
import requests
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

class TrustPositifScraper:
    def __init__(self):
        self.base_url = "https://trustpositif.id"
        self.checker_url = f"{self.base_url}/checker"
        self.session = requests.Session()
        
        # Headers lengkap seperti browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Origin': self.base_url,
            'Referer': f'{self.checker_url}/',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
        }
        
        # CSRF Token dari halaman
        self.csrf_token = "ukvxzVGQTWSBl5G4JnZgTFVeEuj08r49LYISmaP8"
    
    def check_batch(self, domains):
        """Cek domain via scraping HTML (metode yang sudah terbukti)"""
        try:
            if not domains:
                return []
            
            if len(domains) > 100:
                domains = domains[:100]
            
            logger.info(f"🔍 Checking {len(domains)} domains via scraping...")
            
            # Kirim POST request dengan form data (bukan JSON)
            domains_text = "\n".join(domains)
            
            response = self.session.post(
                self.checker_url,
                data={
                    'domains': domains_text,
                    '_token': self.csrf_token,
                },
                headers={
                    **self.headers,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=30,
                verify=False,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                return self._parse_html_results(response.text, domains)
            else:
                logger.error(f"HTTP {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error: {e}")
            return []
    
    def _parse_html_results(self, html, domains):
        """Parse HTML untuk mencari domain yang diblokir"""
        blocked_domains = []
        html_lower = html.lower()
        
        try:
            # Cari pattern domain dengan status di HTML
            # Pattern: <td>domain</td><td><span class="...">Diblokir</span></td>
            # atau pattern lainnya dari hasil scraping
            
            # Method 1: Cari per domain di HTML
            for domain in domains:
                domain_lower = domain.lower()
                
                # Cari domain di HTML
                if domain_lower not in html_lower:
                    logger.info(f"✅ {domain}: AMAN (tidak ditemukan di HTML)")
                    continue
                
                # Ambil konteks di sekitar domain
                domain_index = html_lower.find(domain_lower)
                start = max(0, domain_index - 300)
                end = min(len(html_lower), domain_index + 300)
                context = html_lower[start:end]
                
                # Cek indikasi blokir
                blocked_indicators = [
                    'diblokir',
                    'terblokir',
                    'blocked',
                    'nawala',
                    'bg-red',
                    'text-red',
                    'border-red',
                    'class="checker-badge--blocked"',
                    'class="checker-row--blocked"',
                    'data-status="blocked"',
                    '>Diblokir<',
                    '>BLOCKED<',
                ]
                
                is_blocked = False
                for indicator in blocked_indicators:
                    if indicator in context:
                        is_blocked = True
                        break
                
                # Cek juga di seluruh HTML (jika tidak ditemukan di konteks)
                if not is_blocked:
                    for indicator in blocked_indicators:
                        if indicator in html_lower:
                            # Cek apakah domain dekat dengan indicator
                            idx_indicator = html_lower.find(indicator)
                            if idx_indicator != -1:
                                # Cek jarak antara domain dan indicator
                                distance = abs(domain_index - idx_indicator)
                                if distance < 500:  # Dalam jarak 500 karakter
                                    is_blocked = True
                                    break
                
                if is_blocked:
                    blocked_domains.append(domain)
                    logger.warning(f"🚫 {domain}: DIBLOKIR")
                else:
                    logger.info(f"✅ {domain}: AMAN")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return []
    
    def check_via_api(self, domain):
        """Fallback: cek via API per domain"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/check?domain={domain}",
                headers=self.headers,
                timeout=10,
                verify=False
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('blocked') or data.get('Blocked'):
                    return True
            return False
        except:
            return False
    
    def check_all_domains(self, domains):
        """Cek semua domain dengan batch"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            
            # Coba metode scraping batch
            logger.info("📌 Mencoba metode scraping HTML...")
            blocked_batch = self.check_batch(domains)
            all_blocked.extend(blocked_batch)
            
            # Jika tidak ada yang terdeteksi, coba per domain
            if len(all_blocked) == 0:
                logger.info("📌 Tidak ada yang terdeteksi via batch, coba per domain...")
                for domain in domains:
                    logger.info(f"🔍 Checking: {domain}")
                    is_blocked = self.check_via_api(domain)
                    if is_blocked:
                        all_blocked.append(domain)
                        logger.warning(f"🚫 {domain}: DIBLOKIR (API)")
                    else:
                        logger.info(f"✅ {domain}: AMAN (API)")
                    time.sleep(1)
            
            return all_blocked
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return []

def baca_domain():
    """Baca domain dari file domain.txt"""
    try:
        if not os.path.exists("domain.txt"):
            logger.error("❌ File domain.txt tidak ditemukan!")
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
        logger.error(f"Error membaca domain: {e}")
        return []

# ============================================
# FUNGSI TELEGRAM
# ============================================

async def kirim_status():
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        domain_count = len(domains)
        
        message = (
            "🤖 *TrustPositif Scraper Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** HTML Scraping + API Fallback\n"
            f"🌐 **Sumber:** trustpositif.id/checker\n\n"
            "_Bot akan mengecek domain setiap 15 menit_"
        )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("📤 Status bot terkirim")
        
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

async def kirim_laporan(blocked_domains, total_domains):
    try:
        blocked_count = len(blocked_domains)
        
        if blocked_count == 0:
            message = (
                "✅ *LAPORAN CEK NAWALA*\n\n"
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
                "_Sumber: trustpositif.id/checker (Scraping)_"
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
        logger.error(f"Gagal kirim laporan: {e}")

async def kirim_pesan_terbagi(blocked_domains, total_domains):
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
                    "_Sumber: trustpositif.id/checker (Scraping)_"
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
        logger.error(f"Gagal kirim pesan terbagi: {e}")

async def cek_domain_job():
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.ID")
        logger.info("📌 Mode: HTML Scraping + API Fallback")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = TrustPositifScraper()
        
        start_time = time.time()
        blocked_domains = checker.check_all_domains(domains)
        elapsed_time = time.time() - start_time
        
        logger.info(f"⏱️ Waktu pemrosesan: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {len(blocked_domains)} dari {len(domains)} domain terblokir")
        
        await kirim_laporan(blocked_domains, len(domains))
        
        logger.info("✅ Pemeriksaan selesai")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error dalam cek_domain_job: {e}")
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
            logger.error(f"Error dalam schedule runner: {e}")
            await asyncio.sleep(5)

async def main():
    print("\n" + "=" * 60)
    print("🚀 TRUSTPOSITIF.ID SCRAPER BOT")
    print("📌 Mode: HTML Scraping + API Fallback")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: trustpositif.id/checker (Scraping)")
    
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
    logger.info("📍 Mode: HTML Scraping + API Fallback")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    await schedule_runner()

if __name__ == "__main__":
    try:
        import schedule
        import requests
        from telegram import __version__
        logger.info(f"✅ Dependencies: requests, schedule, python-telegram-bot v{__version__}")
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
