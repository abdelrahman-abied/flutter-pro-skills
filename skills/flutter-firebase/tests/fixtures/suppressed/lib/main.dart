import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  // fire-ignore: FIRE-004 integration-test build only, never shipped
  FirebaseFirestore.instance.useFirestoreEmulator('localhost', 8080);
  runApp(const MaterialApp(home: SizedBox()));
}
