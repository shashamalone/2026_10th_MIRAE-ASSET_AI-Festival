"""Independent, dependency-free contract checks for the committed TBox files.

The repository uses rdflib at build time, but this audit intentionally depends
only on Python's standard library so it can run before project dependencies are
installed. Its small Turtle statement scanner understands the constructs used
by these five schema files and rejects unbalanced strings, IRIs, brackets, and
parentheses in addition to checking the semantic authoring contract below.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TBOX_FILES = (
    REPO_ROOT / "ontology" / "common.ttl",
    REPO_ROOT / "ontology" / "bond_kr.ttl",
    REPO_ROOT / "ontology" / "etf_kr.ttl",
    REPO_ROOT / "ontology" / "etf_gl.ttl",
    REPO_ROOT / "ontology" / "fund_pub.ttl",
)
PROPERTY_TYPES = ("owl:DatatypeProperty", "owl:ObjectProperty")
SUBJECT_RE = re.compile(r"^\s*(fp:[A-Za-z_][\w.-]*)\s+a\s+([^;]+)", re.DOTALL)
RANK_RE = re.compile(r"\bfp:ratingRank\s+([+-]?\d+)\b")


@dataclass(frozen=True)
class Statement:
    path: Path
    line: int
    text: str

    @property
    def location(self) -> str:
        return f"{self.path.relative_to(REPO_ROOT)}:{self.line}"


def scan_statements(path: Path) -> list[Statement]:
    """Split Turtle at top-level terminators while validating lexical balance."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AssertionError(f"cannot read {path.relative_to(REPO_ROOT)} as UTF-8: {exc}") from exc

    statements: list[Statement] = []
    buffer: list[str] = []
    start_line = 1
    line = 1
    quote: str | None = None
    escaped = False
    in_iri = False
    in_comment = False
    bracket_depth = 0
    paren_depth = 0

    for index, char in enumerate(source):
        if in_comment:
            if char == "\n":
                in_comment = False
                buffer.append(char)
                line += 1
            continue

        if quote is not None:
            buffer.append(char)
            if char == "\n":
                line += 1
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if in_iri:
            buffer.append(char)
            if char == ">":
                in_iri = False
            elif char == "\n":
                line += 1
            continue

        if char == "#":
            in_comment = True
            continue
        if char in {'"', "'"}:
            quote = char
            buffer.append(char)
            continue
        if char == "<":
            in_iri = True
            buffer.append(char)
            continue
        if char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        if bracket_depth < 0 or paren_depth < 0:
            raise AssertionError(
                f"unbalanced Turtle delimiter in {path.relative_to(REPO_ROOT)}:{line}"
            )

        buffer.append(char)
        if char == "\n":
            line += 1
        if char != "." or bracket_depth or paren_depth:
            continue

        next_char = source[index + 1] if index + 1 < len(source) else ""
        if next_char and not next_char.isspace() and next_char != "#":
            continue
        text = "".join(buffer).strip()
        if text:
            statements.append(Statement(path=path, line=start_line, text=text))
        buffer.clear()
        start_line = line

    if quote is not None or in_iri or bracket_depth or paren_depth:
        raise AssertionError(f"unterminated Turtle construct in {path.relative_to(REPO_ROOT)}")
    remainder = "".join(buffer).strip()
    if remainder:
        raise AssertionError(
            f"unterminated Turtle statement in {path.relative_to(REPO_ROOT)}:{start_line}"
        )
    return statements


def predicate_value(statement: str, predicate: str) -> str | None:
    """Extract a predicate value through its next top-level semicolon or period."""
    match = re.search(rf"\b{re.escape(predicate)}\b", statement)
    if not match:
        return None

    value: list[str] = []
    quote: str | None = None
    escaped = False
    in_iri = False
    bracket_depth = 0
    paren_depth = 0
    for char in statement[match.end() :]:
        if quote is not None:
            value.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if in_iri:
            value.append(char)
            if char == ">":
                in_iri = False
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "<":
            in_iri = True
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char in ";." and bracket_depth == 0 and paren_depth == 0:
            break
        value.append(char)
    return "".join(value).strip()


def property_definitions(statements: list[Statement]) -> dict[str, Statement]:
    properties: dict[str, Statement] = {}
    for statement in statements:
        match = SUBJECT_RE.match(statement.text)
        if match and any(kind in match.group(2) for kind in PROPERTY_TYPES):
            properties[match.group(1)] = statement
    return properties


def check_prefixes(path: Path, statements: list[Statement], errors: list[str]) -> None:
    text = "\n".join(statement.text for statement in statements)
    for prefix in ("fp", "rdfs", "owl", "xsd"):
        if not re.search(rf"@prefix\s+{prefix}:\s*<[^>]+>\s*\.", text):
            errors.append(f"{path.relative_to(REPO_ROOT)} is missing @{prefix} prefix")


def check_with_rdflib(errors: list[str]) -> bool:
    """Run a full Turtle parse when the project's optional dependency exists."""
    try:
        from rdflib import Graph
    except ModuleNotFoundError:
        return False

    for path in TBOX_FILES:
        try:
            Graph().parse(path, format="turtle")
        except Exception as exc:
            errors.append(f"{path.relative_to(REPO_ROOT)} is invalid Turtle: {exc}")
    return True


def check_property_contracts(
    properties: dict[str, Statement], errors: list[str]
) -> tuple[int, int]:
    datatype_count = 0
    object_count = 0
    for name, statement in sorted(properties.items()):
        match = SUBJECT_RE.match(statement.text)
        if match is None:
            continue
        type_clause = match.group(2)
        is_datatype = "owl:DatatypeProperty" in type_clause
        datatype_count += int(is_datatype)
        object_count += int("owl:ObjectProperty" in type_clause)
        for predicate in ("rdfs:domain", "rdfs:range", "rdfs:label"):
            if predicate_value(statement.text, predicate) is None:
                errors.append(f"{statement.location} {name} is missing {predicate}")
        if is_datatype:
            for predicate in ("fp:sourceTable", "fp:sourceColumn"):
                if predicate_value(statement.text, predicate) is None:
                    errors.append(f"{statement.location} {name} is missing {predicate}")
    return datatype_count, object_count


def check_issued_by(properties: dict[str, Statement], errors: list[str]) -> None:
    statement = properties.get("fp:issuedBy")
    domain = predicate_value(statement.text, "rdfs:domain") if statement else None
    if domain != "fp:Bond":
        errors.append(f"fp:issuedBy domain must be exactly fp:Bond; found {domain or '<none>'}")


def check_rating_taxonomy(statements: list[Statement], errors: list[str]) -> None:
    all_text = "\n".join(statement.text for statement in statements)
    if re.search(r"\bfp:Rating_AAAA\b", all_text):
        errors.append("fp:Rating_AAAA must not exist or be referenced")

    ranks: dict[int, list[str]] = {}
    for statement in statements:
        match = SUBJECT_RE.match(statement.text)
        if not match or "fp:CreditRating" not in match.group(2):
            continue
        rank_match = RANK_RE.search(statement.text)
        if not rank_match:
            errors.append(f"{statement.location} {match.group(1)} is missing fp:ratingRank")
            continue
        rank = int(rank_match.group(1))
        ranks.setdefault(rank, []).append(match.group(1))

    expected = set(range(1, 20))
    actual = set(ranks)
    if actual != expected:
        errors.append(
            "credit-rating ranks must be exactly 1..19; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    for rank, names in sorted(ranks.items()):
        if len(names) != 1:
            errors.append(f"rating rank {rank} must identify one rating; found {names}")


def check_holding_domain(properties: dict[str, Statement], errors: list[str]) -> None:
    statement = properties.get("fp:hasHolding")
    domain = predicate_value(statement.text, "rdfs:domain") if statement else None
    if domain is None:
        errors.append("fp:hasHolding is missing rdfs:domain")
        return
    forbidden = ("fp:ETN", "fp:KoreanETN", "fp:GlobalETN")
    present = [name for name in forbidden if re.search(rf"\b{re.escape(name)}\b", domain)]
    if present:
        errors.append(f"fp:hasHolding domain includes forbidden ETN classes: {present}")


def main() -> int:
    try:
        by_file = {path: scan_statements(path) for path in TBOX_FILES}
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    used_rdflib = check_with_rdflib(errors)
    for path, statements in by_file.items():
        check_prefixes(path, statements, errors)
    statements = [statement for values in by_file.values() for statement in values]
    properties = property_definitions(statements)
    datatype_count, object_count = check_property_contracts(properties, errors)
    check_issued_by(properties, errors)
    check_rating_taxonomy(statements, errors)
    check_holding_domain(properties, errors)

    if errors:
        print(f"FAIL: {len(errors)} TBox contract violation(s)", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"PASS: 5 TBox files ({'rdflib + lexical' if used_rdflib else 'lexical'} validation); "
        f"{datatype_count} datatype properties; {object_count} object properties"
    )
    print("PASS: all properties have domain, range, and label")
    print("PASS: every datatype property has sourceTable and sourceColumn")
    print("PASS: issuedBy domain, rating taxonomy, and hasHolding domain are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
