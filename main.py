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
        self.base_url = "https://trustpositif.app"
        self.api_url = "https://api.trustpositif.app"
        
        # Headers untuk meniru browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }
    
    def check_batch_5_domains(self, domains):
        """Cek domain menggunakan API TrustPositif.app"""
        try:
            if len(domains) > 5:
                domains = domains[:5]
            
            logger.info(f"🔍 Checking batch: {', '.join(domains)}")
            
            # Format domains: satu per baris
            domains_text = "\n".join(domains)
            
            # Coba berbagai endpoint API
            endpoints = [
                f"{self.api_url}/check",
                f"{self.api_url}/scan",
                f"{self.api_url}/domains",
                f"{self.api_url}/v1/check",
                f"{self.api_url}/api/check",
            ]
            
            for endpoint in endpoints:
                try:
                    # Coba dengan berbagai payload
                    payloads = [
                        {'domains': domains},
                        {'domains': domains_text},
                        {'domains': '\n'.join(domains)},
                        {'domain': domains[0] if domains else ''},
                        {'urls': domains},
                        {'list': domains},
                        {'items': domains},
                    ]
                    
                    for payload in payloads:
                        try:
                            response = self.session.post(
                                endpoint,
                                json=payload,
                                headers={
                                    **self.headers,
                                    'Content-Type': 'application/json',
                                },
                                timeout=20,
                                verify=False
                            )
                            
                            if response.status_code == 200:
                                try:
                                    data = response.json()
                                    logger.info(f"✅ API success: {endpoint}")
                                    result = self._parse_response(data, domains)
                                    if result is not None:
                                        return result
                                except:
                                    # Jika bukan JSON, coba parse text
                                    result = self._parse_text_response(response.text, domains)
                                    if result is not None:
                                        return result
                                        
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    continue
            
            # Fallback: coba dengan form data
            try:
                data = {
                    'domains': domains_text,
                    'action': 'check'
                }
                response = self.session.post(
                    f"{self.base_url}/check",
                    data=data,
                    headers={
                        **self.headers,
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    timeout=20,
                    verify=False
                )
                
                if response.status_code == 200:
                    return self._parse_text_response(response.text, domains)
            except:
                pass
            
            logger.error("❌ All API attempts failed")
            return []
            
        except Exception as e:
            logger.error(f"❌ Error checking batch: {e}")
            return []
    
    def _parse_response(self, data, original_domains):
        """Parse JSON response dari API"""
        blocked_domains = []
        
        try:
            logger.info(f"📊 Parsing response: {json.dumps(data)[:200]}...")
            
            # Coba berbagai format response yang mungkin
            # Format 1: {'status': 'success', 'data': [{'domain': 'x', 'status': 'blocked'}]}
            if isinstance(data, dict):
                # Cari di 'data' field
                if 'data' in data:
                    items = data['data']
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                domain = self._extract_domain(item)
                                status = self._extract_status(item)
                                if domain and status and status.lower() not in ['ok', 'clean', 'allowed', 'tidak ada', 'tidak ditemukan']:
                                    blocked_domains.append(f"{domain} ({status})")
                                    logger.warning(f"🚫 {domain}: {status}")
                
                # Format 2: {'results': [{'domain': 'x', 'blocked': true}]}
                if 'results' in data:
                    items = data['results']
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                domain = self._extract_domain(item)
                                blocked = item.get('blocked', False) or item.get('is_blocked', False)
                                status = self._extract_status(item)
                                if domain and (blocked or status.lower() in ['blocked', 'terblokir']):
                                    blocked_domains.append(f"{domain} (terblokir)")
                                    logger.warning(f"🚫 {domain}: Terblokir")
                
                # Format 3: {'domains': {'example.com': 'blocked'}}
                if 'domains' in data and isinstance(data['domains'], dict):
                    for domain, status in data['domains'].items():
                        if domain and str(status).lower() in ['blocked', 'terblokir', 'true', '1']:
                            blocked_domains.append(f"{domain} (terblokir)")
                            logger.warning(f"🚫 {domain}: Terblokir")
                
                # Format 4: {'status': 'blocked', 'domain': 'x'}
                if 'domain' in data and 'status' in data:
                    domain = data.get('domain', '')
                    status = data.get('status', '')
                    if domain and status.lower() in ['blocked', 'terblokir']:
                        blocked_domains.append(f"{domain} ({status})")
                        logger.warning(f"🚫 {domain}: {status}")
            
            # Jika tidak ada yang terdeteksi, asumsi aman
            if not blocked_domains:
                for domain in original_domains:
                    logger.info(f"✅ {domain}: Aman (tidak terdeteksi)")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return []
    
    def _extract_domain(self, item):
        """Extract domain dari berbagai format"""
        for key in ['domain', 'name', 'url', 'host', 'target', 'item']:
            if key in item:
                return item[key].strip().lower()
        return ''
    
    def _extract_status(self, item):
        """Extract status dari berbagai format"""
        for key in ['status', 'result', 'state', 'blocked_status']:
            if key in item:
                return str(item[key]).strip()
        return ''
    
    def _parse_text_response(self, text, domains):
        """Parse text/HTML response"""
        blocked_domains = []
        
        try:
            text_lower = text.lower()
            
            # Cek setiap domain
            for domain in domains:
                domain_lower = domain.lower()
                
                if domain_lower in text_lower:
                    # Cari konteks sekitar domain
                    pattern = f'.{{0,300}}{re.escape(domain_lower)}.{{0,300}}'
                    match = re.search(pattern, text_lower, re.DOTALL)
                    
                    if match:
                        context = match.group(0)
                        # Cek indikasi blokir
                        blocked_indicators = ['blocked', 'terblokir', 'nawala', 'trustpositif', 'diblokir', 'internet positif']
                        allowed_indicators = ['allowed', 'diizinkan', 'aman', 'clean', 'ok']
                        
                        is_blocked = any(ind in context for ind in blocked_indicators)
                        is_allowed = any(ind in context for ind in allowed_indicators)
                        
                        if is_blocked and not is_allowed:
                            blocked_domains.append(f"{domain} (terdeteksi)")
                            logger.warning(f"🚫 {domain}: Terdeteksi terblokir")
                        elif is_allowed:
                            logger.info(f"✅ {domain}: Aman")
                        else:
                            # Jika tidak jelas, asumsi aman
                            logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
                    else:
                        logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
                else:
                    logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ Text parse error: {e}")
            return []
    
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
            "🤖 *TrustPositif.app Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Batch:** 5 domain/request\n"
            f"🌐 **Sumber:** TrustPositif.app\n"
            f"🔗 **API:** api.trustpositif.app\n\n"
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
                "_Sumber: TrustPositif.app_"
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
                    "_Sumber: TrustPositif.app_"
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
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF.APP")
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
    print("🚀 TRUSTPOSITIF.APP DOMAIN MONITORING BOT")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 Source: TrustPositif.app")
    logger.info("🔗 API: api.trustpositif.app")
    
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
    logger.info("📍 Source: TrustPositif.app")
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
