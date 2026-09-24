// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/browser_client.dart';
import '../models/user.dart';

class AuthService {
  static const String bffUrl = 'http://localhost:8001';

  http.Client _createClient() {
    if (kIsWeb) {
      final client = BrowserClient();
      client.withCredentials = true;
      return client;
    }
    return http.Client();
  }

  Future<User?> checkAuth() async {
    final client = _createClient();
    try {
      final response = await client.get(
        Uri.parse('$bffUrl/auth/me'),
        headers: {'Accept': 'application/json'},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['authenticated'] == false) {
          return null;
        }
        return User.fromJson(data);
      }
      return null;
    } catch (e) {
      debugPrint('Error checking auth: $e');
      return null;
    } finally {
      client.close();
    }
  }

  void login() {
    if (kIsWeb) {
      html.window.location.href = '$bffUrl/auth/login';
    }
  }

  void logout() {
    if (kIsWeb) {
      html.window.location.href = '$bffUrl/auth/logout';
    }
  }
}
