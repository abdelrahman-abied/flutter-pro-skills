import 'package:flutter/material.dart';

class App extends StatefulWidget {
  const App({super.key});
  @override
  State<App> createState() => _AppState();
}

class _AppState extends State<App> {
  ThemeMode _themeMode = ThemeMode.system;

  bool get _useLightMode => switch (_themeMode) {
        ThemeMode.system => View.of(context).platformDispatcher.platformBrightness == Brightness.light,
        ThemeMode.light => true,
        ThemeMode.dark => false,
      };

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      themeMode: _themeMode,
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.purple), textTheme: const TextTheme()),
      darkTheme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.purple, brightness: Brightness.dark)),
      home: Text('$_useLightMode'),
    );
  }
}
