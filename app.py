from flask import Flask, render_template, request, abort, jsonify
from SPARQLWrapper import SPARQLWrapper, JSON
from urllib.parse import quote

import queries 

app = Flask(__name__)

@app.template_filter('uquote')
def uquote_filter(s):
    if s:
        return quote(s, safe='')
    return ""

FUSEKI_URL = "http://localhost:3030/bookara/query"

def run_query(query_string):
    sparql = SPARQLWrapper(FUSEKI_URL)
    sparql.setQuery(queries.PREFIX + "\n" + query_string)
    sparql.setReturnFormat(JSON)
    return sparql.query().convert()["results"]["bindings"]

# UPDATE: Tambahkan mapping untuk Sub3
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
        "Subkategori3": row.get("Sub3", {}).get("value", ""), # <-- BARU
        "Gambar": gambar
    }

def load_categories():
    rows = run_query(queries.GET_ALL_CATEGORIES)
    return [r["cat"]["value"] for r in rows]

def load_languages():
    rows = run_query(queries.GET_ALL_LANGUAGES)
    return [r["lang"]["value"] for r in rows]

# UPDATE: Logika Nested Map 4 Level
# Struktur: { 'Utama': { 'Sub1': { 'Sub2': ['Sub3a', 'Sub3b'] } } }
def load_nested_map():
    rows = run_query(queries.GET_NESTED_MAP)
    nested = {}
    for r in rows:
        cat = r["cat"]["value"]
        sub1 = r.get("sub1", {}).get("value")
        sub2 = r.get("sub2", {}).get("value")
        sub3 = r.get("sub3", {}).get("value")

        if cat not in nested:
            nested[cat] = {}
        
        if sub1:
            # Pastikan sub1 ada di dictionary parent
            if sub1 not in nested[cat]:
                nested[cat][sub1] = {}
            
            if sub2:
                # Pastikan sub2 ada di dictionary sub1
                # Di level sub2, nilainya sekarang adalah LIST dari sub3
                if sub2 not in nested[cat][sub1]:
                    nested[cat][sub1][sub2] = []
                
                if sub3:
                    # Jika sub3 belum ada di list, tambahkan
                    if sub3 not in nested[cat][sub1][sub2]:
                        nested[cat][sub1][sub2].append(sub3)
                        
    return nested

# UPDATE: Filter Logic untuk Sub3
def build_filter_string(search_query, current_filter, current_lang):
    sq = search_query.replace('"', '\\"')

    filter_clauses = []
    
    if current_filter:
        if current_filter.startswith("cat_"):
            val = current_filter.replace("cat_", "")
            filter_clauses.append(f'?b bu:KategoriUtama "{val}" .')
        elif current_filter.startswith("sub_"):
            val = current_filter.replace("sub_", "")
            # Filter ini mencari di Sub1, Sub2, ATAU Sub3 (lebih fleksibel)
            filter_clauses.append(f'FILTER(?Sub1 = "{val}" || ?Sub2 = "{val}" || ?Sub3 = "{val}")')
        elif current_filter.startswith("subsub_"):
            val = current_filter.replace("subsub_", "")
            filter_clauses.append(f'?b bu:Subkategori2 "{val}" .')
        elif current_filter.startswith("sub3_"): # <-- BARU
            val = current_filter.replace("sub3_", "")
            filter_clauses.append(f'?b bu:Subkategori3 "{val}" .')

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
    
    return "\n".join(filter_clauses) + ("\n" + search_clause if search_clause else "")

def get_books(search_query="", current_filter="", current_lang="all", selected_sort_price="asc", limit=20, offset=0):
    filters_block = build_filter_string(search_query, current_filter, current_lang)

    order_clause = ""
    if selected_sort_price == "desc":
        order_clause = "ORDER BY DESC(xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', '')))"
    else:
        order_clause = "ORDER BY xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', ''))"

    q = queries.get_books_query(filters_block, order_clause, limit, offset)
    
    rows = run_query(q)
    return [map_book_row(r) for r in rows]

def get_total_books_count(search_query="", current_filter="", current_lang="all"):
    filters_block = build_filter_string(search_query, current_filter, current_lang)
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
    selected_sort_price = request.args.get("sort_price", "asc")

    books = get_books(search_query, current_filter, current_lang, selected_sort_price, limit=20, offset=0)
    total_count = get_total_books_count(search_query, current_filter, current_lang)

    all_categories = load_categories()
    all_languages = load_languages()
    nested_category_map = load_nested_map()

    all_books_for_shelves = get_books("", "", "all", "asc", limit=100, offset=0)
    grouped_books = group_books_by_category(all_books_for_shelves)

    active_filters = build_active_filters(current_filter, current_lang, search_query)

    # Logika untuk menentukan dropdown mana yang terbuka di Sidebar (sampai level 3)
    current_cat = None
    current_sub1 = None
    current_sub2 = None # Sub2 sekarang menjadi parent dari Sub3

    if current_filter:
        if current_filter.startswith("cat_"):
            current_cat = current_filter.replace("cat_", "")
        elif current_filter.startswith("sub_"):
            current_sub1 = current_filter.replace("sub_", "")
        elif current_filter.startswith("subsub_"):
            current_sub2 = current_filter.replace("subsub_", "")
        # Jika filter adalah sub3_, kita tidak perlu variabel khusus karena logic template akan mencarinya

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
        selected_sort_price=selected_sort_price,
        active_filters=active_filters,
        # Pass variable helper untuk template
        current_cat=current_cat,
        current_sub1=current_sub1,
        current_sub2=current_sub2
    )

@app.route("/search")
def search():
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    selected_sort_price = request.args.get("sort_price", "asc")

    books = get_books(search_query, current_filter, current_lang, selected_sort_price, limit=20, offset=0)
    total_count = get_total_books_count(search_query, current_filter, current_lang)

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
        total_count=total_count,
        results_count=len(books)
    )

@app.route("/api/load-more")
def load_more():
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    selected_sort_price = request.args.get("sort_price", "asc")
    offset = request.args.get("offset", 0, type=int)
    limit = 20 

    books = get_books(search_query, current_filter, current_lang, selected_sort_price, limit, offset)
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
        "Subkategori3": r.get("Sub3", {}).get("value", ""), # BARU
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