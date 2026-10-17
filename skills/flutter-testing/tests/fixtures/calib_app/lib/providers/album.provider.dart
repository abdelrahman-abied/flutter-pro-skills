import 'package:flutter_riverpod/flutter_riverpod.dart';

class AlbumNotifier extends StateNotifier<List<String>> {
  AlbumNotifier() : super(const []);

  void add(String name) {
    if (state.contains(name)) return;
    state = [...state, name];
  }
}

final albumProvider = StateNotifierProvider<AlbumNotifier, List<String>>((ref) => AlbumNotifier());
