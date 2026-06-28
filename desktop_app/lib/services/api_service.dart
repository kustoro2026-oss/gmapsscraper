import 'dart:convert';
import 'package:http/http.dart' as http;

/// Service untuk komunikasi dengan License Server (Railway).
class ApiService {
  final String baseUrl;
  String? _cachedApiKey;

  ApiService({required this.baseUrl});

  /// Cek status license dari API key.
  /// Return: (valid: bool, quotaRemaining: int, packageType: String, errorMsg: String?)
  Future<({bool valid, int quotaRemaining, String packageType, String? error})> checkLicense(
    String apiKey,
  ) async {
    try {
      final resp = await http.get(
        Uri.parse('$baseUrl/api/desktop/status'),
        headers: {'Authorization': 'Bearer $apiKey'},
      ).timeout(const Duration(seconds: 10));

      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        return (
          valid: data['active'] == true,
          quotaRemaining: data['quota_remaining'] as int? ?? 0,
          packageType: data['package'] as String? ?? 'unknown',
          error: null,
        );
      } else {
        final data = jsonDecode(resp.body);
        return (
          valid: false,
          quotaRemaining: 0,
          packageType: '',
          error: data['detail'] as String? ?? data['error'] as String? ?? 'Invalid API key',
        );
      }
    } catch (e) {
      return (
        valid: false,
        quotaRemaining: 0,
        packageType: '',
        error: 'Connection failed: $e',
      );
    }
  }

  /// Pakai 1 quota (call setelah scraping selesai).
  Future<bool> useQuota(String apiKey) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/desktop/use'),
        headers: {'Authorization': 'Bearer $apiKey'},
      ).timeout(const Duration(seconds: 5));

      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
