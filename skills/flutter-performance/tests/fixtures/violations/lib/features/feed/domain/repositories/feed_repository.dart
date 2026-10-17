abstract interface class FeedRepository {
  Future<List<String>> loadTitles();
}
