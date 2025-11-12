import time
import json
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import os

# === Konfigurasi Selenium (headless) ===
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
options.add_argument('--log-level=3')
options.add_experimental_option('excludeSwitches', ['enable-logging'])

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
print("Browser Selenium berhasil dijalankan.")

# === URL kategori awal ===
# Ganti URL ini sesuai kebutuhan
start_url = "https://www.gramedia.com/categories/buku"
output_file = "hasil_scrape_gramedia.xlsx"

# ----------------------------------------------------
# 🔹 Logika untuk Resume (Melanjutkan)
# ----------------------------------------------------
visited_products = set()
total_books_scraped = 0

if os.path.exists(output_file):
    print(f"File '{output_file}' ditemukan. Membaca data untuk melanjutkan (resume)...")
    try:
        df_existing = pd.read_excel(output_file)
        if 'URL Buku' in df_existing.columns:
            visited_products.update(df_existing['URL Buku'].dropna().tolist())
            total_books_scraped = len(visited_products)
            print(f"✅ Selesai. Ditemukan {total_books_scraped} buku yang sudah tersimpan. Scraping akan melewatkan buku-buku ini.")
        else:
            print(f"⚠️ Kolom 'URL Buku' tidak ditemukan. File mungkin korup. Membuat file baru.")
            os.remove(output_file)
            
    except Exception as e:
        print(f"⚠️ Gagal membaca file Excel lama: {e}. Membuat file baru (file lama akan dihapus).")
        try:
            os.remove(output_file)
        except OSError:
            pass
        total_books_scraped = 0
else:
    print(f"File '{output_file}' tidak ditemukan. Memulai scrape baru.")
    total_books_scraped = 0
# ----------------------------------------------------

visited_categories = set()


# --------------------------------------
# 🔹 Fungsi bantu (get_subcategories & get_products)
# --------------------------------------
def get_subcategories(soup, current_url):
    subcats = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/categories/" in href and not "/products/" in href:
            full = "https://www.gramedia.com" + href if href.startswith("/") else href
            if full.startswith(current_url) and full != current_url:
                subcats.append(full)
    return list(set(subcats))

def get_products(soup):
    products = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/products/" in href:
            full = "https://www.gramedia.com" + href if href.startswith("/") else href
            products.append(full)
    return list(set(products)) 

# --------------------------------------
# 🔹 Fungsi scraping detail buku
# --------------------------------------
def scrape_book(url):
    # --- PERUBAHAN 1: Tambahkan Subkategori 3 ---
    data_buku = {
        "Kategori Utama": "Tidak ditemukan", "Subkategori 1": "Tidak ditemukan",
        "Subkategori 2": "Tidak ditemukan", "Subkategori 3": "Tidak ditemukan", # <-- DITAMBAHKAN
        "URL Buku": url, "URL Gambar": "Tidak ditemukan", 
        "Nama Penulis": "Tidak ditemukan", "Judul": "Tidak ditemukan", 
        "Harga": "Tidak ditemukan", "Format Buku": "Tidak ditemukan", 
        "Deskripsi": "Tidak ditemukan", "Penerbit": "Tidak ditemukan", 
        "Tanggal Terbit": "Tidak ditemukan", "ISBN": "Tidak ditemukan", 
        "Halaman": "Tidak ditemukan", "Bahasa": "Tidak ditemukan", 
        "Panjang": "Tidak ditemukan", "Lebar": "Tidak ditemukan", 
        "Berat": "Tidak ditemukan"
    }
    # -------------------------------------------
    
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='productDetailSpecificationItemLabel']"))
        )
        time.sleep(0.5) 
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # === Data utama ===
        judul_tag = soup.find(attrs={'data-testid': 'productDetailTitle'})
        if judul_tag: data_buku['Judul'] = judul_tag.get_text(strip=True)
        penulis_tag = soup.find(attrs={'data-testid': 'productDetailAuthor'})
        if penulis_tag: data_buku['Nama Penulis'] = penulis_tag.get_text(strip=True)
        harga_tag = soup.find(attrs={'data-testid': 'productDetailFinalPrice'})
        if harga_tag: data_buku['Harga'] = harga_tag.get_text(strip=True)
        deskripsi_tag = soup.find(attrs={'data-testid': 'productDetailDescriptionContainer'})
        if deskripsi_tag: data_buku['Deskripsi'] = deskripsi_tag.get_text(separator='\n', strip=True)

        # === Breadcrumb (kategori) ===
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data_json = json.loads(script.string)
                if isinstance(data_json, dict) and data_json.get('@type') == 'BreadcrumbList':
                    items = data_json.get('itemListElement', [])
                    names = [i.get('name') for i in items if i.get('name') and i.get('name').lower() != 'home']
                    
                    if len(names) >= 2: data_buku['Kategori Utama'] = names[0]
                    if len(names) >= 3: data_buku['Subkategori 1'] = names[1]
                    if len(names) >= 4: data_buku['Subkategori 2'] = names[2]
                    # --- PERUBAHAN 2: Tambahkan if untuk Subkategori 3 ---
                    if len(names) >= 5: data_buku['Subkategori 3'] = names[3] # <-- DITAMBAHKAN
                    # ----------------------------------------------------
                    break
            except Exception: continue

        # === URL gambar ===
        og_image = soup.find('meta', property='og:image')
        if og_image: data_buku['URL Gambar'] = og_image['content']

        # === Format buku ===
        format_container = soup.find(attrs={'data-testid': 'productDetailVariantChips'})
        if format_container:
            active_chip = format_container.find('button', class_=lambda c: c and 'border-neutral-700' in c)
            if active_chip:
                span = active_chip.find('span')
                if span: data_buku['Format Buku'] = span.get_text(strip=True)

        # === Detail buku lainnya ===
        all_labels = soup.find_all('div', {'data-testid': 'productDetailSpecificationItemLabel'})
        for label_tag in all_labels:
            label_text = label_tag.get_text(strip=True)
            value_tag = label_tag.find_next_sibling('div', {'data-testid': 'productDetailSpecificationItemValue'})
            if value_tag:
                value_text = value_tag.get_text(strip=True)
                if label_text == "Penerbit": data_buku['Penerbit'] = value_text
                elif label_text == "ISBN": data_buku['ISBN'] = value_text
                elif label_text == "Halaman": data_buku['Halaman'] = value_text
                elif label_text == "Bahasa": data_buku['Bahasa'] = value_text
                elif label_text == "Tanggal Terbit": data_buku['Tanggal Terbit'] = value_text
                elif label_text == "Lebar": data_buku['Lebar'] = value_text
                elif label_text == "Panjang": data_buku['Panjang'] = value_text
                elif label_text == "Berat": data_buku['Berat'] = value_text
        
        print(f"✅ Selesai scrape: {data_buku['Judul']}")
        return data_buku
    except Exception as e:
        print(f"❌ Error scrape {url}: {e}")
        return data_buku

# --------------------------------------
# 🔹 Fungsi rekursif: jelajahi kategori
# --------------------------------------
def crawl_category(url):
    global total_books_scraped, visited_products
    
    if url in visited_categories:
        return
    visited_categories.add(url)

    print(f"\n🌿 Menjelajah kategori: {url}")
    driver.get(url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    subcats = get_subcategories(soup, url)

    if subcats:
        print(f"📂 Ditemukan {len(subcats)} subkategori, menjelajahi lebih dalam...")
        for sub in subcats:
            crawl_category(sub)
    else:
        print(f"📚 Tidak ada subkategori lagi, memuat semua produk...")
        
        try:
            stock_filter_switch = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-testid='productListFilterStockSwitch']"))
            )
            if stock_filter_switch.get_attribute('data-state') == 'checked':
                print("⚪ Filter 'Hanya yang tersedia' aktif. Menonaktifkan filter...")
                driver.execute_script("arguments[0].click();", stock_filter_switch)
                time.sleep(3) 
                print("🟢 Filter stok dinonaktifkan.")
            else:
                print("🟢 Filter 'Hanya yang tersedia' sudah tidak aktif.")
        except Exception:
            print(f"⚠️ Tidak dapat menemukan filter stok. Melanjutkan...")

        while True:
            try:
                load_more_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Muat Lebih Banyak')]"))
                )
                print("🔄 Menemukan tombol 'Muat Lebih Banyak' — mengklik...")
                driver.execute_script("arguments[0].click();", load_more_button)
                time.sleep(3)
            except Exception:
                print("✅ Tidak ada lagi tombol 'Muat Lebih Banyak'.")
                break

        soup = BeautifulSoup(driver.page_source, "html.parser")
        products = list(set(get_products(soup)))
        print(f"   → Ditemukan {len(products)} link produk unik di {url}")
        
        books_in_this_category = []
        new_books_found_in_batch = 0
        
        for link in products:
            if link not in visited_products:
                visited_products.add(link)
                book_data = scrape_book(link)
                books_in_this_category.append(book_data)
                new_books_found_in_batch += 1
            else:
                pass
        
        if new_books_found_in_batch > 0:
            print(f"💾 Menemukan {new_books_found_in_batch} buku baru. Menyimpan ke Excel...")
            df_batch = pd.DataFrame(books_in_this_category)
            
            file_exists = os.path.exists(output_file)

            try:
                if not file_exists:
                    print(f"Membuat file baru '{output_file}'...")
                    df_batch.to_excel(output_file, sheet_name='Sheet1', index=False, header=True)
                else:
                    with pd.ExcelWriter(output_file, 
                                        mode='a', 
                                        engine='openpyxl', 
                                        if_sheet_exists='overlay') as writer:
                        start_row = writer.sheets['Sheet1'].max_row
                        df_batch.to_excel(writer, 
                                          sheet_name='Sheet1', 
                                          index=False, 
                                          header=False, 
                                          startrow=start_row)
                
                total_books_scraped += new_books_found_in_batch
                print(f"✅ Berhasil! Total buku tersimpan: {total_books_scraped}")
            
            except Exception as e:
                print(f"❌ GAGAL menyimpan ke Excel: {e}")
                backup_file = f"cadangan_{url.split('/')[-1]}_{int(time.time())}.xlsx"
                df_batch.to_excel(backup_file, index=False)
                print(f"ℹ️ Data batch disimpan ke file cadangan: {backup_file}")
        else:
            print(f"ℹ️ Tidak ada buku baru di kategori ini yang perlu disimpan (semua sudah ada di Excel).")

# === Jalankan dari kategori utama ===
try:
    crawl_category(start_url)
    print(f"\n🎉 Selesai! Total {total_books_scraped} buku unik berhasil disimpan di '{output_file}'!")
except KeyboardInterrupt:
    print("\n🛑 Proses dihentikan oleh pengguna (Ctrl+C). Data yang sudah selesai per-batch telah disimpan.")
except Exception as e:
    print(f"\n❌ Terjadi error yang tidak terduga: {e}")
finally:
    # Selalu pastikan driver ditutup
    driver.quit()
    print("Browser Selenium ditutup.")