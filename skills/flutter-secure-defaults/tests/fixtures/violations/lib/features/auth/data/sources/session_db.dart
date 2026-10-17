import 'package:drift/drift.dart';

// SEC-001 (database): the JWT column of a plain drift database.
class SessionsCompanion {
  const SessionsCompanion({this.userId = const Value.absent(), this.jwt = const Value.absent()});
  final Value<String> userId;
  final Value<String> jwt;
}

SessionsCompanion toRow(String id, String jwt) => SessionsCompanion(userId: Value(id), jwt: Value(jwt));
