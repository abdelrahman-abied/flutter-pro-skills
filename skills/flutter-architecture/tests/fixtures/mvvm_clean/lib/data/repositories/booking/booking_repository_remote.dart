import '../../../domain/models/booking.dart';
import '../../../utils/result.dart';
import '../../services/api/api_client.dart';
import 'booking_repository.dart';

class BookingRepositoryRemote implements BookingRepository {
  BookingRepositoryRemote({required ApiClient apiClient}) : _apiClient = apiClient;
  final ApiClient _apiClient;

  @override
  Future<Result<List<Booking>>> getBookingsList() async {
    final result = await _apiClient.getBookings();
    return switch (result) {
      Ok(:final value) => Result.ok([
          for (final b in value) Booking(id: b.id, destination: b.destinationRef),
        ]),
      Error(:final error) => Result.error(error),
    };
  }
}
