import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'user_repository_impl.dart';

part 'user_repository_provider.g.dart';

@riverpod
UserRepository userRepo(Ref ref) => UserRepositoryImpl();
