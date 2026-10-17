import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../domain/entities/item.dart';
import '../../domain/usecases/load_items_usecase.dart';

part 'shop_notifier.g.dart';

class ShopState {
  const ShopState({this.items = const [], this.isLoading = false, this.hasMore = true});

  final List<Item> items;
  final bool isLoading;
  final bool hasMore;

  ShopState copyWith({List<Item>? items, bool? isLoading, bool? hasMore}) => ShopState(
      items: items ?? this.items, isLoading: isLoading ?? this.isLoading, hasMore: hasMore ?? this.hasMore);
}

@riverpod
class ShopNotifier extends _$ShopNotifier {
  int _page = 0;

  @override
  ShopState build() => const ShopState();

  /// Guarded: a second call while a page is in flight is dropped.
  Future<void> loadMore() async {
    if (state.isLoading || !state.hasMore) return;
    state = state.copyWith(isLoading: true);
    final next = await ref.read(loadItemsUseCaseProvider)(_page + 1);
    _page++;
    state = state.copyWith(items: [...state.items, ...next], isLoading: false, hasMore: next.isNotEmpty);
  }

  /// Sets the flag before the await; every caller checks it before calling.
  Future<void> fetchNextPage() async {
    state = state.copyWith(isLoading: true);
    final next = await ref.read(loadItemsUseCaseProvider)(_page + 1);
    state = state.copyWith(items: [...state.items, ...next], isLoading: false);
  }

  /// Not a page fetch: loads the next single item of a quiz.
  Future<void> loadNextQuestion() async {
    await Future<void>.delayed(Duration.zero);
  }
}

@riverpod
class BasketNotifier extends _$BasketNotifier {
  @override
  int build() => 0;
}

@riverpod
class SortNotifier extends _$SortNotifier {
  @override
  String build() => '';
}
