#!/usr/bin/env python3
"""Reproducible source-to-source similarity audit for MoonJMAP.

This utility deliberately does not claim to discover a contest roster.  The
caller supplies a manifest (or ``--candidate`` paths) containing the projects
that are in scope.  It then records a content-addressed snapshot of each
source tree and compares it with MoonJMAP using several independent signals:

* exact and shape-normalised token winnowing fingerprints;
* canonical source-line overlap;
* public/declaration signature overlap; and
* licence, repository and generated-source provenance indicators.

The output is evidence for review, not a plagiarism/ originality verdict.
It uses only the Python standard library, so a report can be reproduced in a
minimal environment.  ZIP inputs are read with traversal checks and are never
executed.
"""

from __future__ import annotations

import argparse
import ast
import collections
import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import zipfile
from typing import Iterable, Iterator, Sequence


CODE_EXTENSIONS = {
    ".mbt", ".mbti", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".rs", ".go", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".java",
    ".kt", ".kts", ".swift", ".scala", ".rb", ".php", ".lua", ".zig",
    ".sh", ".bash", ".ps1", ".sql", ".wat", ".json", ".toml", ".yaml",
    ".yml", ".xml", ".html", ".css", ".scss", ".vue", ".svelte",
}
TEXT_EXTENSIONS = CODE_EXTENSIONS | {
    ".md", ".mdx", ".rst", ".txt", ".cfg", ".ini", ".conf", ".lock", ".csv",
}
SPECIAL_TEXT_NAMES = {
    "LICENSE", "LICENSE.md", "COPYING", "NOTICE", "README", "README.md",
    "Makefile", "Dockerfile", "moon.mod", "moon.pkg", "package.json",
    "pyproject.toml", "Cargo.toml", "go.mod",
}
IGNORED_PARTS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "_build", "target", "dist", "build", "coverage", ".mypy_cache", "outputs",
    "work", ".codex", ".cache",
}
GENERATED_PARTS = {
    "generated", "gen", "vendor", "third_party", "third-party", "deps",
}
TEST_MARKER = re.compile(r"(?:^|[/_.-])(?:test|tests|fixture|fixtures|spec|example|examples|bench|benchmark)(?:[/_.-]|$)", re.I)

# A small, deterministic concept vocabulary used for semantic *triage*.  It
# deliberately describes observable implementation cues rather than claiming
# to understand program meaning.  A concept is counted only when a token or
# source fragment matches its regular expression; reports expose the matched
# concepts and their limits so a reviewer can inspect the underlying files.
SEMANTIC_CONCEPTS = {
    "jmap": re.compile(r"\bjmap\b|rfc\s*862[01]|urn:ietf:params:jmap", re.I),
    "mail": re.compile(r"\b(?:mail|email|inbox|message|mime|imap|smtp|pop3)\b", re.I),
    "http": re.compile(r"\b(?:http|https|url|uri|request|response|header|cookie|client|server)\b", re.I),
    "json": re.compile(r"\bjson(?:rpc)?\b|application/json|serialize|deserialize", re.I),
    "query": re.compile(r"\b(?:query|filter|where|search|predicate|selector)\b", re.I),
    "pagination": re.compile(r"\b(?:page|paging|cursor|offset|limit|position|anchor|window)\b", re.I),
    "state": re.compile(r"\b(?:state|version|revision|token|sync|change|delta|since|until)\b", re.I),
    "ordering": re.compile(r"\b(?:sort|order|comparator|compare|ascending|descending|rank)\b", re.I),
    "collection": re.compile(r"\b(?:list|array|vector|map|set|dict|fold|reduce|iter|iterator)\b", re.I),
    "stream": re.compile(r"\b(?:stream|event|watch|subscribe|poll|sse|websocket|channel)\b", re.I),
    "storage": re.compile(r"\b(?:file|path|directory|store|database|sqlite|cache|persist|snapshot|restore)\b", re.I),
    "crypto_hash": re.compile(r"\b(?:hash|sha(?:1|2|256)?|md5|hmac|signature|encrypt|decrypt|nonce)\b", re.I),
    "schema": re.compile(r"\b(?:schema|type|struct|record|enum|field|validate|parse|lexer|parser|ast)\b", re.I),
    "errors": re.compile(r"\b(?:error|exception|failure|invalid|panic|throw|retry|timeout)\b", re.I),
    "concurrency": re.compile(r"\b(?:async|await|thread|task|mutex|lock|atomic|parallel|spawn)\b", re.I),
}
SEMANTIC_CONTROL = {
    "if", "else", "elif", "match", "switch", "case", "for", "while", "loop",
    "try", "catch", "finally", "return", "break", "continue", "raise", "throw",
}
SEMANTIC_OPERATIONS = {
    "map", "filter", "fold", "reduce", "sort", "split", "join", "find", "contains",
    "insert", "remove", "delete", "update", "get", "set", "encode", "decode", "parse",
    "serialize", "deserialize", "read", "write", "open", "close", "send", "recv", "request",
    "response", "query", "changes", "sync", "fetch", "load", "save", "hash", "verify",
}

# This lexer is intentionally conservative.  It removes comments and replaces
# literals while retaining punctuation and identifiers.  It is not a parser
# and therefore cannot establish semantic equivalence.
TOKEN_RE = re.compile(
    r"(?P<comment>//[^\n]*|/\*[\s\S]*?\*/|#[^\n]*)"
    r"|(?P<string>'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")"
    r"|(?P<number>\b(?:0[xX][0-9a-fA-F]+|0[bB][01]+|\d+(?:\.\d+)?)\b)"
    r"|(?P<ident>[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+)"
    r"|(?P<op>===|!==|==|!=|<=|>=|=>|->|::|&&|\|\||\+\+|--|\+=|-=|\*=|/=|\.\.\.|[{}()\[\];,.:?+\-*/%<>=!&|^~@#$])"
)
URI_RE = re.compile(r"https?://[^\s\"'<>`]+", re.I)
SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([^\s*]+)", re.I)
LICENSE_RE = re.compile(r"\b(?:MIT|Apache(?:\s+License)?|BSD(?:[- ]\d-Clause)?|GPL(?:v?\d)?|LGPL|MPL|ISC|CC0|Unlicense)\b", re.I)
ORIGIN_RE = re.compile(r"(?:source(?:d)?\s+from|generated\s+from|upstream|origin|repository|repo|源码来自|来源)\s*[:=]?\s*(https?://[^\s)<>]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", re.I)


@dataclasses.dataclass
class FileRecord:
    path: str
    role: str
    extension: str
    bytes: int
    sha256: str
    text: str


@dataclasses.dataclass
class ProjectSnapshot:
    name: str
    origin: str
    metadata: dict
    root_kind: str
    files: list[FileRecord]
    tree_sha256: str
    source_bytes: int
    source_lines: int
    exact_tokens: tuple[str, ...]
    shape_tokens: tuple[str, ...]
    exact_fingerprints: frozenset[str]
    shape_fingerprints: frozenset[str]
    exact_fingerprint_files: dict[str, tuple[str, ...]]
    shape_fingerprint_files: dict[str, tuple[str, ...]]
    test_exact_fingerprints: frozenset[str]
    test_shape_fingerprints: frozenset[str]
    test_canonical_lines: frozenset[str]
    canonical_lines: frozenset[str]
    declarations: frozenset[str]
    ast_exact: frozenset[str]
    ast_shape: frozenset[str]
    structural_signatures: frozenset[str]
    semantic_features: frozenset[str]
    semantic_feature_counts: dict[str, int]
    semantic_fingerprints: frozenset[str]
    semantic_fingerprint_files: dict[str, tuple[str, ...]]
    provenance: dict


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_strings(values: Iterable[str]) -> str:
    h = hashlib.sha256()
    for value in values:
        h.update(value.encode("utf-8", "surrogateescape"))
        h.update(b"\0")
    return h.hexdigest()


def safe_zip_members(zf: zipfile.ZipFile) -> Iterator[tuple[zipfile.ZipInfo, pathlib.PurePosixPath]]:
    for info in zf.infolist():
        if info.is_dir():
            continue
        path = pathlib.PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe ZIP member path: {info.filename!r}")
        yield info, path


def role_for(path: str) -> str:
    parts = pathlib.PurePosixPath(path).parts
    lower_parts = {p.lower() for p in parts}
    basename = pathlib.PurePosixPath(path).name.lower()
    if lower_parts & GENERATED_PARTS or ".generated." in basename or basename.endswith(("_gen.mbt", ".gen.mbt", ".generated.mbt")):
        return "generated_or_vendor"
    if TEST_MARKER.search(path):
        return "test_or_fixture"
    return "production"


def is_text_source(path: pathlib.PurePosixPath) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in SPECIAL_TEXT_NAMES


def iter_directory_files(root: pathlib.Path) -> Iterator[tuple[str, bytes]]:
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in rel.parts):
            continue
        if not is_text_source(path):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        yield rel.as_posix(), raw


def iter_input_files(input_path: pathlib.Path) -> tuple[str, Iterator[tuple[str, bytes]]]:
    if input_path.is_dir():
        return "directory", iter_directory_files(input_path)
    if input_path.suffix.lower() == ".zip":
        def from_zip() -> Iterator[tuple[str, bytes]]:
            with zipfile.ZipFile(input_path) as zf:
                for info, path in safe_zip_members(zf):
                    if is_text_source(path):
                        yield path.as_posix(), zf.read(info)
        return "zip", from_zip()
    raise ValueError(f"candidate must be a directory or ZIP: {input_path}")


def lex_tokens(text: str, *, shape: bool) -> list[str]:
    result: list[str] = []
    for match in TOKEN_RE.finditer(text):
        kind, value = match.lastgroup, match.group(0)
        if kind == "comment":
            continue
        if kind == "string":
            result.append("<STR>")
        elif kind == "number":
            result.append("<NUM>")
        elif kind == "ident":
            result.append("<ID>" if shape else value)
        elif kind == "op":
            result.append(value)
    return result


def token_fingerprints(tokens: Sequence[str], gram: int = 20) -> frozenset[str]:
    """Hash token n-grams.  A set keeps memory bounded and is order-independent."""
    if len(tokens) < gram:
        return frozenset()
    return frozenset(
        hashlib.sha256("\x1f".join(tokens[i : i + gram]).encode("utf-8")).hexdigest()[:24]
        for i in range(len(tokens) - gram + 1)
    )


def canonical_lines(text: str) -> set[str]:
    """Canonical non-trivial source lines for exact-line overlap evidence."""
    result: set[str] = set()
    for line in text.splitlines():
        # Reuse the lexer so comments, literals and whitespace do not dominate.
        tokens = lex_tokens(line, shape=False)
        if len(tokens) < 5:
            continue
        result.add(" ".join(tokens))
    return result


DECL_RE = re.compile(
    r"^\s*(?:(?:pub|public|private|protected|internal|async|unsafe|export|static|const)\s+)*"
    r"(?:fn|func|function|def|class|struct|enum|trait|interface|type|impl|module)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.I,
)


def declarations(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        match = DECL_RE.match(line)
        if not match:
            continue
        # Keep a short shape of the declaration.  Names are retained to catch
        # copied API surfaces, while parameter names and implementation bodies
        # are intentionally excluded.
        prefix = " ".join(lex_tokens(line.split("{")[0], shape=False))
        found.add(prefix[:320])
    return found


def python_ast_signatures(text: str) -> tuple[set[str], set[str]]:
    """Return exact and identifier/literal-normalised Python AST digests.

    MoonBit and most other languages intentionally return empty sets: a
    generic parser would create false confidence.  The report records this
    per-language coverage instead of pretending that token fingerprints are an
    AST comparison.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, TypeError):
        return set(), set()
    exact_dump = ast.dump(tree, annotate_fields=True, include_attributes=False)

    class Shape(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name):  # noqa: N802 - ast API
            node.id = "<ID>"
            return node

        def visit_arg(self, node: ast.arg):  # noqa: N802 - ast API
            node.arg = "<ID>"
            return node

        def visit_Constant(self, node: ast.Constant):  # noqa: N802 - ast API
            if isinstance(node.value, (str, bytes)):
                node.value = "<STR>"
            elif isinstance(node.value, (int, float, complex)) and not isinstance(node.value, bool):
                node.value = 0
            return node

    shaped = Shape().visit(ast.parse(text))
    ast.fix_missing_locations(shaped)
    shape_dump = ast.dump(shaped, annotate_fields=True, include_attributes=False)
    return {hashlib.sha256(exact_dump.encode()).hexdigest()[:24]}, {hashlib.sha256(shape_dump.encode()).hexdigest()[:24]}


def structural_signature(text: str) -> str:
    """A parser-independent syntax shape, useful for triage only."""
    tokens = lex_tokens(text, shape=True)
    depth = 0
    max_depth = 0
    opens = 0
    closes = 0
    for token in tokens:
        if token in {"{", "(", "["}:
            depth += 1
            opens += 1
            max_depth = max(max_depth, depth)
        elif token in {"}", ")", "]"}:
            depth = max(depth - 1, 0)
            closes += 1
    return f"tokens={len(tokens)};opens={opens};closes={closes};max_depth={max_depth};decls={len(declarations(text))}"


def semantic_profile(text: str) -> tuple[set[str], dict[str, int], frozenset[str]]:
    """Return conservative concept/control-flow fingerprints for triage.

    This is intentionally parser-independent so MoonBit and mixed-language
    projects can be compared with the same executable.  It is a *semantic
    cue* profile: concepts are regex/tag observations and the sequence hashes
    preserve coarse operation order.  It cannot prove semantic equivalence,
    authorship, or copying and should always be followed by source review.
    """
    counts: collections.Counter[str] = collections.Counter()
    # Run concept matching over comment/string-free lexical tokens.  README
    # prose, license text and user-facing error messages must not turn a
    # generic package into a false domain match.
    tokens = lex_tokens(text, shape=False)
    concept_text = " ".join(tokens)
    for name, pattern in SEMANTIC_CONCEPTS.items():
        counts[f"concept:{name}"] = len(pattern.findall(concept_text))
    semantic_tokens: list[str] = []
    for token in tokens:
        low = token.lower()
        if low in SEMANTIC_CONTROL:
            semantic_tokens.append(f"control:{low}")
            counts[f"control:{low}"] += 1
        elif low in SEMANTIC_OPERATIONS:
            semantic_tokens.append(f"op:{low}")
            counts[f"op:{low}"] += 1
        elif token in {"{", "}", "(", ")", "[", "]", ":", ";", ",", "=>", "->"}:
            # Keep block and call boundaries in the coarse sequence without
            # allowing punctuation to dominate the feature profile.
            semantic_tokens.append(f"punct:{token}")
    # Concept presence is more stable than raw counts under refactoring; zero
    # entries are omitted from the set while counts retain all observed values.
    features = {name for name, value in counts.items() if value}
    windows = frozenset(
        hashlib.sha256("\x1f".join(semantic_tokens[i : i + 8]).encode("utf-8")).hexdigest()[:24]
        for i in range(max(0, len(semantic_tokens) - 7))
    )
    return features, dict(counts), windows


def file_provenance(records: Sequence[FileRecord]) -> dict:
    licenses: set[str] = set()
    urls: set[str] = set()
    origins: set[str] = set()
    indicators: list[dict] = []
    for record in records:
        text = record.text
        for match in SPDX_RE.finditer(text):
            licenses.add(match.group(1))
            indicators.append({"kind": "spdx", "file": record.path, "value": match.group(1)})
        for match in LICENSE_RE.finditer(text):
            value = " ".join(match.group(0).split())
            licenses.add(value)
            if len(indicators) < 120:
                indicators.append({"kind": "license_text", "file": record.path, "value": value})
        for match in URI_RE.finditer(text):
            value = match.group(0).rstrip(".,;)")
            urls.add(value)
        for match in ORIGIN_RE.finditer(text):
            origins.add(match.group(1).rstrip(".,;)") )
            if len(indicators) < 120:
                indicators.append({"kind": "origin", "file": record.path, "value": match.group(1)})
    return {
        "licenses": sorted(licenses),
        "urls": sorted(urls)[:200],
        "origin_indicators": sorted(origins),
        "evidence": indicators[:120],
    }


def make_snapshot(name: str, input_path: pathlib.Path, origin: str = "", metadata: dict | None = None) -> ProjectSnapshot:
    root_kind, iterator = iter_input_files(input_path)
    records: list[FileRecord] = []
    for rel, raw in iterator:
        text = raw.decode("utf-8", errors="replace")
        path_obj = pathlib.PurePosixPath(rel)
        records.append(
            FileRecord(
                path=rel,
                role=role_for(rel),
                extension=path_obj.suffix.lower(),
                bytes=len(raw),
                sha256=sha256_bytes(raw),
                text=text,
            )
        )
    records.sort(key=lambda record: record.path)
    tree_sha = digest_strings(
        f"{record.path}\t{record.bytes}\t{record.sha256}" for record in records
    )
    production = [record for record in records if record.role == "production"]
    # All code roles are recorded, but production is the default comparison
    # surface.  Tests and generated/vendor code are independently reported.
    source_text = "\n".join(record.text for record in production if record.extension in CODE_EXTENSIONS)
    test_records = [record for record in records if record.role == "test_or_fixture" and record.extension in CODE_EXTENSIONS]
    test_text = "\n".join(record.text for record in test_records)
    exact = lex_tokens(source_text, shape=False)
    shape = lex_tokens(source_text, shape=True)
    test_exact = lex_tokens(test_text, shape=False)
    test_shape = lex_tokens(test_text, shape=True)
    exact_file_map: dict[str, list[str]] = {}
    shape_file_map: dict[str, list[str]] = {}
    semantic_file_map: dict[str, list[str]] = {}
    semantic_features, semantic_counts, semantic_fingerprints = semantic_profile(source_text)
    for record in production:
        if record.extension not in CODE_EXTENSIONS:
            continue
        for fingerprint in token_fingerprints(lex_tokens(record.text, shape=False)):
            exact_file_map.setdefault(fingerprint, []).append(record.path)
        for fingerprint in token_fingerprints(lex_tokens(record.text, shape=True)):
            shape_file_map.setdefault(fingerprint, []).append(record.path)
        _, _, file_semantic_fingerprints = semantic_profile(record.text)
        for fingerprint in file_semantic_fingerprints:
            semantic_file_map.setdefault(fingerprint, []).append(record.path)
    return ProjectSnapshot(
        name=name,
        origin=origin,
        metadata=dict(metadata or {}),
        root_kind=root_kind,
        files=records,
        tree_sha256=tree_sha,
        source_bytes=sum(record.bytes for record in production if record.extension in CODE_EXTENSIONS),
        source_lines=sum(record.text.count("\n") + bool(record.text) for record in production if record.extension in CODE_EXTENSIONS),
        exact_tokens=tuple(exact),
        shape_tokens=tuple(shape),
        exact_fingerprints=token_fingerprints(exact),
        shape_fingerprints=token_fingerprints(shape),
        exact_fingerprint_files={key: tuple(sorted(value)) for key, value in exact_file_map.items()},
        shape_fingerprint_files={key: tuple(sorted(value)) for key, value in shape_file_map.items()},
        test_exact_fingerprints=token_fingerprints(test_exact),
        test_shape_fingerprints=token_fingerprints(test_shape),
        test_canonical_lines=frozenset(line for record in test_records for line in canonical_lines(record.text)),
        canonical_lines=frozenset(
            line for record in production if record.extension in CODE_EXTENSIONS for line in canonical_lines(record.text)
        ),
        declarations=frozenset(
            declaration for record in production if record.extension in CODE_EXTENSIONS for declaration in declarations(record.text)
        ),
        ast_exact=frozenset(
            digest for record in production if record.extension == ".py" for digest in python_ast_signatures(record.text)[0]
        ),
        ast_shape=frozenset(
            digest for record in production if record.extension == ".py" for digest in python_ast_signatures(record.text)[1]
        ),
        structural_signatures=frozenset(
            structural_signature(record.text) for record in production if record.extension in CODE_EXTENSIONS
        ),
        semantic_features=frozenset(semantic_features),
        semantic_feature_counts=semantic_counts,
        semantic_fingerprints=semantic_fingerprints,
        semantic_fingerprint_files={key: tuple(sorted(value)) for key, value in semantic_file_map.items()},
        provenance=file_provenance(records),
    )


def ratio(intersection: int, left: int, right: int) -> float:
    union = left + right - intersection
    return round(intersection / union, 6) if union else 0.0


def weighted_feature_similarity(left: dict[str, int], right: dict[str, int]) -> float:
    """Weighted overlap of semantic cue counts, bounded to [0, 1]."""
    keys = set(left) | set(right)
    numerator = sum(min(int(left.get(key, 0)), int(right.get(key, 0))) for key in keys)
    denominator = sum(max(int(left.get(key, 0)), int(right.get(key, 0))) for key in keys)
    return round(numerator / denominator, 6) if denominator else 0.0


def compare(left: ProjectSnapshot, right: ProjectSnapshot) -> dict:
    target_file_hashes = {record.sha256 for record in left.files if record.role == "production"}
    candidate_file_hashes = {record.sha256 for record in right.files if record.role == "production"}
    file_hash_inter = len(target_file_hashes & candidate_file_hashes)
    exact_inter = len(left.exact_fingerprints & right.exact_fingerprints)
    shape_inter = len(left.shape_fingerprints & right.shape_fingerprints)
    line_inter = len(left.canonical_lines & right.canonical_lines)
    decl_inter = len(left.declarations & right.declarations)
    ast_exact_inter = len(left.ast_exact & right.ast_exact)
    ast_shape_inter = len(left.ast_shape & right.ast_shape)
    structural_inter = len(left.structural_signatures & right.structural_signatures)
    semantic_feature_inter = len(left.semantic_features & right.semantic_features)
    semantic_sequence_inter = len(left.semantic_fingerprints & right.semantic_fingerprints)
    semantic_feature_jaccard = ratio(
        semantic_feature_inter, len(left.semantic_features), len(right.semantic_features)
    )
    semantic_feature_containment = round(
        semantic_feature_inter / len(left.semantic_features), 6
    ) if left.semantic_features else 0.0
    semantic_sequence_containment = round(
        semantic_sequence_inter / len(left.semantic_fingerprints), 6
    ) if left.semantic_fingerprints else 0.0
    semantic_weighted = weighted_feature_similarity(
        left.semantic_feature_counts, right.semantic_feature_counts
    )
    test_exact_inter = len(left.test_exact_fingerprints & right.test_exact_fingerprints)
    test_shape_inter = len(left.test_shape_fingerprints & right.test_shape_fingerprints)
    test_line_inter = len(left.test_canonical_lines & right.test_canonical_lines)
    # Containment is useful when a contest project copies a small but central
    # implementation from MoonJMAP; Jaccard alone can hide this in a large tree.
    target_exact_containment = round(
        exact_inter / len(left.exact_fingerprints), 6
    ) if left.exact_fingerprints else 0.0
    target_shape_containment = round(
        shape_inter / len(left.shape_fingerprints), 6
    ) if left.shape_fingerprints else 0.0
    target_line_containment = round(
        line_inter / len(left.canonical_lines), 6
    ) if left.canonical_lines else 0.0
    target_decl_containment = round(
        decl_inter / len(left.declarations), 6
    ) if left.declarations else 0.0
    # This score is a triage aid only.  It intentionally has no pass/fail
    # threshold; semantic equivalence and independent reimplementation require
    # human or parser-assisted review.
    triage = round(
        0.40 * target_exact_containment
        + 0.25 * target_shape_containment
        + 0.20 * target_line_containment
        + 0.15 * target_decl_containment,
        6,
    )
    return {
        "target": left.name,
        "candidate": right.name,
        "target_tree_sha256": left.tree_sha256,
        "candidate_tree_sha256": right.tree_sha256,
        "target_files": len(left.files),
        "candidate_files": len(right.files),
        "file_sha256": {
            "target_production_files": len(target_file_hashes),
            "candidate_production_files": len(candidate_file_hashes),
            "exact_hash_intersection": file_hash_inter,
            "target_containment": round(file_hash_inter / len(target_file_hashes), 6) if target_file_hashes else 0.0,
            "jaccard": ratio(file_hash_inter, len(target_file_hashes), len(candidate_file_hashes)),
        },
        "exact_token_fingerprints": {
            "target": len(left.exact_fingerprints),
            "candidate": len(right.exact_fingerprints),
            "intersection": exact_inter,
            "jaccard": ratio(exact_inter, len(left.exact_fingerprints), len(right.exact_fingerprints)),
            "target_containment": target_exact_containment,
        },
        "shape_token_fingerprints": {
            "target": len(left.shape_fingerprints),
            "candidate": len(right.shape_fingerprints),
            "intersection": shape_inter,
            "jaccard": ratio(shape_inter, len(left.shape_fingerprints), len(right.shape_fingerprints)),
            "target_containment": target_shape_containment,
        },
        "canonical_source_lines": {
            "target": len(left.canonical_lines),
            "candidate": len(right.canonical_lines),
            "intersection": line_inter,
            "jaccard": ratio(line_inter, len(left.canonical_lines), len(right.canonical_lines)),
            "target_containment": target_line_containment,
        },
        "declaration_signatures": {
            "target": len(left.declarations),
            "candidate": len(right.declarations),
            "intersection": decl_inter,
            "jaccard": ratio(decl_inter, len(left.declarations), len(right.declarations)),
            "target_containment": target_decl_containment,
        },
        "ast_signatures": {
            "mode": "Python ast.parse where applicable; empty for unsupported languages",
            "exact_target": len(left.ast_exact),
            "exact_candidate": len(right.ast_exact),
            "exact_intersection": ast_exact_inter,
            "shape_target": len(left.ast_shape),
            "shape_candidate": len(right.ast_shape),
            "shape_intersection": ast_shape_inter,
        },
        "structural_signatures": {
            "target": len(left.structural_signatures),
            "candidate": len(right.structural_signatures),
            "intersection": structural_inter,
            "jaccard": ratio(structural_inter, len(left.structural_signatures), len(right.structural_signatures)),
        },
        "semantic_cues": {
            "method": "concept/control-flow cue profile and 8-token operation-window hashes; heuristic triage only",
            "target_features": len(left.semantic_features),
            "candidate_features": len(right.semantic_features),
            "feature_intersection": semantic_feature_inter,
            "feature_jaccard": semantic_feature_jaccard,
            "target_feature_containment": semantic_feature_containment,
            "target_sequence_fingerprints": len(left.semantic_fingerprints),
            "candidate_sequence_fingerprints": len(right.semantic_fingerprints),
            "sequence_intersection": semantic_sequence_inter,
            "sequence_jaccard": ratio(semantic_sequence_inter, len(left.semantic_fingerprints), len(right.semantic_fingerprints)),
            "target_sequence_containment": semantic_sequence_containment,
            "weighted_feature_overlap": semantic_weighted,
            "target_features_by_name": sorted(left.semantic_features),
            "candidate_features_by_name": sorted(right.semantic_features),
        },
        "test_surface": {
            "exact_fingerprint_intersection": test_exact_inter,
            "exact_fingerprint_jaccard": ratio(test_exact_inter, len(left.test_exact_fingerprints), len(right.test_exact_fingerprints)),
            "shape_fingerprint_intersection": test_shape_inter,
            "shape_fingerprint_jaccard": ratio(test_shape_inter, len(left.test_shape_fingerprints), len(right.test_shape_fingerprints)),
            "canonical_line_intersection": test_line_inter,
            "canonical_line_jaccard": ratio(test_line_inter, len(left.test_canonical_lines), len(right.test_canonical_lines)),
            "target_test_files": sum(record.role == "test_or_fixture" for record in left.files),
            "candidate_test_files": sum(record.role == "test_or_fixture" for record in right.files),
        },
        "fingerprint_examples": [
            {
                "fingerprint": fingerprint,
                "target_files": list(left.exact_fingerprint_files.get(fingerprint, ())),
                "candidate_files": list(right.exact_fingerprint_files.get(fingerprint, ())),
            }
            for fingerprint in sorted(left.exact_fingerprints & right.exact_fingerprints)[:32]
        ],
        "triage_score": triage,
        "interpretation": (
            "high triage score needs human review; it is not a plagiarism verdict"
            if triage >= 0.15 else "no strong lexical/structural signal in this snapshot"
        ),
    }


def load_manifest(path: pathlib.Path) -> tuple[dict, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"contest": "unspecified", "projects": payload}, payload
    if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list):
        raise ValueError("manifest must be an object with a projects array (or a project array)")
    return payload, payload["projects"]


def project_arg(value: str) -> dict:
    if "=" in value:
        name, path = value.split("=", 1)
    else:
        path = value
        name = pathlib.Path(path).stem
    if not name or not path:
        raise ValueError(f"invalid --candidate value: {value!r}")
    return {"name": name, "path": path}


def json_snapshot(snapshot: ProjectSnapshot) -> dict:
    return {
        "name": snapshot.name,
        "origin": snapshot.origin,
        "metadata": snapshot.metadata,
        "root_kind": snapshot.root_kind,
        "tree_sha256": snapshot.tree_sha256,
        "files": [
            {"path": f.path, "role": f.role, "extension": f.extension, "bytes": f.bytes, "sha256": f.sha256}
            for f in snapshot.files
        ],
        "source_bytes": snapshot.source_bytes,
        "source_lines": snapshot.source_lines,
        "token_counts": {"exact": len(snapshot.exact_tokens), "shape": len(snapshot.shape_tokens)},
        "fingerprint_counts": {
            "exact": len(snapshot.exact_fingerprints),
            "shape": len(snapshot.shape_fingerprints),
            "canonical_lines": len(snapshot.canonical_lines),
            "declarations": len(snapshot.declarations),
            "ast_exact": len(snapshot.ast_exact),
            "ast_shape": len(snapshot.ast_shape),
            "structural_signatures": len(snapshot.structural_signatures),
            "test_exact": len(snapshot.test_exact_fingerprints),
            "test_shape": len(snapshot.test_shape_fingerprints),
            "test_canonical_lines": len(snapshot.test_canonical_lines),
            "semantic_features": len(snapshot.semantic_features),
            "semantic_fingerprints": len(snapshot.semantic_fingerprints),
        },
        "semantic_feature_counts": snapshot.semantic_feature_counts,
        "provenance": snapshot.provenance,
    }


def render_markdown(meta: dict, target: ProjectSnapshot, candidates: Sequence[ProjectSnapshot], comparisons: Sequence[dict]) -> str:
    scope = meta.get("scope", {})
    lines = [
        "# 赛事参赛项目源码相似性审计报告（可复核模板）",
        "",
        f"- 审计时间（UTC）：`{meta['created_at']}`",
        f"- 赛事：`{meta.get('contest', 'unspecified')}`",
        f"- 参赛项目清单 SHA-256：`{meta['manifest_sha256']}`",
        f"- MoonJMAP 源码树 SHA-256：`{target.tree_sha256}`",
        f"- 纳入比较的候选项目：`{len(candidates)}`",
        f"- 清单声明项目数：`{scope.get('expected_count', '未提供')}`",
        f"- 清单数量是否匹配：`{scope.get('count_matches', '未核验')}`",
        "",
        "> 本报告只描述给定源码快照和所列比较方法下观察到的信号。它不能证明赛事完整参赛名单、未公开项目、历史版本或语义等价性，也不能替代赛事组委会的判重结论。没有纳入清单的项目不应写成“已比对”。",
        "",
        "## 判定摘要",
        "",
        "| 候选项目 | 词法精确包含率 | 词法形状包含率 | 规范行包含率 | 声明包含率 | 语义线索重叠 | 分流分数 | 处理建议 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in sorted(comparisons, key=lambda x: x["triage_score"], reverse=True):
        lines.append(
            f"| `{item['candidate']}` | {item['exact_token_fingerprints']['target_containment']:.4f} | "
            f"{item['shape_token_fingerprints']['target_containment']:.4f} | "
            f"{item['canonical_source_lines']['target_containment']:.4f} | "
            f"{item['declaration_signatures']['target_containment']:.4f} | "
            f"{item['semantic_cues']['weighted_feature_overlap']:.4f} | "
            f"{item['triage_score']:.4f} | 人工复核信号；不得自动定性 |")
    lines.extend([
        "",
        "## 方法",
        "",
        "1. 对目录或 ZIP 中的文本源码计算逐文件 SHA-256，并对排序后的路径/大小/哈希计算源码树摘要。",
        "2. 删除注释、将字符串和数字归一化，分别保留精确标识符 token 与形状 token；计算 20-token 滑窗指纹的 Jaccard 和以 MoonJMAP 为分母的包含率。",
        "3. 对非平凡规范化源码行、声明签名分别计算交集和包含率。公共库样板、语言关键字和独立实现可能造成误报。",
        "4. 对概念词、控制流词和操作词生成语义线索特征，并对粗粒度操作序列计算窗口哈希；该层只用于排序人工复核，不能证明语义等价。",
        "5. 读取 SPDX、许可证文本、仓库 URL 和 generated/upstream/source-from 线索；这些是来源核查线索，不是许可证合规结论。",
        "6. 候选项目不执行、不导入、不构建。ZIP 路径穿越会使该候选失败并记录错误。",
        "",
        "## 不可证明的范围",
        "",
        "- 若赛事没有提供完整、带版本/提交号的参赛名单，工具只能审计实际提供的项目，不能证明“全部参赛项目”。",
        "- Python 文件可记录标准库 AST 摘要；MoonBit 和其他语言没有内置验证过的解析器。词法/结构/语义线索指纹均不能识别重命名、重排或独立实现的真实语义关系。",
        "- 公开发布包、工作区源码和赛事最终提交可能不同；必须保存每个候选的 URL、commit/tag、下载时间、SHA-256 和授权范围。",
        "- 许可证字段和来源 URL 来自可读文本与清单，不能证明作者身份、代码创作时间、第三方许可兼容性或抄袭事实。",
        "- 报告不包含赛事评委规则、私有仓库、未公开草稿、提交后的新版本和其他平台的完整代码，除非它们被明确加入清单。",
        "",
        "## 复核材料",
        "",
        "机器可读的 `audit.json` 保存完整快照、文件哈希、指纹计数、许可证/来源线索和各项比较值；人工复核应从最高分项目开始，回到具体文件和提交历史，而不是只看分数。",
        "",
    ])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="MoonJMAP source directory or ZIP")
    parser.add_argument("--manifest", help="JSON manifest with a projects array")
    parser.add_argument("--candidate", action="append", default=[], help="NAME=PATH or PATH; repeatable")
    parser.add_argument("--out-dir", default="outputs/contest-source-audit", help="output directory")
    args = parser.parse_args(argv)
    try:
        manifest_meta: dict = {"contest": "unspecified", "projects": []}
        project_entries: list[dict] = []
        manifest_base: pathlib.Path | None = None
        if args.manifest:
            manifest_path = pathlib.Path(args.manifest).resolve()
            manifest_base = manifest_path.parent
            manifest_meta, project_entries = load_manifest(manifest_path)
            manifest_bytes = manifest_path.read_bytes()
        else:
            manifest_bytes = json.dumps(
                {"projects": [project_arg(value) for value in args.candidate]},
                ensure_ascii=False, sort_keys=True,
            ).encode("utf-8")
        project_entries = project_entries + [project_arg(value) for value in args.candidate]
        if not project_entries:
            raise ValueError("no candidates supplied: use --manifest or at least one --candidate")
        target_path = pathlib.Path(args.project).resolve()
        target = make_snapshot("MoonJMAP", target_path, origin=str(target_path), metadata={"path": str(target_path)})
        candidates: list[ProjectSnapshot] = []
        errors: list[dict] = []
        seen: set[str] = set()
        for entry in project_entries:
            if not isinstance(entry, dict):
                errors.append({"name": "<invalid-manifest-entry>", "error": "entry is not an object"})
                continue
            name = str(entry.get("name") or pathlib.Path(str(entry.get("path", "candidate"))).stem)
            raw_path = entry.get("path") or entry.get("source")
            if not raw_path:
                errors.append({"name": name, "error": "manifest entry has no path/source"})
                continue
            path = pathlib.Path(str(raw_path)).expanduser()
            if manifest_base is not None and not path.is_absolute():
                path = manifest_base / path
            path = path.resolve()
            try:
                if not path.exists():
                    raise FileNotFoundError(path)
                identity = f"{name}\0{path}"
                if identity in seen:
                    continue
                seen.add(identity)
                candidates.append(
                    make_snapshot(
                        name,
                        path,
                        origin=str(entry.get("source_url") or entry.get("url") or path),
                        metadata=entry,
                    )
                )
            except Exception as exc:  # preserve an auditable failure and continue
                errors.append({"name": name, "path": str(path), "error": repr(exc)})
        comparisons = [compare(target, candidate) for candidate in candidates]
        out_dir = pathlib.Path(args.out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "schema": "moon-jmap-contest-source-audit/v1",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "contest": manifest_meta.get("contest", "unspecified"),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "manifest_path": str(pathlib.Path(args.manifest).resolve()) if args.manifest else None,
            "target": json_snapshot(target),
            "candidate_count": len(candidates),
            "error_count": len(errors),
            "errors": errors,
            "scope": {
                "expected_count": manifest_meta.get("expected_count"),
                "roster_source_url": manifest_meta.get("roster_source_url"),
                "count_matches": (
                    len(candidates) == int(manifest_meta["expected_count"])
                    if manifest_meta.get("expected_count") is not None
                    and str(manifest_meta.get("expected_count")).isdigit()
                    else None
                ),
                "official_roster_verified": bool(manifest_meta.get("official_roster_verified", False)),
            },
            "candidates": [json_snapshot(candidate) for candidate in candidates],
            "comparisons": comparisons,
            "limitations": [
                "No complete contest roster is inferred by this tool.",
                "Lexical/structural fingerprints are triage evidence, not semantic or legal proof.",
                "Only supplied local directories/ZIPs are covered; preserve source URL and commit externally.",
            ],
        }
        (out_dir / "audit.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out_dir / "audit.md").write_text(render_markdown(meta, target, candidates, comparisons), encoding="utf-8")
        print(json.dumps({"out_dir": str(out_dir), "candidate_count": len(candidates), "error_count": len(errors), "manifest_sha256": meta["manifest_sha256"]}, ensure_ascii=False))
        return 0 if candidates else 2
    except Exception as exc:
        print(f"source_similarity_audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

