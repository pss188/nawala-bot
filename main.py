import os
import sys
import aiohttp
import asyncio
import aioschedule as schedule
from telegram import Bot

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
bot = Bot(token=TOKEN)

# Fungsi membaca domain dari file
def get_domain_list():
    try:
        with open("domain.txt", "r") as f:
            domains = [line.strip() for line in f if line.strip()]
            print("📄 Domain yang dibaca:", domains)
            return domains
    except Exception as e:
        print(f"❌ Gagal baca domain.txt: {e}")
        return []

# Fungsi cek blokir
async def cek_blokir():
    domains = get_domain_list()
    pesan = []

    async with aiohttp.ClientSession() as session:
        for domain in domains:
            url = f'https://check.skiddle.id/?domains={domain}'
            try:
                async with session.get(url, timeout=5) as response:
                    data = await response.json()
                    print(f"🔍 Respons untuk {domain}:", data)
                    if data.get(domain, {}).get("blocked", False):
                        pesan.append(f"🚫 *{domain}* terdeteksi nawala.")
            except Exception as e:
                pesan.append(f"⚠️ Gagal cek {domain}: {e}")

    if pesan:
        try:
            await bot.send_message(chat_id=CHAT_ID, text="\n".join(pesan), parse_mode="Markdown")
            print("✅ Pesan dikirim ke Telegram.")
        except Exception as e:
            print(f"❌ Gagal kirim pesan: {e}")
    else:
        print("✅ Tidak ada domain yang diblokir.")
    print("🕒 Pengecekan selesai.")

# Fungsi kirim status server
async def kirim_status_server():
    try:
        await bot.send_message(chat_id=CHAT_ID, text="✅ Status Bot On", parse_mode="Markdown")
        print("🟢 Status bot dikirim.")
    except Exception as e:
        print(f"❌ Gagal kirim status server: {e}")

# Scheduler
async def scheduler():
    schedule.every(1).minutes.do(lambda: asyncio.create_task(cek_blokir()))
    schedule.every(3).hours.do(lambda: asyncio.create_task(kirim_status_server()))
    while True:
        await schedule.run_pending()
        await asyncio.sleep(1)

# Jalankan
if __name__ == "__main__":
    asyncio.run(scheduler())
