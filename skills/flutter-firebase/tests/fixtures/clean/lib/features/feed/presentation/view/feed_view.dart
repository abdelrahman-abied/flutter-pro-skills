import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_ui_firestore/firebase_ui_firestore.dart';
import 'package:flutter/material.dart';

class FeedView extends StatefulWidget {
  const FeedView({super.key, required this.query});

  final Query<Map<String, dynamic>> query;

  @override
  State<FeedView> createState() => _FeedViewState();
}

class _FeedViewState extends State<FeedView> {
  StreamSubscription<User?>? _authSub;
  final _subs = <StreamSubscription<Object?>>[];

  @override
  void initState() {
    super.initState();
    _authSub = FirebaseAuth.instance.authStateChanges().listen((_) => setState(() {}));
    _subs.add(FirebaseAuth.instance.idTokenChanges().listen((_) {}));
  }

  @override
  void dispose() {
    _authSub?.cancel();
    for (final s in _subs) {
      s.cancel();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FirestoreListView<Map<String, dynamic>>(
      query: widget.query,
      itemBuilder: (context, doc) => Text(doc.id),
    );
  }
}
