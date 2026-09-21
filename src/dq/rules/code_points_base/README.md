# Unicode Code Points Rule Introduction

Most written text has similar Unicode attributes across most of its characters.
Corrupted data is more likely to be random and therefore show greater variation
in Unicode attributes. `code_points_base` looks for higher variation within the
string. A more varied string is not necessarily invalid, but it is atypical and
certainly warrants inspection.

## Code-Point Buckets

`code_points_base` groups every character in a string into a bucket. Each bucket
combines the character's Unicode Script, Unicode Block, and Unicode Pseudotype.
A difference in any of those three components creates a different bucket.
A string is reported when it spans too many buckets. The limit is set by
`suspicious_buckets_threshold` in `rule.ini`, currently three buckets.

The CSV `reason` field reports the number and names of the distinct buckets.
The `value` field contains the original stored string. A value spanning many
Scripts or Blocks can therefore have a long reason.

The rule-chain entry point in `processor.py` is `failure_reason(value)`. It
returns one reason string when the threshold is reached and `None` otherwise.
The private `_bucket_examples(value)` helper retains the multiple bucket
examples used to build that single reason; it is not a rule-chain entry point.

| <nobr>Bucket Component</nobr> | Meaning |
| ---------------------------- | ------- |
| <nobr>Unicode Script</nobr> | The writing system associated with the character, such as Latin, Greek, or Cyrillic. |
| <nobr>Unicode Block</nobr> | The named Unicode code-point range containing the character, such as Basic Latin or Latin-1 Supplement. |
| <nobr>Unicode Pseudotype</nobr> | DQ's classification of normal and independently suspicious characters; see **Unicode Pseudotype** below. |

## Unicode Pseudotype

Unicode Pseudotype is a DQ classification, not an official Unicode property.
Suspicious cases receive distinct Pseudotypes; every other character type is
considered `normal`.

| <nobr>Unicode Pseudotype</nobr> | Unicode property or character |
| ------------------------------- | ----------------------------- |
| <nobr>`replacement`</nobr> | `U+FFFD REPLACEMENT CHARACTER` |
| <nobr>`surrogate`</nobr> | General Category `Cs` |
| <nobr>`private_use`</nobr> | General Category `Co` |
| <nobr>`unassigned`</nobr> | General Category `Cn` |
| <nobr>`format`</nobr> | General Category `Cf` |
| <nobr>`control`</nobr> | General Category `Cc`, except tab, carriage return, and newline |
| <nobr>`normal`</nobr> | General Categories `Lu`, `Ll`, `Lt`, `Lm`, `Lo`, `Mn`, `Mc`, `Me`, `Nd`, `Nl`, `No`, `Pc`, `Pd`, `Ps`, `Pe`, `Pi`, `Pf`, `Po`, `Sm`, `Sc`, `Sk`, `So` except `U+FFFD`, `Zs`, `Zl`, and `Zp`; also tab, carriage return, and newline from `Cc` |

For example, ordinary `A` and `a` share `Latin / Basic Latin / normal`. `U+FFFD` maps to
`Common / Specials / replacement`.

The bundled `unicode_data/` directory contains Unicode 15.0 Script and Block
range tables derived from the official Unicode Character Database. The files
include their Unicode source and license notices. DQ uses Python's standard
`unicodedata.category()` for General Category, which does not include the
Unicode Script and Block properties. Other Python libraries support those
properties, but they are not included in the standard Python distribution.
No runtime Unicode package is required. The bucket count is an indicator for
review; it does not prove that text is corrupt.
