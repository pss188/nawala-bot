import requests
import schedule
import time
import os
from telegram import Bot

# Ambil dari environment Railway
TOKEN = os.getenv("TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
bot = Bot(token=TOKEN)

# Fungsi untuk membaca domain dari domain.txt
def get_domain_list():
    try:
        with open("domain.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Gagal membaca domain.txt: {e}")
        return []

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
        bot.send_message(chat_id=CHAT_ID, text="\n".join(pesan), parse_mode="Markdown")

# Cek saat startup
cek_blokir()

# Jadwal cek tiap 5 menit
schedule.every(5).minutes.do(cek_blokir)

while True:
    schedule.run_pending()
    time.sleep(1)
