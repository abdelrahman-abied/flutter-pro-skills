import 'package:bloc/bloc.dart';

enum YStatus { initial, loading, success, failure }

class YState {
  const YState({this.status = YStatus.initial, this.count = 0});
  final YStatus status;
  final int count;
  YState copyWith({YStatus? status, int? count}) => YState(status: status ?? this.status, count: count ?? this.count);
}

// bloclibrary flutter_todos stats_bloc shape.
class YBloc extends Bloc<Object, YState> {
  YBloc(this._todos) : super(const YState());
  final Stream<List<int>> Function() _todos;

  // K2-E1: emit.forEach(onError:) is the error path: not ERR-010.
  Future<void> _onSubscriptionRequested(Object event, Emitter<YState> emit) async {
    emit(state.copyWith(status: YStatus.loading));
    await emit.forEach<List<int>>(
      _todos(),
      onData: (todos) => state.copyWith(status: YStatus.success, count: todos.length),
      onError: (_, _) => state.copyWith(status: YStatus.failure),
    );
  }

  // Still ERR-010: emit.forEach without onError rethrows and the status stays loading.
  Future<void> _onWatchUnsafe(Object event, Emitter<YState> emit) async {
    emit(state.copyWith(status: YStatus.loading));
    await emit.forEach<List<int>>(
      _todos(),
      onData: (todos) => state.copyWith(status: YStatus.success, count: todos.length),
    );
  }
}
