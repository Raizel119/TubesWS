from flask import Flask, render_template, request, abort
import json

app = Flask(__name__)

# --- Mock Database (Data Diperbarui dengan 3 Level) ---
BOOKS_DB = [
    {
        "id": 1,
        "title": "Laskar Pelangi",
        "author": "Andrea Hirata",
        "category": "Buku",
        "sub_category": "Fiksi",
        "sub_sub_category": "Sastra",
        "price": 85000,
        "language": "Indonesia",
        "description": "Kisah inspiratif...",
        "publisher": "Bentang Pustaka",
        "image_url": "https://cdn.gramedia.com/uploads/items/9786022911145_Laskar-Pelangi.jpg"
    },
    {
        "id": 2,
        "title": "Bumi Manusia",
        "author": "Pramoedya Ananta Toer",
        "category": "Buku",
        "sub_category": "Fiksi",
        "sub_sub_category": "Fiksi Historis",
        "price": 120000,
        "language": "Indonesia",
        "description": "Bagian pertama...",
        "publisher": "Hasta Mitra",
        "image_url": "https://cdn.gramedia.com/uploads/items/9786020638521_Bumi-Manusia.jpg"
    },
    {
        "id": 3,
        "title": "Sapiens: A Brief History",
        "author": "Yuval Noah Harari",
        "category": "International Book",
        "sub_category": "History",
        "sub_sub_category": "World History",
        "price": 280000,
        "language": "Inggris",
        "description": "Buku yang mengubah cara pandang...",
        "publisher": "Harvill Secker",
        "image_url": "https://cdn.gramedia.com/uploads/items/img20210217_13333010.jpg"
    },
    {
        "id": 4,
        "title": "The Hobbit",
        "author": "J.R.R. Tolkien",
        "category": "International Book",
        "sub_category": "Fiction",
        "sub_sub_category": "Fantasy",
        "price": 210000,
        "language": "Inggris",
        "description": "Petualangan Bilbo Baggins...",
        "publisher": "George Allen & Unwin",
        "image_url": "https://cdn.gramedia.com/uploads/items/the_hobbit.jpg"
    },
    {
        "id": 5,
        "title": "Jurnal Prisma: Sejarah Terbuka",
        "author": "Tim Editor",
        "category": "Majalah",
        "sub_category": "Sosial",
        "sub_sub_category": "Ekonomi",
        "price": 125000,
        "language": "Indonesia",
        "description": "Jurnal pemikiran sosial...",
        "publisher": "LP3ES",
        "image_url": "https://cdn.gramedia.com/uploads/items/9786239955376_Jurnal-Prisma-Sejarah-Terbuka.jpg"
    },
    {
        "id": 6,
        "title": "Now I Can Tell My Feeling",
        "author": "Yoon Jihyun",
        "category": "Ebook",
        "sub_category": "Self-Healing",
        "sub_sub_category": "Psychology",
        "price": 75000,
        "language": "Indonesia",
        "description": "Ebook self-healing...",
        "publisher": "Penerbit B",
        "image_url": "https://cdn.gramedia.com/uploads/items/Cover_Now_I_Can_Tell_My_Feeling_1.jpg"
    },
    {
        "id": 7,
        "title": "Gadis Kretek",
        "author": "Ratih Kumala",
        "category": "Buku",
        "sub_category": "Fiksi",
        "sub_sub_category": "Fiksi Historis",
        "price": 89000,
        "language": "Indonesia",
        "description": "Kisah cinta dan intrik...",
        "publisher": "Gramedia Pustaka Utama",
        "image_url": "https://cdn.gramedia.com/uploads/items/Gadis_Kretek.jpg"
    },
    {
        "id": 8,
        "title": "Harry Potter dan Batu Bertuah",
        "author": "J.K. Rowling",
        "category": "Buku",
        "sub_category": "Fiksi",
        "sub_sub_category": "Fantasi",
        "price": 150000,
        "language": "Indonesia",
        "description": "Awal petualangan...",
        "publisher": "Bloomsbury Publishing",
        "image_url": "https://cdn.gramedia.com/uploads/items/9789791011860_harry-potter-dan-batu-bertuah.jpeg"
    },
    {
        "id": 9,
        "title": "Fiksi Agama", # Buku palsu untuk sub-kategori Fiksi
        "author": "Author Agama",
        "category": "Buku",
        "sub_category": "Fiksi",
        "sub_sub_category": "Agama",
        "price": 90000,
        "language": "Indonesia",
        "description": "Deskripsi...",
        "publisher": "Penerbit",
        "image_url": "https://cdn.gramedia.com/uploads/items/9786230009916_hidup_itu_indah_tertawalah.jpg"
    },
     {
        "id": 10,
        "title": "Fiksi Anak", # Buku palsu untuk sub-kategori
        "author": "Author Anak",
        "category": "Buku",
        "sub_category": "Fiksi Anak & Remaja",
        "sub_sub_category": "Novel Remaja",
        "price": 90000,
        "language": "Indonesia",
        "description": "Deskripsi...",
        "publisher": "Penerbit",
        "image_url": "https://cdn.gramedia.com/uploads/items/9786230009916_hidup_itu_indah_tertawalah.jpg"
    },
    {
        "id": 11,
        "title": "Parenting", # Buku palsu untuk sub-kategori
        "author": "Author Parenting",
        "category": "Buku",
        "sub_category": "Keluarga dan Hubungan",
        "sub_sub_category": "Parenting",
        "price": 90000,
        "language": "Indonesia",
        "description": "Deskripsi...",
        "publisher": "Penerbit",
        "image_url": "https://cdn.gramedia.com/uploads/items/9786230009916_hidup_itu_indah_tertawalah.jpg"
    },
]

# --- BARU: Buat Peta Hierarkis 3-Level ---
NESTED_CATEGORY_MAP = {}
for book in BOOKS_DB:
    cat = book['category']
    sub_cat = book.get('sub_category')
    sub_sub_cat = book.get('sub_sub_category')

    if cat not in NESTED_CATEGORY_MAP:
        NESTED_CATEGORY_MAP[cat] = {}
    
    if sub_cat and sub_cat not in NESTED_CATEGORY_MAP[cat]:
        NESTED_CATEGORY_MAP[cat][sub_cat] = set() # Gunakan set untuk menghindari duplikat
    
    if sub_cat and sub_sub_cat:
        NESTED_CATEGORY_MAP[cat][sub_cat].add(sub_sub_cat)

# Ubah set menjadi list yang diurutkan
for cat, sub_map in NESTED_CATEGORY_MAP.items():
    for sub_cat, sub_sub_set in sub_map.items():
        NESTED_CATEGORY_MAP[cat][sub_cat] = sorted(list(sub_sub_set))
# -------------------------------------------

ALL_LANGUAGES = sorted(list(set(book['language'] for book in BOOKS_DB)))
ALL_CATEGORIES = sorted(list(NESTED_CATEGORY_MAP.keys()))


# --- RUTE BARU: Homepage (Sekarang menjadi halaman utama DAN pencarian) ---
@app.route('/')
def homepage():
    query = request.args.get('query')
    sort_price = request.args.get('sort_price')
    
    # --- LOGIKA FILTER 3-LEVEL BARU ---
    filter_param = request.args.get('filter')
    selected_category = None
    selected_sub_category = None
    selected_sub_sub_category = None # BARU
    
    if filter_param:
        if filter_param.startswith('cat_'):
            selected_category = filter_param.replace('cat_', '', 1)
        elif filter_param.startswith('sub_'):
            selected_sub_category = filter_param.replace('sub_', '', 1)
        elif filter_param.startswith('subsub_'): # BARU
            selected_sub_sub_category = filter_param.replace('subsub_', '', 1)

    lang_param = request.args.get('lang')
    selected_language = None
    
    if lang_param and lang_param != 'all':
        selected_language = lang_param
    # -----------------------------

    total_count = len(BOOKS_DB)
    filtered_books = BOOKS_DB

    if query:
        search_query = query.lower()
        filtered_books = [
            book for book in filtered_books
            if search_query in book['title'].lower() or \
               search_query in book['author'].lower()
        ]
    if selected_category:
        filtered_books = [
            book for book in filtered_books
            if book['category'] == selected_category
        ]
    if selected_sub_category:
        filtered_books = [
            book for book in filtered_books
            if book.get('sub_category') == selected_sub_category
        ]
    if selected_sub_sub_category: # BARU
        filtered_books = [
            book for book in filtered_books
            if book.get('sub_sub_category') == selected_sub_sub_category
        ]
    if selected_language:
        filtered_books = [
            book for book in filtered_books
            if book['language'] == selected_language
        ]

    results_count = len(filtered_books)

    if sort_price == 'asc':
        filtered_books = sorted(filtered_books, key=lambda b: b['price'])
    elif sort_price == 'desc':
        filtered_books = sorted(filtered_books, key=lambda b: b['price'], reverse=True)

    # --- Mempersiapkan data untuk Jinja `open` dan `checked` ---
    current_selected_cat = None
    current_selected_sub = None
    
    if selected_category:
        current_selected_cat = selected_category
    elif selected_sub_category:
        for cat, sub_map in NESTED_CATEGORY_MAP.items():
            if selected_sub_category in sub_map:
                current_selected_cat = cat
                current_selected_sub = selected_sub_category
                break
    elif selected_sub_sub_category:
        for cat, sub_map in NESTED_CATEGORY_MAP.items():
            for sub, subsub_list in sub_map.items():
                if selected_sub_sub_category in subsub_list:
                    current_selected_cat = cat
                    current_selected_sub = sub
                    break
            if current_selected_cat:
                break
    
    # Kelompokkan buku untuk rak (hanya jika tidak ada filter aktif)
    grouped_books = {}
    if not (query or filter_param or lang_param or sort_price):
        for cat in ALL_CATEGORIES:
            grouped_books[cat] = [b for b in BOOKS_DB if b['category'] == cat][:4]
    
    
    # --- BARU: Buat daftar filter aktif ---
    # --- BARU: Buat daftar filter aktif (Logika Diperbaiki) ---
    active_filters = []

    # Level 1: Kategori (akan selalu ada jika salah satu sub-nya dipilih)
    if current_selected_cat:
        active_filters.append({'type': 'filter', 'value': current_selected_cat})
        
    # Level 2: Sub-Kategori (hanya jika sub atau sub-sub dipilih)
    if current_selected_sub:
        active_filters.append({'type': 'filter', 'value': current_selected_sub})

    # Level 3: Sub-Sub-Kategori (hanya jika sub-sub dipilih)
    if selected_sub_sub_category:
        active_filters.append({'type': 'filter', 'value': selected_sub_sub_category})
        
    # Filter Bahasa (terpisah)
    if selected_language:
        active_filters.append({'type': 'lang', 'value': selected_language})
    # -----------------------------------
    # -----------------------------------

    
    return render_template(
        'index.html', 
        books=filtered_books, 
        grouped_books=grouped_books, 
        
        nested_category_map=NESTED_CATEGORY_MAP, 
        all_languages=ALL_LANGUAGES,
        all_categories=ALL_CATEGORIES,
        
        results_count=results_count,
        total_count=total_count,
        search_query=query,
        selected_sort_price=sort_price,
        
        current_filter=filter_param, 
        current_lang=lang_param or 'all',
        current_selected_cat=current_selected_cat,
        current_selected_sub=current_selected_sub,
        
        active_filters=active_filters # BARU: Kirim daftar filter aktif
    )

# --- Rute Detail ---
@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = next((b for b in BOOKS_DB if b['id'] == book_id), None)
    if book is None:
        abort(404)
    # Kirim kategori utama untuk dropdown navbar
    return render_template('detail.html', book=book, all_categories=ALL_CATEGORIES)

@app.errorhandler(404)
def page_not_found(e):
    # Buat file 404.html jika Anda belum memilikinya
    return render_template('404.html'), 404 

if __name__ == '__main__':
    app.run(debug=True)