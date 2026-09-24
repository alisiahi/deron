import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import '../providers/auth_provider.dart';
import '../theme/app_theme.dart';

class AppNavbar extends StatelessWidget implements PreferredSizeWidget {
  const AppNavbar({super.key});

  @override
  Size get preferredSize => const Size.fromHeight(64);

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    return Container(
      height: 64,
      decoration: const BoxDecoration(
        color: AppTheme.surface,
        border: Border(
          bottom: BorderSide(color: AppTheme.border, width: 1),
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Row(
        children: [
          // Logo / Brand
          MouseRegion(
            cursor: SystemMouseCursors.click,
            child: GestureDetector(
              onTap: () => context.go('/'),
              child: RichText(
                text: const TextSpan(
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                  children: [
                    TextSpan(
                      text: 'Kiwi',
                      style: TextStyle(color: AppTheme.primary),
                    ),
                    TextSpan(text: 'App'),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 32),

          // Nav links
          TextButton(
            onPressed: () => context.go('/'),
            child: const Text('Home', style: TextStyle(color: AppTheme.textSecondary)),
          ),
          if (auth.isAuthenticated)
            TextButton(
              onPressed: () => context.go('/dashboard'),
              child: const Text('Dashboard', style: TextStyle(color: AppTheme.textSecondary)),
            ),
          if (auth.isAdmin)
            TextButton(
              onPressed: () => context.go('/admin'),
              child: const Text('Admin', style: TextStyle(color: AppTheme.primary)),
            ),

          const Spacer(),

          // Auth info or action
          if (auth.isLoading)
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.primary),
            )
          else if (auth.isAuthenticated && auth.user != null)
            Row(
              children: [
                Icon(Icons.business_outlined, size: 18, color: AppTheme.textMuted),
                const SizedBox(width: 6),
                Text(
                  auth.user!.organization,
                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 14),
                ),
                const SizedBox(width: 16),
                Icon(Icons.person_outline, size: 18, color: AppTheme.textMuted),
                const SizedBox(width: 6),
                Text(
                  auth.user!.name,
                  style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w500),
                ),
                const SizedBox(width: 24),
                OutlinedButton.icon(
                  onPressed: () => auth.logout(),
                  icon: const Icon(Icons.logout, size: 16, color: AppTheme.textSecondary),
                  label: const Text('Logout', style: TextStyle(color: AppTheme.textSecondary, fontSize: 14)),
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: AppTheme.border),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ],
            )
          else
            ElevatedButton.icon(
              onPressed: () => auth.login(),
              icon: const Icon(Icons.login, size: 18),
              label: const Text('Login with Keycloak'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
              ),
            ),
        ],
      ),
    );
  }
}
