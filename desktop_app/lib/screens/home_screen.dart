import 'dart:io';

import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';
import '../services/scraper_service.dart';
import '../models/business.dart';
import 'result_screen.dart';

/// Screen utama: form keyword + fields + start scrape.
class HomeScreen extends StatefulWidget {
  final String apiKey;
  final ApiService apiService;
  final int quotaRemaining;
  final String packageType;

  const HomeScreen({
    super.key,
    required this.apiKey,
    required this.apiService,
    required this.quotaRemaining,
    required this.packageType,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _keywordController = TextEditingController();
  int _maxScrolls = 10;
  double _paralelTab = 6;

  // Field toggles
  bool _namaUsaha = true;
  bool _nomorHp = true;
  bool _alamat = true;
  bool _website = true;
  bool _rating = true;
  bool _totalReview = true;
  bool _googleMapsUrl = true;
  bool _category = true;

  // Scraping state
  bool _scraping = false;
  double _progress = 0;
  String _progressDetail = '';
  final List<String> _logs = [];

  // File paths
  String? _scraperPath;

  @override
  void initState() {
    super.initState();
    _autoDetectScraper();
  }

  @override
  void dispose() {
    _keywordController.dispose();
    super.dispose();
  }

  /// Auto-detect scraper.exe (production) atau scraper.py (dev).
  /// Priority: shared_prefs → exe dir → assets dir → manual pick.
  Future<void> _autoDetectScraper() async {
    final prefs = await SharedPreferences.getInstance();

    // 1. Cek shared_preferences
    final savedPath = prefs.getString('scraper_path');
    if (savedPath != null && File(savedPath).existsSync()) {
      setState(() => _scraperPath = savedPath);
      return;
    }

    // 2. Cek folder exe — production: scraper.exe (PyInstaller bundle)
    final exeDir = File(Platform.resolvedExecutable).parent;
    final bundleExe = File('${exeDir.path}${Platform.pathSeparator}scraper${Platform.pathSeparator}scraper.exe');
    if (bundleExe.existsSync()) {
      setState(() => _scraperPath = bundleExe.path);
      await prefs.setString('scraper_path', bundleExe.path);
      return;
    }

    // 3. Cek scraper.py di folder exe (dev mode)
    final exePy = File('${exeDir.path}${Platform.pathSeparator}scraper.py');
    if (exePy.existsSync()) {
      setState(() => _scraperPath = exePy.path);
      await prefs.setString('scraper_path', exePy.path);
      return;
    }

    // 4. Cek folder assets (development mode)
    final assetsDir = Directory('${Directory.current.path}${Platform.pathSeparator}assets${Platform.pathSeparator}scraper');
    final assetsPy = File('${assetsDir.path}${Platform.pathSeparator}scraper.py');
    if (assetsPy.existsSync()) {
      setState(() => _scraperPath = assetsPy.path);
      await prefs.setString('scraper_path', assetsPy.path);
      return;
    }

    // 5. Tidak ditemukan — user pilih manual
  }

  /// Build fields string dari toggles.
  String get _fieldsString {
    final parts = <String>[];
    if (_namaUsaha) parts.add('nama_usaha');
    if (_nomorHp) parts.add('nomor_hp');
    if (_alamat) parts.add('alamat');
    if (_website) parts.add('website');
    if (_rating) parts.add('rating');
    if (_totalReview) parts.add('total_review');
    if (_googleMapsUrl) parts.add('google_maps_url');
    if (_category) parts.add('category');
    return parts.join(',');
  }

  Future<void> _pickScraperFile() async {
    final result = await FilePicker.platform.pickFiles(
      dialogTitle: 'Pilih scraper.exe atau scraper.py',
      type: FileType.custom,
      allowedExtensions: ['exe', 'py'],
    );
    if (result != null && result.files.single.path != null) {
      final path = result.files.single.path!;
      setState(() => _scraperPath = path);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('scraper_path', path);
    }
  }

  Future<void> _startScraping() async {
    if (_keywordController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Masukkan kata kunci pencarian')),
      );
      return;
    }

    setState(() {
      _scraping = true;
      _progress = 0;
      _progressDetail = 'Memulai...';
      _logs.clear();
    });

    try {
      final scraper = ScraperService(
        scraperPath: _scraperPath!,
      );

      final results = await scraper.runScrape(
        keyword: _keywordController.text.trim(),
        maxScrolls: _maxScrolls,
        fields: _fieldsString,
        onProgress: (pct, detail) {
          if (!mounted) return;
          setState(() {
            _progress = pct;
            _progressDetail = detail;
          });
        },
        onLog: (line) {
          if (!mounted) return;
          setState(() => _logs.add(line));
        },
      );

      if (!mounted) return;

      // Kurangi quota di server
      widget.apiService.useQuota(widget.apiKey);

      // Geser ke result screen
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            businesses: results,
            keyword: _keywordController.text.trim(),
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
      );
    } finally {
      if (mounted) {
        setState(() => _scraping = false);
      }
    }
  }

  Future<void> _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('api_key');
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, '/');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        title: const Text('Scraper', style: TextStyle(color: Colors.white, fontSize: 16)),
        backgroundColor: const Color(0xFF1E293B),
        elevation: 0,
        actions: [
          // Quota badge
          Container(
            margin: const EdgeInsets.only(right: 8),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: widget.quotaRemaining > 0 ? const Color(0xFF065F46) : const Color(0xFF7F1D1D),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              '${widget.quotaRemaining} quota',
              style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.logout, color: Colors.grey),
            onPressed: _logout,
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── File Configuration ─────────────────────────
            _buildFileConfigCard(),
            const SizedBox(height: 16),

            // ── Keyword ────────────────────────────────────
            _buildSectionLabel('Kata Kunci Pencarian'),
            TextField(
              controller: _keywordController,
              style: const TextStyle(color: Colors.white, fontSize: 14),
              decoration: InputDecoration(
                hintText: 'contoh: jasa tour surabaya',
                hintStyle: TextStyle(color: Colors.grey[500]),
                filled: true,
                fillColor: const Color(0xFF1E293B),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: BorderSide.none,
                ),
                prefixIcon: const Icon(Icons.search, color: Color(0xFF3B82F6)),
              ),
            ),
            const SizedBox(height: 20),

            // ── Max Scrolls ────────────────────────────────
            _buildSectionLabel('Maksimal Scroll: $_maxScrolls'),
            Slider(
              value: _maxScrolls.toDouble(),
              min: 3,
              max: 50,
              divisions: 47,
              activeColor: const Color(0xFF3B82F6),
              label: _maxScrolls.toString(),
              onChanged: (v) => setState(() => _maxScrolls = v.round()),
            ),
            const SizedBox(height: 4),

            // ── Field Toggles ──────────────────────────────
            _buildSectionLabel('Data yang Diekstrak'),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                _buildFieldChip('Nama Usaha', _namaUsaha, (v) => setState(() => _namaUsaha = v)),
                _buildFieldChip('Nomor HP', _nomorHp, (v) => setState(() => _nomorHp = v)),
                _buildFieldChip('Alamat', _alamat, (v) => setState(() => _alamat = v)),
                _buildFieldChip('Website', _website, (v) => setState(() => _website = v)),
                _buildFieldChip('Rating', _rating, (v) => setState(() => _rating = v)),
                _buildFieldChip('Total Review', _totalReview, (v) => setState(() => _totalReview = v)),
                _buildFieldChip('GMaps URL', _googleMapsUrl, (v) => setState(() => _googleMapsUrl = v)),
                _buildFieldChip('Kategori', _category, (v) => setState(() => _category = v)),
              ],
            ),
            const SizedBox(height: 24),

            // ── Start Button ───────────────────────────────
            SizedBox(
              height: 48,
              child: ElevatedButton.icon(
                onPressed: (_scraping || _scraperPath == null) ? null : _startScraping,
                icon: _scraping
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.play_arrow),
                label: Text(
                  _scraping ? 'Scraping...' : 'Mulai Scraping',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF3B82F6),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  disabledBackgroundColor: const Color(0xFF334155),
                ),
              ),
            ),

            // ── Progress ────────────────────────────────────
            if (_scraping) ...[
              const SizedBox(height: 20),
              LinearProgressIndicator(
                value: _progress / 100,
                backgroundColor: const Color(0xFF1E293B),
                color: const Color(0xFF3B82F6),
                minHeight: 8,
                borderRadius: BorderRadius.circular(4),
              ),
              const SizedBox(height: 8),
              Text(
                '${_progress.toStringAsFixed(0)}% — $_progressDetail',
                style: TextStyle(fontSize: 13, color: Colors.grey[300]),
              ),
            ],

            // ── Console Log ─────────────────────────────────
            if (_logs.isNotEmpty) ...[
              const SizedBox(height: 16),
              _buildSectionLabel('Log'),
              Container(
                height: 160,
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFF0B1120),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFF1E293B)),
                ),
                child: SingleChildScrollView(
                child: SelectableText(
                  _logs.join('\n'),
                  style: const TextStyle(
                    color: Color(0xFF22C55E),
                    fontSize: 11,
                    fontFamily: 'monospace',
                  ),
                ),
              ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildSectionLabel(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _buildFieldChip(String label, bool value, ValueChanged<bool> onChange) {
    return FilterChip(
      label: Text(label, style: const TextStyle(fontSize: 12)),
      selected: value,
      onSelected: onChange,
      selectedColor: const Color(0xFF3B82F6),
      checkmarkColor: Colors.white,
      backgroundColor: const Color(0xFF1E293B),
      labelStyle: TextStyle(color: value ? Colors.white : Colors.grey[400]),
      side: BorderSide(color: value ? const Color(0xFF3B82F6) : const Color(0xFF334155)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    );
  }

  Widget _buildFileConfigCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1E293B),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF334155)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.folder, size: 18, color: _scraperPath != null ? const Color(0xFF22C55E) : Colors.grey),
              const SizedBox(width: 8),
              Text(
                'File Scraper',
                style: TextStyle(
                  color: Colors.grey[300],
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          if (_scraperPath != null)
            Text(
              _scraperPath!,
              style: const TextStyle(color: Color(0xFF22C55E), fontSize: 11, fontFamily: 'monospace'),
            )
          else
            Text(
              'scraper.exe / scraper.py belum dipilih',
              style: TextStyle(color: Colors.grey[500], fontSize: 11),
            ),
          const SizedBox(height: 8),
          SizedBox(
            height: 32,
            child: OutlinedButton.icon(
              onPressed: _pickScraperFile,
              icon: const Icon(Icons.file_open, size: 16),
              label: const Text('Pilih scraper.exe', style: TextStyle(fontSize: 12)),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF3B82F6),
                side: const BorderSide(color: Color(0xFF3B82F6)),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
