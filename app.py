from flask import Flask, render_template, request, abort
from SPARQLWrapper import SPARQLWrapper, JSON

app = Flask(__name__)

# Sesuaikan endpoint dataset Fuseki-mu:
FUSEKI_URL = "http://localhost:3030/bookara/query"

# Prefix yang dipakai di query
PREFIX = """
PREFIX bu: <http://buku.org/buku#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# -----------------------
# Helper: run SPARQL query
# -----------------------
def run_query(query):
    sparql = SPARQLWrapper(FUSEKI_URL)
    sparql.setQuery(PREFIX + "\n" + query)
    sparql.setReturnFormat(JSON)
    return sparql.query().convert()["results"]["bindings"]

# -----------------------
# Map raw SPARQL row -> dict
# keys match template usage (Judul, Penulis, Harga, etc.)
# -----------------------
def map_book_row(row):
    # ambil Gambar dari RDF
    gambar = row.get("Gambar", {}).get("value", "")
    if not gambar:
        gambar = "/static/img/cover.avif"  # fallback default

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
# Load lists used by templates
# -----------------------
def load_categories():
    q = """
    SELECT DISTINCT ?cat WHERE {
        ?b bu:KategoriUtama ?cat .
    }
    ORDER BY ?cat
    """
    rows = run_query(q)
    return [r["cat"]["value"] for r in rows]

def load_languages():
    q = """
    SELECT DISTINCT ?lang WHERE {
        ?b bu:Bahasa ?lang .
    }
    ORDER BY ?lang
    """
    rows = run_query(q)
    return [r["lang"]["value"] for r in rows]

def load_nested_map():
    """
    Return nested_category_map format expected by index.html:
    { category: { sub1: [sub2a, sub2b], sub1b: [...] }, ... }
    """
    q = """
    SELECT DISTINCT ?cat ?sub1 ?sub2 WHERE {
        ?b bu:KategoriUtama ?cat .
        OPTIONAL { ?b bu:Subkategori1 ?sub1 . }
        OPTIONAL { ?b bu:Subkategori2 ?sub2 . }
    }
    ORDER BY ?cat ?sub1 ?sub2
    """
    rows = run_query(q)
    nested = {}
    for r in rows:
        cat = r["cat"]["value"]
        sub1 = r.get("sub1", {}).get("value")
        sub2 = r.get("sub2", {}).get("value")
        if cat not in nested:
            nested[cat] = {}
        if sub1:
            nested[cat].setdefault(sub1, [])
            if sub2:
                if sub2 not in nested[cat][sub1]:
                    nested[cat][sub1].append(sub2)
    return nested

# -----------------------
# Generic book fetcher used by index/search
# -----------------------
def get_books(search_query="", current_filter="", current_lang="all", selected_sort_price=""):
    # sanitize minimal (escape double quotes)
    sq = search_query.replace('"', '\\"')

    filter_clauses = []
    # filters based on filter param (cat_, sub_, subsub_)
    if current_filter:
        if current_filter.startswith("cat_"):
            val = current_filter.replace("cat_", "")
            filter_clauses.append(f'?b bu:KategoriUtama "{val}" .')
        elif current_filter.startswith("sub_"):
            val = current_filter.replace("sub_", "")
            # check in either Subkategori1 or Subkategori2
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

    order_clause = ""
    if selected_sort_price == "asc":
        order_clause = "ORDER BY xsd:decimal(REPLACE(REPLACE(?Harga, 'Rp', ''), '.', ''))"
    elif selected_sort_price == "desc":
        order_clause = "ORDER BY DESC(xsd:decimal(REPLACE(REPLACE(?Harga, 'Rp', ''), '.', '')))"

    # build FILTER area
    filters_block = "\n".join(filter_clauses) + ("\n" + search_clause if search_clause else "")

    q = f"""
    SELECT ?id ?Judul ?Penulis ?Harga ?KategoriUtama ?Sub1 ?Sub2 ?Gambar WHERE {{
        ?b rdf:type bu:Buku .
        ?b bu:Judul ?Judul .
        OPTIONAL {{ ?b bu:Penulis ?Penulis . }}
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:KategoriUtama ?KategoriUtama . }}
        OPTIONAL {{ ?b bu:Subkategori1 ?Sub1 . }}
        OPTIONAL {{ ?b bu:Subkategori2 ?Sub2 . }}
        OPTIONAL {{ ?b bu:Gambar ?Gambar . }}

        BIND(STRAFTER(STR(?b), "#") AS ?id)

        {filters_block}
    }}
    {order_clause}
    LIMIT 100
    """
    rows = run_query(q)
    return [map_book_row(r) for r in rows]

def group_books_by_category(all_books):
    grouped = {}
    for b in all_books:
        cat = b.get("KategoriUtama") or "Uncategorized"
        grouped.setdefault(cat, [])
        grouped[cat].append(b)
    # limit first 10 per category as in template
    return {k: v[:10] for k, v in grouped.items()}

def build_active_filters(current_filter, current_lang, search_query):
    active = []
    if search_query:
        active.append({"value": search_query})
    if current_filter:
        active.append({"value": current_filter})
    if current_lang and current_lang != "all":
        active.append({"value": current_lang})
    return active

# -----------------------
# ROUTES
# -----------------------
@app.route("/")
def index():
    # read params (so template logic that checks them works)
    search_query = request.args.get("query", "")
    current_filter = request.args.get("filter", "")
    current_lang = request.args.get("lang", "all")
    selected_sort_price = request.args.get("sort_price", "")

    # fetch books (for results or home shelf)
    books = get_books(search_query, current_filter, current_lang, selected_sort_price)

    # fetch lists needed by template
    all_categories = load_categories()
    all_languages = load_languages()
    nested_category_map = load_nested_map()

    # For home grouped shelves — use all books (no filters) to populate; if you want use dataset top items, adjust
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
    selected_sort_price = request.args.get("sort_price", "")

    books = get_books(search_query, current_filter, current_lang, selected_sort_price)

    all_categories = load_categories()
    all_languages = load_languages()
    nested_category_map = load_nested_map()
    grouped_books = group_books_by_category(get_books("", "", "all", ""))

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
    # detail query
    q = f"""
    SELECT ?Judul ?Penulis ?Harga ?KategoriUtama
           ?Sub1 ?Sub2 ?Penerbit ?TanggalTerbit ?ISBN ?Halaman ?Bahasa
           ?Panjang ?Lebar ?Berat ?Format ?Deskripsi ?Gambar
    WHERE {{
        ?b rdf:type bu:Buku .
        FILTER(STRAFTER(STR(?b), "#") = "{id}")
        OPTIONAL {{ ?b bu:Judul ?Judul . }}
        OPTIONAL {{ ?b bu:Penulis ?Penulis . }}
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:KategoriUtama ?KategoriUtama . }}
        OPTIONAL {{ ?b bu:Subkategori1 ?Sub1 . }}
        OPTIONAL {{ ?b bu:Subkategori2 ?Sub2 . }}
        OPTIONAL {{ ?b bu:Penerbit ?Penerbit . }}
        OPTIONAL {{ ?b bu:TanggalTerbit ?TanggalTerbit . }}
        OPTIONAL {{ ?b bu:ISBN ?ISBN . }}
        OPTIONAL {{ ?b bu:Halaman ?Halaman . }}
        OPTIONAL {{ ?b bu:Bahasa ?Bahasa . }}
        OPTIONAL {{ ?b bu:Panjang ?Panjang . }}
        OPTIONAL {{ ?b bu:Lebar ?Lebar . }}
        OPTIONAL {{ ?b bu:Berat ?Berat . }}
        OPTIONAL {{ ?b bu:Format ?Format . }}
        OPTIONAL {{ ?b bu:Deskripsi ?Deskripsi . }}
        OPTIONAL {{ ?b bu:Gambar ?Gambar . }}
    }}
    LIMIT 1
    """
    rows = run_query(q)
    if not rows:
        abort(404)
    r = rows[0]
    # produce book dict with keys matching template
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
