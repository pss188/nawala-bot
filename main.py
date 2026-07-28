import os
import sys
import time
import requests
import asyncio
import logging
import schedule
import json
from telegram.ext import Application
from datetime import datetime

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

# Proxy configuration
PROXY_HOST = "95.135.92.164"
PROXY_PORT_HTTP = 59100
PROXY_USERNAME = "pulsaslot1888"
PROXY_PASSWORD = "b3Kft6IMwG"

# Proxy URLs
PROXY_HTTP = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_HTTP}"

# Konfigurasi proxy
proxies = {
    'http': PROXY_HTTP,
    'https': PROXY_HTTP,
}

# Bot setup
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

class NawalaChecker:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://nawacek.id"
        self.api_url = "https://nawacek.id/api/check"
        self.session.proxies.update(proxies)
        
        # Headers untuk meniru browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': 'https://nawacek.id',
            'Referer': 'https://nawacek.id/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
    
    def check_domains(self, domains):
        """Cek domain menggunakan API nawacek.id"""
        try:
            if not domains:
                return []
            
            logger.info(f"🔍 Mengecek {len(domains)} domain...")
            
            # Format payload untuk API
            payload = {
                "domains": domains
            }
            
            # Kirim request ke API
            response = self.session.post(
                self.api_url,
                json=payload,
                headers=self.headers,
                timeout=30
            )
            
            logger.info(f"📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                return self.parse_api_response(response.json(), domains)
            else:
                logger.error(f"❌ HTTP Error {response.status_code}")
                logger.error(f"Response: {response.text[:200]}")
                return []
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout saat menghubungi API")
            return []
        except requests.exceptions.ConnectionError:
            logger.error("❌ Connection error")
            return []
        except Exception as e:
            logger.error(f"❌ Error checking domains: {e}")
            return []
    
    def parse_api_response(self, data, original_domains):
        """Parse response dari API nawacek.id"""
        blocked_domains = []
        
        try:
            # Log response untuk debugging
            logger.info(f"📦 API Response: {json.dumps(data, indent=2)[:500]}")
            
            # Cek struktur response
            if isinstance(data, dict):
                # Coba berbagai kemungkinan struktur response
                
                # Struktur 1: Langsung array of objects dengan domain dan status
                if 'data' in data and isinstance(data['data'], list):
                    results = data['data']
                elif 'results' in data and isinstance(data['results'], list):
                    results = data['results']
                elif 'domains' in data and isinstance(data['domains'], list):
                    results = data['domains']
                else:
                    # Mungkin response langsung berupa array
                    results = data if isinstance(data, list) else [data]
                
                # Proses setiap hasil
                for item in results:
                    if isinstance(item, dict):
                        domain = item.get('domain', '').strip().lower()
                        status = item.get('status', '').strip().lower()
                        is_blocked = item.get('blocked', False)
                        keterangan = item.get('keterangan', '')
                        kategori = item.get('kategori', '')
                        
                        if domain:
                            # Cek status terblokir
                            if is_blocked or status in ['blocked', 'terblokir', 'nawala', 'positif']:
                                status_text = f"🚫 TERBLOKIR"
                                if kategori:
                                    status_text += f" - {kategori}"
                                if keterangan:
                                    status_text += f" ({keterangan})"
                                
                                blocked_domains.append(f"{domain} - {status_text}")
                                logger.warning(f"🚫 {domain}: TERBLOKIR")
                            else:
                                logger.info(f"✅ {domain}: Aman")
                    elif isinstance(item, str):
                        # Jika hanya string domain
                        domain = item.lower()
                        # Cek di data lain jika ada
                        if 'blocked_domains' in data and domain in data['blocked_domains']:
                            blocked_domains.append(f"{domain} - 🚫 TERBLOKIR")
                            logger.warning(f"🚫 {domain}: TERBLOKIR")
                        else:
                            logger.info(f"✅ {domain}: Aman")
                
                # Jika tidak ada hasil dari struktur di atas, cek format lain
                if not blocked_domains and isinstance(data, dict):
                    # Cek jika ada field 'blocked' atau 'nawala'
                    for key, value in data.items():
                        if key in ['blocked', 'nawala', 'positive', 'terblokir']:
                            if isinstance(value, list):
                                for domain in value:
                                    if isinstance(domain, str):
                                        blocked_domains.append(f"{domain} - 🚫 TERBLOKIR")
                                        logger.warning(f"🚫 {domain}: TERBLOKIR")
            
            return blocked_domains
            
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return []
    
    def check_all_domains(self, domains):
        """Cek semua domain menggunakan API nawacek.id"""
        try:
            if not domains:
                return []
            
            total_domains = len(domains)
            all_blocked = []
            
            # API nawacek.id bisa menangani banyak domain sekaligus
            # Tapi kita tetap batasi untuk keamanan
            batch_size = 50  # Maksimal 50 domain per request
            
            for i in range(0, total_domains, batch_size):
                batch = domains[i:i + batch_size]
                logger.info(f"📦 Batch {i//batch_size + 1}: {len(batch)} domain")
                
                # Cek batch
                blocked_batch = self.check_domains(batch)
                all_blocked.extend(blocked_batch)
                
                # Delay antar batch
                if i + batch_size < total_domains:
                    delay = 2
                    logger.info(f"⏳ Menunggu {delay} detik sebelum batch berikutnya...")
                    time.sleep(delay)
            
            logger.info(f"📊 Total domain diproses: {total_domains}")
            return all_blocked
            
        except Exception as e:
            logger.error(f"❌ Error checking all domains: {e}")
            return []

def baca_domain():
    """Baca domain dari file domain.txt"""
    try:
        if not os.path.exists("domain.txt"):
            logger.error("❌ File domain.txt tidak ditemukan!")
            # Buat file contoh
            with open("domain.txt", "w") as f:
                f.write("# Daftar domain untuk dicek\n")
                f.write("# Satu domain per baris\n")
                f.write("# Contoh:\n")
                f.write("google.com\n")
                f.write("facebook.com\n")
                f.write("twitter.com\n")
                f.write("youtube.com\n")
                f.write("instagram.com\n")
            logger.info("✅ File domain.txt dibuat dengan contoh")
            return []
        
        domains = []
        with open("domain.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Bersihkan domain
                    line = line.lower()
                    # Hapus protocol
                    for prefix in ['http://', 'https://', 'www.']:
                        if line.startswith(prefix):
                            line = line[len(prefix):]
                    line = line.rstrip('/')
                    # Validasi sederhana
                    if '.' in line and len(line) > 3:
                        domains.append(line)
        
        logger.info(f"📖 Membaca {len(domains)} domain dari domain.txt")
        return domains
        
    except Exception as e:
        logger.error(f"❌ Error membaca domain: {e}")
        return []

async def kirim_status():
    """Kirim status bot"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        
        # Baca jumlah domain
        domains = baca_domain()
        domain_count = len(domains)
        
        message = (
            "🤖 *NawalaCek Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Batch:** 50 domain/request\n\n"
            "_Bot akan mengecek domain setiap 15 menit_\n"
            "_Sumber: nawacek.id_"
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
            # Semua domain aman
            message = (
                "✅ *LAPORAN NAWALA CEK*\n\n"
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
            # Ada domain terblokir
            domain_list = ""
            for i, domain_info in enumerate(blocked_domains, 1):
                domain_list += f"{i}. {domain_info}\n"
            
            message = (
                "🚨 *LAPORAN DOMAIN TERBLOKIR*\n\n"
                f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
                f"{domain_list}\n"
                f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "_Sumber: nawacek.id_"
            )
            
            # Cek panjang pesan
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
        
        # Bagi menjadi chunk 20 domain per pesan
        chunk_size = 20
        chunks = [blocked_domains[i:i + chunk_size] for i in range(0, len(blocked_domains), chunk_size)]
        
        for i, chunk in enumerate(chunks, 1):
            domain_list = ""
            for j, domain_info in enumerate(chunk, 1):
                domain_list += f"{(i-1)*chunk_size + j}. {domain_info}\n"
            
            message = (
                f"🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {i}/{len(chunks)})*\n\n"
                f"{domain_list}\n"
            )
            
            # Jika ini bagian terakhir, tambahkan footer
            if i == len(chunks):
                message += (
                    f"📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                    f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                    "_Sumber: nawacek.id_"
                )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            
            # Delay antar pesan
            if i < len(chunks):
                await asyncio.sleep(1)
        
        logger.info(f"📤 Laporan terbagi: {blocked_count} domain dalam {len(chunks)} pesan")
        
    except Exception as e:
        logger.error(f"❌ Gagal kirim pesan terbagi: {e}")

async def cek_domain_job():
    """Job untuk mengecek domain"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN NAWALA CEK")
        logger.info("=" * 60)
        
        # Baca domain
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        # Buat checker
        checker = NawalaChecker()
        
        # Cek semua domain
        start_time = time.time()
        blocked_domains = checker.check_all_domains(domains)
        elapsed_time = time.time() - start_time
        
        logger.info(f"⏱️ Waktu pemrosesan: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {len(blocked_domains)} dari {len(domains)} domain terblokir")
        
        # Kirim laporan
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

async def test_koneksi():
    """Test koneksi ke nawacek.id"""
    try:
        logger.info("🔗 Testing koneksi ke nawacek.id...")
        
        response = requests.get(
            "https://nawacek.id/",
            timeout=10,
            proxies=proxies
        )
        
        if response.status_code == 200:
            logger.info("✅ Koneksi BERHASIL - nawacek.id terdeteksi")
            return True
        else:
            logger.warning(f"⚠️ HTTP Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test koneksi GAGAL: {e}")
        return False

async def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 NAWALACEK DOMAIN MONITORING BOT")
    print("=" * 60)
    
    logger.info("Bot starting...")
    
    # Test koneksi
    logger.info("Testing connection...")
    if not await test_koneksi():
        logger.warning("⚠️ Koneksi bermasalah, bot tetap berjalan...")
    else:
        logger.info("✅ Koneksi OK")
    
    # Kirim status awal
    await kirim_status()
    
    # Setup schedule
    logger.info("Setting up schedule...")
    
    # Cek domain setiap 15 menit
    schedule.every(15).minutes.do(lambda: run_async_job(cek_domain_job))
    logger.info("✅ Schedule: Check domains every 15 minutes")
    
    # Status setiap 3 jam
    schedule.every(3).hours.do(lambda: run_async_job(kirim_status))
    logger.info("✅ Schedule: Status report every 3 hours")
    
    # Jalankan pengecekan pertama dengan delay
    logger.info("Running first check in 5 seconds...")
    await asyncio.sleep(5)
    await cek_domain_job()
    
    logger.info("✅ Bot successfully started!")
    logger.info("📍 Domain checks: Every 15 minutes")
    logger.info("📍 Status reports: Every 3 hours")
    logger.info("📍 Batch size: 50 domains per request")
    logger.info("📍 Source: nawacek.id")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    # Jalankan schedule runner
    await schedule_runner()

if __name__ == "__main__":
    # Cek dependencies
    try:
        import schedule
        import requests
        from telegram import __version__
        logger.info(f"✅ Dependencies: requests, schedule, python-telegram-bot v{__version__}")
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install -r requirements.txt")
        sys.exit(1)
    
    # Jalankan bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
