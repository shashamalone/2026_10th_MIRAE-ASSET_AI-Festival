# T-102 Ontology schema audit

## Result

The five committed TBox files satisfy the task contract at base commit
`7105519383833db80e6c6f163c240b4394414d19`. No ontology source change was
needed.

The audit found 94 datatype properties and 45 object properties. Every one has
`rdfs:domain`, `rdfs:range`, and `rdfs:label`; every datatype property also has
`fp:sourceTable` and `fp:sourceColumn`.

The safety-specific checks also pass:

- `fp:issuedBy` has exactly `fp:Bond` as its domain.
- Credit-rating instances map one-to-one onto ranks 1 through 19.
- `fp:Rating_AAAA` is neither declared nor referenced.
- `fp:hasHolding` excludes `fp:ETN`, `fp:KoreanETN`, and `fp:GlobalETN` from its
  domain.

## Reproduction

Run from the repository root:

```text
python audit/T-102-ontology/verify_tbox.py
```

`verify_tbox.py` has a Python-standard-library fallback. It always validates
UTF-8 readability and the balanced Turtle constructs used by this repository;
when the project's `rdflib` dependency is installed, it also performs a full
Turtle parse. The contract audit therefore works before dependencies are
installed without weakening the normal project environment. It deliberately
reads only the five TBox files; generated `instances_*.ttl` files and
graph-builder code are outside this task.
