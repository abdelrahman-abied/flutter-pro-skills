import 'dart:io';

import 'package:bloc/bloc.dart';
import 'package:bloc_test/bloc_test.dart';
import 'package:dio/dio.dart';
import 'package:fake_async/fake_async.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../helpers/fakes.dart';

class CounterCubit extends Cubit<int> {
  CounterCubit() : super(0);
  void increment() => emit(state + 1);
}

void _expectSum(int a, int b, int sum) => expect(a + b, sum);

void main() {
  // ---- TEST-no-assertion (3) ----
  test('computes but never checks', () {
    final x = 1 + 1;
    debugPrint('$x');
  });

  test('assertion only inside a string', () {
    debugPrint('expect(1, 1)');
  });

  test('assertion commented out', () {
    final x = 2;
    // expect(x, 2);
    debugPrint('$x');
  });

  // ---- assertions found through helpers: not smells ----
  test('shared helper that fails on timeout', () async {
    var done = false;
    Future<void>.microtask(() => done = true);
    await settles(() => done);
  });

  test('local expect helper', () {
    _expectSum(1, 2, 3);
  });

  blocTest<CounterCubit, int>(
    'bloc_test expect: counts as an assertion, skip: 1 is a state count',
    build: CounterCubit.new,
    act: (c) => c
      ..increment()
      ..increment(),
    skip: 1,
    expect: () => [2],
  );

  // ---- TEST-real-delay (3) ----
  test('blocks the isolate', () {
    sleep(const Duration(milliseconds: 10));
    expect(true, isTrue);
  });

  test('waits on the wall clock', () async {
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(true, isTrue);
  });

  testWidgets('real time inside runAsync', (tester) async {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
    expect(find.byType(Text), findsNothing);
  });

  // ---- not real delays ----
  test('zero delay flushes the event queue', () async {
    await Future<void>.delayed(Duration.zero);
    expect(true, isTrue);
  });

  test('fakeAsync controls the clock', () {
    fakeAsync((async) {
      var fired = false;
      Future<void>.delayed(const Duration(seconds: 5), () => fired = true);
      async.elapse(const Duration(seconds: 5));
      expect(fired, isTrue);
    });
  });

  testWidgets('testWidgets runs on a fake clock', (tester) async {
    await tester.pumpWidget(const Text('hi', textDirection: TextDirection.ltr));
    Future<void>.delayed(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('hi'), findsOneWidget);
  });

  // ---- TEST-real-network (2) ----
  test('talks to the real server', () async {
    final dio = Dio();
    expect(dio.options.baseUrl, isEmpty);
  });

  test('real http client', () {
    final client = http.Client();
    addTearDown(client.close);
    expect(client, isNotNull);
  });

  // ---- TEST-skip-no-reason (1) ----
  test('skipped with no reason', () {
    expect(1, 1);
  }, skip: true);

  test('skipped with a reason', () {
    expect(1, 1);
  }, skip: 'flaky on CI until #123 lands');

  // ---- TEST-preview-only (1) ----
  testWidgets('preview of the empty state', (tester) async {
    await tester.pumpWidget(const RepaintBoundary(child: Text('Empty', textDirection: TextDirection.ltr)));
    await savePng(tester, 'empty_state');
  });
}
