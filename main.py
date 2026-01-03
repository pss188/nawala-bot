import os
import sys
import time
import schedule
import requests
import asyncio
import json
import re
from telegram import Bot
from telegram.ext import Application
import logging

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

# Session untuk requests
session = requests.Session()
session.proxies.update(proxies)

async def kirim_status():
    """Kirim status bot"""
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Monitoring Nawala* aktif!\n⏰ {waktu}\n📍 nawala.asia API",
            parse_mode="Markdown"
        )
        logger.info("Status bot terkirim")
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

def baca_domain():
    """Baca domain dari file domain.txt"""
    try:
        with open("domain.txt", "r") as f:
            domains = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Hapus http:// atau https:// jika ada
                    if line.startswith('http://'):
                        line = line[7:]
                    elif line.startswith('https://'):
                        line = line[8:]
                    # Hapus www. jika ada
                    if line.startswith('www.'):
                        line = line[4:]
                    # Hapus trailing slash
                    line = line.rstrip('/')
                    # Validasi domain
                    if re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$', line):
                        domains.append(line.lower())
                    else:
                        logger.warning(f"Domain tidak valid: {line}")
            return domains
    except Exception as e:
        logger.error(f"Error baca domain: {e}")
        return []

def get_recaptcha_token():
    """Generate reCAPTCHA token simulasi"""
    # Ini adalah token dummy, untuk production perlu implementasi proper
    # Atau gunakan service seperti 2captcha untuk solve captcha
    timestamp = int(time.time())
    dummy_token = f"dummy_recaptcha_token_{timestamp}_simulated"
    logger.info(f"Menggunakan token reCAPTCHA simulasi")
    return dummy_token

def cek_nawala_api(domains):
    """Cek status domain menggunakan API nawala.asia"""
    try:
        if not domains:
            logger.warning("Tidak ada domain untuk dicek")
            return []
        
        # Max 100 domain per request sesuai website
        if len(domains) > 100:
            logger.warning(f"Terlalu banyak domain ({len(domains)}). Hanya 100 pertama yang akan dicek")
            domains = domains[:100]
        
        # Format domains (satu per baris)
        domains_text = "\n".join(domains)
        
        # URL API dari nawala.asia
        api_url = "https://www.nawala.asia/api/check"
        
        # Headers untuk meniru browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.nawala.asia',
            'Referer': 'https://www.nawala.asia/',
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        # Data payload
        data = {
            'domains': domains_text,
            'recaptchaToken': get_recaptcha_token()
        }
        
        logger.info(f"Mengirim {len(domains)} domain ke nawala.asia API...")
        
        # Kirim request POST
        response = session.post(
            api_url,
            headers=headers,
            data=data,
            timeout=30
        )
        
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"Response JSON: {json.dumps(result, indent=2)[:500]}...")
                
                if result.get('status') == 'success':
                    data_results = result.get('data', [])
                    return parse_api_results(data_results)
                elif result.get('status') == 'error':
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"API error: {error_msg}")
                    
                    # Fallback: coba metode scraping jika API gagal
                    return cek_nawala_scraping(domains)
                else:
                    logger.error(f"Status tidak dikenali: {result.get('status')}")
                    return []
                    
            except json.JSONDecodeError as e:
                logger.error(f"Gagal parse JSON: {e}")
                logger.error(f"Response text: {response.text[:500]}")
                # Fallback ke scraping
                return cek_nawala_scraping(domains)
        else:
            logger.error(f"HTTP Error {response.status_code}")
            # Fallback ke scraping
            return cek_nawala_scraping(domains)
            
    except requests.exceptions.Timeout:
        logger.error("Timeout saat mengakses nawala.asia API")
        return []
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error cek nawala API: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def parse_api_results(data_results):
    """Parse hasil dari API response"""
    blocked_domains = []
    
    try:
        for item in data_results:
            if isinstance(item, dict):
                domain = item.get('domain', '')
                status = item.get('status', '')
                
                if domain and status and status.lower() == 'blocked':
                    blocked_domains.append(f"🚫 *{domain}* - Terblokir")
                    logger.warning(f"Domain terblokir: {domain}")
                elif domain:
                    logger.info(f"Domain aman: {domain}")
    
    except Exception as e:
        logger.error(f"Error parse API results: {e}")
    
    return blocked_domains

def cek_nawala_scraping(domains):
    """Fallback method dengan scraping langsung"""
    try:
        blocked_domains = []
        
        for domain in domains[:10]:  # Batasi untuk tidak overload
            try:
                # Coba akses domain melalui nawala.asia proxy
                test_url = f"https://www.nawala.asia/proxy-check/{domain}"
                
                response = session.get(
                    test_url,
                    timeout=10,
                    allow_redirects=False
                )
                
                # Jika redirect atau block tertentu
                if response.status_code in [302, 403, 503]:
                    blocked_domains.append(f"🚫 *{domain}* - Terblokir (scraping)")
                    logger.warning(f"Domain terblokir [scraping]: {domain}")
                else:
                    logger.info(f"Domain aman [scraping]: {domain}")
                    
                time.sleep(1)  # Delay antar request
                
            except Exception as e:
                logger.error(f"Error scraping {domain}: {e}")
        
        return blocked_domains
        
    except Exception as e:
        logger.error(f"Error dalam scraping: {e}")
        return []

def cek_domain_sync():
    """Fungsi synchronous untuk cek domain"""
    try:
        domains = baca_domain()
        
        if not domains:
            logger.info("Tidak ada domain untuk dicek")
            return
        
        total_domains = len(domains)
        logger.info(f"Memulai pengecekan {total_domains} domain...")
        
        # Bagi domain menjadi batch 50 domain
        batch_size = 50
        all_blocked = []
        
        for i in range(0, total_domains, batch_size):
            batch = domains[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_domains + batch_size - 1) // batch_size
            
            logger.info(f"Memproses batch {batch_num}/{total_batches} ({len(batch)} domain)")
            
            blocked_batch = cek_nawala_api(batch)
            all_blocked.extend(blocked_batch)
            
            # Jeda antar batch
            if i + batch_size < total_domains:
                time.sleep(3)
        
        # Kirim laporan
        if all_blocked:
            asyncio.create_task(kirim_laporan_blocked(all_blocked, total_domains))
        else:
            asyncio.create_task(kirim_laporan_aman(total_domains))
            
        logger.info(f"Pengecekan selesai. {len(all_blocked)} domain terblokir.")
        
    except Exception as e:
        logger.error(f"Error dalam cek_domain_sync: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def kirim_laporan_blocked(blocked_list, total_domains):
    """Kirim laporan domain terblokir"""
    try:
        blocked_count = len(blocked_list)
        
        # Buat pesan utama
        header = f"🔔 *LAPORAN NAWALA.ASIA*\n\n"
        footer = f"\n📊 *Ringkasan:* {blocked_count}/{total_domains} domain terblokir\n⏰ {time.strftime('%d-%m-%Y %H:%M:%S')}"
        
        # Gabungkan daftar domain
        domains_text = "\n".join(blocked_list)
        full_message = header + domains_text + footer
        
        # Cek panjang pesan
        if len(full_message) > 4096:
            # Jika terlalu panjang, bagi menjadi beberapa pesan
            await kirim_pesan_terbagi(header, blocked_list, footer)
        else:
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=full_message,
                parse_mode="Markdown"
            )
        
        logger.info(f"Laporan terkirim: {blocked_count} domain terblokir")
        
    except Exception as e:
        logger.error(f"Gagal kirim laporan: {e}")

async def kirim_pesan_terbagi(header, blocked_list, footer):
    """Kirim pesan yang dibagi karena terlalu panjang"""
    try:
        max_chars = 4096 - 100  # Beri margin
        current_message = header
        message_count = 1
        
        for domain in blocked_list:
            if len(current_message) + len(domain) + 2 > max_chars:
                # Kirim pesan saat ini
                if message_count > 1:
                    current_header = f"🔔 *LAPORAN NAWALA.ASIA (Bagian {message_count})*\n\n"
                    current_message = current_header + current_message[len(header):]
                
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=current_message,
                    parse_mode="Markdown"
                )
                
                # Reset untuk pesan berikutnya
                current_message = header + domain + "\n"
                message_count += 1
                await asyncio.sleep(1)
            else:
                current_message += domain + "\n"
        
        # Kirim pesan terakhir
        if current_message.strip() and current_message != header:
            if message_count > 1:
                current_header = f"🔔 *LAPORAN NAWALA.ASIA (Bagian {message_count})*\n\n"
                current_message = current_header + current_message[len(header):] + footer
            else:
                current_message += footer
            
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=current_message,
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Gagal kirim pesan terbagi: {e}")

async def kirim_laporan_aman(total_domains):
    """Kirim laporan jika semua domain aman"""
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"✅ *LAPORAN NAWALA.ASIA*\n\n"
                 f"*Semua domain aman!* 🎉\n\n"
                 f"📍 Total domain: {total_domains}\n"
                 f"⏰ {waktu}\n\n"
                 f"Tidak ada domain yang terblokir oleh TrustPositif.",
            parse_mode="Markdown"
        )
        logger.info(f"Semua {total_domains} domain aman")
    except Exception as e:
        logger.error(f"Gagal kirim laporan aman: {e}")

async def test_koneksi():
    """Test koneksi ke nawala.asia"""
    try:
        test_url = "https://www.nawala.asia/"
        
        response = session.get(
            test_url,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ Koneksi ke nawala.asia berhasil")
            return True
        else:
            logger.warning(f"⚠️  Koneksi ke nawala.asia: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Gagal koneksi ke nawala.asia: {e}")
        return False

async def tugas_utama():
    """Main function"""
    logger.info("🚀 Memulai bot monitoring domain Nawala.Asia...")
    logger.info(f"📍 Proxy: {PROXY_HOST}:{PROXY_PORT_HTTP}")
    
    # Test koneksi
    if not await test_koneksi():
        logger.warning("Koneksi awal gagal, tetap melanjutkan...")
    
    # Jadwalkan tugas
    schedule.every(10).minutes.do(cek_domain_sync)  # Setiap 10 menit
    schedule.every(2).hours.do(lambda: asyncio.create_task(kirim_status()))
    
    # Jalankan segera
    await kirim_status()
    
    # Jalankan pengecekan pertama dengan delay
    await asyncio.sleep(5)
    cek_domain_sync()
    
    logger.info("✅ Bot berjalan. Tekan Ctrl+C untuk berhenti.")
    
    # Loop utama
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Bot dihentikan oleh user")
            break
        except Exception as e:
            logger.error(f"Error dalam loop utama: {e}")
            await asyncio.sleep(5)

def install_dependencies():
    """Install required packages"""
    required_packages = ['requests', 'schedule', 'python-telegram-bot']
    
    for package in required_packages:
        try:
            if package == 'python-telegram-bot':
                from telegram import __version__
                logger.info(f"python-telegram-bot v{__version__} terinstal")
            else:
                __import__(package)
                logger.info(f"{package} terinstal")
        except ImportError:
            logger.warning(f"{package} tidak ditemukan. Menginstal...")
            try:
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                logger.info(f"{package} berhasil diinstal")
            except Exception as e:
                logger.error(f"Gagal install {package}: {e}")

if __name__ == "__main__":
    # Install dependencies
    install_dependencies()
    
    # Jalankan bot
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot berhenti")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
