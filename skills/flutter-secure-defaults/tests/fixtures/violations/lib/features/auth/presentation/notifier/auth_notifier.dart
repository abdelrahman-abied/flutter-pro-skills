import 'package:dio/dio.dart';
import 'package:firebase_analytics/firebase_analytics.dart';
import 'package:flutter/foundation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../state/auth_state.dart';

part 'auth_notifier.g.dart';

@riverpod
class AuthNotifier extends _$AuthNotifier {
  // SEC-010: a static, mutable token cache in logic.
  static String? cachedToken;

  @override
  AuthState build() => const AuthSignedOut();

  Future<void> loadProfile(Dio dio, String accessToken) async {
    // SEC-002: header built in a notifier.
    final res = await dio.get<Object>('/me', options: Options(headers: {'Authorization': 'Bearer $accessToken'}));
    // SEC-004 medium (print) and high (analytics).
    print('loaded profile with $accessToken');
    await FirebaseAnalytics.instance.logEvent(name: 'profile', parameters: {'token': accessToken});
    // SEC-004 low: debug-only.
    if (kDebugMode) {
      debugPrint('token=$accessToken');
    }
    // Not reported: a message about tokens, a boolean, the token's length.
    print('token refreshed');
    print('has token: ${accessToken.isNotEmpty}');
    state = AuthSignedIn(name: '$res');
  }
}
