import 'package:flutter/material.dart';

class Logs extends StatelessWidget {
  const Logs({super.key, required this.lines, required this.rows});

  final List<String> lines;
  final List<String> rows;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // perf-ignore: PERF-001 at most ten lines, capped by the logger
        Expanded(child: ListView(children: lines.map(Text.new).toList())),
        Expanded(
          child: ListView.builder(
            itemCount: rows.length,
            itemBuilder: (context, i) => IntrinsicHeight(child: Text(rows[i])), // perf-ignore: PERF-003 two-line rows, measured in profile mode
          ),
        ),
        Expanded(child: ListView(children: rows.map(Text.new).toList())),
      ],
    );
  }
}
