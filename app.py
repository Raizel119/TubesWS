from flask import Flask, render_template, request, abort
from SPARQLWrapper import SPARQLWrapper, JSON
from urllib.parse import quote

# --- IMPORT FILE QUERIES YANG BARU DIBUAT ---
import queries 

app = Flask(__name__)
@app.template_filter('uquote')
def uquote_filter(s):
    """Mengubah karakter spesial (seperti &) menjadi aman untuk URL"""
    if s:
        return quote(s, safe='')
    return ""

FUSEKI_URL = "http://localhost:3030/bookara/query"

# -----------------------
# Helper: run SPARQL query
# -----------------------
def run_query(query_string):
    sparql = SPARQLWrapper(FUSEKI_URL)
    # Gabungkan PREFIX dari file queries dengan query string
    sparql.setQuery(queries.PREFIX + "\n" + query_string)
    sparql.setReturnFormat(JSON)
    return sparql.query().convert()["results"]["bindings"]

# -----------------------
# Map raw SPARQL row -> dict
# -----------------------
def map_book_row(row):
    gambar = row.get("Gambar", {}).get("value", "")
    if not gambar:
        gambar = "/static/img/cover.avif"

    return {
        "id": row.get("id", {}).get("value", "").split("#")[-1],
        "Judul": row.get("Judul", {}).get("value", ""),
        "Penulis": row.get("Penulis", {}).get("value", ""),
        "Harga": row.get("Harga", {}).get("value", ""),
        "KategoriUtama": row.get("KategoriUtama", {}).get("value", ""),
        "Subkategori1": row.get("Sub1", {}).get("value", ""),
        "Subkategori2": row.get("Sub2", {}).get("value", ""),
        "Gambar": gambar
    }

# -----------------------
# Load lists
# -----------------------
def load_categories():
    # Menggunakan variabel dari queries.py
    rows = run_query(queries.GET_ALL_CATEGORIES)
    return [r["cat"]["value"] for r in rows]

def load_languages():
    rows = run_query(queries.GET_ALL_LANGUAGES)
    return [r["lang"]["value"] for r in rows]

def load_nested_map():
    rows = run_query(queries.GET_NESTED_MAP)
    nested = {}
    for r in rows:
        cat = r["cat"]["value"]
        sub1 = r.get("sub1", {}).get("value")
        sub2 = r.get("sub2", {}).get("value")
        if cat not in nested:
            nested[cat] = {}
        if sub1:
            nested[cat].setdefault(sub1, [])
            if sub2 and sub2 not in nested[cat][sub1]:
                nested[cat][sub1].append(sub2)
    return nested

# -----------------------
# Generic book fetcher
# -----------------------
def get_books(search_query="", current_filter="", current_lang="all", selected_sort_price="asc"):
    # Default selected_sort_price di-set ke "asc" di parameter fungsi ^^^
    
    sq = search_query.replace('"', '\\"')

    filter_clauses = []
    if current_filter:
        if current_filter.startswith("cat_"):
            val = current_filter.replace("cat_", "")
            filter_clauses.append(f'?b bu:KategoriUtama "{val}" .')
        elif current_filter.startswith("sub_"):
            val = current_filter.replace("sub_", "")
            filter_clauses.append(f'FILTER(?Sub1 = "{val}" || ?Sub2 = "{val}")')
        elif current_filter.startswith("subsub_"):
            val = current_filter.replace("subsub_", "")
            filter_clauses.append(f'?b bu:Subkategori2 "{val}" .')

    if current_lang != "all":
        filter_clauses.append(f'?b bu:Bahasa "{current_lang}" .')

    search_clause = ""
    if sq:
        search_clause = f'''
        FILTER(
            CONTAINS(LCASE(?Judul), LCASE("{sq}")) ||
            CONTAINS(LCASE(?Penulis), LCASE("{sq}"))
        )
        '''

    # --- LOGIKA SORTING HARGA YANG DIPERBAIKI ---
    # Rumus: Hapus "Rp", Hapus Titik "[.]", lalu ubah ke Integer
    order_clause = ""
    if selected_sort_price == "desc":
        order_clause = "ORDER BY DESC(xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', '')))"
    else:
        # Default (asc) atau jika kosong
        order_clause = "ORDER BY xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', ''))"

    filters_block = "\n".join(filter_clauses) + ("\n" + search_clause if search_clause else "")

    q = queries.get_books_query(filters_block, order_clause)
    
    rows = run_query(q)
    return [map_book_row(r) for r in rows]

def group_books_by_category(all_books):
    grouped = {}
    for b in all_books:
        cat = b.get("KategoriUtama") or "Uncategorized"
        grouped.setdefault(cat, [])
        grouped[cat].append(b)
    return {k: v[:10] for k, v in grouped.items()}

def build_active_filters(current_filter, current_lang, search_query):
    active = []
    if search_query: active.append({"value": search_query})
    if current_filter: active.append({"value": current_filter})
    if current_lang and current_lang != "all": active.append({"value": current_lang})
    return active

# -----------------------
# ROUTES
# -----------------------
@app.route("/")
def index():
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    # UBAH DISINI: Default 'asc' jika tidak ada di URL
    selected_sort_price = request.args.get("sort_price", "asc") 

    books = get_books(search_query, current_filter, current_lang, selected_sort_price)
    
    # Menggunakan fungsi load yang sudah diperbarui
    all_categories = load_categories()
    all_languages = load_languages()
    nested_category_map = load_nested_map()

    all_books_for_shelves = get_books("", "", "all", "")
    grouped_books = group_books_by_category(all_books_for_shelves)

    active_filters = build_active_filters(current_filter, current_lang, search_query)

    return render_template(
        "index.html",
        books=books,
        grouped_books=grouped_books,
        all_categories=all_categories,
        all_languages=all_languages,
        nested_category_map=nested_category_map,
        total_count=len(all_books_for_shelves),
        results_count=len(books),
        current_filter=current_filter,
        current_lang=current_lang,
        search_query=search_query,
        selected_sort_price=selected_sort_price,
        active_filters=active_filters,
        current_selected_cat=current_filter.replace("cat_", "") if current_filter.startswith("cat_") else None,
        current_selected_sub=current_filter.replace("sub_", "") if current_filter.startswith("sub_") else None
    )

@app.route("/search")
def search():
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    # UBAH DISINI: Default 'asc' jika tidak ada di URL
    selected_sort_price = request.args.get("sort_price", "asc") 

    books = get_books(search_query, current_filter, current_lang, selected_sort_price)
    all_categories = load_categories()
    all_languages = load_languages()
    nested_category_map = load_nested_map()
    
    return render_template(
        "search.html",
        books=books,
        search_query=search_query,
        current_filter=current_filter,
        current_lang=current_lang,
        selected_sort_price=selected_sort_price,
        nested_category_map=nested_category_map,
        all_categories=all_categories,
        all_languages=all_languages,
        total_count=len(get_books("", "", "all", "")),
        results_count=len(books)
    )

@app.route("/book/<id>")
def detail(id):
    # Panggil fungsi pembentuk query dari file terpisah
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
        "id": id
    }

    all_categories = load_categories()
    nested_category_map = load_nested_map()

    return render_template(
        "detail.html",
        book=book,
        all_categories=all_categories,
        nested_category_map=nested_category_map
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)