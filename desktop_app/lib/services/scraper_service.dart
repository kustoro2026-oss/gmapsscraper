import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:csv/csv.dart';
import 'package:path_provider/path_provider.dart';

import '../models/business.dart';

/// Service untuk menjalankan scraper dan parse hasilnya.
/// Mendukung 2 mode:
///   - PY mode (dev): scraper.py + python
///   - EXE mode (production): scraper.exe (PyInstaller bundle, sudah include Python + Playwright + Chromium)
class ScraperService {
  /// Path ke scraper (.exe atau .py).
  final String scraperPath;

  ScraperService({required this.scraperPath});

  bool get _isExe => scraperPath.toLowerCase().endsWith('.exe');

  /// Jalankan scraper dan return hasil via stream progress.
  Future<List<Business>> runScrape({
    required String keyword,
    required int maxScrolls,
    required String fields,
    String? token,
    double? lat,
    double? lng,
    void Function(double progress, String detail)? onProgress,
    void Function(String line)? onLog,
  }) async {
    final tempDir = await getTemporaryDirectory();
    final outputPath = '${tempDir.path}/scrape_result_${DateTime.now().millisecondsSinceEpoch}.csv';

    final scraperDir = File(scraperPath).parent.path;

    // Build args
    final commonArgs = <String>[
      '--keyword', keyword,
      '--max-scrolls', maxScrolls.toString(),
      '--fields', fields,
      '--output', outputPath,
    ];
    if (token != null && token.isNotEmpty) commonArgs.addAll(['--token', token]);
    if (lat != null) commonArgs.addAll(['--lat', lat.toString()]);
    if (lng != null) commonArgs.addAll(['--lng', lng.toString()]);

    late final Process process;
    // Python stdout buffering fix — force flush every line
    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONUNBUFFERED'] = '1';

    if (_isExe) {
      // Production: run scraper.exe directly (bundle includes Python + Playwright + Chromium)
      final args = [scraperPath, ...commonArgs];
      onLog?.call('[CMD] ${args.first} ${args.skip(1).join(' ')}');
      process = await Process.start(scraperPath, commonArgs, workingDirectory: scraperDir, environment: env);
    } else {
      // Development: run with python
      final pythonExe = 'python';
      final args = [scraperPath, ...commonArgs];
      onLog?.call('[CMD] $pythonExe ${args.join(' ')}');
      process = await Process.start(pythonExe, args, workingDirectory: scraperDir, environment: env);
    }

    // Parse stdout untuk PROGRESS: lines
    process.stdout.transform(utf8.decoder).listen((String data) {
      for (final line in data.split('\n')) {
        final trimmed = line.trim();
        if (trimmed.isEmpty) continue;

        if (trimmed.startsWith('PROGRESS:')) {
          final parts = trimmed.substring(9).split(':');
          if (parts.length >= 2) {
            final pct = double.tryParse(parts[0]);
            final detail = parts.sublist(1).join(':').trim();
            if (pct != null) onProgress?.call(pct, detail);
          }
          onLog?.call(trimmed);
        } else if (trimmed.startsWith('RESULT:') || trimmed.startsWith('DATA:')) {
          // Skip internal data lines
        } else {
          onLog?.call(trimmed);
        }
      }
    });

    // Parse stderr
    process.stderr.transform(utf8.decoder).listen((String data) {
      for (final line in data.split('\n')) {
        if (line.trim().isNotEmpty) onLog?.call('[STDERR] $line');
      }
    });

    final exitCode = await process.exitCode;
    onLog?.call('[EXIT] code=$exitCode');

    if (exitCode != 0) {
      throw Exception('Scraper exited with code $exitCode');
    }

    // Baca CSV hasil
    final outputFile = File(outputPath);
    try {
      if (!await outputFile.exists()) {
        throw Exception('Output file not found: $outputPath');
      }

      final csvContent = await outputFile.readAsString(encoding: utf8);
      final rows = const CsvToListConverter().convert(csvContent);

      if (rows.isEmpty) throw Exception('CSV is empty');

      return rows.skip(1).map((row) => Business.fromCsvRow(row)).toList();
    } finally {
      try { await outputFile.delete(); } catch (_) {}
    }
  }
}
