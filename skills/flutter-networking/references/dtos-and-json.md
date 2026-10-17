# DTOs and JSON: validate at the boundary

Server data is input. Parse it into DTOs in the data layer, validate it there,
and map it to domain entities in the repository. A payload that doesn't match
becomes a typed failure, not a `TypeError` thrown from deep inside a widget
build.

## Contents

1. DTO, entity, mapper
2. Code generation (json_serializable, freezed)
3. Hand-written fromJson with validation
4. Errors from parsing
5. Large payloads
6. Sending data

## 1. DTO, entity, mapper

- **DTO** (`ProductDto`, `BookingApiModel`): mirrors the wire format, lives in
  `data/models/` (or the API package), has `fromJson`/`toJson`.
- **Entity / domain model** (`Product`): what the app means, no JSON, no
  nullable fields "because the API might omit them".
- **Mapper:** an extension (`extension on ProductDto { Product toEntity() }`)
  or a method in the repository. The repository is the only caller.

The domain never imports a DTO (ARCH-003/006), and repositories don't return
them (ARCH-107). Small apps may use one model for both when the wire format
*is* the domain (the bloc examples do this inside their API packages); split
them the day the API and the screen disagree.

## 2. Code generation (json_serializable, freezed)

PREFER codegen once you have more than a handful of models: it's consistent,
and its errors name the key that failed.

```dart
@JsonSerializable(checked: true, fieldRename: FieldRename.snake)
class ProductDto {
  ProductDto({required this.id, required this.title, this.priceCents});

  @JsonKey(required: true, disallowNullValue: true)
  final String id;
  @JsonKey(required: true)
  final String title;
  final int? priceCents;

  factory ProductDto.fromJson(Map<String, dynamic> json) => _$ProductDtoFromJson(json);
  Map<String, dynamic> toJson() => _$ProductDtoToJson(this);
}
```

- `checked: true` wraps failures in `CheckedFromJsonException` with the key
  and the bad value; `required: true` rejects missing keys.
- Enums: `@JsonEnum` plus `unknownEnumValue:` so a new server value doesn't
  crash old app versions.
- freezed adds immutability, `copyWith` and unions; its `fromJson` uses
  json_serializable underneath. Keep freezed DTOs in `data/`.
- Run `dart run build_runner build --delete-conflicting-outputs` (or
  `watch`); the generated `*.g.dart`/`*.freezed.dart` files are skipped by the
  suite's checkers.

## 3. Hand-written fromJson with validation

Fine for a few models. Use Dart 3 patterns so a shape mismatch is an explicit
`FormatException` instead of an `as` cast failing somewhere:

```dart
factory ProductDto.fromJson(Object? json) => switch (json) {
      {'id': String id, 'title': String title, 'price_cents': int? price} =>
        ProductDto(id: id, title: title, priceCents: price),
      _ => throw FormatException('Unexpected product payload', json),
    };
```

AVOID chains of hard casts on nested data:

```dart
// Fragile: any missing or null "seller" throws a TypeError, not a FormatException
final name = (json['seller'] as Map<String, dynamic>)['name'] as String;
```

That is the reading-level finding NET-unvalidated-json. The canonical bloc
examples cast (`map['id'] as int`) and catch broadly in the bloc; that's a
tutorial simplification, acceptable while the cast failure is caught and
mapped, not a pattern to grow.

## 4. Errors from parsing

Parsing errors are data errors. In the repository, catch
`FormatException`, `CheckedFromJsonException` and `TypeError` from
`fromJson`, and map them to a typed failure (`ParseFailure`,
`ServerFailure.badPayload`). Never retry them: the same payload fails again.
How failures flow to the UI per pattern is in `flutter-error-handling`
(load that skill; fallback `../flutter-error-handling/SKILL.md`).

## 5. Large payloads

Decoding a big JSON body on the UI isolate janks frames. Dio's default
transformer already decodes large responses off the main isolate on recent
versions; for package:http use `compute(jsonDecode, body)` or
`Isolate.run`. The detection and thresholds are `flutter-performance`'s
(PERF-011); don't re-report them here.

## 6. Sending data

- Serialize with the DTO's `toJson()`; never build JSON strings by hand.
- Query parameters through `queryParameters` (`Uri.https(host, path, {...})`,
  `uri.replace(queryParameters: …)`, Dio `queryParameters:`), so every value
  is encoded (NET-010).
- Path segments from user input: `Uri(pathSegments: [...])` or
  `Uri.encodeComponent`.
- Validate input before sending (forms in `flutter-forms`); the server
  validates again. Never send secrets or personal data in query strings
  (`flutter-secure-defaults`, NAV-006 for URLs the app opens).
