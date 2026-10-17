import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'features/cart/presentation/view/cart_view.dart';
import 'features/settings/presentation/notifier/locale_notifier.dart';
import 'l10n/app_localizations.dart';

void main() => runApp(const ProviderScope(child: ShopApp()));

class ShopApp extends ConsumerWidget {
  const ShopApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp(
      onGenerateTitle: (context) => AppLocalizations.of(context).cartTitle,
      locale: ref.watch(localeNotifierProvider),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const CartView(),
    );
  }
}
