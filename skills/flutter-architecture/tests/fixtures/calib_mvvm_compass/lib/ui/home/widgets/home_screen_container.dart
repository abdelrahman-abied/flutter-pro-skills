// K1 A2: the widget only builds its view model from providers (DI seam) -> no ARCH-008
import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';
import '../../../data/repositories/booking_repository.dart';
import '../view_models/home_viewmodel.dart';

class HomeScreenContainer extends StatefulWidget {
  const HomeScreenContainer({super.key});
  @override
  State<HomeScreenContainer> createState() => _State();
}

class _State extends State<HomeScreenContainer> {
  late final HomeViewModel _vm =
      HomeViewModel(bookingRepository: context.read<BookingRepository>());
  @override
  Widget build(BuildContext context) => const SizedBox();
  @override
  void dispose() {
    _vm.dispose();
    super.dispose();
  }
}
