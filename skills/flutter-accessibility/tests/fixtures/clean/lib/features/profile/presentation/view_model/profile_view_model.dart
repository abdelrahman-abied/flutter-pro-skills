import 'package:flutter/foundation.dart';

enum SaveStatus { idle, saving, saved }

class ProfileViewModel extends ChangeNotifier {
  SaveStatus status = SaveStatus.idle;
  int unread = 0;

  Future<void> save() async {
    status = SaveStatus.saved;
    notifyListeners();
  }
}
