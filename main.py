import os
import sys
import asyncio
import requests
import schedule
import time
import json
import re
from datetime import datetime
from telegram import Bot
from telegram.ext import Application

# Setup logging
import logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
NAWALA_API_URL = "https://www.nawala.asia/api/check"

if not TOKEN or not CHAT_ID:
    logger.error("Token atau Chat ID tidak ditemukan!")
    sys.exit(1)

# Bot setup
application = Application.builder().token(TOKEN).build()

class DomainChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.checking_stats = {
            "nawala_api": 0,
            "skiddle_api": 0,
            "direct_check": 0,
            "failed_checks": 0
        }
    
    def extract_domain(self, url):
        """Extract domain from URL like the JavaScript function"""
        try:
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'http://' + url
            
            # Simple domain extraction
            if '://' in url:
                domain = url.split('://')[1].split('/')[0]
            else:
                domain = url.split('/')[0]
            
            # Remove www prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Validate domain format
            domain_regex = r'^(?!:\/\/)([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$'
            if re.match(domain_regex, domain):
                return domain.lower()
            return None
        except Exception as e:
            logger.error(f"Error extracting domain from {url}: {e}")
            return None
    
    def baca_domain(self):
        """Read domains from file with validation"""
        try:
            with open("domain.txt", "r") as f:
                domains = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        domain = self.extract_domain(line)
                        if domain:
                            domains.append(domain)
                
                # Remove duplicates and limit to 100 like the website
                unique_domains = list(set(domains))[:100]
                logger.info(f"Loaded {len(unique_domains)} unique domains")
                return unique_domains
        except Exception as e:
            logger.error(f"Error reading domain.txt: {e}")
            return []
    
    def cek_nawala_api(self, domains):
        """Check domains using NawalaAsia-like API"""
        try:
            self.checking_stats["nawala_api"] += 1
            
            # Prepare data like the website
            domains_text = "\n".join(domains)
            data = {
                "domains": domains_text,
                "recaptchaToken": "dummy_token"
            }
            
            response = self.session.post(NAWALA_API_URL, data=data, timeout=30)
            if response.status_code == 200:
                logger.info("✅ NawalaAPI: Berhasil")
                return response.json()
            else:
                logger.warning(f"❌ NawalaAPI: Error {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ NawalaAPI: Gagal - {e}")
            return None
    
    def cek_skiddle_api(self, domain):
        """Check using Skiddle API"""
        try:
            self.checking_stats["skiddle_api"] += 1
            
            url = f"https://check.skiddle.id/?domains={domain}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ SkiddleAPI: Berhasil cek {domain}")
                
                if domain in data and data[domain].get("blocked", False):
                    return {"domain": domain, "status": "Blocked", "source": "skiddle"}
                else:
                    return {"domain": domain, "status": "Not Blocked", "source": "skiddle"}
            else:
                logger.warning(f"❌ SkiddleAPI: Error {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ SkiddleAPI: Gagal - {e}")
            return None
    
    def cek_direct(self, domain):
        """Direct HTTP checking with pattern analysis"""
        try:
            self.checking_stats["direct_check"] += 1
            
            test_urls = [
                f"http://{domain}",
                f"https://{domain}"
            ]
            
            for url in test_urls:
                try:
                    response = self.session.get(url, timeout=8, allow_redirects=True)
                    content = response.text.lower()
                    
                    # Blocking patterns
                    blocking_patterns = [
                        "nawala", "trustpositif", "kominfo", "blokir", "diblokir",
                        "180.131.144", "180.131.145", "internet positif",
                        "site is blocked", "akses diblokir"
                    ]
                    
                    # Check if any blocking pattern exists
                    if any(pattern in content for pattern in blocking_patterns):
                        logger.info(f"✅ DirectCheck: {domain} → BLOKIR (Pattern Match)")
                        return {"domain": domain, "status": "Blocked", "source": "direct"}
                    else:
                        logger.info(f"✅ DirectCheck: {domain} → AMAN")
                        return {"domain": domain, "status": "Not Blocked", "source": "direct"}
                        
                except requests.exceptions.RequestException as e:
                    continue
            
            # If all checks failed
            self.checking_stats["failed_checks"] += 1
            logger.warning(f"❌ DirectCheck: Semua metode gagal untuk {domain}")
            return {"domain": domain, "status": "Unknown", "source": "failed"}
            
        except Exception as e:
            logger.error(f"❌ DirectCheck: Error - {e}")
            return {"domain": domain, "status": "Error", "source": "error"}
    
    def get_checking_stats(self):
        """Get statistics of checking methods used"""
        return self.checking_stats.copy()
    
    def reset_stats(self):
        """Reset statistics for new checking session"""
        self.checking_stats = {
            "nawala_api": 0,
            "skiddle_api": 0,
            "direct_check": 0,
            "failed_checks": 0
        }
    
    async def cek_domain(self):
        """Main domain checking function"""
        domains = self.baca_domain()
        if not domains:
            logger.warning("Tidak ada domain yang valid untuk dicek")
            return
        
        # Reset stats for new session
        self.reset_stats()
        
        logger.info(f"🔄 Memulai pengecekan {len(domains)} domain...")
        
        blocked_domains = []
        checking_details = []  # Untuk menyimpan detail sumber pengecekan
        
        # Try Nawala API first for bulk checking
        api_result = self.cek_nawala_api(domains)
        
        if api_result and api_result.get("status") == "success":
            # Process API response
            for item in api_result.get("data", []):
                domain = item.get("domain")
                status = item.get("status")
                if status == "Blocked":
                    blocked_domains.append(domain)
                    checking_details.append(f"• `{domain}` - 🔧 *NawalaAPI*")
                    logger.info(f"🚫 {domain} → BLOKIR (NawalaAPI)")
        else:
            # Fallback to individual checking
            logger.info("🔄 Menggunakan metode pengecekan individual...")
            
            for domain in domains:
                # Try Skiddle API first
                result = self.cek_skiddle_api(domain)
                
                if not result:
                    # Fallback to direct checking
                    result = self.cek_direct(domain)
                
                if result and result.get("status") == "Blocked":
                    blocked_domains.append(domain)
                    source = result.get("source", "unknown")
                    
                    if source == "skiddle":
                        checking_details.append(f"• `{domain}` - 🎯 *SkiddleAPI*")
                        logger.info(f"🚫 {domain} → BLOKIR (SkiddleAPI)")
                    elif source == "direct":
                        checking_details.append(f"• `{domain}` - 🌐 *DirectCheck*")
                        logger.info(f"🚫 {domain} → BLOKIR (DirectCheck)")
                    else:
                        checking_details.append(f"• `{domain}` - ❓ *Unknown*")
                        logger.info(f"🚫 {domain} → BLOKIR (Unknown)")
        
        # Send notification with detailed report
        stats = self.get_checking_stats()
        await self.kirim_laporan(blocked_domains, checking_details, stats, len(domains))
    
    async def kirim_laporan(self, blocked_domains, checking_details, stats, total_domains):
        """Send detailed report to Telegram"""
        try:
            waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            
            if blocked_domains:
                # Detailed report with sources
                message = "🚫 *LAPORAN BLOKIR TRUSTPOSITIF*\n\n"
                message += f"📊 **Statistik Pengecekan:**\n"
                message += f"• Total Domain: `{total_domains}`\n"
                message += f"• Terblokir: `{len(blocked_domains)}`\n"
                message += f"• Aman: `{total_domains - len(blocked_domains)}`\n\n"
                
                message += "🔧 **Metode Pengecekan:**\n"
                message += f"• NawalaAPI: `{stats['nawala_api']}`x\n"
                message += f"• SkiddleAPI: `{stats['skiddle_api']}`x\n"
                message += f"• DirectCheck: `{stats['direct_check']}`x\n"
                message += f"• Gagal: `{stats['failed_checks']}`x\n\n"
                
                message += "📋 **Domain Terblokir:**\n"
                for detail in checking_details:
                    message += f"{detail}\n"
                
                message += f"\n⏰ *Waktu:* {waktu}"
                
            else:
                # No blocking report
                message = "✅ *LAPORAN MONITORING TRUSTPOSITIF*\n\n"
                message += f"📊 **Statistik Pengecekan:**\n"
                message += f"• Total Domain: `{total_domains}`\n"
                message += f"• Terblokir: `0` (Semua Aman) ✅\n\n"
                
                message += "🔧 **Metode Pengecekan:**\n"
                message += f"• NawalaAPI: `{stats['nawala_api']}`x\n"
                message += f"• SkiddleAPI: `{stats['skiddle_api']}`x\n"
                message += f"• DirectCheck: `{stats['direct_check']}`x\n"
                message += f"• Gagal: `{stats['failed_checks']}`x\n\n"
                
                message += "🎉 *Semua domain dapat diakses dengan normal!*\n"
                message += f"\n⏰ *Waktu:* {waktu}"
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            
            logger.info(f"📨 Laporan terkirim: {len(blocked_domains)} domain terblokir")
            
        except Exception as e:
            logger.error(f"❌ Gagal mengirim laporan: {e}")

async def kirim_status():
    """Send bot status"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        message = (
            "🤖 *Bot TrustPositif Checker Aktif*\n\n"
            f"✅ Status: Berjalan normal\n"
            f"⏰ Waktu: {waktu}\n"
            f"🔍 Fitur: Auto-check setiap 5 menit\n"
            f"📊 Monitoring: Real-time TrustPositif\n"
            f"🔧 Sumber: NawalaAPI + SkiddleAPI + DirectCheck\n\n"
            "📋 *Daftar Domain:* https://ceknawalaonline.pro/grup49/"
        )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("✅ Status bot terkirim")
    except Exception as e:
        logger.error(f"❌ Gagal kirim status: {e}")

async def tugas_utama():
    """Main task scheduler"""
    checker = DomainChecker()
    
    try:
        # Schedule tasks
        schedule.every(5).minutes.do(lambda: asyncio.create_task(checker.cek_domain()))
        schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
        
        # Run immediately
        await checker.cek_domain()
        await kirim_status()
        
        logger.info("🚀 Bot TrustPositif Checker berhasil dijalankan!")
        
        # Main loop
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ Error dalam tugas utama: {e}")

if __name__ == "__main__":
    try:
        # Create domain.txt if not exists
        if not os.path.exists("domain.txt"):
            with open("domain.txt", "w") as f:
                f.write("# Masukkan domain yang ingin dipantau\n")
                f.write("# Satu domain per baris\n")
                f.write("google.com\n")
                f.write("youtube.com\n")
                f.write("facebook.com\n")
                f.write("instagram.com\n")
                f.write("twitter.com\n")
            logger.info("📁 File domain.txt created with examples")
        
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("⏹️ Bot dihentikan oleh pengguna")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        logger.info("🛑 Bot TrustPositif Checker berhenti")
