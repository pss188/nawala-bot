import os
import sys
import time
import hashlib
import requests
import asyncio
import logging
from telegram.ext import Application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    logger.error("TOKEN atau CHAT_ID tidak ditemukan!")
    sys.exit(1)

# Bot setup
application = Application.builder().token(TOKEN).build()

class NawalaChecker:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.nawala.asia"
        
    def get_csrf_token(self):
        """Dapatkan CSRF token dari homepage"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            if response.status_code == 200:
                # Cari token dalam HTML
                html = response.text
                # Cari input hidden yang mungkin mengandung token
                import re
                token_patterns = [
                    r'name="csrf_token"\s+value="([^"]+)"',
                    r'name="_token"\s+value="([^"]+)"',
                    r'name="token"\s+value="([^"]+)"'
                ]
                for pattern in token_patterns:
                    match = re.search(pattern, html)
                    if match:
                        return match.group(1)
        except Exception as e:
            logger.error(f"Error get CSRF: {e}")
        return ""
    
    def simulate_browser_request(self, domains):
        """Simulasi request browser lengkap"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.base_url,
                'Referer': self.base_url + '/',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
            }
            
            # Format domains
            domains_text = "\n".join(domains[:20])  # Max 20 dulu
            
            # Data form
            form_data = {
                'domains': domains_text,
                'recaptchaToken': self.generate_dummy_captcha(),
                'action': 'check'
            }
            
            # URL target (dari form action)
            check_url = self.base_url + "/"  # Form submit ke root
            
            logger.info(f"Mengirim {len(domains)} domain ke nawala.asia...")
            
            response = self.session.post(
                check_url,
                data=form_data,
                headers=headers,
                timeout=30,
                allow_redirects=True
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                return self.parse_response(response.text, domains)
            else:
                logger.error(f"HTTP Error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error simulate request: {e}")
            return []
    
    def generate_dummy_captcha(self):
        """Generate dummy recaptcha token"""
        timestamp = str(int(time.time()))
        return f"dummy_token_{timestamp}_{hashlib.md5(timestamp.encode()).hexdigest()[:10]}"
    
    def parse_response(self, html, original_domains):
        """Parse HTML response untuk cari hasil"""
        blocked = []
        
        try:
            # Cari tabel hasil
            lines = html.split('\n')
            in_table = False
            
            for line in lines:
                line_lower = line.lower()
                
                # Cari awal tabel
                if '<table' in line_lower and 'result' in line_lower:
                    in_table = True
                    continue
                
                if in_table and '</table>' in line_lower:
                    break
                
                # Cari baris dengan domain
                if in_table and '<tr>' in line_lower:
                    # Ekstrak domain dan status dari baris
                    for domain in original_domains:
                        if domain in line:
                            # Cek status blocked
                            if 'blocked' in line_lower or '🚫' in line or 'text-danger' in line_lower:
                                blocked.append(f"🚫 *{domain}*")
                                logger.warning(f"Terblokir ditemukan: {domain}")
                                break
            
            # Alternatif parsing
            if not blocked:
                for domain in original_domains:
                    if domain in html:
                        # Cek pattern blocked
                        pattern1 = f'{domain}.*?(blocked|terblokir|🚫|text-danger)'
                        import re
                        if re.search(pattern1, html, re.IGNORECASE):
                            blocked.append(f"🚫 *{domain}*")
                            logger.warning(f"Terblokir (regex): {domain}")
        
        except Exception as e:
            logger.error(f"Error parse response: {e}")
        
        return blocked
    
    def check_domains(self, domains):
        """Main check function"""
        return self.simulate_browser_request(domains)

def baca_domain():
    try:
        with open("domain.txt", "r") as f:
            return [line.strip().lower() for line in f 
                   if line.strip() and not line.startswith('#')]
    except:
        return []

async def kirim_status():
    try:
        await application.bot.send_message(
            CHAT_ID,
            f"🤖 *Nawala Bot Aktif*\n{time.strftime('%d-%m-%Y %H:%M:%S')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Status error: {e}")

async def kirim_laporan(blocked, total):
    if not blocked:
        await application.bot.send_message(
            CHAT_ID,
            f"✅ *Semua Aman*\n{total} domain checked\n{time.strftime('%H:%M:%S')}",
            parse_mode="Markdown"
        )
        return
    
    # Buat pesan
    chunks = []
    current = f"🔔 *Domain Terblokir*\n\n"
    
    for domain in blocked:
        if len(current) + len(domain) + 10 > 4000:
            chunks.append(current)
            current = f"*Lanjutan...*\n\n"
        current += f"{domain}\n"
    
    if current:
        current += f"\n📊 {len(blocked)}/{total} domain"
        current += f"\n⏰ {time.strftime('%d-%m-%Y %H:%M:%S')}"
        chunks.append(current)
    
    # Kirim semua chunks
    for chunk in chunks:
        await application.bot.send_message(CHAT_ID, chunk, parse_mode="Markdown")
        await asyncio.sleep(1)

def cek_domain_job():
    """Job untuk schedule"""
    try:
        domains = baca_domain()
        if not domains:
            return
        
        checker = NawalaChecker()
        blocked = checker.check_domains(domains)
        
        asyncio.create_task(kirim_laporan(blocked, len(domains)))
        
    except Exception as e:
        logger.error(f"Job error: {e}")

async def main():
    logger.info("🚀 Nawala.Asia Bot Starting...")
    
    await kirim_status()
    
    # Schedule
    schedule.every(15).minutes.do(cek_domain_job)
    
    # Run first check
    await asyncio.sleep(2)
    cek_domain_job()
    
    logger.info("✅ Bot running...")
    
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Fatal: {e}")
