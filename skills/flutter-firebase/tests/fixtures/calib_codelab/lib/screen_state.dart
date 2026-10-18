import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';

/// Screen-scoped state: disposed when its screen goes away.
class NotesScreenState extends ChangeNotifier {
  int count = 0;

  void start() {
    FirebaseFirestore.instance.collection('notes').limit(50).snapshots().listen((s) {
      count = s.size;
      notifyListeners();
    });
  }

  @override
  void dispose() {
    super.dispose();
  }
}
