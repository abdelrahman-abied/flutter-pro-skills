import 'package:flutter/widgets.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'locale_notifier.g.dart';

@riverpod
class LocaleNotifier extends _$LocaleNotifier {
  @override
  Locale? build() => null; // null = follow the device

  void select(Locale locale) => state = locale;
}
