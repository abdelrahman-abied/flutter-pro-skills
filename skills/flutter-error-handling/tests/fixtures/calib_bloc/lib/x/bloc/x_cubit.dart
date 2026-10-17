import 'package:bloc/bloc.dart';

import 'x_state.dart';

class XCubit extends Cubit<XState> {
  XCubit() : super(const XState());

  // K2-E2: the chained catchError emits a failure. K2-FN-3: but e.toString() is raw text (ERR-008 low).
  Future<void> load(Future<int> Function() f) async {
    emit(const XState(status: XStatus.loading));
    await f().then((v) => emit(XState(status: XStatus.success, v: v)))
        .catchError((Object e) => emit(XState(status: XStatus.failure, msg: e.toString())));
  }

  // K2-E2: a catchError that only returns a value leaves the state loading (ERR-010 medium).
  Future<void> loadQuietly(Future<int> Function() f) async {
    emit(const XState(status: XStatus.loading));
    await f().then((v) => emit(XState(status: XStatus.success, v: v))).catchError((Object e) {
      return 0;
    });
  }

  // K2-FN-4: copyWith(status: () => X.loading) is a loading state; this await is unguarded (ERR-010 high).
  Future<void> refresh(Future<int> Function() f) async {
    emit(state.copyWith(status: () => XStatus.loading));
    final v = await f();
    emit(XState(status: XStatus.success, v: v));
  }
}
