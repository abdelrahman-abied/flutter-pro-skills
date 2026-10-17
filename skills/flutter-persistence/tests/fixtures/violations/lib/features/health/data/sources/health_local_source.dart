import 'package:hive/hive.dart';

class HealthLocalSource {
  Future<Box<String>> openRecords() => Hive.openBox<String>('medical_records');

  Future<Box<String>> openPayments() => Hive.openBox<String>('payments');
}
