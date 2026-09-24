import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/browser_client.dart';
import 'package:flutter/foundation.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/app_navbar.dart';

class AdminPage extends StatefulWidget {
  const AdminPage({super.key});

  @override
  State<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage> {
  List<dynamic> _requests = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetchRequests();
  }

  // Fetch all permission requests via BFF reverse proxy admin endpoint
  Future<void> _fetchRequests() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    http.Client client;
    if (kIsWeb) {
      final browserClient = BrowserClient();
      browserClient.withCredentials = true;
      client = browserClient;
    } else {
      client = http.Client();
    }

    try {
      final response = await client.get(
        Uri.parse('http://localhost:8001/api/v1/admin/permissions'),
      );

      if (response.statusCode == 200) {
        setState(() {
          _requests = jsonDecode(response.body);
        });
      } else {
        setState(() {
          _error = 'Failed to fetch data (Status ${response.statusCode})';
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Could not connect to BFF server ($e)';
      });
    } finally {
      client.close();
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // Issue a DELETE request to clear a target request by ID
  Future<void> _deleteRequest(int id) async {
    http.Client client;
    if (kIsWeb) {
      final browserClient = BrowserClient();
      browserClient.withCredentials = true;
      client = browserClient;
    } else {
      client = http.Client();
    }

    try {
      final response = await client.delete(
        Uri.parse('http://localhost:8001/api/v1/admin/permissions/$id'),
        headers: {'X-Requested-With': 'XMLHttpRequest'},
      );

      if (response.statusCode == 204 || response.statusCode == 200) {
        setState(() {
          _requests.removeWhere((req) => req['id'] == id);
        });
      }
    } catch (e) {
      debugPrint('Delete request failed: $e');
    } finally {
      client.close();
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    // Client-side route guard: check organization claim
    if (!auth.isAdmin) {
      return Scaffold(
        appBar: const AppNavbar(),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.security, size: 64, color: Colors.redAccent),
              const SizedBox(height: 16),
              const Text(
                'Access Denied',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
              ),
              const SizedBox(height: 8),
              const Text(
                'You must belong to the adminsop organization to access this page.',
                style: TextStyle(color: AppTheme.textSecondary),
              ),
              const SizedBox(height: 24),
              ElevatedButton(
                onPressed: () => context.go('/'),
                child: const Text('Return Home'),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      appBar: const AppNavbar(),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Center(
          child: Container(
            constraints: const BoxConstraints(maxWidth: 1000),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    IconButton(
                      onPressed: () => context.go('/'),
                      icon: const Icon(Icons.arrow_back, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(width: 8),
                    const Icon(Icons.admin_panel_settings, color: AppTheme.primary, size: 32),
                    const SizedBox(width: 12),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        Text(
                          'Admin Portal',
                          style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
                        ),
                        Text(
                          'Manage and view all incoming permission requests',
                          style: TextStyle(color: AppTheme.textSecondary),
                        ),
                      ],
                    ),
                    const Spacer(),
                    OutlinedButton.icon(
                      onPressed: _fetchRequests,
                      icon: const Icon(Icons.refresh, size: 18),
                      label: const Text('Refresh Data'),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: AppTheme.border),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 32),

                if (_error != null) ...[
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.redAccent.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.redAccent.withValues(alpha: 0.4)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.error_outline, color: Colors.redAccent),
                        const SizedBox(width: 12),
                        Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                ],

                Container(
                  decoration: BoxDecoration(
                    color: AppTheme.surface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppTheme.border),
                  ),
                  child: _isLoading
                      ? const Padding(
                          padding: EdgeInsets.all(48),
                          child: Center(child: CircularProgressIndicator(color: AppTheme.primary)),
                        )
                      : _requests.isEmpty
                          ? const Padding(
                              padding: EdgeInsets.all(48),
                              child: Center(
                                child: Text('No permission requests found.', style: TextStyle(color: AppTheme.textMuted)),
                              ),
                            )
                          : ListView.separated(
                              shrinkWrap: true,
                              physics: const NeverScrollableScrollPhysics(),
                              itemCount: _requests.length,
                              separatorBuilder: (context, index) => const Divider(color: AppTheme.border, height: 1),
                              itemBuilder: (context, index) {
                                final req = _requests[index];
                                return ListTile(
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                                  title: Row(
                                    children: [
                                      Text(
                                        '#${req['id']}',
                                        style: const TextStyle(color: AppTheme.textMuted, fontSize: 13, fontFamily: 'monospace'),
                                      ),
                                      const SizedBox(width: 16),
                                      Text(
                                        '${req['first_name']} ${req['last_name']}',
                                        style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                                      ),
                                      const SizedBox(width: 12),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                        decoration: BoxDecoration(
                                          color: AppTheme.primary.withValues(alpha: 0.15),
                                          borderRadius: BorderRadius.circular(999),
                                        ),
                                        child: Text(
                                          req['role'].toString().toUpperCase(),
                                          style: const TextStyle(color: AppTheme.primary, fontSize: 11, fontWeight: FontWeight.bold),
                                        ),
                                      ),
                                    ],
                                  ),
                                  subtitle: Padding(
                                    padding: const EdgeInsets.only(top: 6),
                                    child: Text(
                                      'Email: ${req['email']} • Message: ${req['message']}',
                                      style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                                    ),
                                  ),
                                  trailing: IconButton(
                                    icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
                                    onPressed: () => _deleteRequest(req['id']),
                                  ),
                                );
                              },
                            ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
