// true positive: the widget calls the repository itself -> ARCH-008
import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';
import '../../../data/repositories/booking_repository.dart';

class BookingList extends StatelessWidget {
  const BookingList({super.key});
  @override
  Widget build(BuildContext context) {
    context.read<BookingRepository>().getBookings();
    return const SizedBox();
  }
}
