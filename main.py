import os
import sys
import time
import asyncio
import logging
import schedule
import socket
import struct
import dns.resolver
import dns.exception
import dns.message
import dns.query
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

# Proxy configuration
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# Setup proxy untuk requests
proxies = None
if USE_PROXY and PROXY_HOST and PROXY_PORT:
    proxy_url = f"http://{PROXY_HOST}:{PROXY_PORT}"
    if PROXY_USERNAME and PROXY_PASSWORD:
        proxy_url = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"
    proxies = {
        'http': proxy_url,
        'https': proxy_url,
    }
    logger.info(f"🔑 Menggunakan proxy: {PROXY_HOST}:{PROXY_PORT}")
else:
    logger.info("🔓 Koneksi langsung (tanpa proxy)")

# Bot setup
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

class NawalaChecker:
    def __init__(self):
        # DNS server Nawala
        self.dns_servers = [
            "180.131.144.144",
            "180.131.145.145",
        ]
        self.proxies = proxies
        
        # Setup DNS resolver dengan proxy support
        self.resolver = dns.resolver.Resolver()
        self.resolver.nameservers = self.dns_servers
        self.resolver.timeout = 5
        self.resolver.lifetime = 5
        
        # Untuk DNS over TCP via proxy (jika diperlukan)
        self.use_proxy_for_dns = USE_PROXY
        
    def check_via_dns(self, domain):
        """Cek domain via DNS dengan dukungan proxy"""
        try:
            logger.debug(f"DNS query untuk {domain}...")
            
            # Jika menggunakan proxy, coba via TCP
            if self.use_proxy_for_dns:
                try:
                    # Build DNS query
                    query = dns.message.make_query(domain, 'A')
                    
                    # Kirim via TCP ke DNS server
                    for dns_server in self.dns_servers:
                        try:
                            # Gunakan socket dengan timeout
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(5)
                            
                            # Connect ke DNS server
                            sock.connect((dns_server, 53))
                            
                            # Kirim query
                            wire_data = query.to_wire()
                            sock.send(wire_data)
                            
                            # Receive response
                            response_data = sock.recv(4096)
                            sock.close()
                            
                            # Parse response
                            response = dns.message.from_wire(response_data)
                            
                            # Cek status
                            if response.rcode() == dns.rcode.NXDOMAIN:
                                return "BLOCKED"
                            elif response.rcode() == dns.rcode.NOERROR:
                                if len(response.answer) > 0:
                                    return "SAFE"
                                else:
                                    return "BLOCKED"
                            else:
                                continue
                                
                        except socket.timeout:
                            logger.debug(f"DNS TCP timeout: {dns_server}")
                            continue
                        except Exception as e:
                            logger.debug(f"DNS TCP error: {e}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"DNS TCP fallback error: {e}")
                    # Jika TCP gagal, coba UDP biasa
            
            # Coba DNS normal (UDP)
            try:
                answers = self.resolver.resolve(domain, 'A')
                logger.debug(f"DNS resolved: {domain}")
                return "SAFE"
            except dns.resolver.NXDOMAIN:
                logger.debug(f"DNS NXDOMAIN: {domain}")
                return "BLOCKED"
            except dns.resolver.NoAnswer:
                try:
                    answers = self.resolver.resolve(domain, 'CNAME')
                    return "SAFE"
                except:
                    return "BLOCKED"
            except dns.exception.Timeout:
                logger.debug(f"DNS Timeout: {domain}")
                return "TIMEOUT"
            except dns.resolver.NoNameservers:
                logger.debug(f"No nameservers: {domain}")
                return "ERROR"
                
        except Exception as e:
            logger.debug(f"DNS error: {e}")
            return "ERROR"
    
    def check_via_http(self, domain):
        """Cek domain via HTTP dengan dukungan proxy"""
        try:
            logger.debug(f"HTTP fallback untuk {domain}...")
            
            # Gunakan proxy jika di-set
            session = requests.Session()
            if self.proxies:
                session.proxies.update(self.proxies)
            
            # Coba ke nawala.online
            response = session.post(
                "https://nawala.online",
                data={'domains': domain},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=15,
                verify=False
            )
            
            if response.status_code == 200:
                html_lower = response.text.lower()
                domain_lower = domain.lower()
                
                if domain_lower in html_lower:
                    blocked_indicators = ['blocked', 'terblokir', 'diblokir', 'nawala']
                    for indicator in blocked_indicators:
                        if indicator in html_lower:
                            logger.info(f"HTTP mendeteksi BLOKIR: {domain}")
                            return "BLOCKED"
                    logger.info(f"HTTP mendeteksi AMAN: {domain}")
                    return "SAFE"
                else:
                    logger.info(f"HTTP: Domain tidak ditemukan: {domain}")
                    return "SAFE"
            
            return "ERROR"
            
        except requests.exceptions.ProxyError as e:
            logger.error(f"Proxy error: {e}")
            return "ERROR"
        except Exception as e:
            logger.debug(f"HTTP error: {e}")
            return "ERROR"
    
    def check_via_trustpositif(self, domain):
        """Cek via trustpositif.id dengan proxy"""
        try:
            logger.debug(f"TrustPositif check untuk {domain}...")
            
            session = requests.Session()
            if self.proxies:
                session.proxies.update(self.proxies)
            
            # Kirim POST ke checker
            response = session.post(
                "https://trustpositif.id/checker/check",
                json={'domains': [domain]},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': 'ukvxzVGQTWSBl5G4JnZgTFVeEuj08r49LYISmaP8',
                    'Origin': 'https://trustpositif.id',
                    'Referer': 'https://trustpositif.id/checker',
                },
                timeout=15,
                verify=False
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    results = data.get('results', [])
                    for result in results:
                        if result.get('Blocked') or result.get('blocked'):
                            logger.warning(f"TrustPositif mendeteksi BLOKIR: {domain}")
                            return "BLOCKED"
                    logger.info(f"TrustPositif mendeteksi AMAN: {domain}")
                    return "SAFE"
            
            return "ERROR"
            
        except Exception as e:
            logger.debug(f"TrustPositif error: {e}")
            return "ERROR"
    
    def check_single_domain(self, domain):
        """Cek 1 domain dengan multiple metode"""
        try:
            logger.info(f"🔍 Checking domain: {domain}")
            
            # Metode 1: DNS langsung
            dns_result = self.check_via_dns(domain)
            
            if dns_result == "SAFE":
                logger.info(f"✅ {domain}: AMAN (DNS)")
                return False
            elif dns_result == "BLOCKED":
                logger.warning(f"🚫 {domain}: DIBLOKIR (DNS)")
                return True
            elif dns_result == "TIMEOUT":
                logger.warning(f"⚠️ DNS timeout untuk {domain}, coba HTTP...")
            else:
                logger.warning(f"⚠️ DNS error untuk {domain}, coba HTTP...")
            
            # Metode 2: HTTP fallback (nawala.online)
            http_result = self.check_via_http(domain)
            
            if http_result == "BLOCKED":
                logger.warning(f"🚫 {domain}: DIBLOKIR (HTTP)")
                return True
            elif http_result == "SAFE":
                logger.info(f"✅ {domain}: AMAN (HTTP)")
                return False
            
            # Metode 3: TrustPositif
            tp_result = self.check_via_trustpositif(domain)
            
            if tp_result == "BLOCKED":
                logger.warning(f"🚫 {domain}: DIBLOKIR (TrustPositif)")
                return True
            elif tp_result == "SAFE":
                logger.info(f"✅ {domain}: AMAN (TrustPositif)")
                return False
            
            # Jika semua gagal, asumsi AMAN
            logger.warning(f"⚠️ {domain}: Semua metode gagal, asumsi AMAN")
            return False
            
        except Exception as e:
            logger.error(f"Error checking {domain}: {e}")
            return None
    
    def check_all_domains(self, domains):
        """Cek semua domain satu per satu"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            total = len(domains)
            
            logger.info(f"📋 Total domain: {total}")
            logger.info("=" * 50)
            
            for i, domain in enumerate(domains, 1):
                logger.info(f"[{i}/{total}] Memeriksa: {domain}")
                
                is_blocked = self.check_single_domain(domain)
                
                if is_blocked is True:
                    all_blocked.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                elif is_blocked is False:
                    logger.info(f"✅ {domain}: AMAN")
                else:
                    logger.warning(f"⚠️ {domain}: TIDAK DIKETAHUI")
                
                if i < total:
                    delay = 3
                    logger.info(f"⏳ Menunggu {delay} detik...")
                    time.sleep(delay)
            
            return all_blocked
            
        except Exception as e:
            logger.error(f"Error checking all domains: {e}")
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
        logger.error(f"Error membaca domain: {e}")
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
        
        proxy_status = "✅" if USE_PROXY else "❌"
        
        message = (
            "🤖 *Nawala Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** DNS + HTTP + TrustPositif\n"
            f"🔑 **Proxy:** {proxy_status} {'Aktif' if USE_PROXY else 'Nonaktif'}\n"
            f"🌐 **DNS Server:** 180.131.144.144, 180.131.145.145\n\n"
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
    """Kirim laporan hasil pengecekan"""
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
                "_Sumber: DNS + HTTP + TrustPositif_"
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
                    "_Sumber: DNS + HTTP + TrustPositif_"
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
    """Job untuk mengecek domain"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN NAWALA")
        logger.info(f"🔄 Proxy: {'AKTIF' if USE_PROXY else 'NONAKTIF'}")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = NawalaChecker()
        
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
            logger.error(f"Error dalam schedule runner: {e}")
            await asyncio.sleep(5)

async def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("🚀 NAWALA CHECKER BOT")
    print("📌 Mode: DNS + HTTP + TrustPositif")
    print(f"📌 Proxy: {'AKTIF' if USE_PROXY else 'NONAKTIF'}")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info(f"🌐 Proxy: {'AKTIF' if USE_PROXY else 'NONAKTIF'}")
    
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
    logger.info("📍 Mode: DNS + HTTP + TrustPositif")
    logger.info(f"📍 Proxy: {'AKTIF' if USE_PROXY else 'NONAKTIF'}")
    logger.info("📍 Press Ctrl+C to stop\n")
    
    await schedule_runner()

if __name__ == "__main__":
    try:
        import schedule
        import requests
        from telegram import __version__
        import dns
        logger.info(f"✅ Dependencies: requests, schedule, python-telegram-bot v{__version__}, dnspython")
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot dnspython")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
