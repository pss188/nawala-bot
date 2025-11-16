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
            
            if '://' in url:
                domain = url.split('://')[1].split('/')[0]
            else:
                domain = url.split('/')[0]
            
            if domain.startswith('www.'):
                domain = domain[4:]
            
            domain_regex = r'^(?!:\/\/)([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$'
            if re.match(domain_regex, domain):
                return domain.lower()
            return None
        except Exception:
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
                
                unique_domains = list(set(domains))[:100]
                logger.info(f"Loaded {len(unique_domains)} domains")
                return unique_domains
        except Exception as e:
            logger.error(f"Error reading domain.txt: {e}")
            return []
    
    def cek_nawala_api(self, domains):
        """Check domains using NawalaAsia API"""
        try:
            domains_text = "\n".join(domains)
            data = {
                "domains": domains_text,
                "recaptchaToken": "dummy_token"
            }
            
            response = self.session.post(NAWALA_API_URL, data=data, timeout=30)
            if response.status_code == 200:
                return response.json()
            return None
                
        except Exception as e:
            logger.error(f"NawalaAPI error: {e}")
            return None
    
    def cek_skiddle_api(self, domain):
        """Check using Skiddle API"""
        try:
            url = f"https://check.skiddle.id/?domains={domain}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if domain in data and data[domain].get("blocked", False):
                    return {"domain": domain, "status": "Blocked", "source": "SkiddleAPI"}
                else:
                    return {"domain": domain, "status": "Not Blocked", "source": "SkiddleAPI"}
            return None
                
        except Exception:
            return None
    
    def cek_direct(self, domain):
        """Direct HTTP checking"""
        try:
            test_urls = [f"http://{domain}", f"https://{domain}"]
            
            for url in test_urls:
                try:
                    response = self.session.get(url, timeout=8, allow_redirects=True)
                    content = response.text.lower()
                    
                    blocking_patterns = [
                        "nawala", "trustpositif", "kominfo", "blokir", "diblokir",
                        "180.131.144", "180.131.145", "internet positif"
                    ]
                    
                    if any(pattern in content for pattern in blocking_patterns):
                        return {"domain": domain, "status": "Blocked", "source": "DirectCheck"}
                    else:
                        return {"domain": domain, "status": "Not Blocked", "source": "DirectCheck"}
                        
                except requests.exceptions.RequestException:
                    continue
            
            return {"domain": domain, "status": "Unknown", "source": "Failed"}
            
        except Exception:
            return {"domain": domain, "status": "Error", "source": "Error"}
    
    async def cek_domain(self):
        """Main domain checking function - hanya kirim laporan jika ada yang diblokir"""
        domains = self.baca_domain()
        if not domains:
            return
        
        logger.info(f"Checking {len(domains)} domains...")
        
        blocked_domains = []
        
        # Try Nawala API first for bulk checking
        api_result = self.cek_nawala_api(domains)
        
        if api_result and api_result.get("status") == "success":
            for item in api_result.get("data", []):
                if item.get("status") == "Blocked":
                    blocked_domains.append({
                        "domain": item.get("domain"),
                        "source": "NawalaAPI"
                    })
        else:
            # Fallback to individual checking
            for domain in domains:
                result = self.cek_skiddle_api(domain) or self.cek_direct(domain)
                if result and result.get("status") == "Blocked":
                    blocked_domains.append({
                        "domain": result.get("domain"),
                        "source": result.get("source", "Unknown")
                    })
        
        # Hanya kirim laporan jika ada domain yang diblokir
        if blocked_domains:
            await self.kirim_laporan_simple(blocked_domains, len(domains))
        else:
            logger.info("Tidak ada domain yang diblokir - skip laporan")
    
    async def kirim_laporan_simple(self, blocked_domains, total_domains):
        """Send simple report to Telegram hanya jika ada yang diblokir"""
        try:
            waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            
            message = "📋 *Domain Terblokir:*\n"
            for item in blocked_domains:
                message += f"🚫 {item['domain']} Blocked! 🔧 {item['source']}\n"
            
            message += f"\n📊 {len(blocked_domains)} dari {total_domains} domain\n"
            message += f"⏰ {waktu}"
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            
            logger.info(f"Laporan terblokir terkirim: {len(blocked_domains)} domain")
            
        except Exception as e:
            logger.error(f"Gagal kirim laporan: {e}")

async def kirim_status():
    """Send bot status setiap 30 menit"""
    try:
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        message = (
            "🤖 *Bot TrustPositif Aktif*\n"
            f"✅ Status: Monitoring\n"
            f"⏰ {waktu}\n"
            f"🔍 Auto-check 2 menit"
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
        # Schedule tasks sesuai permintaan
        schedule.every(2).minutes.do(lambda: asyncio.create_task(checker.cek_domain()))
        schedule.every(30).minutes.do(lambda: asyncio.create_task(kirim_status()))
        
        # Jalankan segera saat startup
        await checker.cek_domain()
        await kirim_status()
        
        logger.info("Bot started successfully!")
        logger.info("✅ Domain check: setiap 2 menit")
        logger.info("✅ Status report: setiap 30 menit")
        logger.info("✅ Laporan: hanya jika ada yang terblokir")
        
        # Main loop
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Main task error: {e}")

if __name__ == "__main__":
    try:
        # Create domain.txt if not exists
        if not os.path.exists("domain.txt"):
            with open("domain.txt", "w") as f:
                f.write("# Domain untuk monitoring TrustPositif\n")
                f.write("# Satu domain per baris\n")
                f.write("google.com\n")
                f.write("youtube.com\n")
                f.write("facebook.com\n")
                f.write("instagram.com\n")
                f.write("twitter.com\n")
            logger.info("File domain.txt created")
        
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
