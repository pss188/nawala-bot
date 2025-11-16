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
            # Prepare data like the website
            domains_text = "\n".join(domains)
            data = {
                "domains": domains_text,
                "recaptchaToken": "dummy_token"
            }
            
            response = self.session.post(NAWALA_API_URL, data=data, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error checking Nawala API: {e}")
            return None
    
    def cek_domain_alternative(self, domain):
        """Alternative checking method if API fails"""
        try:
            # Try multiple methods
            check_urls = [
                f"https://check.skiddle.id/?domains={domain}",
            ]
            
            for url in check_urls:
                try:
                    response = self.session.get(url, timeout=10, allow_redirects=True)
                    
                    if response.status_code == 200:
                        # For Skiddle API
                        if "skiddle.id" in url:
                            data = response.json()
                            if domain in data and data[domain].get("blocked", False):
                                return {"domain": domain, "status": "Blocked"}
                            else:
                                return {"domain": domain, "status": "Not Blocked"}
                        
                        # Direct check content analysis
                        content = response.text.lower()
                        blocking_indicators = [
                            "nawala", "trustpositif", "kominfo", "blokir",
                            "180.131.144", "180.131.145"
                        ]
                        
                        if any(indicator in content for indicator in blocking_indicators):
                            return {"domain": domain, "status": "Blocked"}
                            
                        return {"domain": domain, "status": "Not Blocked"}
                        
                except Exception as e:
                    logger.warning(f"Check failed for {url}: {e}")
                    continue
            
            return {"domain": domain, "status": "Unknown"}
            
        except Exception as e:
            logger.error(f"Error in alternative check for {domain}: {e}")
            return {"domain": domain, "status": "Error"}
    
    async def cek_domain(self):
        """Main domain checking function"""
        domains = self.baca_domain()
        if not domains:
            logger.warning("Tidak ada domain yang valid untuk dicek")
            return
        
        logger.info(f"Memulai pengecekan {len(domains)} domain...")
        
        # Try Nawala API first (sync)
        api_result = self.cek_nawala_api(domains)
        
        blocked_domains = []
        if api_result and api_result.get("status") == "success":
            # Process API response
            for item in api_result.get("data", []):
                if item.get("status") == "Blocked":
                    blocked_domains.append(item.get("domain"))
                    logger.info(f"Domain diblokir (API): {item.get('domain')}")
        else:
            # Fallback to alternative checking
            logger.info("Menggunakan metode pengecekan alternatif...")
            for domain in domains:
                result = self.cek_domain_alternative(domain)
                if result.get("status") == "Blocked":
                    blocked_domains.append(result.get("domain"))
                    logger.info(f"Domain diblokir (Alternative): {result.get('domain')}")
        
        # Send notification if blocked domains found
        if blocked_domains:
            message = "🚫 *Domain Terblokir TrustPositif:*\n\n"
            for domain in blocked_domains:
                message += f"• `{domain}`\n"
            
            message += f"\n⏰ {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
            
            try:
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"Notifikasi terkirim untuk {len(blocked_domains)} domain terblokir")
            except Exception as e:
                logger.error(f"Gagal mengirim notifikasi: {e}")
        else:
            logger.info("Tidak ada domain yang terblokir")

async def kirim_status():
    """Send bot status"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        message = (
            "🤖 *Bot TrustPositif Checker Aktif*\n\n"
            f"✅ Status: Berjalan normal\n"
            f"⏰ Waktu: {waktu}\n"
            f"🔍 Fitur: Auto-check setiap 5 menit\n"
            f"📊 Monitoring: Real-time TrustPositif\n\n"
            "📋 *Daftar Domain:* https://ceknawalaonline.pro/grup49/"
        )
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("Status bot terkirim")
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

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
        
        logger.info("Bot TrustPositif Checker berhasil dijalankan!")
        
        # Main loop
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error dalam tugas utama: {e}")

if __name__ == "__main__":
    try:
        # Create domain.txt if not exists
        if not os.path.exists("domain.txt"):
            with open("domain.txt", "w") as f:
                f.write("# Masukkan domain yang ingin dipantau\n")
                f.write("# Satu domain per baris\n")
                f.write("example.com\n")
                f.write("google.com\n")
                f.write("youtube.com\n")
                f.write("facebook.com\n")
            logger.info("File domain.txt created with examples")
        
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh pengguna")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        logger.info("Bot TrustPositif Checker berhenti")
