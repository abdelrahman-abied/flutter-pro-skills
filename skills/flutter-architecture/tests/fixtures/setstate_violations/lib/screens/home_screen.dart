import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../globals.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<String> _items = const [];
  static int _visits = 0; // a State's static counter is exempt from ARCH-105

  @override
  void initState() {
    super.initState();
    _visits++;
    _load();
  }

  Future<void> _load() async {
    final res = await http.get(Uri.parse('${Config.baseUrl}/items'));
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('raw', res.body);
    final decoded = jsonDecode(res.body) as List<dynamic>;
    // "http.get(" in a comment or 'jsonDecode(' in a string is not I/O
    setState(() => _items = decoded.cast<String>());
  }

  @override
  Widget build(BuildContext context) => ListView(
        children: [for (final i in _items) ListTile(title: Text('$i $counter jsonDecode(x)'))],
      );
}
