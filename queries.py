# queries.py
from SPARQLWrapper import SPARQLWrapper, JSON

PREFIX = """
PREFIX bu: <http://buku.org/buku#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
DBPEDIA_ENDPOINT = "https://dbpedia.org/sparql"

# Query sederhana untuk mengisi sidebar
# kategori di navbar
GET_ALL_CATEGORIES = """
SELECT DISTINCT ?cat WHERE { ?b bu:KategoriUtama ?cat . } ORDER BY ?cat
"""

GET_ALL_LANGUAGES = """
SELECT DISTINCT ?lang WHERE { ?b bu:Bahasa ?lang . } ORDER BY ?lang
"""

# Mengambil graph hierarki kategori (Cat -> Sub1 -> Sub2 -> Sub3)
GET_NESTED_MAP = """
SELECT DISTINCT ?cat ?sub1 ?sub2 ?sub3 WHERE {
    ?b bu:KategoriUtama ?cat .
    OPTIONAL { ?b bu:Subkategori1 ?sub1 . }
    OPTIONAL { ?b bu:Subkategori2 ?sub2 . }
    OPTIONAL { ?b bu:Subkategori3 ?sub3 . }
}
ORDER BY ?cat ?sub1 ?sub2 ?sub3
"""

def get_page_filter_clause(page_range):
    """
    Membuat filter rentang halaman.
    """
    if page_range == "0-100":
        return "FILTER(xsd:integer(?Halaman) <= 100)"
    elif page_range == "100-200":
        return "FILTER(xsd:integer(?Halaman) > 100 && xsd:integer(?Halaman) <= 200)"
    elif page_range == "200+":
        return "FILTER(xsd:integer(?Halaman) > 200)"
    return ""

def build_filter_string(search_query, current_filter, current_lang, page_range):
    """
    Inti logika pencarian dinamis (UPDATED).
    Sekarang mendukung Fuzzy Search untuk tanda baca.
    """
    # 1. Sanitasi input asli
    sq_original = search_query.replace('"', '\\"') 
    
    # 2. Buat versi "bersih" (tanpa titik/koma) untuk pencocokan fleksibel
    # Misal: "J.K. Rowling" -> "JK Rowling"
    sq_clean = search_query.replace(".", "").replace(",", "").strip()
    # Hapus spasi ganda jika ada
    while "  " in sq_clean:
        sq_clean = sq_clean.replace("  ", " ")
    sq_clean = sq_clean.replace('"', '\\"')

    filter_clauses = []
    
    # --- Filter Kategori ---
    if current_filter:
        val = current_filter.replace("cat_", "").replace("sub_", "").replace("subsub_", "").replace("sub3_", "")
        
        if current_filter.startswith("cat_"):
            filter_clauses.append(f'?b bu:KategoriUtama "{val}" .')
        elif current_filter.startswith("sub_"):
            filter_clauses.append(f'FILTER(?Sub1 = "{val}" || ?Sub2 = "{val}" || ?Sub3 = "{val}")')
        elif current_filter.startswith("subsub_"):
            filter_clauses.append(f'?b bu:Subkategori2 "{val}" .')
        elif current_filter.startswith("sub3_"):
            filter_clauses.append(f'?b bu:Subkategori3 "{val}" .')

    # --- Filter Bahasa ---
    if current_lang != "all":
        filter_clauses.append(f'?b bu:Bahasa "{current_lang}" .')

    # --- Filter Halaman ---
    page_clause = get_page_filter_clause(page_range)
    if page_clause:
        filter_clauses.append(page_clause)

    # --- Filter Pencarian (UPDATED) ---
    search_clause = ""
    if search_query:
        # Logika:
        # 1. Cek match persis (Standard LCASE)
        # 2. ATAU Cek match jika titik/koma dibuang dari Database DAN Input
        #    REPLACE(STR(?Field), "[.,]", "") artinya hapus titik & koma dari data DB sebelum dicek
        search_clause = f'''
        FILTER(
            CONTAINS(LCASE(?Judul), LCASE("{sq_original}")) ||
            CONTAINS(LCASE(?Penulis), LCASE("{sq_original}")) ||
            CONTAINS(LCASE(REPLACE(STR(?Judul), "[.,]", "")), LCASE("{sq_clean}")) ||
            CONTAINS(LCASE(REPLACE(STR(?Penulis), "[.,]", "")), LCASE("{sq_clean}"))
        )
        '''
    
    return "\n".join(filter_clauses) + ("\n" + search_clause if search_clause else "")

def get_book_detail_query(book_id):
    return f"""
    SELECT ?Judul ?Penulis ?Harga ?KategoriUtama
            ?Sub1 ?Sub2 ?Sub3 ?Penerbit ?TanggalTerbit ?ISBN ?Halaman ?Bahasa
            ?Panjang ?Lebar ?Berat ?Format ?Deskripsi ?Gambar ?URL
    WHERE {{
        ?b rdf:type bu:Buku .
        FILTER(STRAFTER(STR(?b), "#") = "{book_id}")

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

def get_books_query(filters_block, sort_option, limit=20, offset=0):
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

        OPTIONAL {{ ?b bu:Penulis ?Penulis . }}
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:KategoriUtama ?KategoriUtama . }}
        OPTIONAL {{ ?b bu:Subkategori1 ?Sub1 . }}
        OPTIONAL {{ ?b bu:Subkategori2 ?Sub2 . }}
        OPTIONAL {{ ?b bu:Subkategori3 ?Sub3 . }}
        OPTIONAL {{ ?b bu:Gambar ?Gambar . }}
        OPTIONAL {{ ?b bu:Halaman ?Halaman . }}
        OPTIONAL {{ ?b bu:TanggalTerbit ?TanggalTerbit . }}

        BIND(xsd:integer(REPLACE(STR(?TanggalTerbit), ".*([0-9]{4}).*", "$1")) AS ?extractedYear)
        BIND(STRAFTER(STR(?b), "#") AS ?id)

        {filters_block}
    }}
    {order_clause}
    LIMIT {limit}
    OFFSET {offset}
    """

def get_total_count_query(filters_block):
    return f"""
    SELECT (COUNT(DISTINCT ?b) as ?count) WHERE {{
        ?b rdf:type bu:Buku .
        ?b bu:Judul ?Judul .
        OPTIONAL {{ ?b bu:Penulis ?Penulis . }}
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:KategoriUtama ?KategoriUtama . }}
        OPTIONAL {{ ?b bu:Subkategori1 ?Sub1 . }}
        OPTIONAL {{ ?b bu:Halaman ?Halaman . }}
        
        {filters_block}
    }}
    """

def get_books_by_author_query(author_list, exclude_id, limit=6):
    filter_parts = []
    for name in author_list:
        safe_name = name.strip().replace('"', '\\"')
        if len(safe_name) > 1:
            filter_parts.append(f'CONTAINS(LCASE(STR(?Penulis)), LCASE("{safe_name}"))')
    
    if filter_parts:
        final_filter = f"FILTER({' || '.join(filter_parts)})"
    else:
        return "SELECT * WHERE { ?s ?p ?o } LIMIT 0"

    return f"""
    SELECT DISTINCT ?id ?Judul ?Penulis ?Harga ?Gambar WHERE {{
        ?b rdf:type bu:Buku .
        ?b bu:Penulis ?Penulis .
        ?b bu:Judul ?Judul .
        
        {final_filter}
        
        OPTIONAL {{ ?b bu:Harga ?Harga . }}
        OPTIONAL {{ ?b bu:Gambar ?Gambar . }}
        
        BIND(STRAFTER(STR(?b), "#") AS ?id)
        FILTER(?id != "{exclude_id}")
    }}
    LIMIT {limit}
    """

def get_author_info_from_dbpedia(author_name):
    if not author_name: return None
    clean_name = author_name.split(',')[0].strip()
    
    safe_regex = clean_name \
        .replace(".", "[.]\\\\s*") \
        .replace(" ", "\\\\s+") \
        .replace('"', '\\"')
    
    uri_guess_name = clean_name.replace(" ", "_").replace('"', '')

    query = f"""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX dbr: <http://dbpedia.org/resource/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    SELECT DISTINCT ?author ?abstract ?birthDate ?deathDate ?thumbnail ?nationality WHERE {{
        {{
            ?author a dbo:Writer ;
                    rdfs:label ?name .
            FILTER(LANG(?name) = "en")
            FILTER(REGEX(?name, "^{safe_regex}", "i"))
        }}
        UNION
        {{
            BIND(URI(CONCAT("http://dbpedia.org/resource/", ENCODE_FOR_URI("{uri_guess_name}"))) AS ?author)
            ?author a dbo:Writer .
        }}

        OPTIONAL {{ ?author dbo:abstract ?abstract . FILTER(LANG(?abstract) = "en") }}
        OPTIONAL {{ ?author dbo:birthDate ?birthDate . }}
        OPTIONAL {{ ?author dbo:deathDate ?deathDate . }}
        OPTIONAL {{ ?author dbo:thumbnail ?thumbnail . }}
        OPTIONAL {{ ?author dbo:nationality ?nat . ?nat rdfs:label ?nationality . FILTER(LANG(?nationality) = "en") }}
    }}
    LIMIT 1
    """
    
    sparql = SPARQLWrapper(DBPEDIA_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(10)
    
    try:
        results = sparql.query().convert()
        bindings = results["results"]["bindings"]
        if bindings:
            data = bindings[0]
            return {
                "uri": data.get("author", {}).get("value", ""),
                "abstract": data.get("abstract", {}).get("value", ""),
                "birthDate": data.get("birthDate", {}).get("value", ""),
                "deathDate": data.get("deathDate", {}).get("value", ""),
                "thumbnail": data.get("thumbnail", {}).get("value", ""),
                "nationality": data.get("nationality", {}).get("value", "")
            }
        return None
    except Exception as e:
        print(f"⚠️ DBpedia Error: {str(e).splitlines()[0]}")
        return None

def get_film_adaptation(book_title, author_name):
    if not book_title: return None
    
    clean_title = book_title.split('(')[0].strip()
    words = clean_title.split()
    search_term = " ".join(words[:3]) if len(words) > 3 else clean_title
        
    safe_regex = search_term \
        .replace(".", "[.]\\\\s*") \
        .replace(" ", "\\\\s+") \
        .replace('"', '\\"')

    query = f"""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?filmTitle ?directorName ?poster ?abstract ?uri WHERE {{
        ?film a dbo:Film ;
              rdfs:label ?filmTitle .
        
        FILTER(LANG(?filmTitle) = "en")
        FILTER(REGEX(?filmTitle, "{safe_regex}", "i"))

        OPTIONAL {{ ?film dbo:director ?dir . ?dir rdfs:label ?directorName . FILTER(LANG(?directorName)="en") }}
        OPTIONAL {{ ?film dbo:thumbnail ?poster . }}
        OPTIONAL {{ ?film dbo:abstract ?abstract . FILTER(LANG(?abstract)="en") }}
        
        BIND(STR(?film) as ?uri)
    }}
    LIMIT 1
    """
    
    sparql = SPARQLWrapper(DBPEDIA_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(5)

    try:
        results = sparql.query().convert()
        bindings = results["results"]["bindings"]
        
        if bindings:
            data = bindings[0]
            return {
                "uri": data.get("uri", {}).get("value", ""),
                "title": data.get("filmTitle", {}).get("value", ""),
                "director": data.get("directorName", {}).get("value", "Tidak diketahui"),
                "poster": data.get("poster", {}).get("value", ""),
                "abstract": data.get("abstract", {}).get("value", "")
            }
        return None
    except Exception as e:
        print(f"⚠️ DBpedia Error: {str(e)}")
        return None