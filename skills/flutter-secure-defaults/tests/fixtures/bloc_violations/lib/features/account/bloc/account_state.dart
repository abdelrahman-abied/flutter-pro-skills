part of 'account_bloc.dart';

// SEC-010 medium: HydratedBloc persists this state, token included.
final class AccountState {
  const AccountState({this.refreshToken, this.balance = 0});
  final String? refreshToken;
  final int balance;

  Map<String, dynamic> toJson() => {'refreshToken': refreshToken, 'balance': balance};
}
