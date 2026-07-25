import os
import sys
import time
import asyncio
import logging
import schedule
import socket
import struct
from telegram.ext import Application
from datetime import datetime
import urllib3
import requests

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

class NawalaDNSChecker:
    """
    Cek domain dengan query langsung ke DNS server Nawala
    Server DNS Nawala: 180.131.144.144 dan 180.131.145.145
    """
    def __init__(self):
        # DNS server Nawala (Kominfo)
        self.dns_servers = [
            "180.131.144.144",
            "180.131.145.145",
        ]
        # DNS port
        self.dns_port = 53
        # Timeout per query
        self.timeout = 5
        
    def _build_dns_query(self, domain):
        """Bangun DNS query packet untuk domain"""
        # Transaction ID (random)
        transaction_id = b'\xaa\xaa'
        
        # Flags: standard query, recursion desired
        flags = b'\x01\x00'
        
        # Question count: 1
        qdcount = b'\x00\x01'
        
        # Answer count: 0
        ancount = b'\x00\x00'
        
        # Authority count: 0
        nscount = b'\x00\x00'
        
        # Additional count: 0
        arcount = b'\x00\x00'
        
        # Build query name (domain)
        qname = b''
        for part in domain.split('.'):
            qname += bytes([len(part)]) + part.encode()
        qname += b'\x00'
        
        # Query type: A (1)
        qtype = b'\x00\x01'
        
        # Query class: IN (1)
        qclass = b'\x00\x01'
        
        # Build full packet
        packet = transaction_id + flags + qdcount + ancount + nscount + arcount + qname + qtype + qclass
        
        return packet
    
    def _parse_dns_response(self, data):
        """Parse DNS response untuk mendeteksi blokir"""
        try:
            # Cek response code (4 bits)
            response_code = (data[3] & 0x0F)
            
            # Jika response code = 3 (NXDOMAIN) - domain tidak ada
            # Jika response code = 0 (NOERROR) - domain ada
            # Domain terblokir biasanya mengembalikan response code 0 dengan alamat tertentu
            # atau response code 3 dengan TC flag
            
            # Cek flag TC (Truncated) - ini tanda domain diblokir
            tc_flag = (data[2] & 0x02) != 0
            
            # Cek response code
            if response_code == 3:  # NXDOMAIN
                return "NXDOMAIN"
            elif tc_flag:
                return "BLOCKED_TRUNCATED"
            elif response_code == 0:
                # Cek answer section
                # Hitung jumlah answer
                answer_count = struct.unpack('>H', data[6:8])[0]
                if answer_count > 0:
                    return "RESOLVED"
                else:
                    return "NO_RECORD"
            else:
                return f"ERROR_{response_code}"
                
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return "PARSE_ERROR"
    
    def check_domain_via_dns(self, domain):
        """Cek domain via DNS query langsung ke server Nawala"""
        try:
            # Build DNS query
            query = self._build_dns_query(domain)
            
            # Coba ke semua DNS server
            for dns_server in self.dns_servers:
                try:
                    # Create UDP socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(self.timeout)
                    
                    # Send query
                    sock.sendto(query, (dns_server, self.dns_port))
                    
                    # Receive response
                    data, addr = sock.recvfrom(512)
                    sock.close()
                    
                    # Parse response
                    result = self._parse_dns_response(data)
                    
                    logger.debug(f"DNS {dns_server} -> {domain}: {result}")
                    
                    # Jika result adalah BLOCKED_TRUNCATED atau NXDOMAIN
                    # atau RESOLVED dengan IP tertentu (ini domain tidak diblokir)
                    if result == "BLOCKED_TRUNCATED":
                        return "BLOCKED"
                    elif result == "NXDOMAIN":
                        return "BLOCKED"
                    elif result == "RESOLVED":
                        return "SAFE"
                    elif result == "NO_RECORD":
                        return "SAFE"
                    
                    # Jika tidak dapat menentukan, coba server lain
                    
                except socket.timeout:
                    logger.debug(f"DNS {dns_server} timeout untuk {domain}")
                    continue
                except Exception as e:
                    logger.debug(f"DNS {dns_server} error: {e}")
                    continue
            
            # Jika semua server gagal
            return "UNKNOWN"
            
        except Exception as e:
            logger.error(f"Error checking {domain}: {e}")
            return "UNKNOWN"
    
    def check_single_domain(self, domain):
        """Cek 1 domain"""
        try:
            logger.info(f"🔍 Checking domain: {domain}")
            
            result = self.check_domain_via_dns(domain)
            
            if result == "BLOCKED":
                logger.warning(f"🚫 {domain}: DIBLOKIR (Nawala)")
                return True
            elif result == "SAFE":
                logger.info(f"✅ {domain}: AMAN")
                return False
            else:
                logger.warning(f"⚠️ {domain}: UNKNOWN - coba metode alternatif")
                # Coba metode alternatif (via HTTP)
                return self._check_via_http(domain)
                
        except Exception as e:
            logger.error(f"Error checking {domain}: {e}")
            return None
    
    def _check_via_http(self, domain):
        """Metode alternatif via HTTP (fallback)"""
        try:
            # Coba cek via trustpositif.infonawala.com
            response = requests.post(
                "https://trustpositif.infonawala.com",
                data={'domains': domain},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=10,
                verify=False
            )
            
            if response.status_code == 200:
                html_lower = response.text.lower()
                domain_lower = domain.lower()
                
                if domain_lower in html_lower:
                    blocked_patterns = ['terblokir', 'diblokir', 'blocked', 'nawala', 'bg-red', 'text-red']
                    for pattern in blocked_patterns:
                        if pattern in html_lower:
                            return True
                    return False
                return False
                
        except Exception as e:
            logger.debug(f"HTTP fallback error: {e}")
            
        return False
    
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
                
                # Cek domain
                is_blocked = self.check_single_domain(domain)
                
                if is_blocked is True:
                    all_blocked.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                elif is_blocked is False:
                    logger.info(f"✅ {domain}: AMAN")
                else:
                    logger.warning(f"⚠️ {domain}: TIDAK DIKETAHUI")
                
                # Delay antar domain
                if i < total:
                    delay = 2
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
        
        message = (
            "🤖 *Nawala DNS Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** DNS Query langsung ke Server Nawala\n"
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
                "_Sumber: DNS Server Nawala (180.131.144.144, 180.131.145.145)_"
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
                    "_Sumber: DNS Server Nawala_"
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
        logger.info("🔄 MEMULAI PEMERIKSAAN NAWALA VIA DNS")
        logger.info("🔄 DNS Server: 180.131.144.144, 180.131.145.145")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = NawalaDNSChecker()
        
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
    print("🚀 NAWALA DNS CHECKER BOT")
    print("📌 Mode: DNS Query langsung ke Server Nawala")
    print("📌 DNS Server: 180.131.144.144, 180.131.145.145")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 DNS Server: 180.131.144.144, 180.131.145.145")
    logger.info("📌 Mode: DNS Query langsung (paling akurat)")
    
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
    logger.info("📍 Mode: DNS Query langsung ke Server Nawala")
    logger.info("📍 DNS Server: 180.131.144.144, 180.131.145.145")
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
