import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

/// Flip to false to talk to a real project.
bool useLocalEmulator = true;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  if (useLocalEmulator) {
    FirebaseFirestore.instance.useFirestoreEmulator('localhost', 8080);
  }
  runApp(const MaterialApp(home: ItemsPage()));
}

final itemsRef = FirebaseFirestore.instance.collection('items').withConverter<Map<String, Object?>>(
      fromFirestore: (snapshot, _) => snapshot.data()!,
      toFirestore: (value, _) => value,
    );

class ItemsPage extends StatelessWidget {
  const ItemsPage({super.key});

  Future<void> addAndShow() async {
    final docRef = await FirebaseFirestore.instance.collection('items').add({'n': 1});
    final snapshot = await docRef.get();
    debugPrint('${snapshot.data()}');
  }

  Future<void> resetAll() async {
    final all = await itemsRef.get();
    final batch = FirebaseFirestore.instance.batch();
    for (final doc in all.docs) {
      batch.update(doc.reference, {'n': 0});
    }
    await batch.commit();
  }

  @override
  Widget build(BuildContext context) => const SizedBox();
}
