import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'cart_state.dart';
import 'catalog_bloc.dart';

class CartBloc extends Cubit<CartState> {
  CartBloc(this._catalog) : super(CartState(const []));
  final CatalogBloc _catalog;

  void checkout(BuildContext context) {
    showDialog<void>(context: context, builder: (_) => const Text('Done'));
    emit(CartState(_catalog.state));
  }
}
