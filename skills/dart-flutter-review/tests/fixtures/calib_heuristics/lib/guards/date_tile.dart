// K1 H2: `.then` as a fire-and-forget statement in a sync callback (compass search_form_date.dart).
import 'package:flutter/material.dart';

class DateTile extends StatelessWidget {
  const DateTile({super.key, required this.onPicked});
  final ValueChanged<DateTimeRange?> onPicked;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: () {
          showDateRangePicker(context: context, firstDate: DateTime(2020), lastDate: DateTime(2030))
              .then((r) => onPicked(r));
        },
      );
}
