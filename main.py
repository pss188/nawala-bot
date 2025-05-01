import os
import sys
import time
import requests
import schedule
from telegram import Bot

# Ambil TOKEN dan CHAT_ID dari environment Railway
TOKEN = os.getenv("TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")

# Validasi awal
if not TOKEN or not CHAT_ID_RAW:
    print("❌ ERROR: TOKEN atau CHAT_ID belum diset di Railway Variables.")
    sys.exit(1)

try:
    CHAT_ID = int(CHAT_ID_RAW)
except ValueError:
    print("❌ ERROR: CHAT_ID harus berupa angka. Contoh: -1001234567890")
    sys.exit(1)

bot = Bot(token=TOKEN)

# Fungsi untuk membaca domain dari file domain.txt
def get_domain_list():
    try:
        with open("domain.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"❌ Gagal membaca domain.txt: {e}")
        return []

# Fungsi utama: cek apakah domain diblokir
def cek_blokir():
    domains = get_domain_list()
    pesan = []

    for domain in domains:
        url = f'https://check.skiddle.id/?domains={domain}'
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            if data.get("blocked", False):
                pesan.append(f"🚫 *{domain}* kemungkinan diblokir.")
        except Exception as e:
            pesan.append(f"⚠️ Gagal cek {domain}: {e}")

    if pesan:
        try:
            bot.send_message(chat_id=CHAT_ID, text="\n".join(pesan), parse_mode="Markdown")
            print("✅ Pesan terkirim ke grup.")
        except Exception as e:
            print(f"❌ Gagal kirim pesan ke grup: {e}")

# Jalankan saat pertama kali bot aktif
cek_blokir()

# Jadwalkan cek setiap 5 menit
schedule.every(5).minutes.do(cek_blokir)

# Loop terus
while True:
    schedule.run_pending()
    time.sleep(1)
