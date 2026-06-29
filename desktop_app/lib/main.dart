import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'services/api_service.dart';
import 'screens/activation_screen.dart';
import 'screens/home_screen.dart';

/// Default server URL — user bisa ganti di settings.
const String kDefaultServerUrl = 'https://gmapsscraper.com';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const GMapsScraperApp());
}

class GMapsScraperApp extends StatelessWidget {
  const GMapsScraperApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GMaps Scraper Pro',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        colorSchemeSeed: const Color(0xFF3B82F6),
        scaffoldBackgroundColor: const Color(0xFF0F172A),
      ),
      home: const AppLoader(),
    );
  }
}

/// Cek apakah user sudah pernah aktivasi.
/// Jika sudah: langsung ke HomeScreen.
/// Jika belum: tampilkan ActivationScreen.
class AppLoader extends StatefulWidget {
  const AppLoader({super.key});

  @override
  State<AppLoader> createState() => _AppLoaderState();
}

class _AppLoaderState extends State<AppLoader> {
  late final ApiService _apiService;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _initApp();
  }

  Future<void> _initApp() async {
    final prefs = await SharedPreferences.getInstance();
    final savedKey = prefs.getString('api_key');
    final savedUrl = prefs.getString('server_url') ?? kDefaultServerUrl;

    _apiService = ApiService(baseUrl: savedUrl);

    if (savedKey != null && savedKey.isNotEmpty) {
      // Cek license masih valid
      final result = await _apiService.checkLicense(savedKey);

      if (!mounted) return;
      setState(() => _loading = false);

      if (result.valid) {
        // Langsung ke home
        if (!mounted) return;
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => HomeScreen(
              apiKey: savedKey,
              apiService: _apiService,
              quotaRemaining: result.quotaRemaining,
              quotaTotal: result.quotaTotal,
              packageType: result.packageType,
              isTrial: result.isTrial,
              userEmail: result.userEmail,
            ),
          ),
        );
      } else {
        // Key expired — hapus dan tampilkan activation
        await prefs.remove('api_key');
        if (!mounted) return;
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => ActivationScreen(apiService: _apiService),
          ),
        );
      }
    } else {
      if (!mounted) return;
      setState(() => _loading = false);
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ActivationScreen(apiService: _apiService),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0F172A),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.map, size: 48, color: Color(0xFF3B82F6)),
            SizedBox(height: 16),
            CircularProgressIndicator(color: Color(0xFF3B82F6)),
          ],
        ),
      ),
    );
  }
}
