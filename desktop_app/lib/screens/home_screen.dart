import 'dart:io';

import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';
import '../services/scraper_service.dart';
import '../models/business.dart';
import 'result_screen.dart';
import 'activation_screen.dart';

/// Screen utama: form keyword + fields + start scrape.
/// Professional, responsive desktop design.
class HomeScreen extends StatefulWidget {
  final String apiKey;
  final ApiService apiService;
  final int quotaRemaining;
  final int quotaTotal;
  final String packageType;
  final bool isTrial;
  final int initialMaxScrolls;
  final String? userEmail;
  final bool skipValidation;

  const HomeScreen({
    super.key,
    required this.apiKey,
    required this.apiService,
    required this.quotaRemaining,
    required this.quotaTotal,
    required this.packageType,
    required this.isTrial,
    required this.initialMaxScrolls,
    this.userEmail,
    this.skipValidation = false,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _keywordController = TextEditingController();
  int _maxScrolls = 1;
  late int _maxScrollsAllowed; // dari license server

  // Mutable license state (updated by background validation)
  int _quotaRemaining = 0;
  int _quotaTotal = 0;
  String _packageType = '';
  bool _isTrial = false;
  String? _userEmail;
  bool _validating = false;
  String? _licenseError;

  // Field toggles — without total_review, gmaps_url, category
  bool _namaUsaha = true;
  bool _nomorHp = true;
  bool _alamat = true;
  bool _website = true;
  bool _rating = true;

  // Scraping state
  bool _scraping = false;
  double _progress = 0;
  String _progressDetail = '';
  final List<String> _logs = [];
  final ScrollController _logScrollController = ScrollController();

  // File paths
  String? _scraperPath;

  @override
  void initState() {
    super.initState();
    _quotaRemaining = widget.quotaRemaining;
    _quotaTotal = widget.quotaTotal;
    _packageType = widget.packageType;
    _isTrial = widget.isTrial;
    _userEmail = widget.userEmail;
    _maxScrollsAllowed = widget.initialMaxScrolls;
    _autoDetectScraper();
    if (widget.skipValidation) {
      _validateLicenseInBackground();
    }
  }

  /// Validasi license di background — update UI setelah selesai.
  Future<void> _validateLicenseInBackground() async {
    setState(() => _validating = true);
    final result = await widget.apiService.checkLicense(widget.apiKey);
    if (!mounted) return;
    setState(() {
      _validating = false;
      if (result.valid) {
        _quotaRemaining = result.quotaRemaining;
        _quotaTotal = result.quotaTotal;
        _packageType = result.packageType;
        _isTrial = result.isTrial;
        _userEmail = result.userEmail;
        _maxScrollsAllowed = result.maxScrolls;
        if (_maxScrolls > _maxScrollsAllowed) _maxScrolls = _maxScrollsAllowed;
        _licenseError = null;
      } else {
        _licenseError = result.error ?? 'License invalid';
      }
    });
    // Jika key sudah tidak valid, arahkan ke activation
    if (!result.valid && mounted) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('api_key');
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ActivationScreen(apiService: widget.apiService),
        ),
      );
    }
  }

  @override
  void dispose() {
    _keywordController.dispose();
    _logScrollController.dispose();
    super.dispose();
  }

  /// Auto-detect scraper.exe (production) atau scraper.py (dev).
  /// Priority: bundle (exe dir) → dev py → saved prefs → assets → manual.
  Future<void> _autoDetectScraper() async {
    final prefs = await SharedPreferences.getInstance();

    // 1. Cek folder exe — production: scraper.exe (PyInstaller bundle)
    //    PRIORITAS UTAMA untuk end-user: selalu pakai yang di samping .exe
    final exeDir = File(Platform.resolvedExecutable).parent;
    final bundleExe =
        File('${exeDir.path}${Platform.pathSeparator}scraper${Platform.pathSeparator}scraper.exe');
    if (bundleExe.existsSync()) {
      setState(() => _scraperPath = bundleExe.path);
      await prefs.setString('scraper_path', bundleExe.path);
      return;
    }

    // 2. Cek scraper.py di folder exe (dev mode)
    final exePy = File('${exeDir.path}${Platform.pathSeparator}scraper.py');
    if (exePy.existsSync()) {
      setState(() => _scraperPath = exePy.path);
      await prefs.setString('scraper_path', exePy.path);
      return;
    }

    // 3. Fallback: cek shared_preferences (user manual pick sebelumnya)
    final savedPath = prefs.getString('scraper_path');
    if (savedPath != null && File(savedPath).existsSync()) {
      setState(() => _scraperPath = savedPath);
      return;
    }

    // 4. Cek folder assets (development mode)
    final assetsDir = Directory(
        '${Directory.current.path}${Platform.pathSeparator}assets${Platform.pathSeparator}scraper');
    final assetsPy = File('${assetsDir.path}${Platform.pathSeparator}scraper.py');
    if (assetsPy.existsSync()) {
      setState(() => _scraperPath = assetsPy.path);
      await prefs.setString('scraper_path', assetsPy.path);
      return;
    }
  }

  /// Build fields string dari toggles.
  String get _fieldsString {
    final parts = <String>[];
    if (_namaUsaha) parts.add('nama_usaha');
    if (_nomorHp) parts.add('nomor_hp');
    if (_alamat) parts.add('alamat');
    if (_website) parts.add('website');
    if (_rating) parts.add('rating');
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
        const SnackBar(
          content: Text('Masukkan kata kunci pencarian'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    setState(() {
      _scraping = true;
      _progress = 0;
      _progressDetail = 'Memvalidasi license...';
      _logs.clear();
    });

    // Re-validasi license ke server sebelum scrape agar max_scrolls selalu update
    final licenseResult = await widget.apiService.checkLicense(widget.apiKey);

    if (!mounted) return;

    if (!licenseResult.valid) {
      setState(() => _scraping = false);
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('api_key');
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ActivationScreen(apiService: widget.apiService),
        ),
      );
      return;
    }

    // Update data license terbaru dari server
    _quotaRemaining = licenseResult.quotaRemaining;
    _quotaTotal = licenseResult.quotaTotal;
    _packageType = licenseResult.packageType;
    _isTrial = licenseResult.isTrial;
    _userEmail = licenseResult.userEmail;
    _maxScrollsAllowed = licenseResult.maxScrolls;
    if (_maxScrolls > _maxScrollsAllowed) _maxScrolls = _maxScrollsAllowed;

    setState(() {
      _progressDetail = 'Memulai...';
    });

    try {
      final scraper = ScraperService(scraperPath: _scraperPath!);

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
          // Auto-scroll log to bottom
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (_logScrollController.hasClients) {
              _logScrollController.animateTo(
                _logScrollController.position.maxScrollExtent,
                duration: const Duration(milliseconds: 100),
                curve: Curves.easeOut,
              );
            }
          });
        },
      );

      if (!mounted) return;

      // Kurangi quota di server + update lokal
      widget.apiService.useQuota(widget.apiKey);
      setState(() => _quotaRemaining = (_quotaRemaining - 1).clamp(0, _quotaTotal));

      // Geser ke result screen
      if (!mounted) return;
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
        SnackBar(
          content: Text('Error: $e'),
          backgroundColor: Colors.red.shade800,
          behavior: SnackBarBehavior.floating,
        ),
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

  // ── Build methods ──────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final isWide = MediaQuery.of(context).size.width > 700;

    return Scaffold(
      backgroundColor: const Color(0xFF0A0E17),
      appBar: _buildAppBar(),
      body: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            padding: EdgeInsets.symmetric(
              horizontal: isWide ? 40 : 16,
              vertical: 24,
            ),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 900),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // ── Status card ──────────────────────
                    _buildStatusCard(),
                    const SizedBox(height: 24),

                    // ── Keyword + Settings row ──────────
                    if (isWide)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(flex: 3, child: _buildKeywordCard()),
                          const SizedBox(width: 16),
                          Expanded(flex: 2, child: _buildSettingsCard()),
                        ],
                      )
                    else ...[
                      _buildKeywordCard(),
                      const SizedBox(height: 16),
                      _buildSettingsCard(),
                    ],

                    const SizedBox(height: 24),

                    // ── Fields toggles ──────────────────
                    _buildFieldsCard(),
                    const SizedBox(height: 24),

                    // ── Start Button ────────────────────
                    _buildStartButton(),
                    const SizedBox(height: 20),

                    // ── Progress ────────────────────────
                    if (_scraping) _buildProgressSection(),

                    // ── Console Log ─────────────────────
                    if (_logs.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      _buildLogSection(),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  PreferredSizeWidget _buildAppBar() {
    return AppBar(
      backgroundColor: const Color(0xFF111827),
      elevation: 0,
      title: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Image.asset('assets/logo/app-logo.png', width: 32, height: 32),
          const SizedBox(width: 10),
          const Text(
            'GMaps Scraper Pro',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.3,
            ),
          ),
        ],
      ),
      actions: [
        // Quota badge
        Container(
          margin: const EdgeInsets.only(right: 8),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: _quotaRemaining > 0
                ? const Color(0xFF065F46)
                : const Color(0xFF7F1D1D),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                _quotaRemaining > 0 ? Icons.bolt : Icons.bolt_outlined,
                size: 14,
                color: _quotaRemaining > 0
                    ? const Color(0xFF34D399)
                    : const Color(0xFFFCA5A5),
              ),
              const SizedBox(width: 6),
              Text(
                '${_quotaRemaining}/${_quotaTotal}',
                style: TextStyle(
                  color: _quotaRemaining > 0
                      ? const Color(0xFF34D399)
                      : const Color(0xFFFCA5A5),
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
        IconButton(
          icon: const Icon(Icons.logout, color: Colors.grey, size: 20),
          tooltip: 'Logout',
          onPressed: _logout,
        ),
        const SizedBox(width: 4),
      ],
    );
  }

  Widget _buildStatusCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            const Color(0xFF111827),
            const Color(0xFF1A2332),
          ],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF1E293B)),
      ),
      child: Row(
        children: [
          // Email
          if (_userEmail != null) ...[
            const Icon(Icons.person, size: 16, color: Color(0xFF64748B)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                _userEmail!,
                style: const TextStyle(
                  color: Color(0xFF94A3B8),
                  fontSize: 12,
                  fontFamily: 'monospace',
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 16),
          ],
          // Package badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: _isTrial
                  ? const Color(0xFF1E3A5F)
                  : const Color(0xFF374151),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              _isTrial ? 'TRIAL' : _packageType.toUpperCase(),
              style: TextStyle(
                color: _isTrial
                    ? const Color(0xFF60A5FA)
                    : const Color(0xFF9CA3AF),
                fontSize: 10,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.2,
              ),
            ),
          ),
          if (_isTrial) ...[
            const SizedBox(width: 8),
            const Text(
              '10 quota gratis',
              style: TextStyle(
                color: Color(0xFF64748B),
                fontSize: 11,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildKeywordCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1E293B)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: const Color(0xFF3B82F6).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(Icons.search, size: 16, color: Color(0xFF3B82F6)),
              ),
              const SizedBox(width: 10),
              const Text(
                'Kata Kunci Pencarian',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _keywordController,
            enabled: !_scraping,
            style: const TextStyle(color: Colors.white, fontSize: 15),
            decoration: InputDecoration(
              hintText: 'contoh: jasa tour surabaya',
              hintStyle: TextStyle(color: Colors.grey[600], fontSize: 14),
              filled: true,
              fillColor: const Color(0xFF0A0E17),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide.none,
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: const BorderSide(color: Color(0xFF3B82F6), width: 1.5),
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            ),
            onSubmitted: (_scraping || _scraperPath == null) ? null : (_) => _startScraping(),
          ),
        ],
      ),
    );
  }

  Widget _buildSettingsCard() {
    // Hitung level peringatan berdasarkan paket
    final bool atLimit = _maxScrolls >= _maxScrollsAllowed;
    final bool nearLimit = !atLimit && _maxScrollsAllowed > 1 && _maxScrolls >= (_maxScrollsAllowed * 0.7).ceil();
    final Color scrollColor = atLimit
        ? const Color(0xFFEF4444)
        : nearLimit
            ? const Color(0xFFF59E0B)
            : const Color(0xFF3B82F6);
    final Color trackColor = atLimit
        ? const Color(0xFFEF4444)
        : nearLimit
            ? const Color(0xFFF59E0B)
            : const Color(0xFF3B82F6);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: atLimit ? const Color(0xFF7F1D1D) : const Color(0xFF1E293B),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: const Color(0xFF8B5CF6).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(Icons.tune, size: 16, color: Color(0xFF8B5CF6)),
              ),
              const SizedBox(width: 10),
              const Text(
                'Pengaturan Scroll',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Text(
                'Maks $_maxScrollsAllowed',
                style: TextStyle(
                  color: atLimit ? const Color(0xFFFCA5A5) : const Color(0xFF64748B),
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // Max scrolls
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Max Scroll', style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color: atLimit
                      ? const Color(0xFF7F1D1D)
                      : nearLimit
                          ? const Color(0xFF78350F)
                          : const Color(0xFF1E293B),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (atLimit)
                      const Padding(
                        padding: EdgeInsets.only(right: 4),
                        child: Icon(Icons.warning_amber_rounded, size: 14, color: Color(0xFFFCA5A5)),
                      ),
                    Text(
                      '$_maxScrolls',
                      style: TextStyle(
                        color: scrollColor,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SliderTheme(
            data: SliderThemeData(
              trackHeight: 4,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 8),
              activeTrackColor: trackColor,
              inactiveTrackColor: const Color(0xFF1E293B),
              thumbColor: trackColor,
              overlayColor: trackColor.withOpacity(0.15),
            ),
            child: Slider(
              value: _maxScrolls.toDouble(),
              min: 1,
              max: _maxScrollsAllowed.toDouble(),
              divisions: _maxScrollsAllowed > 1 ? _maxScrollsAllowed - 1 : 1,
              onChanged: _scraping ? null : (v) => setState(() => _maxScrolls = v.round()),
            ),
          ),
          // Warning text at limit
          if (atLimit)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  const Icon(Icons.info_outline, size: 14, color: Color(0xFFFCA5A5)),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      _isTrial
                          ? 'Batas maksimum trial (1 scroll). Upgrade untuk scroll lebih banyak.'
                          : 'Batas maksimum paket $_packageType ($_maxScrollsAllowed scroll). Upgrade untuk menambah.',
                      style: const TextStyle(
                        color: Color(0xFFFCA5A5),
                        fontSize: 11,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          if (!atLimit)
            const SizedBox(height: 8),
          // Scraper path indicator
          Row(
            children: [
              Icon(
                Icons.circle,
                size: 8,
                color: _scraperPath != null ? const Color(0xFF22C55E) : const Color(0xFFEF4444),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _scraperPath != null ? 'Scraper siap' : 'Scraper tidak ditemukan',
                  style: TextStyle(
                    color: _scraperPath != null ? const Color(0xFF22C55E) : const Color(0xFFEF4444),
                    fontSize: 11,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              TextButton(
                onPressed: _pickScraperFile,
                style: TextButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: const Text('Pilih', style: TextStyle(fontSize: 11, color: Color(0xFF3B82F6))),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildFieldsCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1E293B)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: const Color(0xFF22C55E).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(Icons.data_array, size: 16, color: Color(0xFF22C55E)),
              ),
              const SizedBox(width: 10),
              const Text(
                'Data yang Diekstrak',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              Text(
                '${_selectedFieldCount}/5 dipilih',
                style: const TextStyle(color: Color(0xFF64748B), fontSize: 11),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _buildFieldChip('Nama Usaha', Icons.store, _namaUsaha, (v) => setState(() => _namaUsaha = v)),
              _buildFieldChip('Nomor HP', Icons.phone, _nomorHp, (v) => setState(() => _nomorHp = v)),
              _buildFieldChip('Alamat', Icons.location_on, _alamat, (v) => setState(() => _alamat = v)),
              _buildFieldChip('Website', Icons.language, _website, (v) => setState(() => _website = v)),
              _buildFieldChip('Rating', Icons.star, _rating, (v) => setState(() => _rating = v)),
            ],
          ),
        ],
      ),
    );
  }

  int get _selectedFieldCount {
    return [_namaUsaha, _nomorHp, _alamat, _website, _rating].where((e) => e).length;
  }

  Widget _buildFieldChip(String label, IconData icon, bool value, ValueChanged<bool> onChange) {
    return FilterChip(
      label: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: value ? Colors.white : const Color(0xFF64748B)),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(fontSize: 12, color: value ? Colors.white : const Color(0xFF94A3B8))),
        ],
      ),
      selected: value,
      onSelected: _scraping ? null : onChange,
      selectedColor: const Color(0xFF3B82F6),
      checkmarkColor: Colors.white,
      backgroundColor: const Color(0xFF1E293B),
      side: BorderSide(
        color: value ? const Color(0xFF3B82F6) : const Color(0xFF334155),
        width: value ? 1.5 : 1,
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }

  Widget _buildStartButton() {
    final enabled = !_scraping && _scraperPath != null;

    return SizedBox(
      height: 52,
      child: ElevatedButton(
        onPressed: enabled ? _startScraping : null,
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF3B82F6),
          foregroundColor: Colors.white,
          disabledBackgroundColor: const Color(0xFF1E293B),
          disabledForegroundColor: const Color(0xFF475569),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          elevation: enabled ? 4 : 0,
          shadowColor: const Color(0xFF3B82F6).withOpacity(0.4),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_scraping)
              const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white),
              )
            else
              const Icon(Icons.play_arrow_rounded, size: 26),
            const SizedBox(width: 10),
            Text(
              _scraping ? 'Scraping...' : 'Mulai Scraping',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, letterSpacing: 0.2),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProgressSection() {
    return Column(
      children: [
        const SizedBox(height: 4),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: _progress / 100,
            backgroundColor: const Color(0xFF1E293B),
            color: const Color(0xFF3B82F6),
            minHeight: 8,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          '${_progress.toStringAsFixed(0)}% — $_progressDetail',
          style: const TextStyle(fontSize: 13, color: Color(0xFF94A3B8)),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  Widget _buildLogSection() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF0B1120),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF1E293B)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.terminal, size: 16, color: Color(0xFF64748B)),
              const SizedBox(width: 8),
              const Text(
                'Console Log',
                style: TextStyle(
                  color: Color(0xFF64748B),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
              const Spacer(),
              Text(
                '${_logs.length} lines',
                style: const TextStyle(color: Color(0xFF475569), fontSize: 10),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            constraints: const BoxConstraints(maxHeight: 200),
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFF060B14),
              borderRadius: BorderRadius.circular(8),
            ),
            child: SingleChildScrollView(
              controller: _logScrollController,
              child: SelectableText(
                _logs.join('\n'),
                style: const TextStyle(
                  color: Color(0xFF4ADE80),
                  fontSize: 11,
                  fontFamily: 'Consolas',
                  height: 1.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
