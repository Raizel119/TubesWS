from flask import Flask, render_template, request, abort, jsonify
from SPARQLWrapper import SPARQLWrapper, JSON
from urllib.parse import quote, unquote
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
    if not gambar:
        gambar = "" 

    return {
        "id": row.get("id", {}).get("value", "").split("#")[-1],
        "Judul": row.get("Judul", {}).get("value", ""),
        "Penulis": row.get("Penulis", {}).get("value", ""),
        "Harga": row.get("Harga", {}).get("value", ""),
        "KategoriUtama": row.get("KategoriUtama", {}).get("value", ""),
        "Subkategori1": row.get("Sub1", {}).get("value", ""),
        "Subkategori2": row.get("Sub2", {}).get("value", ""),
        "Subkategori3": row.get("Sub3", {}).get("value", ""),
        "Gambar": gambar
    }

def load_categories():
    rows = run_query(queries.GET_ALL_CATEGORIES)
    return [r["cat"]["value"] for r in rows]

def load_languages():
    rows = run_query(queries.GET_ALL_LANGUAGES)
    return [r["lang"]["value"] for r in rows]

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

# -------------------------------------------------
# Get Books Logic
# -------------------------------------------------
def get_books(search_query="", current_filter="", current_lang="all", page_range="all", sort_option="price_asc", limit=20, offset=0):
    # Builder hanya urus filter (Where clause)
    filters_block = queries.build_filter_string(search_query, current_filter, current_lang, page_range)
    
    # Sort option dikirim langsung ke query utama
    q = queries.get_books_query(filters_block, sort_option, limit, offset)
    rows = run_query(q)
    return [map_book_row(r) for r in rows]

def get_total_books_count(search_query="", current_filter="", current_lang="all", page_range="all"):
    filters_block = queries.build_filter_string(search_query, current_filter, current_lang, page_range)
    q = queries.get_total_count_query(filters_block)
    rows = run_query(q)
    if rows:
        return int(rows[0]["count"]["value"])
    return 0

def group_books_by_category(all_books):
    grouped = {}
    for b in all_books:
        cat = b.get("KategoriUtama") or "Uncategorized"
        grouped.setdefault(cat, [])
        grouped[cat].append(b)
    return {k: v[:10] for k, v in grouped.items()}

# [PERBAIKAN DI SINI]
def build_active_filters(current_filter, current_lang, search_query, page_range, sort_option):
    active = []

    if search_query:
        active.append({"key": "query", "value": f'"{search_query}"'})

    if current_filter:
        clean = re.sub(r'^(cat_|sub_|subsub_|sub3_)', '', current_filter)
        clean_display = unquote(clean)
        active.append({"key": "filter", "value": clean_display})

    if current_lang and current_lang != "all":
        active.append({"key": "lang", "value": current_lang})

    if page_range and page_range != "all":
        active.append({"key": "page_range", "value": f"{page_range} Hal"})
        
    # [FIX] Sekarang semua opsi sorting akan memunculkan tag
    if sort_option:
        label = ""
        if sort_option == "date_newest": label = "Terbaru"
        elif sort_option == "date_oldest": label = "Terlama"
        elif sort_option == "price_desc": label = "Harga Tertinggi"
        elif sort_option == "price_asc": label = "Harga Terendah" # DITAMBAHKAN
        
        if label:
            active.append({"key": "sort", "value": label})

    return active

# -----------------------
# ROUTES
# -----------------------
@app.route("/")
def index():
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    
    # Menggunakan sort_option
    sort_option = request.args.get("sort", "price_asc") 
    page_range = request.args.get("page_range", "all")

    books = get_books(search_query, current_filter, current_lang, page_range, sort_option, limit=20, offset=0)
    total_count = get_total_books_count(search_query, current_filter, current_lang, page_range)

    all_categories = load_categories()
    all_languages = load_languages()
    nested_category_map = load_nested_map()

    grouped_books = {}
    # Tampilkan rak buku jika halaman bersih (default)
    # Cek: search kosong, filter kosong, lang all, page all, DAN sort harus default (price_asc)
    is_clean_home = not (search_query or current_filter or current_lang != 'all' or page_range != 'all' or sort_option != 'price_asc')
    
    if is_clean_home:
        all_books_for_shelves = get_books("", "", "all", "all", "price_asc", limit=100, offset=0)
        grouped_books = group_books_by_category(all_books_for_shelves)

    active_filters = build_active_filters(current_filter, current_lang, search_query, page_range, sort_option)

    return render_template(
        "index.html",
        books=books,
        grouped_books=grouped_books,
        all_categories=all_categories,
        all_languages=all_languages,
        nested_category_map=nested_category_map,
        total_count=total_count,
        results_count=len(books),
        current_filter=current_filter,
        current_lang=current_lang,
        search_query=search_query,
        sort_option=sort_option,
        page_range=page_range,
        active_filters=active_filters
    )

@app.route("/api/load-more")
def load_more():
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    sort_option = request.args.get("sort", "price_asc") 
    page_range = request.args.get("page_range", "all")
    
    offset = request.args.get("offset", 0, type=int)
    limit = 20 

    books = get_books(search_query, current_filter, current_lang, page_range, sort_option, limit, offset)
    return jsonify(books)

@app.route("/book/<id>")
def detail(id):
    q = queries.get_book_detail_query(id)
    rows = run_query(q)
    
    if not rows:
        abort(404)
    r = rows[0]
    
    book = {
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
        "URL": r.get("URL", {}).get("value", "#"),
        "id": id
    }

    more_books = []
    raw_author = book["Penulis"]
    
    if raw_author:
        # Pecah string berdasarkan koma (,)
        # Contoh: "Nur Aksin, Anna Yuni" -> ["Nur Aksin", "Anna Yuni"]
        author_list = [name.strip() for name in raw_author.split(',') if name.strip()]
        
        if author_list:
            # Kirim list penulis ke query baru
            q_author = queries.get_books_by_author_query(author_list, id)
            rows_author = run_query(q_author)
            more_books = [map_book_row(row) for row in rows_author]

    all_categories = load_categories()
    nested_category_map = load_nested_map()

    return render_template(
        "detail.html",
        book=book,
        more_books=more_books,
        all_categories=all_categories,
        nested_category_map=nested_category_map
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)