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
# Baris di bawah ini bisa di-uncomment (hapus tanda #) untuk menjalankan
# script tanpa membuka jendela browser (mode headless)
# options.add_argument('--headless')
options.add_argument('--disable-gpu')
options.add_argument('--no-sandbox')
options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
options.add_argument('--log-level=3')
options.add_experimental_option('excludeSwitches', ['enable-logging'])

# Menggunakan webdriver_manager untuk menginstal dan setup driver secara otomatis
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
print("Browser Selenium berhasil dijalankan.")

# === Konfigurasi Awal ===
# Ganti URL ini ke kategori paling atas yang ingin Anda scrape
start_url = "https://www.gramedia.com/categories/buku"
output_file = "hasil_scrape_gramedia.xlsx"

# ----------------------------------------------------
# 🔹 Logika untuk Resume (Melanjutkan)
# ----------------------------------------------------
visited_products = set()
total_books_scraped = 0

# Daftar header ini PENTING untuk memastikan urutan kolom di Excel benar
header_list = [
    "Kategori Utama", "Subkategori 1", "Subkategori 2", "Subkategori 3", 
    "URL Buku", "URL Gambar", "Nama Penulis", "Judul", "Harga", 
    "Format Buku", "Deskripsi", "Penerbit", "Tanggal Terbit", "ISBN", 
    "Halaman", "Bahasa", "Panjang", "Lebar", "Berat"
]

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
            if os.path.exists(output_file):
                os.remove(output_file)
            
    except Exception as e:
        print(f"⚠️ Gagal membaca file Excel lama: {e}. Membuat file baru (file lama akan dihapus).")
        try:
            if os.path.exists(output_file):
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
    """Mengambil semua link subkategori unik dari halaman."""
    subcats = set() # Gunakan set untuk duplikat otomatis
    
    # 1. Cek slider "pills" di atas
    pills_container = soup.find('section', class_='category-pills-slider')
    if pills_container:
        for a in pills_container.find_all("a", href=True, attrs={'data-testid': lambda x: x and x.startswith('categoriesPill#')}):
            href = a.get("href", "")
            if "/categories/" in href and not "/products/" in href:
                full = "https://www.gramedia.com" + href if href.startswith("/") else href
                if full.startswith("https://www.gramedia.com/categories/") and full != current_url:
                    subcats.add(full)

    # 2. Cek "Lihat Semua" di setiap product slider di halaman
    product_sliders = soup.find_all('div', {'data-id': 'categoriesProductSliderContainer'})
    for slider in product_sliders:
        see_all_link = slider.find('a', {'data-testid': 'productSliderSeeMore'})
        if see_all_link and see_all_link.get('href'):
             href = see_all_link['href']
             if "/categories/" in href and not "/products/" in href:
                full = "https://www.gramedia.com" + href if href.startswith("/") else href
                if full.startswith("https://www.gramedia.com/categories/") and full != current_url:
                    subcats.add(full)
                    
    return list(subcats) # Mengembalikan link unik

def get_products_from_leaf_page(soup):
    """Mengambil SEMUA link /products/ di halaman (untuk halaman leaf)."""
    products = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/products/" in href:
            full = "https://www.gramedia.com" + href if href.startswith("/") else href
            if full.startswith("https://www.gramedia.com/products/"):
                products.add(full)
    return list(products) 

def get_products_from_parent_grid(soup):
    """Mengambil link /products/ HANYA dari grid 'Lainnya di kategori ini'."""
    products = set()
    # Mencari container spesifik dari "Lainnya di kategori ini"
    container = soup.find(attrs={'data-testid': 'categoriesParentProductList'})
    if not container:
        return [] # Tidak ada container, kembalikan list kosong
        
    for a in container.find_all("a", href=True):
        href = a.get("href", "")
        if "/products/" in href:
            full = "https://www.gramedia.com" + href if href.startswith("/") else href
            if full.startswith("https://www.gramedia.com/products/"):
                products.add(full)
    return list(products)

# --------------------------------------
# 🔹 Fungsi scraping detail buku
# --------------------------------------
def scrape_book(url):
    """Mengambil detail satu buku dari URL-nya."""
    global header_list
    # Buat dictionary kosong berdasarkan header_list
    data_buku = {key: "Tidak ditemukan" for key in header_list}
    data_buku["URL Buku"] = url
    
    try:
        driver.get(url)
        # Menunggu elemen spesifikasi produk, tanda halaman sudah dimuat
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='productDetailSpecificationItemLabel']"))
        )
        time.sleep(0.5) # Jeda singkat agar data ter-render sempurna
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
                    # Ambil nama, kecuali "Home"
                    names = [i.get('name') for i in items if i.get('name') and i.get('name').lower() != 'home']
                    
                    if len(names) >= 2: data_buku['Kategori Utama'] = names[0]
                    if len(names) >= 3: data_buku['Subkategori 1'] = names[1]
                    if len(names) >= 4: data_buku['Subkategori 2'] = names[2]
                    if len(names) >= 5: data_buku['Subkategori 3'] = names[3]
                    break # Hentikan loop jika sudah ketemu
            except Exception: 
                continue # Lanjut ke script tag berikutnya jika ada error JSON

        # === URL gambar ===
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'): 
            data_buku['URL Gambar'] = og_image['content']

        # === Format buku ===
        format_container = soup.find(attrs={'data-testid': 'productDetailVariantChips'})
        if format_container:
            # Cari chip format yang aktif (yang memiliki border)
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
        return data_buku # Kembalikan data default (dengan URL) jika gagal

# --------------------------------------
# 🔹 Fungsi menyimpan ke Excel
# --------------------------------------
def save_products_to_excel(product_links, url_kategori="", is_lainnya=False):
    """
    Menerima daftar link produk, men-scrape, dan menyimpannya ke Excel.
    Fungsi ini otomatis mengecek duplikat berdasarkan visited_products
    dan menambahkan flag 'Lainnya' jika perlu.
    """
    global total_books_scraped, visited_products, header_list
    
    books_to_save = []
    new_books_found = 0
    
    # Memfilter link yang belum di-scrape
    links_to_scrape = []
    for link in product_links:
        if link not in visited_products:
            visited_products.add(link)
            links_to_scrape.append(link)
        else:
            pass # Lewati buku yang sudah ada
    
    if not links_to_scrape:
        print(f"ℹ️ Tidak ada buku baru di batch ini yang perlu disimpan (semua sudah ada di Excel).")
        return

    print(f"Scraping {len(links_to_scrape)} buku baru dari batch ini...")
    for link in links_to_scrape:
        book_data = scrape_book(link)
        
        # --- LOGIKA "LAINNYA" ---
        if is_lainnya:
            # Produk ini dari grid "Lainnya". Kita isi slot subkategori kosong pertama.
            if book_data['Kategori Utama'] != 'Tidak ditemukan' and book_data['Subkategori 1'] == 'Tidak ditemukan':
                book_data['Subkategori 1'] = 'Lainnya'
                print(f"   -> Menandai '{book_data['Judul']}' sebagai Subkategori 1: Lainnya")
            elif book_data['Subkategori 1'] != 'Tidak ditemukan' and book_data['Subkategori 2'] == 'Tidak ditemukan':
                book_data['Subkategori 2'] = 'Lainnya'
                print(f"   -> Menandai '{book_data['Judul']}' sebagai Subkategori 2: Lainnya")
            elif book_data['Subkategori 2'] != 'Tidak ditemukan' and book_data['Subkategori 3'] == 'Tidak ditemukan':
                book_data['Subkategori 3'] = 'Lainnya'
                print(f"   -> Menandai '{book_data['Judul']}' sebagai Subkategori 3: Lainnya")
        # --- Akhir Logika "Lainnya" ---

        books_to_save.append(book_data)
        new_books_found += 1

    if new_books_found > 0:
        print(f"💾 Menemukan {new_books_found} buku baru. Menyimpan ke Excel...")
        df_batch = pd.DataFrame(books_to_save)
        
        # Pastikan urutan kolom sesuai header
        df_batch = df_batch.reindex(columns=header_list)
        
        file_exists = os.path.exists(output_file)

        try:
            if not file_exists:
                print(f"Membuat file baru '{output_file}'...")
                df_batch.to_excel(output_file, sheet_name='Sheet1', index=False, header=header_list)
            else:
                with pd.ExcelWriter(output_file, 
                                    mode='a', 
                                    engine='openpyxl', 
                                    if_sheet_exists='overlay') as writer:
                    # Dapatkan sheet yang ada
                    if 'Sheet1' not in writer.sheets:
                        # Jika sheet terhapus, buat ulang dengan header
                        df_batch.to_excel(writer, sheet_name='Sheet1', index=False, header=header_list)
                    else:
                        start_row = writer.sheets['Sheet1'].max_row
                        df_batch.to_excel(writer, 
                                          sheet_name='Sheet1', 
                                          index=False, 
                                          header=False, 
                                          startrow=start_row)
            
            total_books_scraped += new_books_found
            print(f"✅ Berhasil! Total buku tersimpan: {total_books_scraped}")
        
        except Exception as e:
            print(f"❌ GAGAL menyimpan ke Excel: {e}")
            backup_file = f"cadangan_{url_kategori.split('/')[-1]}_{int(time.time())}.xlsx"
            df_batch.to_excel(backup_file, index=False)
            print(f"ℹ️ Data batch disimpan ke file cadangan: {backup_file}")


# --------------------------------------
# 🔹 Fungsi rekursif: jelajahi kategori
# --------------------------------------
def crawl_category(url):
    """Fungsi utama rekursif untuk menjelajahi dan scrape kategori."""
    global total_books_scraped, visited_products
    
    if url in visited_categories:
        print(f"ℹ️ Kategori {url} sudah dikunjungi, dilewati.")
        return
    visited_categories.add(url)

    print(f"\n🌿 Menjelajah kategori: {url}")
    driver.get(url)
    time.sleep(2) # Waktu tunggu dasar agar halaman memuat
    
    # ---------------------------------
    # 1. CEK & KLIK "Muat Lebih Banyak" UNTUK KATEGORI (SCENARIO A - cth: kat.html)
    # ---------------------------------
    try:
        # Loop untuk mengklik tombol "Muat Lebih Banyak" KATEGORI
        while True:
            # Menggunakan CSS Selector yang spesifik untuk tombol kategori
            load_more_categories_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='categoriesLoadMore']"))
            )
            print("🔄 Menemukan tombol 'Muat Lebih Banyak' (KATEGORI) — mengklik...")
            driver.execute_script("arguments[0].click();", load_more_categories_button)
            time.sleep(2) # Beri waktu kategori baru untuk dimuat
    except Exception:
        print("✅ Tidak ada lagi tombol 'Muat Lebih Banyak' (KATEGORI) di halaman ini.")

    # Ambil soup SETELAH semua subkategori (mungkin) di-load
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    # ---------------------------------
    # 2. CEK & SCROLL Grid "Lainnya di kategori ini" (SCENARIO B - cth: subk.html)
    # ---------------------------------
    parent_product_list_container = soup.find(attrs={'data-testid': 'categoriesParentProductList'})
    if parent_product_list_container:
        print(f"📚 Ditemukan bagian 'Lainnya di kategori ini'. Memuat semua produk (infinite scroll)...")
        try:
            # Temukan anchor untuk infinite scroll
            anchor = driver.find_element(By.CSS_SELECTOR, "div[data-testid='categoriesProductListInfiniteScrollAnchor']")
            
            last_product_count = 0
            while True:
                # Selector spesifik untuk produk di dalam grid "Lainnya"
                selector = "div[data-testid='categoriesParentProductList'] a[href*='/products/']"
                current_product_count = len(driver.find_elements(By.CSS_SELECTOR, selector))
                
                # Jika jumlah produk tidak bertambah, berhenti
                if current_product_count == last_product_count and last_product_count > 0:
                    print("✅ Infinite scroll 'Lainnya' selesai.")
                    break
                
                last_product_count = current_product_count
                
                # Scroll ke anchor
                driver.execute_script("arguments[0].scrollIntoView();", anchor)
                print(f"🔄 Scrolling ke bawah... (produk: {current_product_count})")
                time.sleep(3) # Tunggu 3 detik untuk produk baru

        except Exception as e:
            print(f"⚠️ Selesai/Error saat scrolling 'Lainnya di kategori ini'. Mungkin sudah di akhir.")
        
        # Ambil produk HANYA dari grid "Lainnya"
        soup_final_parent = BeautifulSoup(driver.page_source, "html.parser")
        products_parent = get_products_from_parent_grid(soup_final_parent)
        
        print(f"   → Ditemukan {len(products_parent)} link produk unik di 'Lainnya'.")
        # Panggil save_products_to_excel DENGAN flag is_lainnya=True
        save_products_to_excel(products_parent, url_kategori=url, is_lainnya=True)

    # ---------------------------------
    # 3. CEK & SELAMI Subkategori (SCENARIO A & B)
    # ---------------------------------
    subcats = get_subcategories(soup, url)
    
    if subcats:
        print(f"📂 Ditemukan {len(subcats)} subkategori. Melanjutkan penjelajahan...")
        for sub in subcats:
            crawl_category(sub) # Panggil diri sendiri (rekursif)
    
    # ---------------------------------
    # 4. CEK Halaman Daun / Leaf Page (SCENARIO C)
    # (Jika TIDAK ada grid "Lainnya" DAN TIDAK ada subkategori)
    # ---------------------------------
    elif not parent_product_list_container and not subcats:
        print(f"🍂 Ini adalah halaman produk 'leaf' (tanpa 'Lainnya' & subkategori).")
        
        # --- BLOK FILTER STOK HANYA UNTUK LEAF PAGE ---
        print("Mencari filter stok...")
        try:
            stock_filter_switch = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-testid='productListFilterStockSwitch']"))
            )
            if stock_filter_switch.get_attribute('data-state') == 'checked':
                print("⚪ Filter 'Hanya yang tersedia' aktif. Menonaktifkan filter...")
                driver.execute_script("arguments[0].click();", stock_filter_switch)
                time.sleep(2) 
                print("🟢 Filter stok dinonaktifkan.")
            else:
                print("🟢 Filter 'Hanya yang tersedia' sudah tidak aktif.")
        except Exception:
            print(f"⚠️ Tidak dapat menemukan filter stok di halaman 'leaf' ini. Melanjutkan...")
        # --- AKHIR DARI BLOK FILTER STOK ---
        
        print(f"Memuat semua produk (tombol)...")
        # Ini adalah logika "Muat Lebih Banyak" PRODUK
        while True:
            try:
                # Cari tombol "Muat Lebih Banyak" umum
                load_more_products_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Muat Lebih Banyak')]"))
                )
                
                # Pastikan ini BUKAN tombol kategori
                if load_more_products_button.get_attribute('data-testid') == 'categoriesLoadMore':
                    print("✅ Tombol 'Muat Lebih Banyak' KATEGORI terdeteksi, tapi ini 'leaf', berhenti.")
                    break
                    
                print("🔄 Menemukan tombol 'Muat Lebih Banyak' (PRODUK) — mengklik...")
                driver.execute_script("arguments[0].click();", load_more_products_button)
                time.sleep(2)
            except Exception:
                print("✅ Tidak ada lagi tombol 'Muat Lebih Banyak' (PRODUK).")
                break
        
        # Ambil produk dari SEMUA halaman
        soup_final_leaf = BeautifulSoup(driver.page_source, "html.parser")
        products_leaf = get_products_from_leaf_page(soup_final_leaf)
        
        print(f"   → Ditemukan {len(products_leaf)} link produk unik di halaman 'leaf' {url}")
        # Panggil save_products_to_excel TANPA flag (is_lainnya=False)
        save_products_to_excel(products_leaf, url_kategori=url)
        
    print(f"✅ Penjelajahan kategori {url} selesai.")


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