import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';
import 'home_screen.dart';

/// Screen pertama: masukkan API key untuk aktivasi.
class ActivationScreen extends StatefulWidget {
  final ApiService apiService;

  const ActivationScreen({super.key, required this.apiService});

  @override
  State<ActivationScreen> createState() => _ActivationScreenState();
}

class _ActivationScreenState extends State<ActivationScreen> {
  final _keyController = TextEditingController();
  bool _loading = false;
  String? _error;
  String? _quotaInfo;

  @override
  void dispose() {
    _keyController.dispose();
    super.dispose();
  }

  Future<void> _activate() async {
    final key = _keyController.text.trim();
    if (key.isEmpty) {
      setState(() => _error = 'Masukkan API key terlebih dahulu');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _quotaInfo = null;
    });

    final result = await widget.apiService.checkLicense(key);

    if (!mounted) return;

    setState(() => _loading = false);

    if (result.valid) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('api_key', key);
      await prefs.setString('server_url', widget.apiService.baseUrl);

      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => HomeScreen(
            apiKey: key,
            apiService: widget.apiService,
            quotaRemaining: result.quotaRemaining,
            packageType: result.packageType,
          ),
        ),
      );
    } else {
      setState(() => _error = result.error ?? 'API key tidak valid');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Logo / icon
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  color: const Color(0xFF1E293B),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFF3B82F6), width: 2),
                ),
                child: const Icon(Icons.map, size: 44, color: Color(0xFF3B82F6)),
              ),
              const SizedBox(height: 24),
              const Text(
                'Google Maps Scraper',
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Professional Desktop Edition',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey[400],
                ),
              ),
              const SizedBox(height: 40),

              // API Key input
              TextField(
                controller: _keyController,
                style: const TextStyle(color: Colors.white, fontSize: 14),
                decoration: InputDecoration(
                  hintText: 'Masukkan API Key...',
                  hintStyle: TextStyle(color: Colors.grey[500]),
                  prefixIcon: const Icon(Icons.vpn_key, color: Color(0xFF3B82F6)),
                  filled: true,
                  fillColor: const Color(0xFF1E293B),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Color(0xFF3B82F6), width: 2),
                  ),
                  errorText: _error,
                  errorStyle: const TextStyle(color: Color(0xFFEF4444)),
                ),
              ),
              const SizedBox(height: 24),

              // Activate button
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton(
                  onPressed: _loading ? null : _activate,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF3B82F6),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    disabledBackgroundColor: const Color(0xFF1E40AF),
                  ),
                  child: _loading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text('Aktivasi', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                ),
              ),
              const SizedBox(height: 16),

              // Info
              Text(
                'Belum punya API key? Dapatkan di web dashboard.',
                style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
