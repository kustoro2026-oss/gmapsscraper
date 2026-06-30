import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Secure storage for API key — encrypted with device-derived key.
class SecureStorage {
  static const _keyPrefix = 'sk_';
  static const _salt = 'gmaps_scraper_v2_salt_2026';

  static String _deriveKey() {
    final seed = '${Platform.localHostname}_${Platform.environment['USERNAME'] ?? ''}_$_salt';
    return sha256.convert(utf8.encode(seed)).toString();
  }

  static String _obfuscate(String text, String key) {
    final keyBytes = utf8.encode(key);
    final textBytes = utf8.encode(text);
    final result = <int>[];
    for (var i = 0; i < textBytes.length; i++) {
      result.add(textBytes[i] ^ keyBytes[i % keyBytes.length]);
    }
    return base64.encode(result);
  }

  static String _deobfuscate(String encoded, String key) {
    final bytes = base64.decode(encoded);
    final keyBytes = utf8.encode(key);
    final result = <int>[];
    for (var i = 0; i < bytes.length; i++) {
      result.add(bytes[i] ^ keyBytes[i % keyBytes.length]);
    }
    return utf8.decode(result);
  }

  static Future<void> saveApiKey(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final dk = _deriveKey();
    final encrypted = _obfuscate(key, dk);
    await prefs.setString('${_keyPrefix}api_key', encrypted);
  }

  static Future<String?> getApiKey() async {
    final prefs = await SharedPreferences.getInstance();
    final encrypted = prefs.getString('${_keyPrefix}api_key');
    if (encrypted == null || encrypted.isEmpty) return null;
    try {
      final dk = _deriveKey();
      return _deobfuscate(encrypted, dk);
    } catch (_) {
      return null;
    }
  }

  static Future<void> deleteApiKey() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('${_keyPrefix}api_key');
  }
}
