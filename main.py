import os
import sys
import time
import schedule
import requests
import asyncio
import json
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

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🤖 *Bot Aktif* berjalan normal!\n⏰ {waktu}",
            parse_mode="Markdown"
        )
        logger.info("Status bot terkirim")
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

def baca_domain():
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
                    domains.append(line)
            return domains
    except Exception as e:
        logger.error(f"Error baca domain: {e}")
        return []

def format_domain_list(domains):
    """Format daftar domain untuk dikirim ke nawala.in"""
    return "\n".join(domains)

def cek_nawala_batch(domains):
    """Cek multiple domain sekaligus ke nawala.in"""
    try:
        if not domains:
            return []
        
        # Format domain menjadi string dengan satu domain per baris
        domain_text = format_domain_list(domains)
        
        # URL endpoint nawala.in
        url = "https://nawala.in/check.php"
        
        # Header untuk meniru browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://nawala.in',
            'Referer': 'https://nawala.in/',
        }
        
        # Data yang dikirim (domain list)
        data = {
            'domains': domain_text
        }
        
        logger.info(f"Mengirim {len(domains)} domain ke nawala.in...")
        
        # Kirim request dengan proxy
        response = requests.post(
            url,
            headers=headers,
            data=data,
            proxies=proxies,
            timeout=30
        )
        
        if response.status_code == 200:
            try:
                # Coba parse sebagai JSON
                result = response.json()
                return parse_nawala_result(result, domains)
            except json.JSONDecodeError:
                # Jika bukan JSON, coba parse sebagai HTML/text
                return parse_nawala_html(response.text, domains)
        else:
            logger.error(f"HTTP Error {response.status_code} dari nawala.in")
            return []
            
    except requests.exceptions.Timeout:
        logger.error("Timeout saat mengakses nawala.in")
        return []
    except requests.exceptions.ProxyError as e:
        logger.error(f"Proxy error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error cek nawala: {e}")
        return []

def parse_nawala_result(json_data, original_domains):
    """Parse hasil JSON dari nawala.in"""
    results = []
    
    try:
        # Struktur data dari nawala.in
        if isinstance(json_data, dict):
            # Format 1: {"domain.com": {"status": "blocked", "reason": "..."}}
            for domain in original_domains:
                if domain in json_data:
                    domain_info = json_data[domain]
                    if isinstance(domain_info, dict):
                        status = domain_info.get('status', 'unknown').lower()
                        reason = domain_info.get('reason', '')
                        
                        if status == 'blocked':
                            results.append(f"🚫 *{domain}* terblokir\n  └ {reason}")
                        elif status == 'clean':
                            # Hanya log, tidak dimasukkan ke hasil
                            logger.info(f"Domain aman: {domain}")
                        else:
                            logger.warning(f"Status tidak diketahui untuk {domain}: {status}")
                    else:
                        # Format 2: {"domain.com": "blocked"}
                        status = str(domain_info).lower()
                        if 'block' in status or status == 'true':
                            results.append(f"🚫 *{domain}* terblokir")
                        else:
                            logger.info(f"Domain aman: {domain}")
        elif isinstance(json_data, list):
            # Format 3: [{"domain": "example.com", "status": "blocked", ...}]
            for item in json_data:
                if isinstance(item, dict):
                    domain = item.get('domain', '')
                    status = item.get('status', '').lower()
                    reason = item.get('reason', '')
                    
                    if status == 'blocked':
                        if reason:
                            results.append(f"🚫 *{domain}* terblokir\n  └ {reason}")
                        else:
                            results.append(f"🚫 *{domain}* terblokir")
    
    except Exception as e:
        logger.error(f"Error parse JSON result: {e}")
    
    return results

def parse_nawala_html(html_content, original_domains):
    """Parse hasil HTML dari nawala.in"""
    results = []
    
    try:
        # Cari pola dalam HTML
        lines = html_content.split('\n')
        
        for domain in original_domains:
            # Cari domain dalam HTML response
            domain_found = False
            blocked = False
            
            for line in lines:
                if domain in line:
                    domain_found = True
                    # Cek indikator blocked
                    if 'blocked' in line.lower() or '🚫' in line or 'terblokir' in line.lower():
                        blocked = True
                        break
            
            if blocked:
                results.append(f"🚫 *{domain}* terblokir")
            elif domain_found:
                logger.info(f"Domain aman: {domain}")
    
    except Exception as e:
        logger.error(f"Error parse HTML: {e}")
    
    return results

def cek_domain_sync():
    """Fungsi synchronous untuk cek domain di nawala.in (batch)"""
    try:
        domains = baca_domain()
        if not domains:
            logger.info("Tidak ada domain untuk dicek")
            return
        
        # Bagi domain menjadi batch untuk menghindari timeout
        batch_size = 50  # Maksimal 50 domain per batch
        all_results = []
        
        for i in range(0, len(domains), batch_size):
            batch = domains[i:i + batch_size]
            logger.info(f"Memeriksa batch {i//batch_size + 1}: {len(batch)} domain")
            
            batch_results = cek_nawala_batch(batch)
            all_results.extend(batch_results)
            
            # Jeda antar batch
            if i + batch_size < len(domains):
                time.sleep(2)
        
        if all_results:
            # Kirim hasil via Telegram (async)
            asyncio.create_task(kirim_hasil_domain(all_results, len(domains)))
        else:
            # Kirim laporan kosong jika semua aman
            asyncio.create_task(kirim_hasil_aman(len(domains)))
            
    except Exception as e:
        logger.error(f"Error dalam cek_domain_sync: {e}")

async def kirim_hasil_domain(hasil_list, total_domain):
    """Kirim hasil pemeriksaan domain"""
    try:
        # Jika hasil terlalu panjang, bagi menjadi beberapa pesan
        message_text = f"🔔 *LAPORAN NAWALA.IN*\n\n" + "\n".join(hasil_list) + f"\n\n📊 Total: {len(hasil_list)} dari {total_domain} domain terblokir"
        
        # Batas panjang pesan Telegram
        if len(message_text) > 4096:
            # Bagi pesan
            parts = []
            current_part = f"🔔 *LAPORAN NAWALA.IN*\n\n"
            
            for result in hasil_list:
                if len(current_part) + len(result) + 2 > 4096:
                    parts.append(current_part)
                    current_part = ""
                
                current_part += result + "\n"
            
            if current_part:
                parts.append(current_part + f"\n📊 Total: {len(hasil_list)} dari {total_domain} domain terblokir")
            
            # Kirim semua bagian
            for i, part in enumerate(parts):
                if i > 0:
                    part = f"*Laporan (lanjutan {i+1})*\n\n" + part
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=part,
                    parse_mode="Markdown"
                )
                await asyncio.sleep(1)  # Jeda antar pesan
        else:
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message_text,
                parse_mode="Markdown"
            )
        
        logger.info(f"Laporan terkirim: {len(hasil_list)} domain terblokir")
    except Exception as e:
        logger.error(f"Gagal kirim laporan: {e}")

async def kirim_hasil_aman(total_domain):
    """Kirim laporan jika semua domain aman"""
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"✅ *LAPORAN NAWALA.IN*\n\n"
                 f"Semua domain aman!\n"
                 f"📍 Total domain: {total_domain}\n"
                 f"⏰ {waktu}",
            parse_mode="Markdown"
        )
        logger.info(f"Semua {total_domain} domain aman")
    except Exception as e:
        logger.error(f"Gagal kirim laporan aman: {e}")

async def cek_single_domain():
    """Fungsi untuk testing cek satu domain"""
    try:
        domain = "example.com"  # Ganti dengan domain test
        url = "https://nawala.in/check.php"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        data = {
            'domains': domain
        }
        
        response = requests.post(url, headers=headers, data=data, proxies=proxies, timeout=10)
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response content: {response.text[:500]}")
        
    except Exception as e:
        logger.error(f"Test error: {e}")

async def tugas_utama():
    logger.info("🚀 Memulai bot monitoring domain...")
    logger.info(f"📍 Proxy: {PROXY_HOST}:{PROXY_PORT_HTTP} (HTTP)")
    logger.info("📍 Target: nawala.in batch checking")
    
    # Test koneksi ke nawala.in
    logger.info("Menguji koneksi ke nawala.in...")
    try:
        test_response = requests.get("https://nawala.in", proxies=proxies, timeout=10)
        if test_response.status_code == 200:
            logger.info("✅ Koneksi ke nawala.in berhasil")
        else:
            logger.warning(f"⚠️  Koneksi ke nawala.in: HTTP {test_response.status_code}")
    except Exception as e:
        logger.error(f"❌ Gagal koneksi ke nawala.in: {e}")
    
    # Jadwalkan tugas
    schedule.every(5).minutes.do(cek_domain_sync)  # Setiap 5 menit
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    
    # Jalankan segera
    await kirim_status()
    cek_domain_sync()
    
    logger.info("✅ Bot berjalan. Tekan Ctrl+C untuk berhenti.")
    
    # Loop utama
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Bot dihentikan")
            break
        except Exception as e:
            logger.error(f"Error loop: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    # Cek dan install dependencies jika diperlukan
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
    
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot berhenti")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
