#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AMAROK Nawacek Domain Monitoring Bot
Telegram bot untuk mengecek status domain terhadap sistem Nawala/TrustPositif
Menggunakan API dari nawacek.id (Paket Silver/Gold)
"""

import os
import sys
import json
import time
import asyncio
import logging
import re
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
import aiohttp
import schedule
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==================== LOGGING SETUP ====================

def setup_logging():
    """Setup logging configuration"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # File handler
    file_handler = logging.FileHandler('bot.log')
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# ==================== CONFIGURATION ====================

@dataclass
class Config:
    """Bot configuration"""
    # Telegram
    telegram_token: str
    telegram_chat_id: str
    
    # Nawacek API
    nawacek_api_key: str
    api_base_url: str = "https://nawacek.id"
    api_endpoint: str = "/api/v1/check"
    
    # Bot settings
    check_interval: int = 15  # minutes
    status_interval: int = 180  # minutes
    batch_size: int = 5
    max_retries: int = 3
    timeout: int = 15
    delay_between_batches: int = 2  # seconds
    
    # Proxy (optional)
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables"""
        return cls(
            telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            nawacek_api_key=os.getenv("NAWACEK_API_KEY", ""),
            api_base_url=os.getenv("API_BASE_URL", "https://nawacek.id"),
            api_endpoint=os.getenv("API_ENDPOINT", "/api/v1/check"),
            check_interval=int(os.getenv("CHECK_INTERVAL", "15")),
            status_interval=int(os.getenv("STATUS_INTERVAL", "180")),
            batch_size=int(os.getenv("BATCH_SIZE", "5")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            timeout=int(os.getenv("TIMEOUT", "15")),
            delay_between_batches=int(os.getenv("DELAY_BETWEEN_BATCHES", "2")),
            proxy_host=os.getenv("PROXY_HOST"),
            proxy_port=int(os.getenv("PROXY_PORT")) if os.getenv("PROXY_PORT") else None,
            proxy_username=os.getenv("PROXY_USERNAME"),
            proxy_password=os.getenv("PROXY_PASSWORD")
        )

def load_config_file() -> Dict[str, Any]:
    """Load additional configuration from config.json"""
    config_file = Path("config.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {}

# ==================== DOMAIN UTILITIES ====================

def validate_domain(domain: str) -> bool:
    """
    Validate domain format
    
    Args:
        domain: Domain string to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Remove protocol and path
    domain = re.sub(r'^https?://', '', domain)
    domain = domain.split('/')[0]
    
    # Basic domain validation pattern
    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain))

def extract_domain(url_or_domain: str) -> str:
    """
    Extract domain from URL or domain string
    
    Args:
        url_or_domain: URL or domain string
        
    Returns:
        Cleaned domain
    """
    # Remove protocol
    domain = re.sub(r'^https?://', '', url_or_domain)
    
    # Remove path and query parameters
    domain = domain.split('/')[0]
    domain = domain.split('?')[0]
    domain = domain.split('#')[0]
    
    # Remove www prefix
    if domain.startswith('www.'):
        domain = domain[4:]
    
    return domain.lower().strip()

def read_domains_from_file(filepath: str = "domain.txt") -> List[str]:
    """
    Read domains from file
    
    Args:
        filepath: Path to domain file
        
    Returns:
        List of valid domains
    """
    try:
        if not os.path.exists(filepath):
            logger.warning(f"⚠️ File {filepath} tidak ditemukan")
            create_sample_domain_file(filepath)
            return []
        
        domains = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Clean domain
                domain = extract_domain(line)
                if validate_domain(domain):
                    domains.append(domain)
                else:
                    logger.warning(f"⚠️ Format domain tidak valid: {line}")
        
        logger.info(f"📖 Membaca {len(domains)} domain dari {filepath}")
        return domains
        
    except Exception as e:
        logger.error(f"❌ Error membaca domain: {e}")
        return []

def create_sample_domain_file(filepath: str = "domain.txt"):
    """Create sample domain file if not exists"""
    sample_content = """# Daftar domain untuk dicek terhadap Nawala/TrustPositif
# Satu domain per baris
# Baris yang diawali # akan diabaikan

# Contoh domain (ganti dengan domain Anda)
google.com
facebook.com
twitter.com
youtube.com

# Domain yang sering diblokir di Indonesia
# (contoh untuk testing)
thepiratebay.org
123movies.com
"""

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(sample_content)
        logger.info(f"✅ File {filepath} dibuat dengan contoh")
    except Exception as e:
        logger.error(f"❌ Gagal membuat file contoh: {e}")

# ==================== NAWACEK API CLIENT ====================

class NawacekAPIError(Exception):
    """Custom exception for Nawacek API errors"""
    pass

class NawacekClient:
    """
    Client for nawacek.id API
    Requires Silver/Gold subscription
    """
    
    def __init__(self, config: Config):
        """
        Initialize Nawacek API client
        
        Args:
            config: Bot configuration
        """
        self.config = config
        self.api_key = config.nawacek_api_key
        self.base_url = config.api_base_url
        self.endpoint = config.api_endpoint
        self.timeout = config.timeout
        self.session = None
        
        # Validate API key
        if not self.api_key:
            logger.error("❌ NAWACEK_API_KEY tidak ditemukan!")
            raise ValueError("NAWACEK_API_KEY is required")
        
        # Setup proxy if configured
        self.proxy = None
        if config.proxy_host and config.proxy_port:
            proxy_url = f"http://{config.proxy_host}:{config.proxy_port}"
            if config.proxy_username and config.proxy_password:
                proxy_url = f"http://{config.proxy_username}:{config.proxy_password}@{config.proxy_host}:{config.proxy_port}"
            self.proxy = proxy_url
            logger.info(f"🔗 Proxy configured: {config.proxy_host}:{config.proxy_port}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.create_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_session()
    
    async def create_session(self):
        """Create aiohttp session"""
        if self.session is None:
            connector = None
            if self.proxy:
                connector = aiohttp.TCPConnector(
                    limit=10,
                    ttl_dns_cache=300
                )
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': 'AMAROK-Bot/2.0'
                }
            )
            logger.info("✅ Session created")
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Session closed")
    
    async def check_domains(self, domains: List[str]) -> Dict[str, str]:
        """
        Check domains against Nawala system
        
        Args:
            domains: List of domains (max 5 per request)
            
        Returns:
            Dictionary {domain: status} where status is 'ALLOWED', 'BLOCKED', or 'UNKNOWN'
            
        Raises:
            NawacekAPIError: If API request fails
        """
        if len(domains) > 5:
            logger.warning(f"⚠️ Batch terlalu besar ({len(domains)}), dipotong ke 5")
            domains = domains[:5]
        
        if not domains:
            return {}
        
        try:
            # Ensure session exists
            if self.session is None:
                await self.create_session()
            
            # Prepare request
            url = f"{self.base_url}{self.endpoint}"
            payload = {"domains": domains}
            
            logger.info(f"🔍 Mengecek {len(domains)} domain: {', '.join(domains)}")
            
            # Make request with retries
            for attempt in range(self.config.max_retries):
                try:
                    async with self.session.post(url, json=payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            # Parse response - adjust based on actual API response structure
                            return self._parse_response(data, domains)
                        elif response.status == 401:
                            logger.error("❌ API Key tidak valid atau expired")
                            raise NawacekAPIError("Invalid or expired API key")
                        elif response.status == 429:
                            logger.warning("⚠️ Rate limit exceeded, waiting...")
                            await asyncio.sleep(2 ** attempt)
                            continue
                        else:
                            error_text = await response.text()
                            logger.error(f"❌ API Error {response.status}: {error_text}")
                            if attempt < self.config.max_retries - 1:
                                await asyncio.sleep(1)
                                continue
                            raise NawacekAPIError(f"API returned {response.status}: {error_text}")
                
                except aiohttp.ClientError as e:
                    logger.warning(f"⚠️ Request failed (attempt {attempt + 1}): {e}")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise NawacekAPIError(f"Request failed after {self.config.max_retries} attempts: {e}")
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error checking domains: {e}")
            return {}
    
    def _parse_response(self, data: Dict[str, Any], original_domains: List[str]) -> Dict[str, str]:
        """
        Parse API response
        
        Expected response format (adjust based on actual API):
        {
            "data": {
                "domain1.com": "ALLOWED",
                "domain2.com": "BLOCKED",
                ...
            },
            "status": "success"
        }
        """
        result = {}
        
        try:
            # Try different response structures
            if 'data' in data:
                status_map = data['data']
                if isinstance(status_map, dict):
                    for domain in original_domains:
                        status = status_map.get(domain, 'UNKNOWN')
                        result[domain] = status
            elif 'results' in data:
                for item in data['results']:
                    if isinstance(item, dict):
                        domain = item.get('domain', '')
                        status = item.get('status', 'UNKNOWN')
                        if domain:
                            result[domain] = status
            else:
                # If response is directly the map
                for domain in original_domains:
                    status = data.get(domain, 'UNKNOWN')
                    result[domain] = status
            
            # Log results
            for domain, status in result.items():
                if status == 'BLOCKED':
                    logger.warning(f"🚫 {domain}: {status}")
                elif status == 'ALLOWED':
                    logger.info(f"✅ {domain}: {status}")
                else:
                    logger.info(f"❓ {domain}: {status}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error parsing response: {e}")
            return {domain: 'UNKNOWN' for domain in original_domains}

# ==================== BOT HANDLERS ====================

class DomainBot:
    """Main bot class"""
    
    def __init__(self):
        """Initialize bot"""
        self.config = Config.from_env()
        
        # Validate required config
        if not self.config.telegram_token:
            logger.error("❌ TELEGRAM_TOKEN tidak ditemukan!")
            sys.exit(1)
        
        if not self.config.telegram_chat_id:
            logger.error("❌ TELEGRAM_CHAT_ID tidak ditemukan!")
            sys.exit(1)
        
        # Initialize application
        self.application = Application.builder().token(self.config.telegram_token).build()
        self.nawacek_client = NawacekClient(self.config)
        self.running = False
        
        # Register handlers
        self._register_handlers()
        
        logger.info("✅ Bot berhasil diinisialisasi")
    
    def _register_handlers(self):
        """Register command handlers"""
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("check", self.cmd_check))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("domains", self.cmd_domains))
        self.application.add_handler(CommandHandler("add", self.cmd_add_domain))
        self.application.add_handler(CommandHandler("remove", self.cmd_remove_domain))
        self.application.add_handler(CommandHandler("health", self.cmd_health))
        
        # Message handler for domain checking
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
    
    # ==================== COMMAND HANDLERS ====================
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome = f"""
🐺 *AMAROK Nawacek Domain Monitor*

Selamat datang di bot monitoring domain Nawala/TrustPositif!

*Fitur:*
• 🔍 Cek domain terhadap Nawala/TrustPositif
• 📊 Monitor domain secara otomatis setiap {self.config.check_interval} menit
• 📱 Notifikasi real-time via Telegram
• 📈 Laporan status domain lengkap

*Cara Penggunaan:*
• Kirim domain atau URL untuk cek langsung
• /check [domain] - Cek domain tertentu
• /status - Lihat status bot
• /domains - Lihat daftar domain yang dimonitor
• /add domain - Tambah domain ke monitoring
• /remove domain - Hapus domain dari monitoring
• /help - Bantuan lengkap

*Domain tersedia:* {len(read_domains_from_file())} domain
*Interval pengecekan:* {self.config.check_interval} menit

_Bot ini menggunakan API dari nawacek.id (paket Silver/Gold)_
"""
        await update.message.reply_text(welcome, parse_mode="Markdown")
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 *Bantuan Penggunaan Bot*

*Perintah:*
• /start - Menampilkan pesan selamat datang
• /help - Menampilkan bantuan ini
• /check [domain] - Cek status domain
• /status - Status bot dan informasi
• /domains - Daftar domain yang dimonitor
• /add domain - Tambah domain ke monitoring
• /remove domain - Hapus domain dari monitoring
• /health - Cek kesehatan bot

*Status Domain:*
• ✅ ALLOWED - Domain aman, tidak diblokir
• 🚫 BLOCKED - Domain terblokir (Nawala/TrustPositif)
• ❓ UNKNOWN - Status tidak diketahui

*Contoh:*
• Kirim: `google.com` → Cek domain
• Kirim: `https://example.com/path` → Otomatis ekstrak domain
• /check facebook.com → Cek domain spesifik
• /add domain-baru.com → Tambah ke monitoring

*File Konfigurasi:*
• `domain.txt` - Daftar domain untuk monitoring otomatis
• `config.json` - Konfigurasi bot
• `.env` - Environment variables (token, API key)
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check command"""
        if not context.args:
            await update.message.reply_text("❌ Mohon berikan domain yang ingin dicek.\nContoh: /check google.com")
            return
        
        domain = context.args[0]
        await self._check_domain_and_reply(update, domain)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        domains = read_domains_from_file()
        total_domains = len(domains)
        
        status = f"""
📊 *Status Bot*

*Bot Info:*
• Status: 🟢 Berjalan
• Waktu: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}

*Domain:*
• Total domain: {total_domains}
• Interval cek: {self.config.check_interval} menit

*API:*
• Provider: nawacek.id
• Base URL: {self.config.api_base_url}
• Status: {'✅ Terhubung' if self.nawacek_client.session else '⏳ Menunggu'}

*Schedule:*
• Cek domain: Setiap {self.config.check_interval} menit
• Status report: Setiap {self.config.status_interval} menit
"""
        await update.message.reply_text(status, parse_mode="Markdown")
    
    async def cmd_domains(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /domains command"""
        domains = read_domains_from_file()
        
        if not domains:
            await update.message.reply_text("📭 Belum ada domain yang dimonitor.\nTambahkan dengan /add domain")
            return
        
        # Format domain list
        domain_list = ""
        for i, domain in enumerate(domains[:50], 1):  # Max 50 per message
            domain_list += f"{i}. `{domain}`\n"
        
        if len(domains) > 50:
            domain_list += f"\n... dan {len(domains) - 50} domain lainnya"
        
        message = f"""
📋 *Daftar Domain ({len(domains)} total)*

{domain_list}

_Tambahkan domain dengan /add domain_
_Hapus dengan /remove domain_
"""
        await update.message.reply_text(message, parse_mode="Markdown")
    
    async def cmd_add_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add command"""
        if not context.args:
            await update.message.reply_text("❌ Mohon berikan domain yang ingin ditambahkan.\nContoh: /add domain.com")
            return
        
        domain_input = context.args[0]
        domain = extract_domain(domain_input)
        
        if not validate_domain(domain):
            await update.message.reply_text(f"❌ Format domain tidak valid: {domain_input}")
            return
        
        # Check if domain already exists
        existing_domains = read_domains_from_file()
        if domain in existing_domains:
            await update.message.reply_text(f"ℹ️ Domain `{domain}` sudah ada dalam daftar", parse_mode="Markdown")
            return
        
        # Add domain to file
        try:
            with open("domain.txt", "a", encoding='utf-8') as f:
                f.write(f"{domain}\n")
            await update.message.reply_text(f"✅ Domain `{domain}` berhasil ditambahkan ke monitoring", parse_mode="Markdown")
            logger.info(f"📝 Domain added: {domain}")
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal menambahkan domain: {e}")
    
    async def cmd_remove_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /remove command"""
        if not context.args:
            await update.message.reply_text("❌ Mohon berikan domain yang ingin dihapus.\nContoh: /remove domain.com")
            return
        
        domain_to_remove = extract_domain(context.args[0])
        
        # Read existing domains
        domains = read_domains_from_file()
        if domain_to_remove not in domains:
            await update.message.reply_text(f"❌ Domain `{domain_to_remove}` tidak ditemukan", parse_mode="Markdown")
            return
        
        # Remove domain from file
        try:
            with open("domain.txt", "r", encoding='utf-8') as f:
                lines = f.readlines()
            
            with open("domain.txt", "w", encoding='utf-8') as f:
                for line in lines:
                    line_domain = extract_domain(line.strip())
                    if line_domain != domain_to_remove and not (line.strip() and not line.strip().startswith('#')):
                        f.write(line)
            
            await update.message.reply_text(f"✅ Domain `{domain_to_remove}` berhasil dihapus", parse_mode="Markdown")
            logger.info(f"📝 Domain removed: {domain_to_remove}")
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal menghapus domain: {e}")
    
    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /health command"""
        try:
            # Test connection to nawacek API
            test_domains = ["google.com", "facebook.com"]
            async with self.nawacek_client:
                result = await self.nawacek_client.check_domains(test_domains)
            
            if result:
                status = "✅ Bot sehat dan API terhubung"
            else:
                status = "⚠️ Bot berjalan tapi API tidak merespons"
            
            health = f"""
🏥 *Health Check*

*Status:* {status}
*Uptime:* {time.time() - start_time:.0f} detik
*Waktu:* {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}
*Domain terdaftar:* {len(read_domains_from_file())}
*API Key:* {'✅ Terkonfigurasi' if self.config.nawacek_api_key else '❌ Tidak ada'}
"""
            await update.message.reply_text(health, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Health check gagal: {e}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages (domain check)"""
        text = update.message.text.strip()
        await self._check_domain_and_reply(update, text)
    
    async def _check_domain_and_reply(self, update: Update, domain_input: str):
        """Check domain and reply with result"""
        domain = extract_domain(domain_input)
        
        if not validate_domain(domain):
            await update.message.reply_text(
                f"❌ Format domain tidak valid: `{domain_input}`\n"
                "Contoh format yang benar:\n"
                "• google.com\n"
                "• example.co.id\n"
                "• https://domain.com/path\n"
                "• sub.domain.com",
                parse_mode="Markdown"
            )
            return
        
        # Send typing indicator
        await update.message.chat.send_action(action="typing")
        
        try:
            # Check domain using API
            async with self.nawacek_client:
                result = await self.nawacek_client.check_domains([domain])
            
            status = result.get(domain, 'UNKNOWN')
            
            # Format response based on status
            if status == 'ALLOWED':
                emoji = "✅"
                status_text = "AMAN"
                description = "Domain tidak diblokir oleh Nawala/TrustPositif"
            elif status == 'BLOCKED':
                emoji = "🚫"
                status_text = "TERBLOKIR"
                description = "Domain terdeteksi diblokir oleh Nawala/TrustPositif"
            else:
                emoji = "❓"
                status_text = "TIDAK DIKETAHUI"
                description = "Status domain tidak dapat dipastikan"
            
            response = f"""
{emoji} *Hasil Cek Domain*

• *Domain:* `{domain}`
• *Status:* **{status_text}**
• *Keterangan:* {description}
• *Waktu:* {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}
• *Sumber:* nawacek.id

---
💡 _Domain ini akan dicek secara otomatis setiap {self.config.check_interval} menit_
"""
            await update.message.reply_text(response, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error checking domain {domain}: {e}")
            await update.message.reply_text(
                f"❌ Gagal mengecek domain `{domain}`\n"
                f"Error: {str(e)}\n\n"
                "Pastikan API Key valid dan terhubung dengan internet",
                parse_mode="Markdown"
            )

# ==================== SCHEDULED JOBS ====================

async def send_status_report(application: Application, chat_id: str):
    """Send status report"""
    try:
        domains = read_domains_from_file()
        total = len(domains)
        
        message = f"""
🤖 *Status Monitoring Bot*

✅ Status: Aktif & Berjalan
⏰ Waktu: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}
📊 Domain: {total} domain terdaftar
🔢 Batch: {Config.from_env().batch_size} domain/request
⏱️ Interval: {Config.from_env().check_interval} menit

_Bot akan mengecek domain secara otomatis_
"""
        await application.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )
        logger.info("📤 Status report sent")
    except Exception as e:
        logger.error(f"❌ Failed to send status report: {e}")

async def check_domains_job(application: Application, chat_id: str, config: Config):
    """Job to check all domains"""
    try:
        logger.info("=" * 60)
        logger.info("🔄 MEMULAI PEMERIKSAAN DOMAIN")
        logger.info("=" * 60)
        
        # Read domains
        domains = read_domains_from_file()
        if not domains:
            logger.warning("⚠️ Tidak ada domain untuk dicek")
            return
        
        logger.info(f"📋 Jumlah domain: {len(domains)}")
        
        # Initialize client
        client = NawacekClient(config)
        blocked_domains = []
        checked_domains = []
        
        start_time = time.time()
        
        # Process in batches
        for i in range(0, len(domains), config.batch_size):
            batch = domains[i:i + config.batch_size]
            
            try:
                async with client:
                    results = await client.check_domains(batch)
                    
                    for domain, status in results.items():
                        if status == 'BLOCKED':
                            blocked_domains.append(domain)
                        checked_domains.append(domain)
                    
                    # Delay between batches
                    if i + config.batch_size < len(domains):
                        await asyncio.sleep(config.delay_between_batches)
                    
            except Exception as e:
                logger.error(f"❌ Error checking batch {batch}: {e}")
                continue
        
        elapsed_time = time.time() - start_time
        
        # Send report
        if blocked_domains:
            await send_blocked_report(application, chat_id, blocked_domains, len(domains))
        else:
            await send_safe_report(application, chat_id, len(domains))
        
        logger.info(f"✅ Pemeriksaan selesai dalam {elapsed_time:.2f} detik")
        logger.info(f"📊 Hasil: {len(blocked_domains)} dari {len(domains)} domain terblokir")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error in check_domains_job: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def send_blocked_report(application: Application, chat_id: str, blocked_domains: List[str], total_domains: int):
    """Send report of blocked domains"""
    try:
        blocked_count = len(blocked_domains)
        
        # Format domain list
        domain_list = ""
        for i, domain in enumerate(blocked_domains, 1):
            domain_list += f"{i}. 🚫 `{domain}`\n"
        
        # Check message length
        if len(domain_list) > 3500:  # Leave room for header/footer
            # Send in chunks
            chunks = [blocked_domains[i:i+20] for i in range(0, len(blocked_domains), 20)]
            
            for idx, chunk in enumerate(chunks, 1):
                chunk_list = ""
                for i, domain in enumerate(chunk, 1):
                    chunk_list += f"{(idx-1)*20 + i}. 🚫 `{domain}`\n"
                
                message = f"""
🚨 *LAPORAN DOMAIN TERBLOKIR (Bagian {idx}/{len(chunks)})*

{chunk_list}
"""
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown"
                )
                await asyncio.sleep(1)
            
            # Send summary
            summary = f"""
📊 *Ringkasan*
Total domain: {total_domains}
Terblokir: {blocked_count}
Waktu: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}
"""
            await application.bot.send_message(
                chat_id=chat_id,
                text=summary,
                parse_mode="Markdown"
            )
        else:
            message = f"""
🚨 *LAPORAN DOMAIN TERBLOKIR*

**{blocked_count} DOMAIN TERBLOKIR**

{domain_list}

📊 *Statistik:* {blocked_count}/{total_domains} domain terblokir
⏰ *Waktu:* {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}

_Sumber: nawacek.id (AMAROK API)_
"""
            await application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown"
            )
        
        logger.info(f"📤 Laporan terblokir dikirim: {blocked_count} domain")
        
    except Exception as e:
        logger.error(f"❌ Failed to send blocked report: {e}")

async def send_safe_report(application: Application, chat_id: str, total_domains: int):
    """Send report when all domains are safe"""
    try:
        message = f"""
✅ *LAPORAN DOMAIN AMAN*

**SEMUA DOMAIN AMAN!** 🎉

📊 *Total Domain:* {total_domains}
⏰ *Waktu:* {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}

Tidak ada domain yang terblokir oleh Nawala/TrustPositif.

_Sumber: nawacek.id (AMAROK API)_
"""
        await application.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )
        logger.info(f"📤 Laporan aman dikirim: {total_domains} domain")
        
    except Exception as e:
        logger.error(f"❌ Failed to send safe report: {e}")

# ==================== SCHEDULE RUNNER ====================

async def schedule_runner(application: Application, chat_id: str, config: Config):
    """Run scheduled jobs"""
    global start_time
    start_time = time.time()
    
    # Schedule jobs
    schedule.every(config.check_interval).minutes.do(
        lambda: asyncio.create_task(check_domains_job(application, chat_id, config))
    )
    logger.info(f"✅ Schedule: Check domains every {config.check_interval} minutes")
    
    schedule.every(config.status_interval).minutes.do(
        lambda: asyncio.create_task(send_status_report(application, chat_id))
    )
    logger.info(f"✅ Schedule: Status report every {config.status_interval} minutes")
    
    # Run first check immediately (with delay)
    logger.info("Running first check in 3 seconds...")
    await asyncio.sleep(3)
    await check_domains_job(application, chat_id, config)
    
    # Main schedule loop
    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("🛑 Schedule runner cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Error in schedule runner: {e}")
            await asyncio.sleep(5)

# ==================== MAIN ====================

async def main():
    """Main entry point"""
    print("\n" + "=" * 60)
    print("🐺 AMAROK NAWACEK DOMAIN MONITORING BOT")
    print("=" * 60)
    
    # Load configuration
    config = Config.from_env()
    config_file = load_config_file()
    
    # Override config with file values
    for key, value in config_file.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    # Validate configuration
    if not config.telegram_token:
        logger.error("❌ TELEGRAM_TOKEN tidak ditemukan di .env!")
        logger.info("💡 Buat file .env dengan TELEGRAM_TOKEN=your_token")
        sys.exit(1)
    
    if not config.telegram_chat_id:
        logger.error("❌ TELEGRAM_CHAT_ID tidak ditemukan di .env!")
        logger.info("💡 Buat file .env dengan TELEGRAM_CHAT_ID=your_chat_id")
        sys.exit(1)
    
    if not config.nawacek_api_key:
        logger.error("❌ NAWACEK_API_KEY tidak ditemukan di .env!")
        logger.info("💡 Daftar di nawacek.id dan upgrade ke paket Silver/Gold untuk API key")
        logger.info("💡 Buat file .env dengan NAWACEK_API_KEY=your_api_key")
        sys.exit(1)
    
    # Initialize bot
    bot = DomainBot()
    
    # Start bot and schedule
    try:
        # Start the bot
        await bot.application.initialize()
        await bot.application.start()
        
        logger.info("✅ Bot started successfully!")
        logger.info(f"📍 Chat ID: {config.telegram_chat_id}")
        logger.info(f"📍 Domain checks: Every {config.check_interval} minutes")
        logger.info(f"📍 Status reports: Every {config.status_interval} minutes")
        logger.info(f"📍 Batch size: {config.batch_size} domains per request")
        logger.info("📍 Press Ctrl+C to stop\n")
        
        # Send startup message
        await bot.application.bot.send_message(
            chat_id=config.telegram_chat_id,
            text=f"""
🐺 *AMAROK Bot Started!*

✅ Status: Online
⏰ Waktu: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}
📊 Domain terdaftar: {len(read_domains_from_file())}
🔄 Interval cek: {config.check_interval} menit
🔢 Batch size: {config.batch_size} domain

_Bot siap memonitor domain Anda_
""",
            parse_mode="Markdown"
        )
        
        # Run schedule runner
        await schedule_runner(bot.application, config.telegram_chat_id, config)
        
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Cleanup
        if bot.application:
            await bot.application.stop()
            await bot.application.shutdown()
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"💥 Critical error: {e}")
        import traceback
        traceback.print_exc()
