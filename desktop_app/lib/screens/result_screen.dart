import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:csv/csv.dart';
import 'package:file_picker/file_picker.dart';

import '../models/business.dart';

/// Screen hasil scraping: profesional card-based list + export CSV.
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
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  void _copyToClipboard(BuildContext context, String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Disalin ke clipboard'),
        duration: Duration(seconds: 1),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Future<void> _openUrl(String url) async {
    // Simple URL opener — strip if needed
    if (!url.startsWith('http')) url = 'https://$url';
    try {
      await Process.run('cmd', ['/c', 'start', url]);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final isWide = MediaQuery.of(context).size.width > 800;

    return Scaffold(
      backgroundColor: const Color(0xFF0A0E17),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111827),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.check_circle_rounded, size: 20, color: Color(0xFF22C55E)),
            const SizedBox(width: 8),
            Text(
              'Hasil Pencarian',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        actions: [
          // Download CSV
          IconButton(
            icon: const Icon(Icons.download_rounded, color: Color(0xFF3B82F6)),
            tooltip: 'Download CSV',
            onPressed: () => _downloadCsv(context),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: businesses.isEmpty
          ? _buildEmptyState()
          : LayoutBuilder(
              builder: (context, constraints) {
                return Column(
                  children: [
                    // ── Header summary ──────────────────
                    _buildHeader(context),
                    const SizedBox(height: 8),
                    // ── Business cards ──────────────────
                    Expanded(
                      child: isWide
                          ? GridView.builder(
                              padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
                              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: 2,
                                childAspectRatio: 2.8,
                                crossAxisSpacing: 16,
                                mainAxisSpacing: 16,
                              ),
                              itemCount: businesses.length,
                              itemBuilder: (_, i) => _buildBusinessCard(context, businesses[i], i),
                            )
                          : ListView.builder(
                              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                              itemCount: businesses.length,
                              itemBuilder: (_, i) => Padding(
                                padding: const EdgeInsets.only(bottom: 12),
                                child: _buildBusinessCard(context, businesses[i], i),
                              ),
                            ),
                    ),
                  ],
                );
              },
            ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              color: const Color(0xFF1E293B),
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Icon(Icons.search_off_rounded, size: 40, color: Color(0xFF64748B)),
          ),
          const SizedBox(height: 20),
          const Text(
            'Tidak ada hasil ditemukan',
            style: TextStyle(color: Color(0xFF94A3B8), fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 8),
          const Text(
            'Coba kata kunci lain atau perbesar area scroll',
            style: TextStyle(color: Color(0xFF64748B), fontSize: 13),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final withRating = businesses.where((b) => b.rating.isNotEmpty).toList();
    final avgRating = withRating.isNotEmpty
        ? withRating
                .map((b) => double.tryParse(b.rating) ?? 0)
                .reduce((a, b) => a + b) /
            withRating.length
        : 0.0;
    final withPhone = businesses.where((b) => b.nomorHp.isNotEmpty).length;
    final withWeb = businesses.where((b) => b.website.isNotEmpty).length;

    return Container(
      margin: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF111827), Color(0xFF1A2332)],
        ),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1E293B)),
      ),
      child: Row(
        children: [
          // Count
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: const Color(0xFF3B82F6).withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: Text(
                '${businesses.length}',
                style: const TextStyle(
                  color: Color(0xFF3B82F6),
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ),
          const SizedBox(width: 14),
          // Info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '"$keyword"',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 12,
                  children: [
                    _buildStat(Icons.star_rounded, '${avgRating.toStringAsFixed(1)} avg', const Color(0xFFF59E0B)),
                    _buildStat(Icons.phone_rounded, '$withPhone telp', const Color(0xFF22C55E)),
                    _buildStat(Icons.language_rounded, '$withWeb web', const Color(0xFF60A5FA)),
                  ],
                ),
              ],
            ),
          ),
          // Download button
          SizedBox(
            height: 40,
            child: ElevatedButton.icon(
              onPressed: () => _downloadCsv(context),
              icon: const Icon(Icons.download_rounded, size: 18),
              label: const Text('CSV', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF3B82F6),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                padding: const EdgeInsets.symmetric(horizontal: 16),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStat(IconData icon, String label, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: color),
        const SizedBox(width: 3),
        Text(
          label,
          style: TextStyle(color: color.withOpacity(0.8), fontSize: 11, fontWeight: FontWeight.w500),
        ),
      ],
    );
  }

  Widget _buildBusinessCard(BuildContext context, Business b, int index) {
    final hasRating = b.rating.isNotEmpty;
    final ratingVal = double.tryParse(b.rating) ?? 0.0;
    final ratingColor = ratingVal >= 4.0
        ? const Color(0xFF22C55E)
        : ratingVal >= 3.0
            ? const Color(0xFFF59E0B)
            : const Color(0xFFEF4444);

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1E293B)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.2),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Top row: number + rating
              Row(
                children: [
                  // Number badge
                  Container(
                    width: 26,
                    height: 26,
                    decoration: BoxDecoration(
                      color: const Color(0xFF1E293B),
                      borderRadius: BorderRadius.circular(7),
                    ),
                    child: Center(
                      child: Text(
                        '${index + 1}',
                        style: const TextStyle(
                          color: Color(0xFF64748B),
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Name
                  Expanded(
                    child: Text(
                      b.namaUsaha,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        height: 1.3,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8),
                  // Rating badge
                  if (hasRating)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: ratingColor.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: ratingColor.withOpacity(0.3)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.star_rounded, size: 14, color: ratingColor),
                          const SizedBox(width: 4),
                          Text(
                            b.rating,
                            style: TextStyle(
                              color: ratingColor,
                              fontSize: 13,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 14),
              // Detail rows
              if (b.alamat.isNotEmpty) ...[
                _buildDetailRow(Icons.location_on_outlined, b.alamat, Colors.grey),
                const SizedBox(height: 6),
              ],
              if (b.nomorHp.isNotEmpty) ...[
                _buildDetailRow(
                  Icons.phone_outlined,
                  b.nomorHp,
                  const Color(0xFF22C55E),
                  onTap: () => _copyToClipboard(context, b.nomorHp),
                  trailing: const Icon(Icons.copy_rounded, size: 14, color: Color(0xFF475569)),
                ),
                const SizedBox(height: 6),
              ],
              if (b.website.isNotEmpty) ...[
                _buildDetailRow(
                  Icons.language_outlined,
                  b.website,
                  const Color(0xFF60A5FA),
                  onTap: () => _openUrl(b.website),
                  trailing: const Icon(Icons.open_in_new_rounded, size: 14, color: Color(0xFF475569)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDetailRow(
    IconData icon,
    String text,
    Color color, {
    VoidCallback? onTap,
    Widget? trailing,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 14, color: color.withOpacity(0.7)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                color: color.withOpacity(0.85),
                fontSize: 12,
                height: 1.3,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: 8),
            trailing,
          ],
        ],
      ),
    );
  }
}
