# Placing platform code by architecture

The rule is the same in every pattern: **a channel, Pigeon API or FFI binding
is a data source.** It sits behind a repository or service contract, the
repository maps `PlatformException`/`MissingPluginException` to the pattern's
failure type, and logic and views see only domain values. The patterns differ
in folder names, in how the source is injected, and in which lifetime hook
cancels streams and clears handlers.

Detect the pattern first (`../flutter-architecture/scripts/arch_check.py
--json`, or read the project); a pattern declared in the project's
instructions file wins.

## Contents

1. MVN (Model-View-Notifier, Riverpod)
2. MVVM (Flutter architecture guide)
3. Bloc / Cubit
4. Clean Architecture
5. Provider, GetX, plain Riverpod
6. Apps without layers

## 1. MVN

```
lib/features/battery/
  data/sources/battery_platform_source.dart      # channel / Pigeon / FFI wrapper
  data/repositories/battery_repository_impl.dart # catches PlatformException → BatteryFailure
  domain/repositories/battery_repository.dart    # contract
  domain/usecases/get_battery_level.dart         # @riverpod use case
  presentation/notifier/battery_notifier.dart    # calls the use case only
  presentation/view/battery_view.dart
```

- The source gets a `@Riverpod(keepAlive: true)` provider; register
  `ref.onDispose(source.dispose)` there when it holds a subscription or a
  handler.
- Notifiers own event-stream subscriptions from the repository's `Stream` and
  cancel them in `ref.onDispose` (PLAT-005).
- The MVN spec routes notifiers through use cases; a notifier holding a
  channel is PLAT-001 (and ARCH-012 if it imports the source).

## 2. MVVM

```
lib/data/services/battery_service.dart           # the channel wrapper (like the guide's API services)
lib/data/repositories/battery_repository.dart    # returns Result<int>; maps PlatformException
lib/ui/battery/view_models/battery_view_model.dart
lib/ui/battery/widgets/battery_screen.dart
```

- The service is created at the composition root and passed to the
  repository; view models receive repositories.
- The view model's `Command` exposes the error state; the view shows it.
- Subscriptions live in the view model or repository and are cancelled in
  `dispose()`.

## 3. Bloc / Cubit

```
packages/battery_client/lib/battery_client.dart  # data provider (channel/Pigeon wrapper)
lib/battery/data/battery_repository.dart         # maps PlatformException to a domain error
lib/battery/bloc/battery_bloc.dart
lib/battery/view/battery_page.dart
```

- bloclibrary's layering: the data provider wraps the platform, the
  repository composes data providers, blocs use repositories received through
  `RepositoryProvider`.
- Streams from native become repository streams; the bloc subscribes with
  `emit.forEach`/`emit.onEach`, which cancels on close, or cancels its own
  subscription in `close()`.
- Permission flows are events (`CameraPermissionRequested`) and states
  (`granted`, `denied`, `permanentlyDenied`).

## 4. Clean Architecture

- `data/datasources/battery_platform_datasource.dart` implements the source;
  `data/repositories/battery_repository_impl.dart` maps exceptions to
  `Failure`s (`Either<Failure, int>` or a sealed result).
- `domain/` holds the contract, the entities and the use cases; it never
  imports `package:flutter/services.dart` or `dart:ffi` (ARCH-003).

## 5. Provider, GetX, plain Riverpod

| Pattern | Source lives in | Built where | Lifetime hook |
|---|---|---|---|
| Provider | `data/` service | root `Provider(create: ..., dispose: ...)` | `dispose()` of the service or ChangeNotifier |
| GetX | a `GetxService` | the initial binding (`permanent: true`) | `onClose()` |
| Riverpod | a source class + its provider | a keepAlive provider | `ref.onDispose` |

In plain Riverpod, a keepAlive provider (or notifier) in `core/` or `data/`
that only exposes platform data is a data provider; that's fine. A notifier
under `presentation/` that holds the channel is PLAT-001.

## 6. Apps without layers

A sample or a one-screen app may have no data layer. Keep the channel in a
small wrapper class anyway (the Flutter platform_channels sample's `Counter`
is the model): one constant name, typed methods, errors mapped. It becomes
the data source when the app grows. The checker reports channels in widgets
here as Low, not Medium.
