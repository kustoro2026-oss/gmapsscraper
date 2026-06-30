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
  /// @deprecated Gunakan preScrape() untuk consume quota sebelum scrape.
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

  /// Dapatkan pre-scrape token (sekaligus konsumsi 1 quota di server).
  Future<({
    bool success,
    String token,
    int maxScrolls,
    int remaining,
    String logId,
    String? error,
  })> preScrape(String apiKey, {String keyword = '', int scrolls = 1}) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/desktop/pre-scrape'),
        headers: {'Authorization': 'Bearer $apiKey'},
        body: {'keyword': keyword, 'scrolls': scrolls.toString()},
      ).timeout(const Duration(seconds: 10));

      Map<String, dynamic> data;
      try {
        data = jsonDecode(resp.body);
      } catch (_) {
        return (success: false, token: '', maxScrolls: 0, remaining: 0, logId: '', error: 'Invalid server response');
      }

      if (resp.statusCode == 200 && data['success'] == true) {
        return (
          success: true,
          token: data['token'] as String? ?? '',
          maxScrolls: data['max_scrolls'] as int? ?? 0,
          remaining: data['remaining'] as int? ?? 0,
          logId: data['log_id'] as String? ?? '',
          error: null,
        );
      } else {
        return (
          success: false,
          token: '',
          maxScrolls: 0,
          remaining: 0,
          logId: '',
          error: data['detail'] as String? ?? 'Pre-scrape failed',
        );
      }
    } catch (e) {
      return (success: false, token: '', maxScrolls: 0, remaining: 0, logId: '', error: 'Connection failed: $e');
    }
  }

  /// Report hasil scraping ke server (update results_count di UsageLog).
  Future<void> updateResult(String apiKey, String logId, int resultsCount) async {
    try {
      await http.post(
        Uri.parse('$baseUrl/api/desktop/update-result'),
        headers: {'Authorization': 'Bearer $apiKey'},
        body: {'log_id': logId, 'results_count': resultsCount.toString()},
      ).timeout(const Duration(seconds: 5));
    } catch (_) {}
  }
}
