import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:csv/csv.dart';
import 'package:file_picker/file_picker.dart';
import 'package:path_provider/path_provider.dart';

import '../models/business.dart';

/// Screen hasil scraping: tabel + download CSV.
class ResultScreen extends StatelessWidget {
  final List<Business> businesses;
  final String keyword;

  const ResultScreen({
    super.key,
    required this.businesses,
    required this.keyword,
  });

  Future<void> _downloadCsv(BuildContext context) async {
    final dir = await FilePicker.platform.getDirectoryPath(
      dialogTitle: 'Pilih folder untuk menyimpan CSV',
    );
    if (dir == null) return;

    final rows = <List<String>>[
      Business.headers,
      ...businesses.map((b) => b.toRow()),
    ];
    final csv = const ListToCsvConverter().convert(rows);

    final filePath = '$dir${Platform.pathSeparator}gmaps_${keyword.replaceAll(RegExp(r'\s+'), '_')}.csv';
    await File(filePath).writeAsString(csv, encoding: utf8);

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('CSV tersimpan: $filePath'),
          backgroundColor: const Color(0xFF065F46),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final columns = Business.headers;

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        title: Text(
          'Hasil: "$keyword" (${businesses.length} data)',
          style: const TextStyle(color: Colors.white, fontSize: 14),
        ),
        backgroundColor: const Color(0xFF1E293B),
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.download, color: Color(0xFF3B82F6)),
            tooltip: 'Download CSV',
            onPressed: () => _downloadCsv(context),
          ),
        ],
      ),
      body: businesses.isEmpty
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.search_off, size: 56, color: Colors.grey),
                  const SizedBox(height: 12),
                  Text(
                    'Tidak ada hasil ditemukan',
                    style: TextStyle(color: Colors.grey[400], fontSize: 15),
                  ),
                ],
              ),
            )
          : SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SingleChildScrollView(
                child: DataTable(
                  headingRowColor: WidgetStateProperty.all(const Color(0xFF1E293B)),
                  dataRowColor: WidgetStateProperty.all(const Color(0xFF0F172A)),
                  border: TableBorder.all(color: const Color(0xFF1E293B), width: 1),
                  headingTextStyle: const TextStyle(
                    color: Color(0xFF3B82F6),
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                  dataTextStyle: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                  ),
                  columns: columns
                      .map((c) => DataColumn(
                            label: ConstrainedBox(
                              constraints: const BoxConstraints(minWidth: 110, maxWidth: 200),
                              child: Text(c),
                            ),
                          ))
                      .toList(),
                  rows: businesses.asMap().entries.map((entry) {
                    final i = entry.key;
                    final b = entry.value;
                    return DataRow(
                      color: WidgetStateProperty.resolveWith((states) {
                        return i.isEven ? const Color(0xFF162032) : const Color(0xFF0F172A);
                      }),
                      cells: [
                        DataCell(ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 200),
                          child: Text(b.namaUsaha),
                        )),
                        DataCell(Text(b.nomorHp)),
                        DataCell(ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 200),
                          child: Text(b.alamat),
                        )),
                        DataCell(SelectableText(b.website, style: const TextStyle(color: Color(0xFF3B82F6)))),
                        DataCell(Text(b.rating)),
                        DataCell(Text(b.totalReview)),
                        DataCell(ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 200),
                          child: SelectableText(
                            b.googleMapsUrl,
                            style: const TextStyle(color: Color(0xFF60A5FA), fontSize: 10),
                          ),
                        )),
                        DataCell(Text(b.category)),
                      ],
                    );
                  }).toList(),
                ),
              ),
            ),
    );
  }
}
