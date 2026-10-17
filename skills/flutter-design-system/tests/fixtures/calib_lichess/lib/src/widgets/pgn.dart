import 'package:flutter/material.dart';

const kViewVerticalPadding = 10.0;
const kViewHorizontalPadding = 10.0;
const kCommentVerticalPadding = 8.0;
const kIndexPadding = 6.0;

class PgnView extends StatelessWidget {
  const PgnView({super.key});

  @override
  Widget build(BuildContext context) => const Padding(padding: EdgeInsets.all(12), child: SizedBox(height: 7));
}
