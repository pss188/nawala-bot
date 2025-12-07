import os
import sys
import asyncio
import requests
import schedule
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from telegram import Bot
from telegram.ext import Application
from urllib.parse import urlparse

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

if not TOKEN or not CHAT_ID:
    logger.error("Token atau Chat ID tidak ditemukan!")
    sys.exit(1)

# Bot setup
application = Application.builder().token(TOKEN).build()

# Global variables
working_proxies = []
proxy_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=10)

def fetch_proxies_from_source(source_url, proxy_type="http"):
    """Ambil proxy dari berbagai sumber"""
    try:
        response = requests.get(source_url, timeout=10)
        if response.status_code == 200:
            proxies = []
            for line in response.text.strip().split('\n'):
                line = line.strip()
                if line:
                    if ':' in line and not line.startswith(('http://', 'https://', 'socks')):
                        proxies.append(f"{proxy_type}://{line}")
                    elif line.startswith(('http://', 'https://', 'socks')):
                        proxies.append(line)
            return proxies
    except Exception as e:
        logger.debug(f"Gagal fetch dari {source_url}: {e}")
    return []

def get_all_free_proxies():
    """Ambil proxy dari berbagai sumber publik"""
    all_proxies = []
    
    # Sumber proxy yang lebih beragam
    sources = [
        # HTTP/HTTPS proxies
        ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt", "http"),
        ("https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt", "http"),
        ("https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt", "https"),
        ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt", "http"),
        
        # SOCKS proxies
        ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt", "socks4"),
        ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt", "socks5"),
        ("https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt", "socks4"),
        ("https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt", "socks5"),
        
        # API-based
        ("https://api.openproxylist.xyz/http.txt", "http"),
        ("https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000", "http"),
        ("https://www.proxy-list.download/api/v1/get?type=http", "http"),
        ("https://www.proxy-list.download/api/v1/get?type=https", "https"),
    ]
    
    logger.info("Mengumpulkan proxy dari berbagai sumber...")
    
    # Fetch dari semua sumber secara paralel
    futures = []
    for source_url, proxy_type in sources:
        future = executor.submit(fetch_proxies_from_source, source_url, proxy_type)
        futures.append(future)
    
    for future in futures:
        try:
            proxies = future.result(timeout=15)
            if proxies:
                all_proxies.extend(proxies)
                logger.info(f"Ditambahkan {len(proxies)} proxy")
        except Exception as e:
            continue
    
    # Remove duplicates
    all_proxies = list(set(all_proxies))
    logger.info(f"Total {len(all_proxies)} proxy terkumpul")
    
    # Tambahkan beberapa proxy manual sebagai cadangan
    manual_proxies = [
        # Indonesia proxies (sering berubah)
        "http://103.155.54.26:83",
        "http://103.147.77.66:3125",
        "http://103.153.140.142:8080",
        
        # Global proxies
        "http://185.199.229.156:7492",
        "http://185.199.228.220:7300",
        "http://185.199.231.45:8382",
        
        # SOCKS5
        "socks5://64.124.191.146:1080",
        "socks5://67.213.212.58:4145",
    ]
    
    all_proxies.extend(manual_proxies)
    return all_proxies

def test_single_proxy(proxy_url):
    """Test satu proxy"""
    try:
        proxies = {
            'http': proxy_url,
            'https': proxy_url,
        }
        
        # Test dengan multiple endpoints
        test_urls = [
            'http://httpbin.org/ip',
            'http://api.ipify.org?format=json',
            'https://checkip.amazonaws.com'
        ]
        
        for test_url in test_urls:
            try:
                response = requests.get(
                    test_url,
                    proxies=proxies,
                    timeout=5,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                if response.status_code == 200:
                    return True, proxy_url
            except:
                continue
    except Exception as e:
        pass
    
    return False, proxy_url

def find_working_proxies_parallel(proxies, max_workers=20):
    """Cari proxy yang berfungsi secara paralel"""
    logger.info(f"Testing {len(proxies)} proxy secara paralel...")
    
    working = []
    
    # Test dalam batch
    batch_size = 50
    for i in range(0, len(proxies), batch_size):
        batch = proxies[i:i + batch_size]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(test_single_proxy, proxy) for proxy in batch]
            
            for future in futures:
                try:
                    is_working, proxy_url = future.result(timeout=10)
                    if is_working:
                        working.append(proxy_url)
                        logger.debug(f"Proxy berfungsi: {proxy_url}")
                except:
                    continue
        
        if len(working) >= 5:  # Stop jika sudah dapat 5 proxy yang berfungsi
            break
    
    logger.info(f"Ditemukan {len(working)} proxy yang berfungsi")
    return working

def update_proxy_list():
    """Update daftar proxy yang berfungsi"""
    global working_proxies
    
    try:
        # Dapatkan semua proxy
        all_proxies = get_all_free_proxies()
        
        if not all_proxies:
            logger.warning("Tidak ada proxy yang ditemukan")
            return
        
        # Cari proxy yang berfungsi
        new_working_proxies = find_working_proxies_parallel(all_proxies)
        
        with proxy_lock:
            working_proxies.clear()
            working_proxies.extend(new_working_proxies)
        
        if working_proxies:
            logger.info(f"Proxy list updated: {len(working_proxies)} proxy berfungsi")
        else:
            logger.warning("Tidak ada proxy yang berfungsi")
            
    except Exception as e:
        logger.error(f"Error update proxy: {e}")

def get_proxy():
    """Dapatkan proxy acak yang berfungsi"""
    global working_proxies
    
    with proxy_lock:
        if working_proxies:
            return random.choice(working_proxies)
    
    return None

async def kirim_status():
    try:
        waktu = time.strftime("%d-%m-%Y %H:%M:%S")
        
        with proxy_lock:
            proxy_count = len(working_proxies)
        
        status_text = f"🤖 *Bot Aktif* berjalan normal!\n"
        status_text += f"Waktu: {waktu}\n"
        status_text += f"Proxy aktif: {proxy_count}"
        
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=status_text,
            parse_mode="Markdown"
        )
        logger.info("Status bot terkirim")
    except Exception as e:
        logger.error(f"Gagal kirim status: {e}")

def baca_domain():
    try:
        with open("domain.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"Error baca domain: {e}")
        return []

async def cek_domain():
    domains = baca_domain()
    if not domains:
        logger.info("Tidak ada domain untuk dicek")
        return
    
    # Update proxy jika tidak ada yang berfungsi
    with proxy_lock:
        if not working_proxies:
            logger.info("Tidak ada proxy yang berfungsi, melakukan update...")
            # Jalankan update proxy di thread terpisah
            threading.Thread(target=update_proxy_list, daemon=True).start()
            await asyncio.sleep(10)  # Tunggu sebentar untuk update
    
    hasil = []
    
    for domain in domains:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                proxy = get_proxy()
                
                if proxy:
                    proxies = {'http': proxy, 'https': proxy}
                    logger.info(f"Mencoba domain {domain} dengan proxy: {proxy.split('://')[1].split('@')[-1] if '@' in proxy else proxy}")
                else:
                    proxies = None
                    logger.info(f"Mencoba domain {domain} tanpa proxy")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Referer': 'https://check.skiddle.id/',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin',
                }
                
                response = requests.get(
                    f'https://check.skiddle.id/?domains={domain}',
                    proxies=proxies,
                    headers=headers,
                    timeout=20,
                    verify=False  # Nonaktifkan SSL verification jika perlu
                )
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if domain in data and data.get(domain, {}).get("blocked", False):
                            hasil.append(f"🚫 *{domain}* nawala!")
                            logger.info(f"{domain}: TERBLOKIR")
                        else:
                            logger.info(f"{domain}: AMAN")
                        break  # Berhasil, keluar dari retry loop
                    except ValueError:
                        logger.warning(f"Response bukan JSON: {response.text[:100]}")
                elif response.status_code == 403:
                    logger.warning(f"Access denied (403) untuk {domain}")
                    # Hapus proxy jika tidak berfungsi
                    if proxy and proxy in working_proxies:
                        with proxy_lock:
                            working_proxies.remove(proxy)
                            logger.info(f"Proxy dihapus karena 403: {proxy}")
                    continue
                else:
                    logger.warning(f"Status {response.status_code} untuk {domain}")
                    
            except requests.exceptions.ProxyError:
                logger.warning("Proxy error")
                if proxy and proxy in working_proxies:
                    with proxy_lock:
                        working_proxies.remove(proxy)
                continue
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout untuk {domain}")
            except requests.exceptions.SSLError:
                logger.warning(f"SSL error untuk {domain}")
            except Exception as e:
                logger.error(f"Error cek {domain}: {str(e)[:100]}")
            
            # Tunggu sebelum retry
            await asyncio.sleep(random.uniform(2, 5))
    
    if hasil:
        try:
            message = "*Hasil Pengecekan Domain:*\n\n" + "\n".join(hasil)
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"Status domain terkirim: {len(hasil)} domain terblokir")
        except Exception as e:
            logger.error(f"Gagal kirim hasil: {e}")
    else:
        logger.info("Tidak ada domain yang terblokir.")

async def tugas_utama():
    # Update proxy list saat start
    logger.info("Inisialisasi proxy...")
    threading.Thread(target=update_proxy_list, daemon=True).start()
    
    # Tunggu proxy siap
    await asyncio.sleep(15)
    
    # Jadwalkan tugas
    schedule.every(30).seconds.do(lambda: asyncio.create_task(cek_domain()))
    schedule.every(6).hours.do(lambda: threading.Thread(target=update_proxy_list, daemon=True).start())
    schedule.every(1).hours.do(lambda: asyncio.create_task(kirim_status()))
    
    # Jalankan segera
    await cek_domain()
    await kirim_status()

    # Loop utama
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    # Nonaktifkan SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        asyncio.run(tugas_utama())
    except KeyboardInterrupt:
        logger.info("Bot dihentikan oleh pengguna")
        executor.shutdown()
    except Exception as e:
        logger.error(f"Bot error: {e}")
        executor.shutdown()
