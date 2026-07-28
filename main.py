# main.py - Versi lengkap dengan DNS + Proxy Scraping
import os
import sys
import time
import requests
import asyncio
import logging
import schedule
import dns.resolver
from telegram.ext import Application
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ... (config sama seperti sebelumnya)

class HybridChecker:
    def __init__(self):
        self.session = requests.Session()
        self.session.proxies.update(proxies)
        
    def check_via_dns(self, domain):
        """Cek via DNS Nawala"""
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ['202.134.0.155', '202.134.2.155']
            resolver.timeout = 3
            resolver.lifetime = 5
            
            try:
                resolver.resolve(domain, 'A')
                return True  # Aman
            except:
                return False  # Diblokir
        except:
            return None  # Unknown
            
    def check_via_scraping(self, domain):
        """Cek via scraping TrustPositif dengan proxy"""
        try:
            # Sama seperti sebelumnya
            # ...
            return None
        except:
            return None
    
    def check_domain(self, domain):
        """Cek domain dengan hybrid approach"""
        # Coba DNS dulu (cepat)
        dns_result = self.check_via_dns(domain)
        
        if dns_result is True:
            return True, "ALLOWED (DNS)"
        elif dns_result is False:
            return False, "BLOCKED (DNS)"
        
        # Jika DNS gagal, coba scraping
        scrap_result = self.check_via_scraping(domain)
        if scrap_result is not None:
            return scrap_result
            
        return None, "UNKNOWN"
