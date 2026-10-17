// K1 A6: material imported only for value types -> ARCH-009 low
import 'package:flutter/material.dart';
import '../../../data/repositories/booking_repository.dart';

class HomeViewModel extends ChangeNotifier {
  HomeViewModel({required BookingRepository bookingRepository}) : _repo = bookingRepository;
  final BookingRepository _repo;
  DateTimeRange? range;
  ThemeMode mode = ThemeMode.system;
  Future<void> load() async {
    await _repo.getBookings();
    notifyListeners();
  }
}

class AViewModel extends ChangeNotifier {}

class BViewModel extends ChangeNotifier {}
