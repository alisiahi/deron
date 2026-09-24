import 'package:flutter/foundation.dart';
import '../models/user.dart';
import '../services/auth_service.dart';

class AuthProvider extends ChangeNotifier {
  final AuthService _authService = AuthService();

  User? _user;
  bool _isLoading = true;

  User? get user => _user;
  bool get isLoading => _isLoading;
  bool get isAuthenticated => _user != null;
  bool get isAdmin =>
      _user != null &&
      (_user!.organization == 'adminsop' || _user!.organization == 'adminops');

  AuthProvider() {
    initAuth();
  }

  Future<void> initAuth() async {
    _isLoading = true;
    notifyListeners();

    _user = await _authService.checkAuth();

    _isLoading = false;
    notifyListeners();
  }

  void login() {
    _authService.login();
  }

  void logout() {
    _authService.logout();
  }
}
