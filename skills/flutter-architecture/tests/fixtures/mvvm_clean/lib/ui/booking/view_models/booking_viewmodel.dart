import 'package:flutter/foundation.dart';

import '../../../data/repositories/booking/booking_repository.dart';
import '../../../domain/models/booking.dart';
import '../../../utils/result.dart';

class BookingViewModel extends ChangeNotifier {
  BookingViewModel({required BookingRepository bookingRepository})
      : _bookingRepository = bookingRepository;

  final BookingRepository _bookingRepository;

  List<Booking> _bookings = const [];
  List<Booking> get bookings => _bookings;

  Future<void> load() async {
    final result = await _bookingRepository.getBookingsList();
    if (result case Ok(:final value)) {
      _bookings = value;
      notifyListeners();
    }
  }
}
