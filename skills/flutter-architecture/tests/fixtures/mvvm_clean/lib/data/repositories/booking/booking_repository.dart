import '../../../domain/models/booking.dart';
import '../../../utils/result.dart';

abstract class BookingRepository {
  Future<Result<List<Booking>>> getBookingsList();
}
