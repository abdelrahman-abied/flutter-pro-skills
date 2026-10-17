import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'data/repositories/booking/booking_repository.dart';
import 'data/repositories/booking/booking_repository_remote.dart';
import 'data/services/api/api_client.dart';
import 'routing/router.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        Provider(create: (_) => ApiClient()),
        Provider<BookingRepository>(
          create: (context) => BookingRepositoryRemote(apiClient: context.read()),
        ),
      ],
      child: MaterialApp.router(routerConfig: router()),
    ),
  );
}
