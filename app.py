# app.py
from flask import Flask, render_template, request, abort, jsonify
from SPARQLWrapper import SPARQLWrapper, JSON
from urllib.parse import quote, unquote
from collections import defaultdict
from functools import lru_cache # Import untuk caching
import re
import queries 

app = Flask(__name__)

@app.template_filter('uquote')
def uquote_filter(s):
    if s:
        return quote(s, safe='')
    return ""

@app.route("/about") 
def about():
    return render_template("about.html") 

FUSEKI_URL = "http://localhost:3030/bookara/query"

def run_query(query_string):
    """
    Mengirim query SPARQL mentah ke server Fuseki.
    """
    sparql = SPARQLWrapper(FUSEKI_URL)
    sparql.setQuery(queries.PREFIX + "\n" + query_string)
    sparql.setReturnFormat(JSON)

    try:
        return sparql.query().convert()["results"]["bindings"]
    except Exception as e:
        print(f"SPARQL Error: {e}")
        return []

def map_book_row(row):
    gambar = row.get("Gambar", {}).get("value", "")
    
    # ID diambil dengan memecah URI (misal: http://buku.org/buku#B001 -> B001)
    return {
        "id": row.get("id", {}).get("value", "").split("#")[-1],
        "Judul": row.get("Judul", {}).get("value", ""),
        "Penulis": row.get("Penulis", {}).get("value", ""),
        "Harga": row.get("Harga", {}).get("value", ""),
        "KategoriUtama": row.get("KategoriUtama", {}).get("value", ""),
        "Subkategori1": row.get("Sub1", {}).get("value", ""),
        "Subkategori2": row.get("Sub2", {}).get("value", ""),
        "Subkategori3": row.get("Sub3", {}).get("value", ""),
        "Gambar": gambar if gambar else ""
    }

# --- OPTIMASI 1: CACHING SIDEBAR ---
# Data kategori/bahasa jarang berubah. Kita cache agar tidak query berulang-ulang.
@lru_cache(maxsize=1)
def load_categories():
    rows = run_query(queries.GET_ALL_CATEGORIES)
    return [r["cat"]["value"] for r in rows]

@lru_cache(maxsize=1)
def load_languages():
    rows = run_query(queries.GET_ALL_LANGUAGES)
    return [r["lang"]["value"] for r in rows]

@lru_cache(maxsize=1)
def load_nested_map():
    rows = run_query(queries.GET_NESTED_MAP)
    nested = {}

    def clean(val):
        if not val: return None
        if val.strip().lower() == "tidak ditemukan": return None
        return val

    for r in rows:
        cat = clean(r["cat"]["value"])
        sub1 = clean(r.get("sub1", {}).get("value"))
        sub2 = clean(r.get("sub2", {}).get("value"))
        sub3 = clean(r.get("sub3", {}).get("value"))

        if not cat: continue

        if cat not in nested: nested[cat] = {}
        if sub1:
            if sub1 not in nested[cat]: nested[cat][sub1] = {}
            if sub2:
                if sub2 not in nested[cat][sub1]: nested[cat][sub1][sub2] = []
                if sub3 and sub3 not in nested[cat][sub1][sub2]:
                    nested[cat][sub1][sub2].append(sub3)
    return nested
# -----------------------------------

def get_books(search_query="", current_filter="", current_lang="all",
                page_range="all", sort_option="price_asc",
                limit=20, offset=0):
    filters_block = queries.build_filter_string(
        search_query, current_filter, current_lang, page_range
    )
    q = queries.get_books_query(filters_block, sort_option, limit, offset)
    return [map_book_row(r) for r in run_query(q)]

def get_total_books_count(search_query="", current_filter="", current_lang="all", page_range="all"):
    filters_block = queries.build_filter_string(search_query, current_filter, current_lang, page_range)
    q = queries.get_total_count_query(filters_block)
    rows = run_query(q)
    if rows:
        return int(rows[0]["count"]["value"])
    return 0

def build_active_filters(current_filter, current_lang, search_query, page_range, sort_option):
    active = []
    if search_query:
        active.append({"key": "query", "value": f'"{search_query}"'})
        
    if current_filter:
        # Hapus prefix teknis
        clean = re.sub(r'^(cat_|sub_|subsub_|sub3_)', '', current_filter)
        decoded = unquote(clean)
        
        # FIX TAMPILAN: Jika ada pipa '|', ambil bagian paling terakhir saja untuk ditampilkan
        # Contoh: "Buku|Agama|Lainnya" -> Tampilkan "Lainnya"
        display_label = decoded.split('|')[-1]
        
        active.append({"key": "filter", "value": display_label})

    if current_lang and current_lang != "all":
        # Ubah label bahasa untuk UI jika English -> Inggris
        lang_label = current_lang
        if current_lang == "English": lang_label = "Inggris"
        elif current_lang == "Indonesian": lang_label = "Indonesia"
        
        active.append({"key": "lang", "value": lang_label})

    if page_range and page_range != "all":
        active.append({"key": "page_range", "value": f"{page_range} Hal"})

    if sort_option:
        labels = {
            "date_newest": "Terbaru", "date_oldest": "Terlama",
            "price_desc": "Harga Tertinggi", "price_asc": "Harga Terendah"
        }
        if sort_option in labels:
            active.append({"key": "sort", "value": labels[sort_option]})
            
    return active

@app.route("/")
def index():
    # Mengambil parameter dari URL (?query=..., ?filter=...)
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    sort_option = request.args.get("sort", "price_asc")
    page_range = request.args.get("page_range", "all")

    # Ambil data utama (untuk list view)
    books = get_books(search_query, current_filter, current_lang, page_range, sort_option, limit=20)
    total_count = get_total_books_count(search_query, current_filter, current_lang, page_range)

    # Cek apakah sedang di Home bersih
    is_clean_home = not (
        search_query or current_filter or current_lang != 'all'
        or page_range != 'all' or sort_option != 'price_asc'
    )

    grouped_books = defaultdict(list)
    # Gunakan load_categories yang sudah di-cache (lebih cepat)
    all_categories = load_categories()

    if is_clean_home:
        # --- OPTIMASI 2: EAGER LOADING (PYTHON GROUPING) ---
        # Daripada request ke DB 20 kali (1 kali per kategori),
        # Kita request 1 kali saja untuk ambil BANYAK data (misal 500 buku),
        # Lalu kita sortir manual di Python. Jauh lebih cepat (mengurangi HTTP Round-trip).
        
        # Ambil 500 buku acak/terbaru (tanpa filter)
        raw_home_books = get_books(limit=500, sort_option="date_newest") 
        
        for b in raw_home_books:
            cat = b.get('KategoriUtama')
            # Hanya masukkan jika kategori valid dan belum penuh (max 10 buku per rak)
            if cat and cat in all_categories and len(grouped_books[cat]) < 10:
                grouped_books[cat].append(b)
        
        # Konversi defaultdict ke dict biasa agar template tidak bingung
        grouped_books = dict(grouped_books)

    return render_template(
        "index.html",
        books=books,
        grouped_books=grouped_books,
        all_categories=all_categories,
        all_languages=load_languages(), # Ini juga sekarang cached
        nested_category_map=load_nested_map(), # Ini juga cached
        total_count=total_count,
        results_count=len(books),
        current_filter=current_filter,
        current_lang=current_lang,
        search_query=search_query,
        sort_option=sort_option,
        page_range=page_range,
        active_filters=build_active_filters(current_filter, current_lang, search_query, page_range, sort_option)
    )

@app.route("/api/load-more")
def load_more():
    offset = request.args.get("offset", 0, type=int)
    books = get_books(
        request.args.get("query", ""), 
        request.args.get("filter", ""), 
        request.args.get("lang", "all"), 
        request.args.get("page_range", "all"), 
        request.args.get("sort", "price_asc"), 
        limit=20, offset=offset
    )
    return jsonify(books)

@app.route("/book/<id>")
def detail(id):
    # Detail buku sudah cukup eager (menarik semua properti dalam 1 query)
    rows = run_query(queries.get_book_detail_query(id))
    if not rows: abort(404)

    r = rows[0]
    book = {
        "id": id,
        "Judul": r.get("Judul", {}).get("value", ""),
        "Penulis": r.get("Penulis", {}).get("value", ""),
        "Harga": r.get("Harga", {}).get("value", ""),
        "KategoriUtama": r.get("KategoriUtama", {}).get("value", ""),
        "Subkategori1": r.get("Sub1", {}).get("value", ""),
        "Subkategori2": r.get("Sub2", {}).get("value", ""),
        "Subkategori3": r.get("Sub3", {}).get("value", ""),
        "Penerbit": r.get("Penerbit", {}).get("value", ""),
        "TanggalTerbit": r.get("TanggalTerbit", {}).get("value", ""),
        "ISBN": r.get("ISBN", {}).get("value", ""),
        "Halaman": r.get("Halaman", {}).get("value", ""),
        "Bahasa": r.get("Bahasa", {}).get("value", ""),
        "Panjang": r.get("Panjang", {}).get("value", ""),
        "Lebar": r.get("Lebar", {}).get("value", ""),
        "Berat": r.get("Berat", {}).get("value", ""),
        "Format": r.get("Format", {}).get("value", ""),
        "Deskripsi": r.get("Deskripsi", {}).get("value", ""),
        "Gambar": r.get("Gambar", {}).get("value", "/static/img/cover.avif"),
        "URL": r.get("URL", {}).get("value", "#")
    }

    # Info Penulis dari DBpedia
    author_dbpedia = None
    if book["Penulis"]:
        print(f"🔍 Mencari info penulis '{book['Penulis']}' di DBpedia...")
        author_dbpedia = queries.get_author_info_from_dbpedia(book["Penulis"])

    # Info Film
    film_dbpedia = None
    if book["Judul"]:
        print(f"🎬 Mencari adaptasi film untuk '{book['Judul']}'...")
        film_dbpedia = queries.get_film_adaptation(book["Judul"], book["Penulis"])

    # Rekomendasi
    more_books = []
    if book["Penulis"]:
        author_list = [name.strip() for name in book["Penulis"].split(',') if name.strip()]
        if author_list:
            rows_author = run_query(queries.get_books_by_author_query(author_list, id))
            more_books = [map_book_row(row) for row in rows_author]

    return render_template(
        "detail.html",
        book=book,
        author_dbpedia=author_dbpedia,
        film_dbpedia=film_dbpedia,
        more_books=more_books,
        # Menggunakan fungsi cached agar loading detail page juga lebih cepat
        all_categories=load_categories(),
        nested_category_map=load_nested_map()
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)