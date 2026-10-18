import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

/// App-wide state, created once above MaterialApp and never disposed.
class ApplicationState extends ChangeNotifier {
  ApplicationState() {
    init();
  }

  int members = 0;
  List<String> notes = [];
  StreamSubscription<QuerySnapshot<Map<String, dynamic>>>? _notesSub;

  Future<void> init() async {
    await Firebase.initializeApp();
    FirebaseFirestore.instance.collection('members').where('active', isEqualTo: true).limit(500).snapshots().listen((s) {
      members = s.docs.length;
      notifyListeners();
    });
    FirebaseAuth.instance.userChanges().listen((user) {
      if (user != null) {
        _notesSub = FirebaseFirestore.instance
            .collection('notes')
            .orderBy('createdAt', descending: true)
            .snapshots()
            .listen((s) {
          notes = [for (final d in s.docs) d.id];
          notifyListeners();
        });
      } else {
        _notesSub?.cancel();
      }
    });
  }
}
