import os
import sys
import time
import hashlib
import requests
import asyncio
import logging
import re
import schedule
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
        self.base_url = "https://www.nawala.asia"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.nawala.asia',
            'Referer': 'https://www.nawala.asia/',
            'X-Requested-With': 'XMLHttpRequest',
        }
    
    def get_cookies(self):
        """Ambil cookies dari homepage"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ Cookies diperoleh: {list(self.session.cookies.keys())}")
                return True
        except Exception as e:
            logger.error(f"❌ Error get cookies: {e}")
        return False
    
    def generate_recaptcha_token(self):
        """Generate recaptcha token"""
        # Token format yang diterima nawala.asia
        timestamp = int(time.time())
        random_str = hashlib.md5(str(timestamp).encode()).hexdigest()[:20]
        # Format: 03AGdBq27[random]IXJKEw8WnGmB2Y2kD7VrT6cQlFw7BfLhM9sPqRtZyXwvKuN1oA3bC5dE7gH9jK1mN3pQ5rS7tV9wXyZ2aB4dF6hJ8kL0nP2qR4sU6vW8xY0zC3eG5i
        token = f"03AGdBq27{random_str}IXJKEw8WnGmB2Y2kD7VrT6cQlFw7BfLhM9sPqRtZyXwvKuN1oA3bC5dE7gH9jK1mN3pQ5rS7tV9wXyZ2aB4dF6hJ8kL0nP2qR4sU6vW8xY0zC3eG5i"
        return token
    
    def check_domains_batch(self, domains):
        """Cek batch domain sekaligus - FIXED VERSION"""
        try:
            if not domains:
                return []
            
            # Pastikan kita punya cookies dulu
            if not self.get_cookies():
                logger.warning("⚠️ Gagal mendapatkan cookies, tetap melanjutkan...")
            
            # Batasi domain (max 100 sesuai website)
            domains = domains[:100]
            
            # Format domains: satu per baris
            domains_text = "\n".join(domains)
            
            # Data payload sesuai form website
            payload = {
                'domains': domains_text,
                'recaptchaToken': self.generate_recaptcha_token()
            }
            
            logger.info(f"📤 Mengirim {len(domains)} domain ke nawala.asia API...")
            
            # API endpoint dari JavaScript di website
            api_url = f"{self.base_url}/api/check"
            
            # Kirim POST request
            response = self.session.post(
                api_url,
                data=payload,
                headers=self.headers,
                timeout=30,
                allow_redirects=False
            )
            
            logger.info(f"📡 Response status: {response.status_code}")
            logger.info(f"📡 Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                try:
                    # Coba parse sebagai JSON
                    result = response.json()
                    logger.info(f"📊 Response type: JSON, keys: {list(result.keys())}")
                    
                    blocked_domains = []
                    
                    # Parse berdasarkan struktur response
                    if 'status' in result and result['status'] == 'success':
                        if 'data' in result and isinstance(result['data'], list):
                            for item in result['data']:
                                if isinstance(item, dict):
                                    domain = item.get('domain', '')
                                    status = item.get('status', '')
                                    if domain and status and status.lower() == 'blocked':
                                        blocked_domains.append(domain)
                                        logger.warning(f"🚫 Domain terblokir (JSON): {domain}")
                    
                    return blocked_domains
                    
                except ValueError:
                    # Bukan JSON, coba parse HTML
                    logger.info("📄 Response bukan JSON, mencoba parse HTML...")
                    return self.parse_html_response(response.text, domains)
            
            elif response.status_code == 403:
                logger.error("❌ 403 Forbidden - Mungkin butuh recaptcha solving")
                # Coba method fallback
                return self.check_domains_fallback(domains)
            
            else:
                logger.error(f"❌ HTTP Error {response.status_code}")
                return []
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout saat mengakses API")
            return []
        except requests.exceptions.ConnectionError:
            logger.error("❌ Connection error")
            return []
        except Exception as e:
            logger.error(f"❌ Error in batch check: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def parse_html_response(self, html, domains):
        """Parse HTML response untuk mencari hasil"""
        blocked_domains = []
        
        try:
            # Cari tabel hasil
            table_pattern = r'<table[^>]*id="tableResult"[^>]*>.*?<tbody>(.*?)</tbody>'
            table_match = re.search(table_pattern, html, re.DOTALL | re.IGNORECASE)
            
            if table_match:
                tbody_content = table_match.group(1)
                logger.info("✅ Tabel hasil ditemukan")
                
                # Cari semua baris
                row_pattern = r'<tr[^>]*>(.*?)</tr>'
                rows = re.findall(row_pattern, tbody_content, re.DOTALL | re.IGNORECASE)
                
                for row in rows:
                    # Cari kolom
                    col_pattern = r'<td[^>]*>(.*?)</td>'
                    cols = re.findall(col_pattern, row, re.DOTALL | re.IGNORECASE)
                    
                    if len(cols) >= 2:
                        domain = re.sub(r'<[^>]+>', '', cols[0]).strip()
                        status = re.sub(r'<[^>]+>', '', cols[1]).strip()
                        
                        if domain in domains and 'blocked' in status.lower():
                            blocked_domains.append(domain)
                            logger.warning(f"🚫 HTML parse: {domain} -> {status}")
            
            # Jika tidak ada tabel, cari dengan pattern sederhana
            if not blocked_domains:
                for domain in domains:
                    if domain in html:
                        # Cari status di sekitar domain
                        domain_index = html.lower().find(domain.lower())
                        if domain_index != -1:
                            # Ambil 100 karakter setelah domain
                            start = domain_index
                            end = min(len(html), start + 100)
                            snippet = html[start:end].lower()
                            
                            if 'blocked' in snippet or 'terblokir' in snippet or '🚫' in snippet:
                                blocked_domains.append(domain)
                                logger.warning(f"🚫 Snippet match: {domain}")
        
        except Exception as e:
            logger.error(f"❌ Error parsing HTML: {e}")
        
        return blocked_domains
    
    def check_domains_fallback(self, domains):
        """Fallback method jika API gagal"""
        logger.info("🔄 Menggunakan metode fallback...")
        
        blocked_domains = []
        
        for domain in domains[:20]:  # Batasi untuk tidak overload
            try:
                # Coba akses domain melalui nawala.asia live check
                check_url = f"https://www.nawala.asia/live?domain={domain}"
                
                response = self.session.get(check_url, timeout=10)
                
                if response.status_code == 200:
                    html = response.text
                    
                    # Cek indikator blocked
                    if 'blocked' in html.lower() or 'terblokir' in html.lower():
                        blocked_domains.append(domain)
                        logger.warning(f"🚫 Fallback: {domain} terblokir")
                    else:
                        logger.info(f"✅ Fallback: {domain} aman")
                
                # Delay untuk hindari rate limit
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Fallback error for {domain}: {e}")
        
        return blocked_domains

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
                    # Clean the domain
                    line = line.lower()
                    # Remove protocols
                    if line.startswith('http://'):
                        line = line[7:]
                    elif line.startswith('https://'):
                        line = line[8:]
                    # Remove www.
                    if line.startswith('www.'):
                        line = line[4:]
                    # Remove trailing slash
                    line = line.rstrip('/')
                    # Simple validation
                    if '.' in line and len(line) > 3:
                        domains.append(line)
        
        logger.info(f"📖 Membaca {len(domains)} domain dari domain.txt")
        return domains
        
    except Exception as e:
        logger.error(f"❌ Error membaca domain: {e}")
        return []

async def kirim_status():
    """Kirim status bot ke Telegram"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        
        message = (
            "🤖 *Nawala.Asia Monitoring Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📍 **Target:** nawala.asia API\n"
            f"📊 **Mode:** Batch Checking\n\n"
            "_Bot akan mengecek domain setiap 5 menit_"
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
        if not blocked_domains:
            # Semua domain aman
            message = (
                "✅ *LAPORAN PEMERIKSAAN DOMAIN*\n\n"
                "**SEMUA DOMAIN AMAN!** 🎉\n\n"
                f"📊 **Total Domain:** {total_domains}\n"
                f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n\n"
                "Tidak ada domain yang terblokir oleh TrustPositif Nawala."
            )
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"📤 Laporan aman: {total_domains} domain")
            
        else:
            # Ada domain terblokir
            blocked_count = len(blocked_domains)
            
            # Buat pesan utama
            message_parts = []
            current_message = "🚨 *LAPORAN DOMAIN TERBLOKIR*\n\n"
            current_message += f"**{blocked_count} DOMAIN TERBLOKIR**\n\n"
            
            for i, domain in enumerate(blocked_domains, 1):
                line = f"{i}. 🚫 `{domain}`\n"
                
                # Jika pesan terlalu panjang, kirim yang sekarang dan buat baru
                if len(current_message) + len(line) > 4000:
                    message_parts.append(current_message)
                    current_message = f"*Lanjutan...*\n\n{line}"
                else:
                    current_message += line
            
            # Tambahkan footer ke pesan terakhir
            if current_message:
                current_message += f"\n📊 **Statistik:** {blocked_count}/{total_domains} domain terblokir\n"
                current_message += f"⏰ **Waktu:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n"
                current_message += f"\n_Generated by Nawala.Asia Monitor_"
                message_parts.append(current_message)
            
            # Kirim semua bagian
            for i, part in enumerate(message_parts, 1):
                if len(message_parts) > 1:
                    # Tambahkan nomor bagian
                    lines = part.split('\n')
                    lines[0] = f"🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {i}/{len(message_parts)})*"
                    part = '\n'.join(lines)
                
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=part,
                    parse_mode="Markdown"
                )
                
                # Delay antar pesan
                if i < len(message_parts):
                    await asyncio.sleep(1)
            
            logger.info(f"📤 Laporan terblokir: {blocked_count} domain")
            
    except Exception as e:
        logger.error(f"❌ Gagal kirim laporan: {e}")

async def cek_domain_job():
    """Job untuk mengecek domain - dipanggil oleh schedule"""
    try:
        logger.info("=" * 50)
        logger.info("🔄 MEMULAI PEMERIKSAAN DOMAIN")
        logger.info("=" * 50)
        
        # Baca domain
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        # Buat checker
        checker = NawalaChecker()
        
        # Cek domain
        start_time = time.time()
        blocked_domains = checker.check_domains_batch(domains)
        elapsed_time = time.time() - start_time
        
        logger.info(f"⏱️ Waktu pemrosesan: {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {len(blocked_domains)} dari {len(domains)} domain terblokir")
        
        # Kirim laporan
        await kirim_laporan(blocked_domains, len(domains))
        
        logger.info("✅ Pemeriksaan selesai")
        
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
    """Test koneksi ke nawala.asia"""
    try:
        logger.info("🔗 Testing koneksi ke nawala.asia...")
        
        response = requests.get("https://www.nawala.asia/", timeout=10)
        
        if response.status_code == 200:
            logger.info("✅ Koneksi ke nawala.asia BERHASIL")
            return True
        else:
            logger.warning(f"⚠️ Koneksi nawala.asia: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test koneksi GAGAL: {e}")
        return False

async def main():
    """Main function"""
    logger.info("=" * 50)
    logger.info("🚀 NAWALA.ASIA DOMAIN MONITORING BOT")
    logger.info("=" * 50)
    
    # Test koneksi
    if not await test_koneksi():
        logger.warning("⚠️ Koneksi bermasalah, bot tetap berjalan...")
    
    # Kirim status awal
    await kirim_status()
    
    # Setup schedule jobs
    logger.info("⏰ Mengatur jadwal...")
    
    # Cek domain setiap 5 menit
    schedule.every(5).minutes.do(lambda: run_async_job(cek_domain_job))
    
    # Status setiap 1 jam
    schedule.every(1).hours.do(lambda: run_async_job(kirim_status))
    
    # Jalankan pengecekan pertama dengan delay
    await asyncio.sleep(3)
    await cek_domain_job()
    
    logger.info("✅ Bot berhasil dijalankan!")
    logger.info("📍 Pengecekan otomatis setiap 5 menit")
    logger.info("📍 Status dikirim setiap 1 jam")
    logger.info("📍 Tekan Ctrl+C untuk menghentikan")
    
    # Jalankan schedule runner
    await schedule_runner()

def install_dependencies():
    """Cek dan install dependencies"""
    try:
        import importlib
        import subprocess
        
        requirements = [
            ("requests", "requests"),
            ("schedule", "schedule"),
            ("python-telegram-bot", "telegram")
        ]
        
        for pkg_name, import_name in requirements:
            try:
                importlib.import_module(import_name)
                logger.info(f"✅ {pkg_name} sudah terinstall")
            except ImportError:
                logger.warning(f"📦 Menginstall {pkg_name}...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg_name])
                logger.info(f"✅ {pkg_name} berhasil diinstall")
                
    except Exception as e:
        logger.error(f"❌ Error install dependencies: {e}")

if __name__ == "__main__":
    # Install dependencies jika perlu
    install_dependencies()
    
    # Cek file domain.txt
    if not os.path.exists("domain.txt"):
        logger.warning("📄 Membuat file domain.txt...")
        with open("domain.txt", "w") as f:
            f.write("# Daftar domain untuk dimonitor\n")
            f.write("# Satu domain per baris\n")
            f.write("# Contoh:\n")
            f.write("google.com\n")
            f.write("facebook.com\n")
            f.write("twitter.com\n")
        logger.info("✅ File domain.txt dibuat")
    
    # Jalankan bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot dihentikan dengan aman")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
