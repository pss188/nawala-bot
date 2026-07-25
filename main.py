import os
import sys
import time
import asyncio
import logging
import schedule
import json
import re
from telegram.ext import Application
from datetime import datetime
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

class TrustPositifChecker:
    def __init__(self):
        self.base_url = "https://trustpositif.id"
        self.checker_url = f"{self.base_url}/checker"
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Origin': self.base_url,
            'Referer': f'{self.checker_url}/',
            'Content-Type': 'application/json',
        }
    
    def check_batch(self, domains):
        try:
            if not domains:
                return []
            if len(domains) > 50:
                domains = domains[:50]
            
            logger.info(f"🔍 Checking {len(domains)} domains...")
            
            response = self.session.post(
                f"{self.checker_url}/check",
                json={'domains': domains},
                headers=self.headers,
                timeout=30,
                verify=False
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return self._parse_results(data.get('results', []))
            return []
        except Exception as e:
            logger.error(f"Error: {e}")
            return []
    
    def _parse_results(self, results):
        blocked = []
        for result in results:
            domain = result.get('Domain', '') or result.get('domain', '')
            is_blocked = result.get('Blocked', False) or result.get('blocked', False)
            if domain and is_blocked:
                blocked.append(domain)
                logger.warning(f"🚫 {domain}: DIBLOKIR")
            elif domain:
                logger.info(f"✅ {domain}: AMAN")
        return blocked
    
    def check_all_domains(self, domains):
        try:
            if not domains:
                return []
            all_blocked = []
            batch_size = 50
            for i in range(0, len(domains), batch_size):
                batch = domains[i:i + batch_size]
                blocked_batch = self.check_batch(batch)
                all_blocked.extend(blocked_batch)
                if i + batch_size < len(domains):
                    time.sleep(5)
            return all_blocked
        except Exception as e:
            logger.error(f"Error: {e}")
            return []

def baca_domain():
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

async def kirim_status():
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        domains = baca_domain()
        message = (
            "🤖 *TrustPositif Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {len(domains)} domain terdaftar\n"
            f"🔢 **Mode:** Batch (max 50 domain/request)\n"
            f"🌐 **Sumber:** trustpositif.id/checker\n\n"
            "_Bot akan mengecek domain setiap 15 menit_"
        )
        await application.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
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
            await application.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
        else:
            domain_list = ""
            for i, domain in enumerate(blocked_domains, 1):
                domain_list += f"{i}. 🚫 `{domain}`\n"
            message = (
                f"❌❌❌❌❌❌❌❌❌\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: trustpositif.id/checker_"
            )
            if len(message) > 4096:
                chunks = [blocked_domains[i:i+20] for i in range(0, len(blocked_domains), 20)]
                for i, chunk in enumerate(chunks, 1):
                    msg = f"🚨 Bagian {i}/{len(chunks)}\n\n"
                    for j, d in enumerate(chunk, 1):
                        msg += f"{j}. 🚫 `{d}`\n"
                    await application.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
            else:
                await application.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Gagal kirim laporan: {e}")

async def cek_domain_job():
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.ID")
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
        logger.error(f"Error: {e}")
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
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            await asyncio.sleep(5)

async def main():
    print("\n" + "=" * 60)
    print("🚀 TRUSTPOSITIF.ID CHECKER BOT")
    print("=" * 60)
    logger.info("Bot starting...")
    await kirim_status()
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    await asyncio.sleep(5)
    await cek_domain_job()
    logger.info("✅ Bot started!")
    await schedule_runner()

if __name__ == "__main__":
    try:
        import schedule
        import requests
        from telegram import __version__
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        sys.exit(1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
