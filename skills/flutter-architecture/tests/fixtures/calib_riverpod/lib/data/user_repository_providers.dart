// K3 A6: a provider-only wiring file is role di (no ARCH-011, no test gap)
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'user_repository.dart';
import 'entries_repository.dart';

final userRepositoryProvider = Provider<UserRepository>((ref) => UserRepository());
final entriesRepositoryProvider = Provider<EntriesRepository>((ref) => EntriesRepository());
