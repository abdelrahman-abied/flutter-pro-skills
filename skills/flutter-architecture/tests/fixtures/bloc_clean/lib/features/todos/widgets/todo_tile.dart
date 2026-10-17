import 'package:flutter/material.dart';

class TodoTile extends StatelessWidget {
  const TodoTile({super.key, required this.title});
  final String title;

  @override
  Widget build(BuildContext context) => ListTile(title: Text(title));
}
