// K1: lib/config/ is the composition root (mvvm.md section 4)
import 'package:provider/provider.dart';
import '../data/repositories/booking_repository.dart';
import '../data/repositories/booking_repository_remote.dart';

List<Provider<BookingRepository>> providers = [
  Provider<BookingRepository>(create: (_) => BookingRepositoryRemote()),
];
