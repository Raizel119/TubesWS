# queries.py
from SPARQLWrapper import SPARQLWrapper, JSON
import re
import requests
import json

PREFIX = """
PREFIX bu: <http://buku.org/buku#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""
DBPEDIA_ENDPOINT = "https://dbpedia.org/sparql"

# Mengambil semua kategori unik untuk Sidebar
GET_ALL_CATEGORIES = """
SELECT DISTINCT ?cat WHERE { ?b bu:KategoriUtama ?cat . } ORDER BY ?cat
"""

# Mengambil semua bahasa yang tersedia
GET_ALL_LANGUAGES = """
SELECT DISTINCT ?lang WHERE { ?b bu:Bahasa ?lang . } ORDER BY ?lang
"""

# Membangun struktur hierarki: Kategori -> Sub1 -> Sub2 -> Sub3
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
    Menghasilkan klausa FILTER SPARQL untuk rentang halaman buku.
    Logika: Membandingkan nilai integer ?Halaman.
    """
    if page_range == "0-100":
        return "FILTER(xsd:integer(?Halaman) <= 100)"
    elif page_range == "100-200":
        return "FILTER(xsd:integer(?Halaman) > 100 && xsd:integer(?Halaman) <= 200)"
    elif page_range == "200+":
        return "FILTER(xsd:integer(?Halaman) > 200)"
    return ""

def create_fuzzy_regex(text):
    """
    Membuat pola Regex untuk menangani typo double huruf.
    Contoh Input: "Harrry Poter"
    
    1. Collapse: "Hary Poter" (Hapus huruf ganda berurutan di input)
    2. Expand: "H+a+r+y+.*P+o+t+e+r+"
    """
    if not text: return ""
    
    # Bersihkan simbol selain angka/huruf/spasi agar regex tidak error
    clean_text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    words = clean_text.split()
    
    fuzzy_parts = []
    for word in words:
        # Collapse huruf ganda user (User ngetik 'Harrry' -> jadi 'Hary')
        # \1+ artinya: karakter yang sama muncul berulang
        skeleton = re.sub(r'(.)\1+', r'\1', word)
        
        # Tambahkan + setelah setiap huruf (h+a+r+y+)
        # re.escape memastikan jika ada simbol regex (seperti titik) dianggap teks biasa
        fuzzy_word = "".join([re.escape(char) + "+" for char in skeleton])
        fuzzy_parts.append(fuzzy_word)
    
    # Gabungkan kata dengan .* agar spasi fleksibel
    return ".*".join(fuzzy_parts)

def build_filter_string(search_query, current_filter, current_lang, page_range):
    """
    Menyusun klausa FILTER dinamis.
    """
    clean_sq = search_query.replace('"', '').replace('.', '').strip()
    
    filter_clauses = []
    
    # [FILTER KATEGORI STRICT]
    # Pecah value berdasarkan tanda pipa '|'
    if current_filter:
        if current_filter.startswith("cat_"):
            # Format: cat_Buku
            val = current_filter[4:] 
            filter_clauses.append(f'?b bu:KategoriUtama "{val}" .')
            
        elif current_filter.startswith("sub_"):
            # Format: sub_Buku|Agama
            raw = current_filter[4:]
            parts = raw.split('|')
            if len(parts) >= 2:
                filter_clauses.append(f'?b bu:KategoriUtama "{parts[0]}" .')
                filter_clauses.append(f'?b bu:Subkategori1 "{parts[1]}" .')
            else:
                # Fallback jika format lama/error
                filter_clauses.append(f'?b bu:Subkategori1 "{raw}" .')

        elif current_filter.startswith("subsub_"):
            # Format: subsub_Buku|Agama|Lainnya
            raw = current_filter[7:]
            parts = raw.split('|')
            if len(parts) >= 3:
                filter_clauses.append(f'?b bu:KategoriUtama "{parts[0]}" .')
                filter_clauses.append(f'?b bu:Subkategori1 "{parts[1]}" .')
                filter_clauses.append(f'?b bu:Subkategori2 "{parts[2]}" .')
            else:
                filter_clauses.append(f'?b bu:Subkategori2 "{raw}" .')
            
        elif current_filter.startswith("sub3_"):
            # Format: sub3_Buku|Agama|Lainnya|Islam
            raw = current_filter[5:]
            parts = raw.split('|')
            if len(parts) >= 4:
                filter_clauses.append(f'?b bu:KategoriUtama "{parts[0]}" .')
                filter_clauses.append(f'?b bu:Subkategori1 "{parts[1]}" .')
                filter_clauses.append(f'?b bu:Subkategori2 "{parts[2]}" .')
                filter_clauses.append(f'?b bu:Subkategori3 "{parts[3]}" .')
            else:
                filter_clauses.append(f'?b bu:Subkategori3 "{raw}" .')

    # Filter Bahasa
    if current_lang != "all":
        filter_clauses.append(f'?b bu:Bahasa "{current_lang}" .')

    # Filter Halaman
    page_clause = get_page_filter_clause(page_range)
    if page_clause:
        filter_clauses.append(page_clause)

    # Search Text
    if clean_sq:
        fuzzy_pattern = create_fuzzy_regex(clean_sq)
        search_clause = f'''
        FILTER(
            REGEX(REPLACE(?Judul, "[.]", ""), "{fuzzy_pattern}", "i") ||
            REGEX(REPLACE(?Penulis, "[.]", ""), "{fuzzy_pattern}", "i") ||
            REGEX(STR(?KategoriUtama), "{fuzzy_pattern}", "i") ||
            REGEX(STR(?Sub1), "{fuzzy_pattern}", "i") ||
            REGEX(STR(?Sub2), "{fuzzy_pattern}", "i") ||
            REGEX(STR(?Sub3), "{fuzzy_pattern}", "i")
        )
        '''
        filter_clauses.append(search_clause)
    
    return "\n".join(filter_clauses)

def get_book_detail_query(book_id):
    """
    Query untuk mengambil seluruh properti detail dari satu buku spesifik.
    """
    return f"""
    SELECT ?Judul ?Penulis ?Harga ?KategoriUtama
            ?Sub1 ?Sub2 ?Sub3 ?Penerbit ?TanggalTerbit ?ISBN ?Halaman ?Bahasa
            ?Panjang ?Lebar ?Berat ?Format ?Deskripsi ?Gambar ?URL
    WHERE {{
        ?b rdf:type bu:Buku .
        # Filter berdasarkan ID yang ada di ujung URI (setelah tanda #)
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
    """
    Query utama untuk list buku dengan fitur Sorting harga dan tanggal.
    """
    # [SORTING HARGA]
    # REPLACE pertama membuang 'Rp'.
    # REPLACE kedua membuang titik separator ribuan (100.000 -> 100000).
    # xsd:integer mengubah string jadi angka agar bisa diurutkan (bukan urutan abjad).
    if sort_option == "price_asc":
        order_clause = "ORDER BY xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', ''))"
    elif sort_option == "price_desc":
        order_clause = "ORDER BY DESC(xsd:integer(REPLACE(REPLACE(STR(?Harga), 'Rp', ''), '[.]', '')))"
    
    # [SORTING TANGGAL]
    # Mengurutkan berdasarkan variabel ?extractedYear
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

        # [EKSTRAKSI TAHUN]
        # Regex ".*([0-9]{4}).*" mencari 4 digit angka berurutan di mana saja dalam string tanggal.
        # $1 mengambil hanya 4 digit tersebut.
        BIND(xsd:integer(REPLACE(STR(?TanggalTerbit), ".*([0-9]{4}).*", "$1")) AS ?extractedYear)
        
        # Mengambil ID unik setelah tanda #
        BIND(STRAFTER(STR(?b), "#") AS ?id)

        {filters_block}
    }}
    {order_clause}
    LIMIT {limit}
    OFFSET {offset}
    """

def get_total_count_query(filters_block):
    """
    Menghitung total buku untuk pagination.
    """
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
    """
    Mencari buku lain berdasarkan list nama penulis (untuk Rekomendasi).
    """
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
        # Exclude buku yang sedang dibuka sekarang
        FILTER(?id != "{exclude_id}")
    }}
    LIMIT {limit}
    """

def get_author_info_from_dbpedia(author_name):
    """
    Query Semantic Web ke DBpedia untuk mengambil biodata penulis.
    """
    if not author_name: return None
    clean_name = author_name.split(',')[0].strip()
    
    # [REGEX PENULIS]
    # [.]? = Titik bersifat opsional.
    # \\s+ = Spasi bersifat fleksibel (bisa 1 atau banyak).
    safe_regex = clean_name \
        .replace(".", "[.]\\\\s*") \
        .replace(" ", "\\\\s+") \
        .replace('"', '\\"')
    
    # [LOGIKA URI GUESSING]
    # Mencoba menebak link langsung: "J.K. Rowling" -> "J.K._Rowling"
    uri_guess_name = clean_name.replace(" ", "_").replace('"', '')

    query = f"""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX dbr: <http://dbpedia.org/resource/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    SELECT DISTINCT ?author ?abstract ?birthDate ?deathDate ?thumbnail ?nationality WHERE {{
        {{
            # Regex Match pada label nama (fleksibel)
            ?author a dbo:Writer ;
                    rdfs:label ?name .
            FILTER(LANG(?name) = "en")
            FILTER(REGEX(?name, "^{safe_regex}", "i"))
        }}
        UNION
        {{
            # Direct URI Construct (Jika ejaan nama sangat akurat)
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
    """
    Mencari adaptasi film di DBpedia berdasarkan Judul Buku.
    Fitur: Pembersihan judul otomatis & Regex 'Sakti' untuk menangani simbol.
    """
    if not book_title: return None
    
    search_term = ""
    
    # [LOGIKA PRIORITAS KURUNG]
    # Cek apakah ada teks dalam kurung "()", misal: "Hunger Games #2 (Catching Fire)".
    match = re.search(r'\((.*?)\)', book_title)
    if match:
        candidate = match.group(1).strip()
        # Filter yang diambil jangan info teknis seperti "Edisi Revisi"
        blocklist = ["edisi", "cover", "terjemahan", "repubish", "hard", "soft", "bahasa", "new"]
        if not any(word in candidate.lower() for word in blocklist):
            search_term = candidate

    # [LOGIKA PEMBERSIHAN SIMBOL]
    # Jika tidak ada kurung, gunakan judul utama & hapus simbol lain
    if not search_term:
        clean = re.sub(r'#\d+', '', book_title) # Hapus nomor seri "#1", "#2"
        for char in [":", "-", ".", ",", "!", "?", "'", '"']:
            clean = clean.replace(char, " ") # Ganti simbol dengan spasi
        search_term = clean.strip()

    # Ambil Keyword
    words = search_term.split()
    if len(words) > 3:
        final_keyword = " ".join(words[:3])
    else:
        final_keyword = " ".join(words)
        
    # [LOGIKA REGEX]
    # .replace(" ", "[\\\\s\\\\W]+")
    # Mengubah spasi biasa menjadi pola Regex: "Spasi ATAU Karakter Non-Huruf".
    # Agar "Hunger Games Mockingjay" cocok dengan "Hunger Games: Mockingjay" (ada titik dua).
    safe_regex = final_keyword.strip().replace(" ", "[\\\\s\\\\W]+")

    print(f"🎬 DEBUG FILM: Regex Akhir='{safe_regex}'")

    query = f"""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?filmTitle ?directorName ?poster ?abstract ?uri WHERE {{
        ?film a dbo:Film ;
              rdfs:label ?filmTitle .
        
        FILTER(LANG(?filmTitle) = "en")
        
        FILTER(REGEX(?filmTitle, "{safe_regex}", "i"))

        OPTIONAL {{ 
            ?film dbo:director ?dir . 
            ?dir rdfs:label ?directorName . 
            FILTER(LANG(?directorName)="en") 
        }}
        OPTIONAL {{ ?film dbo:thumbnail ?poster . }}
        OPTIONAL {{ 
            ?film dbo:abstract ?abstract . 
            FILTER(LANG(?abstract)="en") 
        }}
        
        BIND(STR(?film) as ?uri)
    }}
    LIMIT 1
    """
    
    sparql = SPARQLWrapper(DBPEDIA_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(15) 

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
        print(f"⚠️ DBpedia Film Error: {str(e)}")
        return None
    
def get_movie_trailer_link(movie_title, api_key):
    """
    Mencari ID video trailer YouTube untuk judul film yang diberikan menggunakan YouTube Data API v3.
    """

    if not api_key or not movie_title:
        return None
        
    search_query = f"{movie_title} official trailer"
    YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    
    params = {
        'part': 'id,snippet', 
        'q': search_query,
        'key': api_key,
        'type': 'video',
        'maxResults': 1
    }
    
    try:
        response = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=5)
        
        # Jika ada kode status HTTP 4xx atau 5xx, coba ekstrak pesan error JSON
        response.raise_for_status() 
        
        data = response.json()
        
        if data and 'items' in data and data['items']:
            video_id = data['items'][0]['id']['videoId']
            return video_id
        else:
            return None
            
    except requests.exceptions.HTTPError as e:
        # Menangkap error spesifik dari API (misal 403 Quota Exceeded)
        try:
            error_data = e.response.json()
            error_message = error_data.get('error', {}).get('message', 'Unknown HTTP Error')
            print(f"❌ YOUTUBE API HTTP ERROR: {error_message} (Periksa Kuota atau Kunci API)")
        except:
            print(f"❌ YOUTUBE API UNEXPECTED HTTP ERROR: {e}")
        return None
        
    except requests.exceptions.RequestException as e:
        # Menangkap error koneksi umum
        print(f"❌ YOUTUBE API CONNECTION ERROR: {e}")
        return None