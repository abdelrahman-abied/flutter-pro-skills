import 'package:bloc/bloc.dart';

sealed class FeedEvent {}

final class FeedNextPageRequested extends FeedEvent {}

final class FeedState {
  const FeedState({this.items = const [], this.hasReachedMax = false});

  final List<String> items;
  final bool hasReachedMax;
}

abstract interface class FeedRepository {
  Future<List<String>> page(int offset);
}

class FeedBloc extends Bloc<FeedEvent, FeedState> {
  FeedBloc(this._repository) : super(const FeedState()) {
    on<FeedNextPageRequested>(_onNextPage);
  }

  final FeedRepository _repository;

  Future<void> _onNextPage(FeedNextPageRequested event, Emitter<FeedState> emit) async {
    if (state.hasReachedMax) return;
    final items = await _repository.page(state.items.length);
    emit(FeedState(items: [...state.items, ...items], hasReachedMax: items.isEmpty));
  }
}
