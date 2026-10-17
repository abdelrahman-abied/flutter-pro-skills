class FavoritesRepository {
  final _ids = <String>{};

  bool isFavorite(String id) => _ids.contains(id);
  void toggle(String id) => _ids.contains(id) ? _ids.remove(id) : _ids.add(id);
}
