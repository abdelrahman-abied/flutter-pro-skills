// K1 notes: material only for DateTimeRange (ARCH-003 low under mvvm); a widget-free ui/ helper (ARCH-002 medium)
import 'package:flutter/material.dart';
import '../../ui/core/date_format.dart';

class ShareBookingUseCase {
  String text(DateTimeRange r) => formatRange(r.start, r.end);
}
