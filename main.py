import os
import sys
import time
import schedule
import requests
import asyncio
import json
import logging
from telegram.ext import Application

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
    logger.error("Token atau Chat ID tidak ditemukan!")
    sys.exit(1)

# Proxy configuration
PROXY_HOST = "95.135.92.164"
PROXY_PORT_HTTP = 59100
PROXY_PORT_SOCKS5 = 59101
PROXY_USERNAME = "pulsaslot1888"
PROXY_PASSWORD = "b3Kft6IMwG"

# Proxy URLs
PROXY_HTTP = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_HTTP}"
PROXY_SOCKS5 = f"socks5://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT_SOCKS5}"

# Konfigurasi proxy untuk requests
proxies = {
    'http': PROXY_HTTP,
    'https': PROXY_HTTP,
}

# Bot setup dengan proxy SOCKS5
try:
    application = Application.builder()\
        .token(TOKEN)\
        .get_updates_proxy_url(PROXY_SOCKS5)\
        .build()
    logger.info("Bot berhasil diinisialisasi dengan proxy SOCKS5")
except Exception as e:
    logger.warning(f"Gagal setup proxy SOCKS5: {e}. Menggunakan tanpa proxy...")
    application = Application.builder().token(TOKEN).build()

# Session dengan retry
session = requests.Session()
session.proxies.update(proxies)

def baca_domain():
    """Baca domain dari file domain.txt"""
    try:
        with open("domain.txt", "r") as f:
            domains = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Bersihkan domain
                    for prefix in ['http://', 'https://', 'www.']:
                        if line.startswith(prefix):
                            line = line[len(prefix):]
                    line = line.rstrip('/')
                    if '.' in line and len(line) > 3:
                        domains.append(line.lower())
            return domains
    except Exception as e:
        logger.error(f"Error baca domain: {e}")
        return []

async def kirim_status():
    """Kirim status bot"""
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Monitoring Domain* aktif!\n⏰ {waktu}\n📍 Skiddle.id API",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

def cek_domain_skiddle(domains):
    """Cek domain menggunakan API Skiddle.id - SIMPLE VERSION"""
    try:
        if not domains:
            return []
        
        blocked_domains = []
        
        # Skiddle API bisa handle multiple domain sekaligus
        domains_str = ','.join(domains)
        api_url = f"https://check.skiddle.id/?domains={domains_str}"
        
        logger.info(f"Checking {len(domains)} domains via Skiddle...")
        
        response = session.get(api_url, timeout=15)
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                for domain in domains:
                    if domain in data:
                        domain_data = data[domain]
                        if isinstance(domain_data, dict) and domain_data.get('blocked', False):
                            blocked_domains.append(f"🚫 *{domain}*")
                            logger.warning(f"Blocked: {domain}")
                        else:
                            logger.info(f"OK: {domain}")
                    else:
                        logger.warning(f"Domain not in response: {domain}")
                        
            except json.JSONDecodeError:
                logger.error("Invalid JSON response")
                # Fallback: cek satu per satu
                for domain in domains:
                    try:
                        single_url = f"https://check.skiddle.id/?domains={domain}"
                        resp = session.get(single_url, timeout=10)
                        if resp.status_code == 200:
                            single_data = resp.json()
                            if domain in single_data and single_data[domain].get('blocked', False):
                                blocked_domains.append(f"🚫 *{domain}*")
                                logger.warning(f"Blocked (single): {domain}")
                            else:
                                logger.info(f"OK (single): {domain}")
                        time.sleep(0.5)
                    except:
                        pass
        
        return blocked_domains
        
    except Exception as e:
        logger.error(f"Error checking domains: {e}")
        return []

def cek_domain_sync():
    """Fungsi synchronous untuk cek domain"""
    try:
        domains = baca_domain()
        
        if not domains:
            logger.info("No domains to check")
            return
        
        logger.info(f"Checking {len(domains)} domains...")
        
        # Gunakan Skiddle API
        blocked = cek_domain_skiddle(domains)
        
        # Kirim laporan
        if blocked:
            asyncio.create_task(kirim_laporan(blocked, len(domains)))
        else:
            asyncio.create_task(kirim_laporan_aman(len(domains)))
            
        logger.info(f"Done. {len(blocked)} domains blocked.")
        
    except Exception as e:
        logger.error(f"Error in check: {e}")

async def kirim_laporan(blocked_list, total):
    """Kirim laporan domain terblokir"""
    try:
        if not blocked_list:
            return
            
        message = f"🔔 *DOMAIN BLOCK REPORT*\n\n"
        message += "\n".join(blocked_list)
        message += f"\n\n📊 *Summary:* {len(blocked_list)}/{total} domains blocked"
        message += f"\n⏰ {time.strftime('%d-%m-%Y %H:%M:%S')}"
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Failed to send report: {e}")

async def kirim_laporan_aman(total):
    """Kirim laporan jika semua domain aman"""
    try:
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"✅ *ALL DOMAINS ARE SAFE*\n\n"
                 f"No blocked domains found!\n"
                 f"Total checked: {total}\n"
                 f"Time: {time.strftime('%d-%m-%Y %H:%M:%S')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to send safe report: {e}")

async def tugas_utama():
    """Main function"""
    logger.info("🚀 Starting Domain Monitor Bot...")
    
    # Test connection
    try:
        test = session.get("https://check.skiddle.id/?domains=google.com", timeout=10)
        if test.status_code == 200:
            logger.info("✅ Skiddle API is working")
        else:
            logger.warning(f"⚠️ Skiddle API returned {test.status_code}")
    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")
    
    # Schedule tasks
    schedule.every(5).minutes.do(cek_domain_sync)
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    
    # Run immediately
    await kirim_status()
    await asyncio.sleep(2)
    cek_domain_sync()
    
    logger.info("✅ Bot is running. Press Ctrl+C to stop.")
    
    # Main loop
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped")
            break
        except Exception as e:
            logger.error(f"Loop error: {e}")
            await asyncio.sleep(5)

def install_deps():
    """Install required packages"""
    try:
        import subprocess
        import importlib
        
        required = ['requests', 'schedule', 'python-telegram-bot']
        
        for package in required:
            try:
                if package == 'python-telegram-bot':
                    import telegram
                    logger.info(f"telegram-bot installed")
                else:
                    importlib.import_module(package)
                    logger.info(f"{package} installed")
            except ImportError:
                logger.info(f"Installing {package}...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                logger.info(f"{package} installed successfully")
                
    except Exception as e:
        logger.error(f"Failed to install dependencies: {e}")

# Create domain.txt if not exists
if not os.path.exists("domain.txt"):
    with open("domain.txt", "w") as f:
        f.write("# Add your domains here, one per line\n")
        f.write("google.com\n")
        f.write("facebook.com\n")
        f.write("example.com\n")
    logger.info("Created domain.txt template")

if __name__ == "__main__":
    install_deps()
    
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
