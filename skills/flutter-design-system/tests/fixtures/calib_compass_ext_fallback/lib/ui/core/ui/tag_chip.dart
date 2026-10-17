import 'package:flutter/material.dart';

class TagChipTheme extends ThemeExtension<TagChipTheme> {
  const TagChipTheme({required this.onChipColor});
  final Color onChipColor;
  @override
  TagChipTheme copyWith({Color? onChipColor}) => TagChipTheme(onChipColor: onChipColor ?? this.onChipColor);
  @override
  TagChipTheme lerp(covariant ThemeExtension<TagChipTheme> other, double t) {
    if (other is! TagChipTheme) return this;
    return TagChipTheme(onChipColor: Color.lerp(onChipColor, other.onChipColor, t) ?? onChipColor);
  }
}

class TagChip extends StatelessWidget {
  const TagChip({super.key});

  @override
  Widget build(BuildContext context) {
    return Icon(
      Icons.tag,
      color: Theme.of(context).extension<TagChipTheme>()?.onChipColor ?? Colors.white,
    );
  }
}
