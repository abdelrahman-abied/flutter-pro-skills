import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/note.dart';

part 'notes_notifier.g.dart';

@riverpod
class NotesNotifier extends _$NotesNotifier {
  @override
  Future<List<Note>> build() async => const [];
}

@riverpod
class TagsNotifier extends _$TagsNotifier {
  @override
  List<String> build() => const [];
}

@riverpod
class FilterNotifier extends _$FilterNotifier {
  @override
  String build() => '';
}
