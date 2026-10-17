// K2 C1/C5: repository handed over in BlocProvider(create:), get_it at the DI site -> no ARCH-005/008/104
import 'package:flutter/widgets.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:calib_bloc_mixed/injector.dart';
import 'package:calib_bloc_mixed/cart/bloc/cart_cubit.dart';
import 'package:calib_bloc_mixed/shopping_repository.dart';

class CartPage extends StatelessWidget {
  const CartPage({super.key});
  @override
  Widget build(BuildContext context) => MultiBlocProvider(
        providers: [
          BlocProvider(create: (context) => CartCubit(repo: context.read<ShoppingRepository>())),
          BlocProvider(create: (_) => sl<CartCubit>()),
        ],
        child: const SizedBox(),
      );
}
