// FX-T note: a RouterDelegate with ChangeNotifier is routing glue (composition root), not logic
import 'package:flutter/material.dart';

class AppRouter extends RouterDelegate<Object> with ChangeNotifier {
  @override
  Widget build(BuildContext context) => Navigator(pages: const [], onDidRemovePage: (_) {});
  @override
  Future<bool> popRoute() async => false;
  @override
  Future<void> setNewRoutePath(Object configuration) async {}
}
