// K2 FN-1: repositories_impl/ and *_repo_impl.dart are repository implementations
import '../../domain/repositories/post_repository.dart';

class PostRepoImpl implements PostRepository {
  @override
  Future<List<String>> posts() async => const [];
}
