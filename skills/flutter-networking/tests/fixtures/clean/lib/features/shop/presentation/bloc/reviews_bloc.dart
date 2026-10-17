import 'package:bloc/bloc.dart';
import 'package:bloc_concurrency/bloc_concurrency.dart';

sealed class ReviewsEvent {}

final class ReviewsNextPageRequested extends ReviewsEvent {}

final class ReviewsRefreshed extends ReviewsEvent {}

final class ReviewsState {
  const ReviewsState({this.items = const [], this.hasReachedMax = false, this.loading = false});

  final List<String> items;
  final bool hasReachedMax;
  final bool loading;
}

abstract interface class ReviewsRepository {
  Future<List<String>> page(int offset);
}

class ReviewsBloc extends Bloc<ReviewsEvent, ReviewsState> {
  ReviewsBloc(this._repository) : super(const ReviewsState()) {
    on<ReviewsNextPageRequested>(_onNextPage, transformer: droppable());
    on<ReviewsRefreshed>(_onRefresh);
  }

  final ReviewsRepository _repository;

  Future<void> _onNextPage(ReviewsNextPageRequested event, Emitter<ReviewsState> emit) async {
    if (state.hasReachedMax) return;
    final items = await _repository.page(state.items.length);
    emit(ReviewsState(items: [...state.items, ...items], hasReachedMax: items.isEmpty));
  }

  /// Not a page fetch: reloads from the start.
  Future<void> _onRefresh(ReviewsRefreshed event, Emitter<ReviewsState> emit) async {
    if (state.loading) return;
    final items = await _repository.page(0);
    emit(ReviewsState(items: items));
  }
}
