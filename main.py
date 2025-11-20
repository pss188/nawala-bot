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
from typing import List, Dict, Optional

# Setup logging
import logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NAWALA_API_URL = "https://www.nawala.asia/api/check"
DOMAIN_FILE = "domain.txt"

# Validate required environment variables
if not TOKEN or not CHAT_ID:
    logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables not found!")
    sys.exit(1)

class DomainChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        })
        self.timeout = 15
        self.max_retries = 2
    
    def extract_domain(self, url: str) -> Optional[str]:
        """Extract and validate domain from URL"""
        try:
            # Clean the input
            url = url.strip()
            if not url:
                return None
            
            # Add protocol if missing
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            
            # Extract domain
            domain = url.split('://', 1)[1].split('/', 1)[0]
            
            # Remove www prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Validate domain format
            domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
            if re.match(domain_pattern, domain):
                return domain.lower()
            
            return None
            
        except Exception as e:
            logger.debug(f"Domain extraction failed for '{url}': {e}")
            return None
    
    def baca_domain(self) -> List[str]:
        """Read and validate domains from file"""
        domains = []
        
        if not os.path.exists(DOMAIN_FILE):
            logger.error(f"Domain file '{DOMAIN_FILE}' not found!")
            return domains
        
        try:
            with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    domain = self.extract_domain(line)
                    if domain:
                        domains.append(domain)
                    else:
                        logger.warning(f"Invalid domain format at line {line_num}: {line}")
            
            # Remove duplicates while preserving order
            unique_domains = []
            seen = set()
            for domain in domains:
                if domain not in seen:
                    seen.add(domain)
                    unique_domains.append(domain)
            
            # Limit to reasonable number
            unique_domains = unique_domains[:200]
            logger.info(f"Loaded {len(unique_domains)} valid domains from {DOMAIN_FILE}")
            return unique_domains
            
        except Exception as e:
            logger.error(f"Error reading domain file: {e}")
            return []
    
    def cek_nawala_api(self, domains: List[str]) -> Optional[Dict]:
        """Check domains using NawalaAsia API"""
        try:
            domains_text = "\n".join(domains)
            data = {
                "domains": domains_text,
                "recaptchaToken": "dummy_token"
            }
            
            response = self.session.post(
                NAWALA_API_URL, 
                data=data, 
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    return result
                else:
                    logger.warning("Nawala API returned non-success status")
                    return None
            else:
                logger.warning(f"Nawala API returned status code: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Nawala API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Nawala API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Nawala API: {e}")
            return None
    
    def cek_skiddle_api(self, domain: str) -> Optional[Dict]:
        """Check using Skiddle API"""
        try:
            url = f"https://check.skiddle.id/?domains={domain}"
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if domain in data:
                    blocked_status = data[domain].get("blocked", False)
                    return {
                        "domain": domain, 
                        "status": "Blocked" if blocked_status else "Not Blocked", 
                        "source": "SkiddleAPI"
                    }
                else:
                    logger.warning(f"Domain {domain} not found in Skiddle API response")
                    return None
            else:
                logger.warning(f"Skiddle API returned status code: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"Skiddle API request timed out for domain: {domain}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Skiddle API request error for domain {domain}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Skiddle API for domain {domain}: {e}")
            return None
    
    async def cek_domain(self):
        """Main domain checking function - hanya kirim laporan jika ada yang diblokir"""
        domains = self.baca_domain()
        if not domains:
            logger.warning("No domains to check")
            return
        
        logger.info(f"Checking {len(domains)} domains using Nawala API and Skiddle API...")
        
        blocked_domains = []
        
        # Try Nawala API first for bulk checking
        api_result = self.cek_nawala_api(domains)
        
        if api_result and api_result.get("status") == "success":
            logger.info("Nawala API check successful")
            for item in api_result.get("data", []):
                if item.get("status") == "Blocked":
                    blocked_domains.append({
                        "domain": item.get("domain"),
                        "source": "NawalaAPI"
                    })
        else:
            logger.warning("Nawala API failed, falling back to Skiddle API")
            # Fallback to Skiddle API individual checking
            for domain in domains:
                result = self.cek_skiddle_api(domain)
                if result and result.get("status") == "Blocked":
                    blocked_domains.append({
                        "domain": result.get("domain"),
                        "source": result.get("source", "SkiddleAPI")
                    })
                # Add small delay to be nice to the API
                await asyncio.sleep(0.5)
        
        # Hanya kirim laporan jika ada domain yang diblokir
        if blocked_domains:
            await self.kirim_laporan_simple(blocked_domains, len(domains))
        else:
            logger.info("Tidak ada domain yang diblokir - skip laporan")
    
    async def kirim_laporan_simple(self, blocked_domains: List[Dict], total_domains: int):
        """Send simple report to Telegram hanya jika ada yang diblokir"""
        try:
            waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            
            # Buat pesan yang lebih informatif
            message = "🚨 *LAPORAN DOMAIN TERBLOKIR* 🚨\n\n"
            message += "📋 *Domain Terblokir:*\n"
            
            for i, item in enumerate(blocked_domains, 1):
                message += f"{i}. 🚫 `{item['domain']}`\n"
                message += f"   🔧 Sumber: {item['source']}\n\n"
            
            message += f"📊 *Statistik:*\n"
            message += f"• Terblokir: {len(blocked_domains)}\n"
            message += f"• Total: {total_domains}\n"
            message += f"• Persentase: {(len(blocked_domains)/total_domains)*100:.1f}%\n\n"
            message += f"⏰ *Waktu Check:* {waktu}"
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            
            logger.info(f"Laporan terblokir terkirim: {len(blocked_domains)} domain")
            
        except Exception as e:
            logger.error(f"Gagal kirim laporan: {e}")

async def kirim_status():
    """Send bot status setiap 30 menit"""
    try:
        checker = DomainChecker()
        domains = checker.baca_domain()
        total_domains = len(domains)
        
        waktu = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        message = (
            "🤖 *Bot TrustPositif Monitor*\n\n"
            "✅ *Status:* Active\n"
            f"🔍 *Monitoring:* {total_domains} domains\n"
            f"🕒 *Interval Check:* 2 menit\n"
            f"📊 *Status Report:* 30 menit\n"
            f"🔧 *Metode:* NawalaAPI + SkiddleAPI\n\n"
            f"⏰ *Update:* {waktu}"
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
        schedule.every(2).minutes.do(lambda: asyncio.create_task(checker.cek_domain()))
        schedule.every(30).minutes.do(lambda: asyncio.create_task(kirim_status()))
        
        # Jalankan segera saat startup
        await checker.cek_domain()
        await kirim_status()
        
        logger.info("Bot started successfully!")
        logger.info("✅ Domain check: setiap 2 menit (NawalaAPI + SkiddleAPI)")
        logger.info("✅ Status report: setiap 30 menit")
        logger.info("✅ Laporan: hanya jika ada yang terblokir")
        
        # Main loop
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Main task error: {e}")

def buat_file_domain_contoh():
    """Create example domain file if not exists"""
    if not os.path.exists(DOMAIN_FILE):
        try:
            with open(DOMAIN_FILE, "w", encoding="utf-8") as f:
                f.write("# Domain untuk monitoring TrustPositif\n")
                f.write("# Satu domain per baris\n")
                f.write("# Format: domain.com atau www.domain.com\n\n")
                f.write("google.com\n")
                f.write("youtube.com\n")
                f.write("facebook.com\n")
                f.write("instagram.com\n")
                f.write("twitter.com\n")
                f.write("tiktok.com\n")
                f.write("whatsapp.com\n")
                f.write("telegram.org\n")
                f.write("netflix.com\n")
                f.write("spotify.com\n")
            logger.info(f"File {DOMAIN_FILE} created with example domains")
        except Exception as e:
            logger.error(f"Gagal membuat file {DOMAIN_FILE}: {e}")

if __name__ == "__main__":
    try:
        # Setup
        buat_file_domain_contoh()
        
        # Run main task
        asyncio.run(tugas_utama())
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        sys.exit(1)
