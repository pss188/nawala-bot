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

# Validasi awal
if not TOKEN or not CHAT_ID_RAW:
    print("❌ ERROR: TOKEN atau CHAT_ID belum diset di Railway Variables.")
    sys.exit(1)

try:
    CHAT_ID = int(CHAT_ID_RAW)
except ValueError:
    print("❌ ERROR: CHAT_ID harus berupa angka. Contoh: -1001234567890")
    sys.exit(1)

# Inisialisasi bot menggunakan aplikasi asynchronous
application = Application.builder().token(TOKEN).build()

# Fungsi untuk membaca domain dari file domain.txt
def get_domain_list():
    try:
        with open("domain.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"❌ Gagal membaca domain.txt: {e}")
        return []

# Fungsi untuk mengecek apakah domain diblokir
async def cek_blokir():
    domains = get_domain_list()
    pesan = []

    for domain in domains:
        url = f'https://check.skiddle.id/?domains={domain}'
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            # Mengecek jika 'blocked' bernilai True untuk domain
            if data.get(domain, {}).get("blocked", False):
                pesan.append(f"🚫 *{domain}* kemungkinan diblokir.")
        except Exception as e:
            pesan.append(f"⚠️ Gagal cek {domain}: {e}")

    if pesan:
        try:
            # Kirim pesan menggunakan bot Telegram dengan asynchronous
            await application.bot.send_message(chat_id=CHAT_ID, text="\n".join(pesan), parse_mode="Markdown")
            print("✅ Pesan terkirim ke grup.")
        except Exception as e:
            print(f"❌ Gagal kirim pesan ke grup: {e}")
    else:
        print("✅ Tidak ada domain yang diblokir.")

    # Log pengecekan selesai
    print("✅ Pengecekan selesai pada:", time.strftime("%Y-%m-%d %H:%M:%S"))

# Fungsi untuk menjalankan schedule pengecekan setiap 1 menit
async def main():
    # Jalankan pengecekan pertama kali dan terus periksa setiap menit
    await cek_blokir()

    # Jadwalkan pengecekan setiap 1 menit
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)  # Menunggu 60 detik untuk pengecekan berikutnya

# Loop untuk menjalankan pengecekan setiap menit
if __name__ == '__main__':
    # Jadwalkan pengecekan setiap 1 menit
    schedule.every(1).minutes.do(lambda: asyncio.create_task(cek_blokir()))

    # Jalankan aplikasi asynchronous
    asyncio.run(main())
