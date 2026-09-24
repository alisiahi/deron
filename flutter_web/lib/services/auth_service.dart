// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/browser_client.dart';
import '../models/user.dart';

class AuthService {
  static const String bffUrl = 'http://localhost:8001';

  // Configures a BrowserClient with credentials enabled to automatically transmit cookies in web CORS mode
  http.Client _createClient() {
    if (kIsWeb) {
      final client = BrowserClient();
      client.withCredentials = true;
      return client;
    }
    return http.Client();
  }

  // Polls the BFF endpoint to resolve active session user info
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
      debugPrint('Auth check failed: $e');
      return null;
    } finally {
      client.close();
    }
  }

  // Redirects browser window to the BFF login route to initiate OIDC authorization flow
  void login() {
    if (kIsWeb) {
      html.window.location.href = '$bffUrl/auth/login';
    }
  }

  // Redirects browser window to the BFF logout route to clear cookies and revoke Keycloak SSO session
  void logout() {
    if (kIsWeb) {
      html.window.location.href = '$bffUrl/auth/logout';
    }
  }
}
