import os
import sys
import time
import asyncio
import logging
import schedule
import socket
import struct
import socks
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
PROXY_HOST = "193.5.64.24"
PROXY_PORT = 59101  # SOCKS5
PROXY_USERNAME = "pulsaslot1888"
PROXY_PASSWORD = "b3Kft6IMwG"

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# Setup SOCKS5 proxy untuk semua koneksi socket
try:
    socks.set_default_proxy(
        socks.SOCKS5,
        PROXY_HOST,
        PROXY_PORT,
        username=PROXY_USERNAME,
        password=PROXY_PASSWORD
    )
    # Patch socket untuk menggunakan SOCKS5
    socket.socket = socks.socksocket
    logger.info(f"✅ SOCKS5 proxy di-set: {PROXY_HOST}:{PROXY_PORT}")
except Exception as e:
    logger.error(f"❌ Gagal setup SOCKS5: {e}")
    sys.exit(1)

# Setup proxy untuk requests
proxies = {
    'http': f'socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}',
    'https': f'socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}',
}

# Bot setup
try:
    application = Application.builder().token(TOKEN).build()
    logger.info("✅ Bot Telegram berhasil diinisialisasi")
except Exception as e:
    logger.error(f"❌ Gagal setup bot: {e}")
    sys.exit(1)

class NawalaDNSChecker:
    def __init__(self):
        # DNS server Nawala (Kominfo)
        self.dns_servers = [
            ("180.131.144.144", 53),
            ("180.131.145.145", 53),
        ]
        # Timeout per query
        self.timeout = 5
        
        # IP yang menandakan domain diblokir (Nawala)
        self.blocked_ips = [
            "180.131.144.144",
            "180.131.145.145",
            "114.127.223.16",  # IndiHome
            "0.0.0.0",
        ]
    
    def _build_dns_query(self, domain):
        """Bangun DNS query packet untuk domain"""
        # Transaction ID
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
        """Parse DNS response untuk deteksi blokir"""
        try:
            # Cek apakah ini response
            qr = (data[2] & 0x80) != 0
            if not qr:
                return None, None
            
            # Cek flag TC (Truncated) - tanda blokir
            tc_flag = (data[2] & 0x02) != 0
            if tc_flag:
                return "BLOCKED", None
            
            # Cek response code
            response_code = data[3] & 0x0F
            
            # NXDOMAIN (3) = domain tidak ada = BLOKIR
            if response_code == 3:
                return "BLOCKED", None
            
            # NOERROR (0) = domain ada
            if response_code == 0:
                # Dapatkan jumlah answer
                answer_count = struct.unpack('>H', data[6:8])[0]
                
                if answer_count > 0:
                    # Coba ekstrak IP address dari answer
                    ip_addresses = self._extract_ips_from_response(data)
                    
                    # Cek apakah IP termasuk IP blokir
                    for ip in ip_addresses:
                        if ip in self.blocked_ips:
                            return "BLOCKED_IP", ip
                    
                    return "RESOLVED", ip_addresses[0] if ip_addresses else None
                else:
                    return "NO_RECORD", None
            
            return f"ERROR_{response_code}", None
            
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return "PARSE_ERROR", None
    
    def _extract_ips_from_response(self, data):
        """Ekstrak IP address dari DNS response"""
        ips = []
        try:
            # Cari di answer section
            # Skip header (12 bytes)
            pos = 12
            
            # Skip question section
            while pos < len(data):
                if data[pos] == 0:
                    pos += 5  # Skip null + qtype + qclass
                    break
                if data[pos] & 0xC0:  # Pointer
                    pos += 2
                    break
                pos += data[pos] + 1
            
            # Parse answer section
            answer_count = struct.unpack('>H', data[6:8])[0]
            
            for _ in range(answer_count):
                # Skip name (pointer atau label)
                if data[pos] & 0xC0:
                    pos += 2
                else:
                    while data[pos] != 0:
                        pos += data[pos] + 1
                    pos += 1
                
                # Type, Class, TTL, Data Length
                qtype = struct.unpack('>H', data[pos:pos+2])[0]
                pos += 2
                qclass = struct.unpack('>H', data[pos:pos+2])[0]
                pos += 2
                ttl = struct.unpack('>I', data[pos:pos+4])[0]
                pos += 4
                data_len = struct.unpack('>H', data[pos:pos+2])[0]
                pos += 2
                
                # Jika type A (1), ekstrak IP
                if qtype == 1 and data_len == 4:
                    ip = f"{data[pos]}.{data[pos+1]}.{data[pos+2]}.{data[pos+3]}"
                    ips.append(ip)
                
                pos += data_len
            
        except Exception as e:
            logger.debug(f"Extract IP error: {e}")
        
        return ips
    
    def check_via_dns(self, domain):
        """Cek domain via DNS query melalui proxy SOCKS5"""
        try:
            # Build DNS query
            query = self._build_dns_query(domain)
            
            # Coba ke semua DNS server
            for dns_server, dns_port in self.dns_servers:
                try:
                    # Buat socket melalui SOCKS5 proxy
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(self.timeout)
                    
                    # Kirim query ke DNS server
                    sock.sendto(query, (dns_server, dns_port))
                    
                    # Terima response
                    data, addr = sock.recvfrom(512)
                    sock.close()
                    
                    # Parse response
                    status, ip = self._parse_dns_response(data)
                    
                    logger.debug(f"DNS {dns_server}: {domain} -> {status} ({ip})")
                    
                    if status == "BLOCKED" or status == "BLOCKED_IP":
                        return True
                    elif status == "RESOLVED" or status == "NO_RECORD":
                        return False
                    # Jika error, coba server lain
                    
                except socket.timeout:
                    logger.debug(f"DNS {dns_server} timeout untuk {domain}")
                    continue
                except Exception as e:
                    logger.debug(f"DNS {dns_server} error: {e}")
                    continue
            
            # Jika semua server gagal
            logger.warning(f"⚠️ Semua DNS server gagal untuk {domain}")
            return False
            
        except Exception as e:
            logger.error(f"DNS error untuk {domain}: {e}")
            return False
    
    def check_via_http_fallback(self, domain):
        """Fallback: cek via HTTP dengan proxy"""
        try:
            session = requests.Session()
            session.proxies.update(proxies)
            
            response = session.post(
                "https://trustpositif.id/checker/check",
                json={'domains': [domain]},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Content-Type': 'application/json',
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
                            return True
            return False
            
        except Exception as e:
            logger.debug(f"HTTP fallback error: {e}")
            return False
    
    def check_single_domain(self, domain):
        """Cek 1 domain"""
        try:
            logger.info(f"🔍 Checking: {domain}")
            
            # Metode 1: DNS query via SOCKS5
            is_blocked = self.check_via_dns(domain)
            
            if is_blocked:
                logger.warning(f"🚫 {domain}: DIBLOKIR (DNS)")
                return True
            
            # Metode 2: HTTP fallback jika DNS gagal
            logger.info(f"📡 DNS tidak mendeteksi blokir, coba HTTP fallback...")
            is_blocked = self.check_via_http_fallback(domain)
            
            if is_blocked:
                logger.warning(f"🚫 {domain}: DIBLOKIR (HTTP Fallback)")
                return True
            else:
                logger.info(f"✅ {domain}: AMAN")
                return False
                
        except Exception as e:
            logger.error(f"Error checking {domain}: {e}")
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
                
                is_blocked = self.check_single_domain(domain)
                
                if is_blocked:
                    all_blocked.append(domain)
                    logger.warning(f"🚫 {domain}: TERBLOKIR")
                else:
                    logger.info(f"✅ {domain}: AMAN")
                
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
            "🤖 *Nawala DNS Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** DNS Query via SOCKS5 Proxy\n"
            f"🔑 **Proxy:** {PROXY_HOST}:{PROXY_PORT}\n"
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
                "_Sumber: DNS Server Nawala via SOCKS5_"
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
                    "_Sumber: DNS Server Nawala via SOCKS5_"
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
        logger.info("🔄 MEMULAI PEMERIKSAAN DNS NAWALA")
        logger.info(f"🔑 Proxy: {PROXY_HOST}:{PROXY_PORT} (SOCKS5)")
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
    print("🚀 NAWALA DNS CHECKER BOT")
    print(f"🔑 Proxy: {PROXY_HOST}:{PROXY_PORT} (SOCKS5)")
    print("📌 Mode: DNS Query ke Server Nawala")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info(f"🌐 Proxy: {PROXY_HOST}:{PROXY_PORT} (SOCKS5)")
    
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
    logger.info("📍 Mode: DNS Query via SOCKS5")
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
        logger.info("💡 Install dengan: pip install requests schedule python-telegram-bot PySocks")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
