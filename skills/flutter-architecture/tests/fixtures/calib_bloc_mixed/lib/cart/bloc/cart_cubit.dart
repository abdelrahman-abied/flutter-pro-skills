// K2 C1 + C6: no ARCH-007 for a concrete repository; the BlocProvider.of accessor is one low ARCH-102
import 'package:bloc/bloc.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:calib_bloc_mixed/shopping_repository.dart';

class CartCubit extends Cubit<List<String>> {
  CartCubit({required ShoppingRepository repo}) : _repo = repo, super(const []);
  final ShoppingRepository _repo;
  static CartCubit get(BuildContext context) => BlocProvider.of(context);
  Future<void> load() async => emit(await _repo.loadCatalog());
}
