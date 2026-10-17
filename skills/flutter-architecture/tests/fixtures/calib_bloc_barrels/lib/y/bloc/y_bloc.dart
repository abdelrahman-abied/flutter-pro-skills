// K2 FN-5: bloc -> bloc through a feature barrel is still ARCH-010
import 'package:bloc/bloc.dart';
import '../../x/bloc/bloc.dart';

class YBloc extends Cubit<int> {
  YBloc(this._x) : super(0);
  final XBloc _x;
}
