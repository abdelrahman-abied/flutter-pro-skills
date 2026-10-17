import '../repositories/feed_repository.dart';

class GetFeedUseCase {
  const GetFeedUseCase(this._repository);

  final FeedRepository _repository;

  Future<List<String>> call() => _repository.loadTitles();
}
