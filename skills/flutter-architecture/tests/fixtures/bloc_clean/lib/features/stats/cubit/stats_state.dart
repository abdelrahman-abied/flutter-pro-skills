import 'package:equatable/equatable.dart';

final class StatsState extends Equatable {
  const StatsState({this.total = 0});
  final int total;

  @override
  List<Object> get props => [total];
}
