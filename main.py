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

class NawalaDNSChecker:
    def __init__(self):
        # DNS server ISP Indonesia (yang terkenal memblokir)
        self.dns_servers = [
            ("180.131.144.144", 53),  # Nawala
            ("180.131.145.145", 53),  # Nawala
            ("202.152.2.2", 53),      # MyRepublic
            ("103.12.160.2", 53),     # First Media
        ]
        
        # IP yang menunjukkan domain diblokir
        self.blocked_ips = [
            "114.127.223.16",  # IndiHome
            "180.131.144.144", # Nawala
            "0.0.0.0",
            "127.0.0.1",
        ]
    
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
        
        qtype = b'\x00\x01'
        qclass = b'\x00\x01'
        
        packet = transaction_id + flags + qdcount + ancount + nscount + arcount + qname + qtype + qclass
        return packet
    
    def _parse_dns_response(self, data):
        """Parse DNS response"""
        try:
            # Check if it's a response
            qr = (data[2] & 0x80) != 0
            if not qr:
                return None
            
            # Check TC flag (Truncated) - tanda blokir
            tc_flag = (data[2] & 0x02) != 0
            if tc_flag:
                return "BLOCKED_TC"
            
            # Check response code
            response_code = data[3] & 0x0F
            if response_code == 3:  # NXDOMAIN
                return "BLOCKED_NX"
            
            # Get answer count
            answer_count = struct.unpack('>H', data[6:8])[0]
            if answer_count > 0:
                # Cek IP address di answer
                try:
                    # Cari IP di response
                    ip_start = data.find(b'\xc0\x0c')  # Pointer ke nama
                    if ip_start != -1:
                        # Coba extract IP dari answer section
                        # Ini parsing sederhana, bisa lebih kompleks
                        pass
                except:
                    pass
                return "RESOLVED"
            else:
                return "NO_RECORD"
            
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return "ERROR"
    
    def check_via_dns(self, domain):
        """Cek domain via DNS query"""
        try:
            query = self._build_dns_query(domain)
            
            for dns_server, dns_port in self.dns_servers:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(3)
                    sock.sendto(query, (dns_server, dns_port))
                    data, addr = sock.recvfrom(512)
                    sock.close()
                    
                    result = self._parse_dns_response(data)
                    
                    if result in ["BLOCKED_TC", "BLOCKED_NX"]:
                        return "BLOCKED"
                    elif result == "RESOLVED":
                        return "SAFE"
                    elif result == "NO_RECORD":
                        return "SAFE"
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    continue
            
            return "TIMEOUT"
            
        except Exception as e:
            return "ERROR"
    
    def check_single_domain(self, domain):
        """Cek 1 domain"""
        try:
            logger.info(f"🔍 Checking: {domain}")
            
            result = self.check_via_dns(domain)
            
            if result == "BLOCKED":
                logger.warning(f"🚫 {domain}: DIBLOKIR")
                return True
            elif result in ["SAFE", "NO_RECORD"]:
                logger.info(f"✅ {domain}: AMAN")
                return False
            else:
                logger.warning(f"⚠️ {domain}: {result} - asumsi AMAN")
                return False
                
        except Exception as e:
            logger.error(f"Error: {e}")
            return False
    
    def check_all_domains(self, domains):
        """Cek semua domain"""
        try:
            if not domains:
                return []
            
            all_blocked = []
            total = len(domains)
            
            for i, domain in enumerate(domains, 1):
                logger.info(f"[{i}/{total}] {domain}")
                is_blocked = self.check_single_domain(domain)
                if is_blocked:
                    all_blocked.append(domain)
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
        logger.error(f"Error: {e}")
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
            "🤖 *Nawala Checker Bot*\n\n"
            f"✅ **Status:** Aktif & Berjalan\n"
            f"⏰ **Waktu:** {waktu}\n"
            f"📊 **Domain:** {domain_count} domain terdaftar\n"
            f"🔢 **Mode:** DNS Query\n"
            f"🌐 **DNS Server:** Nawala + ISP Indonesia\n\n"
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
                "_Sumber: DNS Server Nawala + ISP Indonesia_"
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
                    "_Sumber: DNS Server Nawala + ISP Indonesia_"
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
        logger.info("🔄 MEMULAI PEMERIKSAAN NAWALA VIA DNS")
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
            logger.info("🛑 Schedule runner dihentikan")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            await asyncio.sleep(5)

async def main():
    print("\n" + "=" * 60)
    print("🚀 NAWALA DNS CHECKER BOT")
    print("📌 Mode: DNS Query ke Server ISP Indonesia")
    print("=" * 60)
    
    logger.info("Bot starting...")
    
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
    logger.info("📍 Mode: DNS Query")
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
