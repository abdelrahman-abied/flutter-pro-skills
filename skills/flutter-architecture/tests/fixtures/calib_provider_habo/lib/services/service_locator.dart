import 'sync_service.dart';

class ServiceLocator {
  static final ServiceLocator instance = ServiceLocator._();
  ServiceLocator._();
  final SyncService syncService = SyncService();
}
