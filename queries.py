# queries.py

# ==========================================================
# 1. PREFIX GLOBAL UNTUK SEMUA QUERY
#    Prefix ini dipakai supaya query SPARQL lebih pendek.
# ==========================================================
PREFIX = """
PREFIX bu: <http://buku.org/buku#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# ==========================================================
# 2. QUERY STATIS
#    Query langsung tanpa filter dinamis.
# ==========================================================

# Ambil semua kategori utama
GET_ALL_CATEGORIES = """
SELECT DISTINCT ?cat WHERE {
    ?b bu:KategoriUtama ?cat .
}
ORDER BY ?cat
"""

# Ambil semua bahasa yang ada dalam data
GET_ALL_LANGUAGES = """
SELECT DISTINCT ?lang WHERE {
    ?b bu:Bahasa ?lang .
}
ORDER BY ?lang
"""

# Ambil semua tanggal terbit (dipakai untuk kebutuhan tertentu)
GET_ALL_DATES = """
SELECT DISTINCT ?date WHERE {
    ?b bu:TanggalTerbit ?date .
}
"""

# Ambil struktur kategori lengkap: kategori → sub1 → sub2 → sub3
GET_NESTED_MAP = """
SELECT DISTINCT ?cat ?sub1 ?sub2 ?sub3 WHERE {
    ?b bu:KategoriUtama ?cat .
    OPTIONAL { ?b bu:Subkategori1 ?sub1 . }
    OPTIONAL { ?b bu:Subkategori2 ?sub2 . }
    OPTIONAL { ?b bu:Subkategori3 ?sub3 . }
}
ORDER BY ?cat ?sub1 ?sub2 ?sub3
"""

# ==========================================================
# 3. PEMBUAT FILTER BERDASARKAN JUMLAH HALAMAN
# ==========================================================
def get_page_filter_clause(page_range):
    if not page_range or page_range == "all":
        return ""
    
    if page_range == "0-100":
        return "FILTER(xsd:integer(?Halaman) <= 100)"
    elif page_range == "100-200":
        return "FILTER(xsd:integer(?Halaman) > 100 && xsd:integer(?Halaman) <= 200)"
    elif page_range == "200+":
        return "FILTER(xsd:integer(?Halaman) > 200)"
    
    return ""

# ==========================================================
# 4. PEMBUAT FILTER UTAMA (search, kategori, bahasa, halaman)
#    Fungsi ini membuat potongan query SPARQL sesuai input
# ==========================================================
def build_filter_string(search_query, current_filter, current_lang, page_range):
    sq = search_query.replace('"', '\\"')
    filter_clauses = []
    
    # ---------- Filter Kategori ----------
    if current_filter:
        # Filter kategori utama
        if current_filter.startswith("cat_"):
            val = current_filter.replace("cat_", "")
            filter_clauses.append(f'?b bu:KategoriUtama "{val}" .')

        # Filter subkategori 1/2/3
        elif current_filter.startswith("sub_"):
            val = current_filter.replace("sub_", "")
            filter_clauses.append(
                f'FILTER(?Sub1 = "{val}" || ?Sub2 = "{val}" || ?Sub3 = "{val}")'
            )

        # Filter level subkategori 2
        elif current_filter.startswith("subsub_"):
            val = current_filter.replace("subsub_", "")
            filter_clauses.append(f'?b bu:Subkategori2 "{val}" .')

        # Filter level subkategori 3
        elif current_filter.startswith("sub3_"):
            val = current_filter.replace("sub3_", "")
            filter_clauses.append(f'?b bu:Subkategori3 "{val}" .')

    # ---------- Filter Bahasa ----------
    if current_lang != "all":
        filter_clauses.append(f'?b bu:Bahasa "{current_lang}" .')

    # ---------- Filter Halaman ----------
    page_clause = get_page_filter_clause(page_range)
    if page_clause:
        filter_clauses.append(page_clause)

    # ---------- Filter Search ----------
    search_clause = ""
    if sq:
        search_clause = f'''
        FILTER(
            CONTAINS(LCASE(?Judul), LCASE("{sq}")) ||
            CONTAINS(LCASE(?Penulis), LCASE("{sq}"))
        )
        '''
    
    return "\n".join(filter_clauses) + ("\n" + search_clause if search_clause else "")

# ==========================================================
# 5. QUERY DETAIL BUKU BERDASARKAN ID
# ==========================================================
def get_book_detail_query(book_id):
    return f"""
    SELECT ?Judul ?Penulis ?Harga ?KategoriUtama
           ?Sub1 ?Sub2 ?Sub3 ?Penerbit ?TanggalTerbit ?ISBN ?Halaman ?Bahasa
           ?Panjang ?Lebar ?Berat ?Format ?Deskripsi ?Gambar ?URL
    WHERE {{
        ?b rdf:type bu:Buku .
        FILTER(STRAFTER(STR(?b), "#") = "{book_id}")

        # Semua bagian data buku bersifat opsional
        OPTIONAL {{ ?b bu:Judul ?Judul . }}
        OPTIONAL {{ ?b bu:Penulis ?Penulis . }}
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:KategoriUtama ?KategoriUtama . }}
        OPTIONAL {{ ?b bu:Subkategori1 ?Sub1 . }}
        OPTIONAL {{ ?b bu:Subkategori2 ?Sub2 . }}
        OPTIONAL {{ ?b bu:Subkategori3 ?Sub3 . }}
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
        OPTIONAL {{ ?b bu:URL ?URL . }}
    }}
    LIMIT 1
    """

# ==========================================================
# 6. QUERY LIST BUKU UTAMA (dengan sorting, paging, dll)
# ==========================================================
def get_books_query(filters_block, sort_option, limit=20, offset=0):
    
    # Bagian sorting berdasarkan opsi
    if sort_option == "price_asc":
        order_clause = "ORDER BY xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', ''))"
    elif sort_option == "price_desc":
        order_clause = "ORDER BY DESC(xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', '')))"
    elif sort_option == "date_newest":
        order_clause = "ORDER BY DESC(?extractedYear)"
    elif sort_option == "date_oldest":
        order_clause = "ORDER BY ASC(?extractedYear)"
    else:
        order_clause = "ORDER BY xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', ''))"

    return f"""
    SELECT ?id ?Judul ?Penulis ?Harga ?KategoriUtama ?Sub1 ?Sub2 ?Sub3 ?Gambar ?TanggalTerbit ?extractedYear WHERE {{
        ?b rdf:type bu:Buku .
        ?b bu:Judul ?Judul .

        # Semua data buku bersifat opsional
        OPTIONAL {{ ?b bu:Penulis ?Penulis . }}
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:KategoriUtama ?KategoriUtama . }}
        OPTIONAL {{ ?b bu:Subkategori1 ?Sub1 . }}
        OPTIONAL {{ ?b bu:Subkategori2 ?Sub2 . }}
        OPTIONAL {{ ?b bu:Subkategori3 ?Sub3 . }}
        OPTIONAL {{ ?b bu:Gambar ?Gambar . }}
        OPTIONAL {{ ?b bu:Halaman ?Halaman . }}
        OPTIONAL {{ ?b bu:TanggalTerbit ?TanggalTerbit . }}

        # Ambil tahun dari TanggalTerbit
        BIND(xsd:integer(REPLACE(STR(?TanggalTerbit), ".*([0-9]{4}).*", "$1")) AS ?extractedYear)

        # Ambil ID buku dari URI
        BIND(STRAFTER(STR(?b), "#") AS ?id)

        {filters_block}
    }}
    {order_clause}
    LIMIT {limit}
    OFFSET {offset}
    """

# ==========================================================
# 7. QUERY TOTAL JUMLAH BUKU (untuk pagination)
# ==========================================================
def get_total_count_query(filters_block):
    return f"""
    SELECT (COUNT(DISTINCT ?b) as ?count) WHERE {{
        ?b rdf:type bu:Buku .
        ?b bu:Judul ?Judul .
        OPTIONAL {{ ?b bu:Penulis ?Penulis . }}
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:KategoriUtama ?KategoriUtama . }}
        OPTIONAL {{ ?b bu:Subkategori1 ?Sub1 . }}
        OPTIONAL {{ ?b bu:Subkategori2 ?Sub2 . }}
        OPTIONAL {{ ?b bu:Subkategori3 ?Sub3 . }}
        OPTIONAL {{ ?b bu:Halaman ?Halaman . }}
        
        {filters_block}
    }}
    """

# ==========================================================
# 8. FIX QUERY REKOMENDASI BUKU SESUAI PENULIS
#    Lebih fleksibel menangani perbedaan kapital/huruf
# ==========================================================
def get_books_by_author_query(author_name, exclude_id, limit=6):
    safe_author = author_name.replace('"', '\\"')
    
    return f"""
    SELECT ?id ?Judul ?Penulis ?Harga ?Gambar WHERE {{
        ?b rdf:type bu:Buku .
        ?b bu:Penulis ?Penulis .
        ?b bu:Judul ?Judul .
        
        # Cocokkan nama penulis tanpa peduli kapital huruf
        FILTER(CONTAINS(LCASE(STR(?Penulis)), LCASE("{safe_author}")))
        
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:Gambar ?Gambar . }}
        
        # Ambil ID buku
        BIND(STRAFTER(STR(?b), "#") AS ?id)

        # Jangan tampilkan buku yang sama
        FILTER(?id != "{exclude_id}")
    }}
    LIMIT {limit}
    """
