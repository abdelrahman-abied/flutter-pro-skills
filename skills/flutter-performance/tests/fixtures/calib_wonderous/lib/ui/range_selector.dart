import 'package:flutter/material.dart';

class PanelController extends ValueNotifier<bool> {
  PanelController(super.value);

  void toggle() => value = !value;
}

// FP 2: a ValueNotifier subclass named *Controller changes on taps, not per frame (PERF-009 must not fire).
class RangeSelector extends StatefulWidget {
  const RangeSelector({super.key, required this.panelController});

  final PanelController panelController;

  @override
  State<RangeSelector> createState() => _RangeSelectorState();
}

class _RangeSelectorState extends State<RangeSelector> {
  final ScrollController _list = ScrollController();
  double _offset = 0;

  @override
  void initState() {
    super.initState();
    widget.panelController.addListener(() => setState(() {}));
    // TP 2: a ScrollController listener that rebuilds the State on every offset (PERF-009 still fires).
    _list.addListener(() => setState(() => _offset = _list.offset));
  }

  @override
  void dispose() {
    _list.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      ListView.builder(controller: _list, itemBuilder: (c, i) => Text('$i $_offset ${widget.panelController.value}'));
}
