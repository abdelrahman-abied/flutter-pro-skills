import 'booking_repository.dart';

class BookingRepositoryRemote implements BookingRepository {
  @override
  Future<List<String>> getBookings() async => const [];
}
