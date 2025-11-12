import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# --- Konfigurasi Selenium (headless mode) ---
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

url = "https://www.gramedia.com/products/harry-potter-and-the-philosophers-stone-minalima-edition"
print(f"Mencoba mengambil data dari: {url}\n")

data_buku = {
    "Kategori Utama": "Tidak ditemukan",
    "Subkategori 1": "Tidak ditemukan",
    "Subkategori 2": "Tidak ditemukan",
    "Subkategori 3": "Tidak ditemukan",
    "URL Buku": url,
    "URL Gambar": "Tidak ditemukan",
    "Nama Penulis": "Tidak ditemukan",
    "Judul": "Tidak ditemukan",
    "Harga": "Tidak ditemukan",
    "Format Buku": "Tidak ditemukan",
    "Toko": "Tidak ditemukan",
    "Deskripsi": "Tidak ditemukan",
    "Penerbit": "Tidak ditemukan",
    "Tanggal Terbit": "Tidak ditemukan",
    "ISBN": "Tidak ditemukan",
    "Halaman": "Tidak ditemukan",
    "Bahasa": "Tidak ditemukan",
    "Panjang": "Tidak ditemukan",
    "Lebar": "Tidak ditemukan",
    "Berat": "Tidak ditemukan"
}

try:
    # Buka halaman dan tunggu JS
    driver.get(url)
    print("Menunggu halaman memuat data dinamis...")
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='productDetailSpecificationContainer']"))
    )
    print("✅ Halaman berhasil dimuat!")

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()

    # --- Ekstraksi dasar ---
    judul_tag = soup.find(attrs={'data-testid': 'productDetailTitle'})
    if judul_tag:
        data_buku['Judul'] = judul_tag.get_text(strip=True)

    penulis_tag = soup.find(attrs={'data-testid': 'productDetailAuthor'})
    if penulis_tag:
        data_buku['Nama Penulis'] = penulis_tag.get_text(strip=True)

    harga_tag = soup.find(attrs={'data-testid': 'productDetailFinalPrice'})
    if harga_tag:
        data_buku['Harga'] = harga_tag.get_text(strip=True)

    deskripsi_tag = soup.find(attrs={'data-testid': 'productDetailDescriptionContainer'})
    if deskripsi_tag:
        data_buku['Deskripsi'] = deskripsi_tag.get_text(separator='\n', strip=True)

    # --- Breadcrumb: ambil semua level kategori ---
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data_json = json.loads(script.string)
            if isinstance(data_json, dict) and data_json.get('@type') == 'BreadcrumbList':
                items = data_json.get('itemListElement', [])
                names = [i.get('name') for i in items if i.get('name') and i.get('name').lower() != 'home']

                # contoh: ['Buku', 'Komputer', 'Aplikasi Bisnis & Produktivitas', 'Akuntansi & Keuangan', 'Produk']
                if len(names) >= 2:
                    data_buku['Kategori Utama'] = names[0]
                if len(names) >= 3:
                    data_buku['Subkategori 1'] = names[1]
                if len(names) >= 4:
                    data_buku['Subkategori 2'] = names[2]
                if len(names) >= 5:
                    data_buku['Subkategori 3'] = names[3]
                break
        except Exception:
            continue

    # --- URL Gambar ---
    og_image = soup.find('meta', property='og:image')
    if og_image:
        data_buku['URL Gambar'] = og_image['content']

    # --- Format Buku ---
    format_container = soup.find(attrs={'data-testid': 'productDetailVariantChips'})
    if format_container:
        active_chip = format_container.find('button', class_=lambda c: c and 'border-neutral-700' in c)
        if active_chip:
            span = active_chip.find('span')
            if span:
                data_buku['Format Buku'] = span.get_text(strip=True)

    # --- Toko ---
    toko_button = soup.find(attrs={'data-testid': 'productDetailWarehouseTriggerButton'})
    if toko_button:
        toko_div = toko_button.find('div', class_='truncate')
        if toko_div:
            data_buku['Toko'] = toko_div.get_text(strip=True)

    # --- Detail buku lainnya ---
    all_labels = soup.find_all('div', {'data-testid': 'productDetailSpecificationItemLabel'})
    for label_tag in all_labels:
        label_text = label_tag.get_text(strip=True)
        value_tag = label_tag.find_next_sibling('div', {'data-testid': 'productDetailSpecificationItemValue'})
        if value_tag:
            value_text = value_tag.get_text(strip=True)
            if label_text in data_buku:
                data_buku[label_text] = value_text
            elif label_text == "Penerbit":
                data_buku['Penerbit'] = value_text
            elif label_text == "ISBN":
                data_buku['ISBN'] = value_text
            elif label_text == "Halaman":
                data_buku['Halaman'] = value_text
            elif label_text == "Bahasa":
                data_buku['Bahasa'] = value_text
            elif label_text == "Tanggal Terbit":
                data_buku['Tanggal Terbit'] = value_text
            elif label_text == "Lebar":
                data_buku['Lebar'] = value_text
            elif label_text == "Panjang":
                data_buku['Panjang'] = value_text
            elif label_text == "Berat":
                data_buku['Berat'] = value_text

    # --- Cetak hasil ---
    print("\n--- HASIL SCRAPING LENGKAP ---")
    for k, v in data_buku.items():
        if k == "Deskripsi":
            print(f"{k}: {v[:150]}...")
        else:
            print(f"{k}: {v}")

except Exception as e:
    print(f"\n❌ Terjadi error: {e}")
    if 'driver' in locals():
        driver.quit()
