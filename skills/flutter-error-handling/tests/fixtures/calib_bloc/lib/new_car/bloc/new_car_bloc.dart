import 'package:flutter_bloc/flutter_bloc.dart';

import '../new_car_repository.dart';

class NewCarState {
  const NewCarState.initial() : brands = const [];
  const NewCarState.brandsLoadInProgress() : brands = const [];
  const NewCarState.brandsLoadSuccess({required this.brands});
  final List<String> brands;
}

class NewCarBloc extends Bloc<Object, NewCarState> {
  NewCarBloc({required NewCarRepository newCarRepository})
      : _newCarRepository = newCarRepository,
        super(const NewCarState.initial());
  final NewCarRepository _newCarRepository;

  // The awaited repository method can't fail (it only waits and returns a constant): not ERR-010.
  Future<void> _onNewCarFormLoaded(Object event, Emitter<NewCarState> emit) async {
    emit(const NewCarState.brandsLoadInProgress());
    final brands = await _newCarRepository.fetchBrands();
    emit(NewCarState.brandsLoadSuccess(brands: brands));
  }
}
