from flask import Flask, render_template, request, abort
from rdflib import Graph, Namespace, RDF
import re

app = Flask(__name__)

# ====== CACHE GLOBAL ======
rdf_graph = None
cached_books = None

# ====== HELPERS ======
def parse_price_to_number(price_str):
    """
    Contoh input: "Rp107.000" atau "Rp 25.350"
    Return float: 107000.0 or 25350.0
    Jika gagal, return None
    """
    if not price_str:
        return None
    # ambil angka dan hapus pemisah ribuan (.) dan koma
    s = str(price_str)
    # Hapus anything selain digit
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    try:
        return float(digits)
    except:
        return None


# ====== LOAD RDF SEKALI ======
def load_rdf():
    global rdf_graph
    if rdf_graph is None:
        rdf_graph = Graph()
        # file RDF: RDF/XML → set format xml agar lebih robust
        rdf_graph.parse("DataBukuGramedia.rdf", format="xml")
    return rdf_graph


# ====== EXTRACT ALL BOOKS SEKALI ======
def extract_books():
    """
    Kembalikan list dict, setiap dict berisi semua properti dari RDF
    Keys mengikuti nama predikat setelah '#', mis: 'Judul', 'Penulis', 'Harga', dst.
    """
    global cached_books

    if cached_books is not None:
        return cached_books

    g = load_rdf()
    BU = Namespace("http://buku.org/buku#")

    books = []

    # Ambil semua subject yang rdf:type bu:Buku
    for subj in g.subjects(RDF.type, BU.Buku):
        b = {"id": str(subj).split("#")[-1], "uri": str(subj)}
        # ambil semua predikat-objek
        for p, o in g.predicate_objects(subj):
            key = str(p).split("#")[-1]  # nama after #
            b[key] = str(o)
        # normalize harga numeric
        b["Harga_num"] = parse_price_to_number(b.get("Harga"))
        # juga standar nama field bahasa/ukuran agar template mudah dipanggil
        books.append(b)

    cached_books = books
    return books


# ====== GENERATE MULTILEVEL CATEGORY ======
def generate_category_tree(books):
    nested = {}
    for b in books:
        cat1 = b.get("KategoriUtama")
        sub1 = b.get("Subkategori1")
        sub2 = b.get("Subkategori2")

        if not cat1:
            continue

        nested.setdefault(cat1, {})

        if sub1:
            nested[cat1].setdefault(sub1, [])
            if sub2 and sub2 not in nested[cat1][sub1]:
                nested[cat1][sub1].append(sub2)

    return nested


# ====== ROUTE HALAMAN UTAMA ======
@app.route("/")
def index():
    all_books = extract_books()
    books = list(all_books)  # salinan untuk filter

    # Ambil parameter
    search_query = request.args.get("query", "").strip()
    search_query_lower = search_query.lower()
    current_filter = request.args.get("filter")
    current_lang = request.args.get("lang", "all")
    selected_sort_price = request.args.get("sort_price")

    # ==== SEARCH ====
    if search_query:
        def matches_search(b):
            judul = b.get("Judul", "")
            penulis = b.get("Penulis", "")
            return (search_query_lower in judul.lower()) or (search_query_lower in penulis.lower())
        books = [b for b in books if matches_search(b)]

    # ==== FILTER KATEGORI / SUB / SUBSUB ====
    if current_filter:
        try:
            filter_type, value = current_filter.split("_", 1)
        except ValueError:
            filter_type, value = None, None

        if filter_type == "cat":
            books = [b for b in books if b.get("KategoriUtama") == value]
        elif filter_type == "sub":
            books = [
                b for b in books
                if b.get("Subkategori1") == value or b.get("Subkategori2") == value
            ]
        elif filter_type == "subsub":
            books = [b for b in books if b.get("Subkategori2") == value]

    # ==== FILTER BAHASA ====
    if current_lang != "all":
        books = [b for b in books if b.get("Bahasa") == current_lang]

    # ==== SORTING HARGA ====
    if selected_sort_price:
        # keep only those that have harga_num
        books = [b for b in books if b.get("Harga_num") is not None]
        if selected_sort_price == "asc":
            books.sort(key=lambda x: x["Harga_num"])
        elif selected_sort_price == "desc":
            books.sort(key=lambda x: x["Harga_num"], reverse=True)

    # ==== SIDEBAR KATEGORI / BAHASA ====
    nested_category_map = generate_category_tree(all_books)
    all_categories = sorted({b.get("KategoriUtama") for b in all_books if b.get("KategoriUtama")})
    all_languages = sorted({b.get("Bahasa") for b in all_books if b.get("Bahasa") and b.get("Bahasa") != "-"})

    # ==== GROUP BOOKS PER KATEGORI (HOME SECTION) ====
    grouped_books = {
        cat: [b for b in all_books if b.get("KategoriUtama") == cat][:10]
        for cat in nested_category_map
    }

    # ==== COUNTS ====
    total_count = len(all_books)
    results_count = len(books)

    # ==== ACTIVE FILTERS (format sederhana) ====
    active_filters = []
    if search_query:
        active_filters.append({"value": search_query})
    if current_filter:
        # show friendly label (remove prefix)
        active_filters.append({"value": current_filter})
    if current_lang != "all":
        active_filters.append({"value": current_lang})

    current_selected_cat = None
    current_selected_sub = None
    if current_filter and current_filter.startswith("cat_"):
        current_selected_cat = current_filter.replace("cat_", "")
    if current_filter and current_filter.startswith("sub_"):
        current_selected_sub = current_filter.replace("sub_", "")

    return render_template(
        "index.html",
        books=books,
        grouped_books=grouped_books,
        all_categories=all_categories,
        all_languages=all_languages,
        nested_category_map=nested_category_map,
        total_count=total_count,
        results_count=results_count,
        current_filter=current_filter,
        current_lang=current_lang,
        search_query=search_query,
        selected_sort_price=selected_sort_price,
        active_filters=active_filters,
        current_selected_cat=current_selected_cat,
        current_selected_sub=current_selected_sub
    )


# ====== GET SINGLE BOOK ======
def get_book_by_id(book_id):
    """
    Ambil data dari cache (cached_books). Jika tidak ditemukan return {}
    """
    books = extract_books()
    for b in books:
        if b.get("id") == book_id:
            return b
    return {}


# ====== ROUTE DETAIL ======
@app.route("/book/<book_id>")
def detail(book_id):
    book = get_book_by_id(book_id)
    if not book:
        abort(404, description="Buku tidak ditemukan")

    # kirim all_categories agar navbar tetap berfungsi
    all_books = extract_books()
    all_categories = sorted({b.get("KategoriUtama") for b in all_books if b.get("KategoriUtama")})

    return render_template("detail.html", book=book, all_categories=all_categories)


if __name__ == "__main__":
    app.run(debug=True)
