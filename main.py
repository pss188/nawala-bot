# solve_captcha.py
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def solve_nawala_captcha():
    """Solve reCAPTCHA menggunakan Selenium"""
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')  # Run tanpa GUI
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=options)
        driver.get("https://www.nawala.asia/")
        
        # Tunggu halaman load
        time.sleep(3)
        
        # Isi domain test
        textarea = driver.find_element(By.ID, "domains")
        textarea.send_keys("google.com\nfacebook.com")
        
        # Klik tombol cek
        button = driver.find_element(By.ID, "btnSubmit")
        button.click()
        
        # Tunggu hasil
        time.sleep(5)
        
        # Ambil hasil
        results = driver.find_elements(By.CSS_SELECTOR, "#tableResult tbody tr")
        
        for row in results:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 2:
                domain = cols[0].text
                status = cols[1].text
                print(f"{domain}: {status}")
        
        driver.quit()
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    solve_nawala_captcha()
