════════════════════════════════════════════════════
  📍 Google Maps Scraper — DOM Extraction
════════════════════════════════════════════════════

Web app untuk mencari tempat usaha di Google Maps,
lalu mengekstrak data (nama, nomor HP, alamat, website)
langsung dari DOM — tanpa AI, tanpa token, tanpa API key.

Alur di belakang layar:
  Keyword → Playwright buka GMaps → scroll hasil pencarian
  → kumpulkan link tiap usaha → buka tiap link di tab paralel
  → ekstrak data dari DOM → hasil tampil di web


════════════════════════════════════════════════════
 A.  PERSYARATAN
════════════════════════════════════════════════════

1. Python 3.9+
2. Koneksi internet stabil


════════════════════════════════════════════════════
 B.  INSTALLASI (sekali saja)
════════════════════════════════════════════════════

1. Buka terminal / PowerShell di folder ini

2. Install Python dependencies:

   pip install -r requirements.txt

3. Install browser Playwright (Chromium):

   playwright install chromium


════════════════════════════════════════════════════
 C.  MENJALANKAN WEB APP
════════════════════════════════════════════════════

1. Jalankan server:

   python app.py

2. Buka browser ke:

   http://localhost:8000

3. Isi form:
   - Kata kunci pencarian (contoh: jasa tour surabaya)
   - Centang field yang mau diekstrak (nama, nomor HP, alamat, website)
   - Klik "Mulai Cari"

4. Tunggu beberapa detik (tergantung jumlah hasil)
   → Hasil muncul dalam tabel
   → Bisa Download CSV


════════════════════════════════════════════════════
 D.  STRUKTUR FILE
════════════════════════════════════════════════════

tanya/
├── app.py               ← Backend (FastAPI + Playwright)
├── city_coords.py       ← Koordinat 514 kab/kota di Indonesia
├── requirements.txt      ← Daftar dependency
├── templates/
│   └── index.html        ← Frontend halaman web
└── static/
    ├── style.css         ← Styling
    └── script.js         ← Logika frontend


════════════════════════════════════════════════════
 E.  CATATAN PENTING
════════════════════════════════════════════════════

- Data diekstrak langsung dari DOM Google Maps,
  TANPA menggunakan AI / GPT / token / API key.

- Google Maps kadang tampil popup/cookie dialog,
  script otomatis mencoba menutupnya (tombol Escape).

- Semakin besar max_scroll, semakin banyak hasil,
  tapi makin lama proses scraping.

- Playwright jalan di headless mode (tanpa tampilan browser).

- city_coords.py berisi koordinat 514 kabupaten/kota
  di Indonesia. Keyword akan otomatis dideteksi lokasinya
  agar hasil pencarian Google Maps lebih akurat.

════════════════════════════════════════════════════
