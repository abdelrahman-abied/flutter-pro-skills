import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../ui/booking/view_models/booking_viewmodel.dart';
import '../ui/booking/widgets/booking_screen.dart';

GoRouter router() => GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) =>
              BookingScreen(viewModel: BookingViewModel(bookingRepository: context.read())),
        ),
      ],
    );
