// rel-ignore-file: REL-006 the flavor ribbon is the point of this widget
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

class BannerView extends StatelessWidget {
  const BannerView({super.key});

  @override
  Widget build(BuildContext context) => Text(appFlavor ?? '');
}
