import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:hydrated_bloc/hydrated_bloc.dart';

part 'account_state.dart';

class AccountCubit extends HydratedCubit<AccountState> {
  AccountCubit() : super(const AccountState());

  void signedIn(String refreshToken) {
    // SEC-004 high: crash-report breadcrumbs leave the device.
    FirebaseCrashlytics.instance.log('signed in with $refreshToken');
    emit(AccountState(refreshToken: refreshToken));
  }

  @override
  AccountState? fromJson(Map<String, dynamic> json) => AccountState(refreshToken: json['refreshToken'] as String?);

  @override
  Map<String, dynamic>? toJson(AccountState state) => state.toJson();
}
