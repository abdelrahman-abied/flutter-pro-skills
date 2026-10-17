import 'package:flutter_riverpod/flutter_riverpod.dart';

class Page {
  const Page({this.rows = const [], this.isLoading = false});

  final List<String> rows;
  final bool isLoading;
}

abstract interface class RowsRepository {
  Future<List<String>> before(String? cursor);
  Future<List<String>> pageAt(int page);
}

final rowsRepositoryProvider = Provider<RowsRepository>((ref) => throw UnimplementedError());

/// Sets the flag before the await; its only caller checks it (FP cause: guard at the call site).
class ArchiveController extends AsyncNotifier<Page> {
  @override
  Future<Page> build() async => const Page();

  Future<void> fetchNext() async {
    final current = state.requireValue;
    state = AsyncData(Page(rows: current.rows, isLoading: true));
    final more = await ref.read(rowsRepositoryProvider).before(current.rows.lastOrNull);
    state = AsyncData(Page(rows: [...current.rows, ...more]));
  }
}

/// A button-triggered "load older" with no guard: still reported, but Low (TP).
class ThreadController extends AsyncNotifier<Page> {
  @override
  Future<Page> build() async => const Page();

  Future<void> fetchMore() async {
    final current = state.requireValue;
    final older = await ref.read(rowsRepositoryProvider).before(current.rows.firstOrNull);
    state = AsyncData(Page(rows: [...older, ...current.rows]));
  }
}

/// Same flag pattern, but the scroll caller does not check it (TP, Medium).
class TimelineController extends AsyncNotifier<Page> {
  @override
  Future<Page> build() async => const Page();

  Future<void> fetchNext() async {
    final current = state.requireValue;
    state = AsyncData(Page(rows: current.rows, isLoading: true));
    final more = await ref.read(rowsRepositoryProvider).before(current.rows.lastOrNull);
    state = AsyncData(Page(rows: [...current.rows, ...more]));
  }
}

/// Not page fetches (FP cause: name vocabulary): the next single round, and an explicit page jump.
class RoundController extends AsyncNotifier<Page> {
  @override
  Future<Page> build() async => const Page();

  Future<void> _loadNextRound(bool solved) async {
    await ref.read(rowsRepositoryProvider).before(null);
  }

  Future<Page> _fetchPage(int page) async {
    final rows = await ref.read(rowsRepositoryProvider).pageAt(page);
    return Page(rows: rows);
  }

  void restart() => _loadNextRound(false).then((_) => _fetchPage(1));
}

final archiveProvider = AsyncNotifierProvider<ArchiveController, Page>(ArchiveController.new);
final threadProvider = AsyncNotifierProvider<ThreadController, Page>(ThreadController.new);
final timelineProvider = AsyncNotifierProvider<TimelineController, Page>(TimelineController.new);
