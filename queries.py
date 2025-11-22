# queries.py

# 1. Prefix Global
PREFIX = """
PREFIX bu: <http://buku.org/buku#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# 2. Query Statis
GET_ALL_CATEGORIES = """
SELECT DISTINCT ?cat WHERE {
    ?b bu:KategoriUtama ?cat .
}
ORDER BY ?cat
"""

GET_ALL_LANGUAGES = """
SELECT DISTINCT ?lang WHERE {
    ?b bu:Bahasa ?lang .
}
ORDER BY ?lang
"""

GET_NESTED_MAP = """
SELECT DISTINCT ?cat ?sub1 ?sub2 WHERE {
    ?b bu:KategoriUtama ?cat .
    OPTIONAL { ?b bu:Subkategori1 ?sub1 . }
    OPTIONAL { ?b bu:Subkategori2 ?sub2 . }
}
ORDER BY ?cat ?sub1 ?sub2
"""

# 3. Query Dinamis

def get_book_detail_query(book_id):
    return f"""
    SELECT ?Judul ?Penulis ?Harga ?KategoriUtama
           ?Sub1 ?Sub2 ?Penerbit ?TanggalTerbit ?ISBN ?Halaman ?Bahasa
           ?Panjang ?Lebar ?Berat ?Format ?Deskripsi ?Gambar
    WHERE {{
        ?b rdf:type bu:Buku .
        FILTER(STRAFTER(STR(?b), "#") = "{book_id}")
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

def get_books_query(filters_block, order_clause, limit=20, offset=0):
    # Jika order_clause kosong (default), kita paksa urutkan by Harga ASC
    if not order_clause:
        order_clause = "ORDER BY xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', ''))"

    return f"""
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
    LIMIT {limit}
    OFFSET {offset}
    """