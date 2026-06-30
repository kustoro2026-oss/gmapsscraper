import 'dart:convert';
import 'package:http/http.dart' as http;

/// Service untuk komunikasi dengan License Server (Railway).
class ApiService {
  final String baseUrl;
  String? _cachedApiKey;

  ApiService({required this.baseUrl});

  /// Cek status license dari API key.
  Future<({
    bool valid,
    int quotaRemaining,
    int quotaTotal,
    int maxScrolls,
    String packageType,
    bool isTrial,
    String? error,
    String? upgradeUrl,
    String? userEmail,
  })> checkLicense(String apiKey) async {
    try {
      final resp = await http.get(
        Uri.parse('$baseUrl/api/desktop/status'),
        headers: {'Authorization': 'Bearer $apiKey'},
      ).timeout(const Duration(seconds: 10));

      Map<String, dynamic> data;
      try {
        data = jsonDecode(resp.body);
      } catch (_) {
        return (
          valid: false,
          quotaRemaining: 0,
          quotaTotal: 0,
          maxScrolls: 0,
          packageType: '',
          isTrial: false,
          error: 'Server response not valid (HTTP ${resp.statusCode}). Check server URL.',
          upgradeUrl: null,
          userEmail: null,
        );
      }

      if (resp.statusCode == 200) {
        return (
          valid: data['active'] == true,
          quotaRemaining: data['quota_remaining'] as int? ?? 0,
          quotaTotal: data['quota_total'] as int? ?? 0,
          maxScrolls: data['max_scrolls'] as int? ?? 10,
          packageType: data['package'] as String? ?? 'unknown',
          isTrial: data['is_trial'] == true,
          error: null,
          upgradeUrl: data['upgrade_url'] as String?,
          userEmail: data['user_email'] as String?,
        );
      } else {
        return (
          valid: false,
          quotaRemaining: 0,
          quotaTotal: 0,
          maxScrolls: 0,
          packageType: '',
          isTrial: false,
          error: data['detail'] as String? ?? data['error'] as String? ?? 'Invalid API key',
          upgradeUrl: data['upgrade_url'] as String?,
          userEmail: null,
        );
      }
    } catch (e) {
      return (
        valid: false,
        quotaRemaining: 0,
        quotaTotal: 0,
        maxScrolls: 0,
        packageType: '',
        isTrial: false,
        error: 'Connection failed: $e',
        upgradeUrl: null,
        userEmail: null,
      );
    }
  }

  /// Pakai 1 quota (call setelah scraping selesai).
  Future<bool> useQuota(String apiKey, {String keyword = '', int resultsCount = 0}) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/desktop/use'),
        headers: {'Authorization': 'Bearer $apiKey'},
        body: {'keyword': keyword, 'results_count': resultsCount.toString()},
      ).timeout(const Duration(seconds: 5));

      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
