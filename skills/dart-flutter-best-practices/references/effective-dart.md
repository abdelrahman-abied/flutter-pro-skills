# Effective Dart — complete guideline checklist

Generated from the source of https://dart.dev/effective-dart (dart-lang/site-www,
`src/content/effective-dart/*.md`), 149 guidelines. Every heading is verbatim.

**Enforced by** column:
- `lint_name` (set) — the analyzer rule that checks it, and where it's on by default:
  `core` / `recommended` (package:lints), `flutter` (package:flutter_lints, which
  includes recommended), or `opt-in` (must be enabled in `analysis_options.yaml`;
  `assets/analysis_options.yaml` enables the useful ones).
- **judgment** — no lint; you have to read the code. 76 of 149 guidelines.
  These are where an agent adds value over `dart analyze`, so check them deliberately.

Strength: **DO/DON'T** ≈ always · **PREFER/AVOID** = unless good reason ·
**CONSIDER** = context-dependent. Report findings at the strength of the rule.

Overarching themes: **be consistent** (code that looks different should *be*
different) and **be brief** (economical, not dense).

## Contents

- Style
  - Identifiers
  - Ordering
  - Formatting
- Documentation
  - Comments
  - Doc comments
  - Markdown
  - Writing
- Usage
  - Libraries
  - Null
  - Strings
  - Collections
  - Functions
  - Variables
  - Members
  - Constructors
  - Error handling
  - Asynchrony
- Design
  - Names
  - Libraries
  - Classes and mixins
  - Constructors
  - Members
  - Types
  - Parameters
  - Equality

Grep for a keyword (`late`, `FutureOr`, `catch`, `getter`) instead of reading every row.

## Style


### Identifiers

| Guideline | Enforced by | Note |
|---|---|---|
| DO name types using `UpperCamelCase` | `camel_case_types` (core) |  |
| DO name extensions using `UpperCamelCase` | `camel_case_extensions` (core) |  |
| DO name packages, directories, and source files using `lowercase_with_underscores` | `file_names` (core), `package_names` (recommended) |  |
| DO name import prefixes using `lowercase_with_underscores` | `library_prefixes` (recommended) |  |
| DO name other identifiers using `lowerCamelCase` | `non_constant_identifier_names` (core) |  |
| PREFER using `lowerCamelCase` for constant names | `constant_identifier_names` (recommended) |  |
| DO capitalize acronyms and abbreviations longer than two letters like words | **judgment** |  |
| PREFER using wildcards for unused callback parameters | `unnecessary_underscores` (recommended) |  |
| DON'T use a leading underscore for identifiers that aren't private | `no_leading_underscores_for_local_identifiers` (recommended) |  |
| DON'T use prefix letters | **judgment** |  |
| DON'T explicitly name libraries | `unnecessary_library_name` (recommended) | `library;` or nothing. |

### Ordering

| Guideline | Enforced by | Note |
|---|---|---|
| DO place `dart:` imports before other imports | `directives_ordering` (opt-in) |  |
| DO place `package:` imports before relative imports | `directives_ordering` (opt-in) |  |
| DO specify exports in a separate section after all imports | `directives_ordering` (opt-in) |  |
| DO sort sections alphabetically | `directives_ordering` (opt-in) |  |

### Formatting

| Guideline | Enforced by | Note |
|---|---|---|
| DO format your code using `dart format` | **judgment** |  |
| CONSIDER changing your code to make it more formatter-friendly | **judgment** | Long expressions/nested closures the formatter can't lay out well are a signal to extract a variable or function. |
| PREFER lines 80 characters or fewer | `lines_longer_than_80_chars` (opt-in) |  |
| DO use curly braces for all flow control statements | `curly_braces_in_flow_control_structures` (core) |  |

## Documentation


### Comments

| Guideline | Enforced by | Note |
|---|---|---|
| DO format comments like sentences | **judgment** | Capitalised, ends with a period (unless it's an identifier or a fragment like `// TODO`). |
| DON'T use block comments for documentation | **judgment** | Use `//` / `///`; `/* */` only to comment out code temporarily. |

### Doc comments

| Guideline | Enforced by | Note |
|---|---|---|
| DO use `///` doc comments to document members and types | `slash_for_doc_comments` (recommended) |  |
| PREFER writing doc comments for public APIs | `public_member_api_docs` (opt-in) |  |
| CONSIDER writing a library-level doc comment | **judgment** | `///` before `library;` at the top of the library entry file. |
| CONSIDER writing doc comments for private APIs | **judgment** |  |
| DO start doc comments with a single-sentence summary | **judgment** | First sentence is the summary dartdoc shows in lists; make it stand alone. |
| DO separate the first sentence of a doc comment into its own paragraph | **judgment** | Blank `///` line after the summary. |
| AVOID redundancy with the surrounding context | **judgment** | Don't restate the class name, param types, or what the signature already says. |
| PREFER starting comments of a function or method with third-person verbs if its main purpose is a side effect | **judgment** | `/// Connects to the server…`, `/// Starts the stopwatch…` |
| PREFER starting a non-boolean variable or property comment with a noun phrase | **judgment** | `/// The current day of the week…` |
| PREFER starting a boolean variable or property comment with "Whether" followed by a noun or gerund phrase | **judgment** | `/// Whether the modal is currently displayed…` (not "Returns true if"). |
| PREFER a noun phrase or non-imperative verb phrase for a function or method if returning a value is its primary purpose | **judgment** | Docs: `/// The [index]th element…` / `/// Returns the…` is also accepted. |
| DON'T write documentation for both the getter and setter of a property | **judgment** | Doc the getter only; dartdoc merges them. |
| PREFER starting library or type comments with noun phrases | **judgment** | `/// A chunk of non-breaking output text…` |
| CONSIDER including code samples in doc comments | **judgment** | Fenced ```dart``` blocks. |
| DO use square brackets in doc comments to refer to in-scope identifiers | `comment_references` (opt-in) |  |
| DO use prose to explain parameters, return values, and exceptions | **judgment** | No `@param`/`@returns` Javadoc tags; weave `[param]` references into sentences. |
| DO put doc comments before metadata annotations | **judgment** | `/// Doc` then `@override`/`@Deprecated`, not the reverse. |

### Markdown

| Guideline | Enforced by | Note |
|---|---|---|
| AVOID using markdown excessively | **judgment** |  |
| AVOID using HTML for formatting | `unintended_html_in_doc_comment` (core) | `unintended_html_in_doc_comment` (core) catches accidental `<T>` in prose — wrap in backticks. |
| PREFER backtick fences for code blocks | **judgment** | Not 4-space indented blocks. |

### Writing

| Guideline | Enforced by | Note |
|---|---|---|
| PREFER brevity | **judgment** |  |
| AVOID abbreviations and acronyms unless they are obvious | **judgment** |  |
| PREFER using "this" instead of "the" to refer to a member's instance | **judgment** | `/// True if this box has no contents.` |

## Usage


### Libraries

| Guideline | Enforced by | Note |
|---|---|---|
| DO use strings in `part of` directives | `use_string_in_part_of_directives` (core) |  |
| DON'T import libraries that are inside the `src` directory of another package | `implementation_imports` (recommended) |  |
| DON'T allow an import path to reach into or out of `lib` | `avoid_relative_lib_imports` (core) |  |
| PREFER relative import paths | `prefer_relative_imports` (opt-in) |  |

### Null

| Guideline | Enforced by | Note |
|---|---|---|
| DON'T explicitly initialize variables to `null` | `avoid_init_to_null` (recommended) |  |
| DON'T use an explicit default value of `null` | `avoid_init_to_null` (recommended) |  |
| DON'T use `true` or `false` in equality operations | **judgment** | `if (nonNullable)` not `== true`. For nullable bools `== true` / `?? false` is fine. |
| AVOID `late` variables if you need to check whether they are initialized | **judgment** | There's no way to ask a `late` field whether it's set; use a nullable field instead. |
| CONSIDER type promotion or null-check patterns for using nullable types | **judgment** | Copy a nullable field to a local (`final user = _user; if (user != null)…`) or use `if (_user case final user?)`. Avoid scattering `!`. |

### Strings

| Guideline | Enforced by | Note |
|---|---|---|
| DO use adjacent strings to concatenate string literals | `prefer_adjacent_string_concatenation` (recommended) |  |
| PREFER using interpolation to compose strings and values | `prefer_interpolation_to_compose_strings` (recommended) |  |
| AVOID using curly braces in interpolation when not needed | `unnecessary_brace_in_string_interps` (recommended) |  |

### Collections

| Guideline | Enforced by | Note |
|---|---|---|
| DO use collection literals when possible | `prefer_collection_literals` (recommended) |  |
| DON'T use `.length` to see if a collection is empty | `prefer_is_empty` (core), `prefer_is_not_empty` (core) |  |
| AVOID using `Iterable.forEach()` with a function literal | `avoid_function_literals_in_foreach_calls` (recommended) |  |
| DON'T use `List.from()` unless you intend to change the type of the result | **judgment** | Use `.toList()` / `[...x]`; `List<int>.from(numbers)` only to downcast. |
| DO use `whereType()` to filter a collection by type | `prefer_iterable_whereType` (core) |  |
| DON'T use `cast()` when a nearby operation will do | **judgment** | e.g. `List<int>.from(x)` / `map<int>()` / `whereType<int>()`. |
| AVOID using `cast()` | **judgment** | Create the collection with the right type, or cast each element on access. |

### Functions

| Guideline | Enforced by | Note |
|---|---|---|
| DO use a function declaration to bind a function to a name | `prefer_function_declarations_over_variables` (recommended) |  |
| DON'T create a lambda when a tear-off will do | `unnecessary_lambdas` (opt-in) |  |

### Variables

| Guideline | Enforced by | Note |
|---|---|---|
| DO follow a consistent rule for `var` and `final` on local variables | `prefer_final_locals` (opt-in) | Either `final` for non-reassigned + `var` for reassigned, or `var` everywhere. Match the project. (`prefer_final_locals` enforces the first.) |
| AVOID storing what you can calculate | **judgment** | Compute in a getter instead of a field you must keep in sync (cache only when measured). |

### Members

| Guideline | Enforced by | Note |
|---|---|---|
| DON'T wrap a field in a getter and setter unnecessarily | `unnecessary_getters_setters` (recommended) |  |
| PREFER using a `final` field to make a read-only property | **judgment** | `final` public field, not private field + getter. |
| CONSIDER using `=>` for simple members | `prefer_expression_function_bodies` (opt-in) |  |
| DON'T use `this.` except to redirect to a named constructor or to avoid shadowing | `unnecessary_this` (recommended) |  |
| DO initialize fields at their declaration when possible | **judgment** | When the value doesn't depend on constructor params. |

### Constructors

| Guideline | Enforced by | Note |
|---|---|---|
| DO use initializing formals when possible | `prefer_initializing_formals` (recommended) |  |
| DON'T use `late` when a constructor initializer list will do | **judgment** |  |
| DO use `;` instead of `{}` for empty constructor bodies | `empty_constructor_bodies` (recommended) |  |
| PREFER using concise constructor syntax | `unnecessary_type_name_in_constructor` (opt-in) |  |
| DON'T use `new` | `unnecessary_new` (recommended) |  |
| DON'T use `const` redundantly | `unnecessary_const` (recommended) |  |

### Error handling

| Guideline | Enforced by | Note |
|---|---|---|
| AVOID catches without `on` clauses | `avoid_catches_without_on_clauses` (opt-in) |  |
| DON'T discard errors from catches without `on` clauses | **judgment** | If you catch everything, log/report/rethrow — never silently drop. |
| DO throw objects that implement `Error` only for programmatic errors | `only_throw_errors` (opt-in) | `ArgumentError`, `StateError` = caller bug. Runtime/IO failures → `Exception` (`only_throw_errors` stops throwing strings). |
| DON'T explicitly catch `Error` or types that implement it | `avoid_catching_errors` (opt-in) |  |
| DO use `rethrow` to rethrow a caught exception | `use_rethrow_when_possible` (recommended) |  |

### Asynchrony

| Guideline | Enforced by | Note |
|---|---|---|
| PREFER async/await over using raw futures | **judgment** | Linear code; `try/catch` works; easier to read. |
| DON'T use `async` when it has no useful effect | **judgment** | A function that just returns another future doesn't need `async`. Keep it when you `await`, need errors as futures, or return `Future<void>` from sync work. |
| CONSIDER using higher-order methods to transform a stream | **judgment** | `map`, `where`, `asyncMap`, `expand` before reaching for a StreamController. |
| AVOID using Completer directly | **judgment** | Only to wrap callback-based APIs; otherwise `async`/`then`. |
| DO test for `Future<T>` when disambiguating a `FutureOr<T>` whose type argument could be `Object` | **judgment** | `if (value is Future<T>)` first, else `T` — testing `is T` first is wrong when T is Object. |

## Design


### Names

| Guideline | Enforced by | Note |
|---|---|---|
| DO use terms consistently | **judgment** | See naming.md §3. |
| AVOID abbreviations | **judgment** | See naming.md §3. |
| PREFER putting the most descriptive noun last | **judgment** | `pageCount` not `numPages`. |
| CONSIDER making the code read like a sentence | **judgment** |  |
| PREFER a noun phrase for a non-boolean property or variable | **judgment** |  |
| PREFER a non-imperative verb phrase for a boolean property or variable | **judgment** | `isEnabled`, `hasElements`, `canClose`. |
| CONSIDER omitting the verb for a named boolean *parameter* | **judgment** | `growable: true`, `enabled: false`. |
| PREFER the "positive" name for a boolean property or variable | **judgment** | `isConnected` over `isDisconnected`. |
| PREFER an imperative verb phrase for a function or method whose main purpose is a side effect | **judgment** |  |
| PREFER a noun phrase or non-imperative verb phrase for a function or method if returning a value is its primary purpose | **judgment** | Docs: `/// The [index]th element…` / `/// Returns the…` is also accepted. |
| CONSIDER an imperative verb phrase for a function or method if you want to draw attention to the work it performs | **judgment** | `fetchUser()`, `downloadData()`. |
| AVOID starting a function or method name with `get` | **judgment** | Getter if cheap; otherwise name the work (`fetch`, `calculate`, `load`). |
| PREFER naming a method `to___()` if it copies the object's state to a new object | `use_to_and_as_if_applicable` (opt-in) |  |
| PREFER naming a method `as___()` if it returns a different representation backed by the original object | `use_to_and_as_if_applicable` (opt-in) |  |
| AVOID describing the parameters in the function's or method's name | **judgment** | `list.add(element)` not `addElement`. |
| DO follow existing mnemonic conventions when naming type parameters | **judgment** | `E`, `K`/`V`, `R`, `T`/`S`/`U`. |

### Libraries

| Guideline | Enforced by | Note |
|---|---|---|
| PREFER making declarations private | **judgment** | Public = maintained forever; start private, widen when needed. |
| CONSIDER declaring multiple classes in the same library | **judgment** | Dart privacy is per-library; small cooperating classes may share a file. |

### Classes and mixins

| Guideline | Enforced by | Note |
|---|---|---|
| AVOID defining a one-member abstract class when a simple function will do | `one_member_abstracts` (opt-in, deprecated) |  |
| AVOID defining a class that contains only static members | `avoid_classes_with_only_static_members` (opt-in) |  |
| AVOID extending a class that isn't intended to be subclassed | **judgment** |  |
| DO use class modifiers to control if your class can be extended | **judgment** | `final`, `base`, `interface`, `sealed`; document intent. |
| AVOID implementing a class that isn't intended to be an interface | **judgment** |  |
| DO use class modifiers to control if your class can be an interface | **judgment** |  |
| PREFER defining a pure `mixin` or pure `class` to a `mixin class` | `prefer_mixin` (opt-in) |  |

### Constructors

| Guideline | Enforced by | Note |
|---|---|---|
| CONSIDER making your constructor `const` if the class supports it | **judgment** | All fields final + no body logic. Note: making it const is a public promise you can't easily take back. |

### Members

| Guideline | Enforced by | Note |
|---|---|---|
| PREFER making fields and top-level variables `final` | `prefer_final_fields` (recommended) |  |
| DO use getters for operations that conceptually access properties | **judgment** | No args, returns result, no visible side effects, idempotent, fast. |
| DO use setters for operations that conceptually change properties | `use_setters_to_change_properties` (opt-in) |  |
| DON'T define a setter without a corresponding getter | `avoid_setters_without_getters` (opt-in) |  |
| AVOID using runtime type tests to fake overloading | **judgment** | Separate named methods instead of `if (x is A) … else if (x is B)`. (Exhaustive `switch` on a `sealed` type is fine.) |
| AVOID public `late final` fields without initializers | **judgment** | They expose an implicit setter that throws on second write. |
| AVOID returning nullable `Future`, `Stream`, and collection types | **judgment** | Return empty collection / completed future instead of `null`. |
| AVOID returning `this` from methods just to enable a fluent interface | `avoid_returning_this` (opt-in) | Dart has cascades `..`. |

### Types

| Guideline | Enforced by | Note |
|---|---|---|
| DO type annotate variables without initializers | `prefer_typing_uninitialized_variables` (core) |  |
| DO type annotate fields and top-level variables if the type isn't obvious | `type_annotate_public_apis` (opt-in) |  |
| DON'T redundantly type annotate initialized local variables | `omit_local_variable_types` (opt-in) |  |
| DO annotate return types on function declarations | `always_declare_return_types` (opt-in) | (`always_declare_return_types`) |
| DO annotate parameter types on function declarations | **judgment** |  |
| DON'T annotate inferred parameter types on function expressions | `avoid_types_on_closure_parameters` (opt-in) |  |
| DON'T type annotate initializing formals | `type_init_formals` (recommended) |  |
| DO write type arguments on generic invocations that aren't inferred | **judgment** | `<int>[]`, `Future<String>.value(...)` when context doesn't infer. |
| DON'T write type arguments on generic invocations that are inferred | **judgment** |  |
| AVOID writing incomplete generic types | **judgment** | `List<num>` not raw `List` (→ `List<dynamic>`). |
| DO annotate with `dynamic` instead of letting inference fail | `strict_top_level_inference` (core) | Make the intent explicit; `strict_top_level_inference` (core) catches top-level cases. |
| PREFER signatures in function type annotations | **judgment** | `bool Function(Item)` not bare `Function`. |
| DON'T specify a return type for a setter | `avoid_return_types_on_setters` (recommended) |  |
| DON'T use the legacy typedef syntax | `prefer_generic_function_type_aliases` (core) |  |
| PREFER inline function types over typedefs | `avoid_private_typedef_functions` (opt-in, deprecated) |  |
| PREFER using function type syntax for parameters | `use_function_type_syntax_for_parameters` (recommended) |  |
| AVOID using `dynamic` unless you want to disable static checking | `avoid_dynamic_calls` (opt-in) | Use `Object?` for 'any value'. (`avoid_dynamic_calls` catches calls through dynamic.) |
| DO use `Future<void>` as the return type of asynchronous members that do not produce values | `avoid_void_async` (opt-in) | Not `void` (`avoid_void_async`) and not `Future` raw. |
| AVOID using `FutureOr<T>` as a return type | **judgment** | Return `Future<T>` — callers then always `await`. `FutureOr` is for parameters. |

### Parameters

| Guideline | Enforced by | Note |
|---|---|---|
| AVOID positional boolean parameters | `avoid_positional_boolean_parameters` (opt-in) |  |
| AVOID optional positional parameters if the user may want to omit earlier parameters | **judgment** | Use named params. |
| AVOID mandatory parameters that accept a special "no argument" value | **judgment** | Make it optional / nullable named instead of passing `-1` or `null` to mean 'none'. |
| DO use inclusive start and exclusive end parameters to accept a range | **judgment** | Like `substring(start, end)`. |

### Equality

| Guideline | Enforced by | Note |
|---|---|---|
| DO override `hashCode` if you override `==` | `hash_and_equals` (core) |  |
| DO make your `==` operator obey the mathematical rules of equality | **judgment** | Reflexive, symmetric, transitive, consistent; and `hashCode` agrees. |
| AVOID defining custom equality for mutable classes | `avoid_equals_and_hash_code_on_mutable_classes` (opt-in) |  |
| DON'T make the parameter to `==` nullable | `avoid_null_checks_in_equality_operators` (opt-in, deprecated) |  |
