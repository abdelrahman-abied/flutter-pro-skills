// K1 A1: a Flutter-MVVM use case depends on the abstract repository in data/repositories/
import '../../data/repositories/booking_repository.dart';

class CreateBookingUseCase {
  CreateBookingUseCase(this._repo);
  final BookingRepository _repo;
  Future<int> count() async => (await _repo.getBookings()).length;
}
