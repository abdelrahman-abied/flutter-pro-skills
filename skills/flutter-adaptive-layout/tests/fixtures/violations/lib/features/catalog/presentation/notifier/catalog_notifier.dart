import 'dart:io';

import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'catalog_notifier.g.dart';

@riverpod
class CatalogNotifier extends _$CatalogNotifier {
  bool isTablet = false;

  @override
  List<String> build() {
    if (Platform.isAndroid) {
      return const ['android'];
    }
    return const [];
  }
}
