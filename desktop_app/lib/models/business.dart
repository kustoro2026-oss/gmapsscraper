/// Data model untuk satu hasil scraping Google Maps.
class Business {
  final String namaUsaha;
  final String nomorHp;
  final String alamat;
  final String website;
  final String rating;

  const Business({
    required this.namaUsaha,
    required this.nomorHp,
    required this.alamat,
    required this.website,
    required this.rating,
  });

  factory Business.fromCsvRow(List<dynamic> row) {
    return Business(
      namaUsaha: row.isNotEmpty ? row[0].toString().trim() : '',
      nomorHp: row.length > 1 ? row[1].toString().trim() : '',
      alamat: row.length > 2 ? row[2].toString().trim() : '',
      website: row.length > 3 ? row[3].toString().trim() : '',
      rating: row.length > 4 ? row[4].toString().trim() : '',
    );
  }

  List<String> toRow() {
    return [namaUsaha, nomorHp, alamat, website, rating];
  }

  static const List<String> headers = [
    'Nama Usaha',
    'Nomor HP',
    'Alamat',
    'Website',
    'Rating',
  ];
}
