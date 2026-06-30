import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'services/api_service.dart';
import 'screens/activation_screen.dart';
import 'screens/home_screen.dart';

/// Default server URL — user bisa ganti di settings.
const String kDefaultServerUrl = 'https://gmapsscraper.pro';

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
  Widget? _screen; // null = loading, set = direct render

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

    if (!mounted) return;

    // Langsung set screen via setState — no Navigator needed
    if (savedKey != null && savedKey.isNotEmpty) {
      setState(() {
        _screen = HomeScreen(
          apiKey: savedKey,
          apiService: _apiService,
          quotaRemaining: 0,
          quotaTotal: 0,
          packageType: '',
          isTrial: false,
          initialMaxScrolls: 1,
          userEmail: null,
          skipValidation: true,
        );
      });
    } else {
      setState(() {
        _screen = ActivationScreen(apiService: _apiService);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // Direct render — no Navigator
    if (_screen != null) return _screen!;

    return Scaffold(
      backgroundColor: Color(0xFF0F172A),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Image.asset('assets/logo/app-logo.png', width: 56, height: 56),
            SizedBox(height: 16),
            CircularProgressIndicator(color: Color(0xFF3B82F6)),
          ],
        ),
      ),
    );
  }
}
