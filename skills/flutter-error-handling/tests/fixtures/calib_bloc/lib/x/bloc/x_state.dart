enum XStatus { initial, loading, success, failure }

class XState {
  const XState({this.status = XStatus.initial, this.v = 0, this.msg = ''});
  final XStatus status;
  final int v;
  final String msg;

  XState copyWith({XStatus Function()? status}) => XState(status: status != null ? status() : this.status);
}
