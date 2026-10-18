import 'package:flutter/material.dart';

void main() {
  // An app without Firebase: nothing below is a Firebase call.
  final store = _FakeStore()..useFirestoreEmulator('localhost', 8080);
  store.collection('x').snapshots();
  runApp(const MaterialApp(home: SizedBox()));
}

class _FakeStore {
  void useFirestoreEmulator(String host, int port) {}
  _FakeStore collection(String name) => this;
  Stream<int> snapshots() => const Stream.empty();
}
