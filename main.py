import os
import sys
import requests
import asyncio
import schedule
import time
from telegram import Bot
from telegram.ext import Application

# Ambil TOKEN dan CHAT_ID dari environment Railway
TOKEN = os.getenv("TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID_RAW:
    print("❌ ERROR: TOKEN atau CHAT_ID belum diset di Railway Variables.")
    sys.exit(1)

try:
    CHAT_ID = int(CHAT_ID_RAW)
except ValueError:
    print("❌ ERROR: CHAT_ID harus berupa angka.")
    sys.exit(1)

# Inisialisasi bot
application = Application.builder().token(TOKEN).build()

# Fungsi membaca domain
def get_domain_list():
    try:
        with open("domain.txt", "r") as f:
            domains = [line.strip() for line in f if line.strip()]
            print("📄 Domain yang dibaca dari domain.txt:", domains)  # Log di sini
            return domains
    except Exception as e:
        print(f"❌ Gagal membaca domain.txt: {e}")
        return []

# Fungsi cek blokir
async def cek_blokir():
    domains = get_domain_list()
    pesan = []

    for domain in domains:
        url = f'https://check.skiddle.id/?domains={domain}'
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            print(f"🔍 Respons dari API untuk {domain}:", data)  # Log respons API

            if data.get(domain, {}).get("blocked", False):
                pesan.append(f"🚫 *{domain}* terdeteksi nawala.")
        except Exception as e:
            pesan.append(f"⚠️ Gagal cek {domain}: {e}")

    if pesan:
        try:
            await application.bot.send_message(chat_id=CHAT_ID, text="\n".join(pesan), parse_mode="Markdown")
            print("✅ Pesan terkirim ke grup.")
        except Exception as e:
            print(f"❌ Gagal kirim pesan ke Telegram: {e}")
    else:
        print("✅ Tidak ada domain yang diblokir.")

    print("🕒 Pengecekan selesai:", time.strftime("%Y-%m-%d %H:%M:%S"))

# Fungsi main loop
async def main():
    await cek_blokir()
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)

# Jalankan
if __name__ == "__main__":
    schedule.every(1).minutes.do(lambda: asyncio.create_task(cek_blokir()))
    asyncio.run(main())
