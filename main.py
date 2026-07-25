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

class MultiISPDNSChecker:
    def __init__(self):
        # DNS Server ISP Indonesia
        self.dns_servers = [
            ("198.0.0.1", 53, "Telkomsel"),           # Telkomsel
            ("180.131.144.144", 53, "Nawala"),        # Nawala Kominfo
            ("180.131.145.145", 53, "Nawala"),        # Nawala Kominfo
            ("118.98.44.10", 53, "IndiHome"),         # IndiHome
            ("103.12.160.2", 53, "First Media"),      # First Media
            ("202.152.2.2", 53, "MyRepublic"),        # MyRepublic
        ]
        
        # IP yang menandakan domain diblokir
        self.blocked_ips = [
            "198.0.0.1",           # Telkomsel
            "180.131.144.144",     # Nawala
            "180.131.145.145",     # Nawala
            "114.127.223.16",      # IndiHome
            "36.86.63.182",        # IndiHome
            "0.0.0.0",
        ]
        
        self.timeout = 5
    
    def _build_dns_query(self, domain):
        """Bangun DNS query packet"""
        transaction_id = b'\xaa\xaa'
        flags = b'\x01\x00'
        qdcount = b'\x00\x01'
        ancount = b'\x00\x00'
        nscount = b'\x00\x00'
        arcount = b'\x00\x00'
        
        qname = b''
        for part in domain.split('.'):
            qname += bytes([len(part)]) + part.encode()
        qname += b'\x00'
        
        qtype = b'\x00\x01'  # A record
        qclass = b'\x00\x01'  # IN
        
        packet = transaction_id + flags + qdcount + ancount + nscount + arcount + qname + qtype + qclass
        return packet
    
    def _parse_dns_response(self, data):
        """Parse DNS response"""
        try:
            qr = (data[2] & 0x80) != 0
            if not qr:
                return None, None
            
            # Cek flag TC (Truncated) - tanda blokir
            tc_flag = (data[2] & 0x02) != 0
            if tc_flag:
                return "BLOCKED_TC", None
            
            # Cek response code
            response_code = data[3] & 0x0F
            
            # NXDOMAIN = domain tidak ada (bisa jadi blokir)
            if response_code == 3:
                return "BLOCKED_NX", None
            
            # NOERROR = domain ada
            if response_code == 0:
                answer_count = struct.unpack('>H', data[6:8])[0]
                
                if answer_count > 0:
                    ips = self._extract_ips(data)
                    
                    # Cek apakah IP termasuk IP blokir
                    for ip in ips:
                        if ip in self.blocked_ips:
                            return "BLOCKED_IP", ip
                    
                    return "RESOLVED", ips[0] if ips else None
                else:
                    return "NO_RECORD", None
            
            return f"ERROR_{response_code}", None
            
        except Exception as e:
            return "PARSE_ERROR", None
    
    def _extract_ips(self, data):
        """Ekstrak IP dari DNS response"""
        ips = []
        try:
            pos = 12
            
            # Skip question
            while pos < len(data):
                if data[pos] == 0:
                    pos += 5
                    break
                if data[pos] & 0xC0:
                    pos += 2
                    break
                pos += data[pos] + 1
            
            # Parse answer
            answer_count = struct.unpack('>H', data[6:8])[0]
            
            for _ in range(answer_count):
                if data[pos] & 0xC0:
                    pos += 2
                else:
                    while data[pos] != 0:
                        pos += data[pos] + 1
                    pos += 1
                
                qtype = struct.unpack('>H', data[pos:pos+2])[0]
                pos += 2
                pos += 2  # class
                pos += 4  # TTL
                data_len = struct.unpack('>H', data[pos:pos+2])[0]
                pos += 2
                
                if qtype == 1 and data_len == 4:
                    ip = f"{data[pos]}.{data[pos+1]}.{data[pos+2]}.{data[pos+3]}"
                    ips.append(ip)
                
                pos += data_len
            
        except Exception as e:
            pass
        
        return ips
    
    def check_via_dns(self, domain):
        """Cek domain via DNS query ke semua ISP"""
        results = {}
        
        for dns_server, dns_port, isp_name in self.dns_servers:
            try:
                query = self._build_dns_query(domain)
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(self.timeout)
                sock.sendto(query, (dns_server, dns_port))
                data, addr = sock.recvfrom(512)
                sock.close()
                
                status, ip = self._parse_dns_response(data)
                results[isp_name] = {
                    'status': status,
                    'ip': ip,
                    'server': dns_server
                }
                
                logger.debug(f"{isp_name} ({dns_server}): {domain} -> {status} ({ip})")
                
                # Jika terdeteksi blokir, langsung return True
                if status in ["BLOCKED_TC", "BLOCKED_NX", "BLOCKED_IP"]:
                    return True, isp_name, status
                
            except socket.timeout:
                results[isp_name] = {'status': 'TIMEOUT', 'ip': None, 'server': dns_server}
                continue
            except Exception as e:
                results[isp_name] = {'status': f'ERROR: {str(e)[:30]}', 'ip': None, 'server': dns_server}
                continue
        
        # Jika semua server mengembalikan RESOLVED atau NO_RECORD, domain aman
        return False, None, None
    
    def check_via_http_fallback(self, domain):
        """Fallback: cek via HTTP API"""
        try:
            # Coba ke trustpositif.id
            response = requests.post(
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
        """Cek 1 domain dengan semua metode"""
        try:
            logger.info(f"🔍 Checking: {domain}")
            
            # Metode 1: DNS via Multi-ISP
            is_blocked, isp_name, status = self.check_via_dns(domain)
            
            if is_blocked:
                logger.warning(f"🚫 {domain}: DIBLOKIR (DNS) - {isp_name} ({status})")
                return True
            
            # Metode 2: HTTP fallback
            logger.info(f"📡 Coba HTTP fallback untuk {domain}...")
            is_blocked = self.check_via_http_fallback(domain)
            
            if is_blocked:
                logger.warning(f"🚫 {domain}: DIBLOKIR (HTTP Fallback)")
                return True
            
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
            "🤖 *Multi-ISP DNS Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** Multi-ISP DNS Query\n"
            f"🌐 **DNS Server:** Telkomsel, Nawala, IndiHome, First Media, MyRepublic\n\n"
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
                "_Sumber: Multi-ISP DNS Checker_"
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
                    "_Sumber: Multi-ISP DNS Checker_"
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
        logger.info("🔄 MEMULAI PEMERIKSAAN MULTI-ISP DNS")
        logger.info("🌐 DNS Server: Telkomsel, Nawala, IndiHome, First Media, MyRepublic")
        logger.info("=" * 60)
        
        domains = baca_domain()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        checker = MultiISPDNSChecker()
        
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
    print("🚀 MULTI-ISP DNS CHECKER BOT")
    print("📌 Mode: DNS Query ke 5 ISP Indonesia")
    print("🌐 DNS: Telkomsel, Nawala, IndiHome, First Media, MyRepublic")
    print("=" * 60)
    
    logger.info("Bot starting...")
    logger.info("🌐 DNS Server: Telkomsel, Nawala, IndiHome, First Media, MyRepublic")
    
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
    logger.info("📍 Mode: Multi-ISP DNS Query")
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
