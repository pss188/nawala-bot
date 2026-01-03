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

class TrustPositifChecker:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://trustpositif.komdigi.go.id"
        self.session.proxies.update(proxies)
        
        # Headers untuk meniru browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # CSRF token dari HTML (tetap)
        self.csrf_token = "3835f8d38d9c0a271d2d782a70113bc2"
        
        # API endpoints dari JavaScript
        self.api_url = f"{self.base_url}/Rest_server/getrecordsname_home"
    
    def check_batch_5_domains(self, domains):
        """Cek 5 domain sekaligus sesuai limit website"""
        try:
            if len(domains) > 5:
                logger.warning(f"⚠️ Batch terlalu besar ({len(domains)}), hanya 5 pertama yang dicek")
                domains = domains[:5]
            
            # Format domains: satu per baris
            domains_text = "\n".join(domains)
            
            logger.info(f"🔍 Mengecek batch: {', '.join(domains)}")
            
            # Data payload sesuai form
            data = {
                'csrf_token': self.csrf_token,
                'name': domains_text
            }
            
            # Headers untuk AJAX request
            api_headers = self.headers.copy()
            api_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Referer': f'{self.base_url}/',
                'Origin': self.base_url
            })
            
            # Kirim request
            response = self.session.post(
                self.api_url,
                data=data,
                headers=api_headers,
                timeout=15
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
        """Parse API response"""
        blocked_domains = []
        
        try:
            # Coba parse JSON
            try:
                result = json.loads(response_text)
                
                if 'values' in result:
                    # Mapping hasil ke domain asli
                    domain_status_map = {}
                    
                    for item in result['values']:
                        if isinstance(item, dict):
                            domain = item.get('Domain', '').strip().lower()
                            status = item.get('Status', '').strip()
                            
                            if domain:
                                domain_status_map[domain] = status
                    
                    # Cek status untuk setiap domain asli
                    for domain in original_domains:
                        domain_lower = domain.lower()
                        status = domain_status_map.get(domain_lower, '')
                        
                        if status == 'Tidak Ada':
                            logger.info(f"✅ {domain}: Aman")
                        else:
                            # Jika ada status selain 'Tidak Ada' atau tidak ditemukan
                            if status:
                                blocked_domains.append(f"{domain} ({status})")
                                logger.warning(f"🚫 {domain}: {status}")
                            else:
                                # Jika tidak ada dalam response, asumsi aman
                                logger.info(f"✅ {domain}: Tidak ditemukan (asumsi aman)")
                
                return blocked_domains
                
            except json.JSONDecodeError:
                # Bukan JSON, parse HTML
                return self.parse_html_response(response_text, original_domains)
                
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return []
    
    def parse_html_response(self, html, domains):
        """Parse HTML response (fallback)"""
        blocked_domains = []
        
        try:
            # Konversi ke lowercase untuk case-insensitive search
            html_lower = html.lower()
            
            for domain in domains:
                domain_lower = domain.lower()
                
                # Cari domain dalam response
                if domain_lower in html_lower:
                    # Cari konteks sekitar domain
                    domain_index = html_lower.find(domain_lower)
                    start = max(0, domain_index - 100)
                    end = min(len(html_lower), domain_index + 150)
                    context = html_lower[start:end]
                    
                    # Cek apakah ada "tidak ada" dalam konteks
                    if 'tidak ada' in context:
                        logger.info(f"✅ HTML: {domain} aman")
                    else:
                        # Cari status dalam tabel
                        # Pattern: <td>domain</td><td>status</td>
                        if f'<td>{domain_lower}</td>' in html_lower:
                            # Cari status setelah domain
                            pattern = f'<td>{domain_lower}</td>.*?<td>(.*?)</td>'
                            import re
                            match = re.search(pattern, html_lower, re.DOTALL)
                            if match:
                                status = match.group(1).strip()
                                if status != 'tidak ada':
                                    blocked_domains.append(f"{domain} ({status})")
                                    logger.warning(f"🚫 HTML: {domain} -> {status}")
                                else:
                                    logger.info(f"✅ HTML: {domain} aman")
                        else:
                            # Jika domain ditemukan tapi tidak ada status jelas
                            blocked_domains.append(f"{domain} (terdeteksi)")
                            logger.warning(f"⚠️ HTML: {domain} terdeteksi tapi status tidak jelas")
                else:
                    # Domain tidak ditemukan dalam response
                    logger.info(f"✅ {domain}: Tidak ditemukan dalam response (asumsi aman)")
        
        except Exception as e:
            logger.error(f"❌ HTML parse error: {e}")
        
        return blocked_domains
    
    def check_all_domains(self, domains):
        """Cek semua domain dengan batch 5 domain"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            total_domains = len(domains)
            
            # Bagi domain menjadi batch 5 domain
            batch_size = 5
            batch_count = 0
            
            for i in range(0, total_domains, batch_size):
                batch = domains[i:i + batch_size]
                batch_count += 1
                
                logger.info(f"📦 Batch {batch_count}: {len(batch)} domain")
                
                # Cek batch
                blocked_batch = self.check_batch_5_domains(batch)
                all_blocked.extend(blocked_batch)
                
                # Delay antar batch untuk hindari rate limiting
                if i + batch_size < total_domains:
                    delay = 3  # 3 detik
                    logger.info(f"⏳ Menunggu {delay} detik sebelum batch berikutnya...")
                    time.sleep(delay)
            
            logger.info(f"📊 Total batch diproses: {batch_count}")
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
                f.write("# Daftar domain untuk dicek (maksimal disarankan 50 domain)\n")
                f.write("# Satu domain per baris\n")
                f.write("# Contoh:\n")
                f.write("google.com\n")
                f.write("facebook.com\n")
                f.write("twitter.com\n")
                f.write("hkbpokerqqid2.pages.dev\n")
                f.write("hkbwdcom.pages.dev\n")
                f.write("jendelatoto.id\n")
                f.write("jendelatotocomamp.pages.dev\n")
                f.write("rtpjendelatt.pages.dev\n")
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
            "🤖 *TrustPositif Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Batch:** 5 domain/request\n\n"
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
            # Semua domain aman
            message = (
                "✅ *LAPORAN TRUSTPOSITIF KOMINFO*\n\n"
                "**SEMUA DOMAIN AMAN!** 🎉\n\n"
                f"📊 **Total Domain:** {total_domains}\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "Tidak ada domain yang terblokir oleh TrustPositif Kominfo."
            )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"📤 Laporan aman: {total_domains} domain")
            
        else:
            # Ada domain terblokir
            # Format domain dengan nomor
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
                domain_list += f"{(i-1)*chunk_size + j}. 🚫 `{domain_info}`\n"
            
            message = (
                f"🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {i}/{len(chunks)})*\n\n"
                f"{domain_list}\n"
            )
            
            # Jika ini bagian terakhir, tambahkan footer
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
        logger.info("🔄 MEMULAI PEMERIKSAAN TRUSTPOSITIF KOMINFO")
        logger.info("=" * 60)
        
        # Baca domain
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        # Buat checker
        checker = TrustPositifChecker()
        
        # Cek semua domain dengan batch 5
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
    """Test koneksi ke trustpositif.komdigi.go.id"""
    try:
        logger.info("🔗 Testing koneksi ke trustpositif.komdigi.go.id...")
        
        response = requests.get(
            "https://trustpositif.komdigi.go.id/",
            timeout=10,
            proxies=proxies
        )
        
        if response.status_code == 200:
            # Cek apakah halaman utama terbuka
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
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 TRUSTPOSITIF KOMINFO DOMAIN MONITORING BOT")
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
    logger.info("📍 Batch size: 5 domains per request")
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
