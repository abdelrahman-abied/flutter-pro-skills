import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../data/repositories/cart_repository_impl.dart';
import '../repositories/cart_repository.dart';

part 'cart_usecase.g.dart';

class GetCartTotal {
  final CartRepository _repository;
  const GetCartTotal(this._repository);

  Future<int> call() => _repository.total();
}

@riverpod
GetCartTotal getCartTotal(Ref ref) => GetCartTotal(ref.watch(cartRepositoryProvider));
