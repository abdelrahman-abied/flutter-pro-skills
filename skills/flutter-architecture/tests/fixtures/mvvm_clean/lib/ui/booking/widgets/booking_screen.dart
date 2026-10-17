import 'package:flutter/material.dart';

import '../view_models/booking_viewmodel.dart';

class BookingScreen extends StatefulWidget {
  const BookingScreen({super.key, required this.viewModel});
  final BookingViewModel viewModel;

  @override
  State<BookingScreen> createState() => _BookingScreenState();
}

class _BookingScreenState extends State<BookingScreen> {
  @override
  void initState() {
    super.initState();
    widget.viewModel.load();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: widget.viewModel,
        builder: (context, _) => ListView(
          children: [for (final b in widget.viewModel.bookings) ListTile(title: Text(b.destination))],
        ),
      );
}
