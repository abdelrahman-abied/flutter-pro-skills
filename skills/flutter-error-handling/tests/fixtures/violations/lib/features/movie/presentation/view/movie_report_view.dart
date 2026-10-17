import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

class MovieReportView extends StatefulWidget {
  const MovieReportView({super.key, required this.dio});
  final Dio dio;
  @override
  State<MovieReportView> createState() => _MovieReportViewState();
}

class _MovieReportViewState extends State<MovieReportView> {
  int? _code;

  // ERR-014: awaits a network call in a UI callback with no try/catch.
  Future<void> _report() async {
    final res = await widget.dio.post<void>('/report');
    setState(() => _code = res.statusCode);
  }

  @override
  Widget build(BuildContext context) => TextButton(onPressed: _report, child: Text('report ${_code ?? ''}'));
}
