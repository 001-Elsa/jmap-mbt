# MoonJMAP release checklist

This checklist describes the local source-delivery gate for the current
`0.1.0` project. It is intentionally separate from a public repository,
Mooncakes publication, or a real-server compatibility claim.

## Inputs and metadata

- [x] `moon.mod` has the intended package name, version, license, and
  description.
- [x] `LICENSE` is present and matches the `license = "Apache-2.0"` metadata.
- [x] `README.md` states the supported boundary and the unverified
  interoperability boundary.
- [x] `CHANGELOG.md` describes only implemented local-delivery behavior.
- [x] No repository URL, commit, tag, registry publication, or certification is
  invented when those events have not occurred.

## Product-positioning gate

Before a release artifact is described to a reviewer, check the emphasis order:

- [x] The first described behavior is the fixed JMAP mail-query ordered-prefix
  transition: two independent state frontiers, same-state fill, ID placement,
  and explicit completeness decisions.
- [x] The second described behavior is the JMAP-specific
  `JmapEmailPrefixCertificate` (`DecisionCertificate` compatibility spelling) and its offline verifier, including query/email state
  boundaries and per-slot before-position/introduced-ID witnesses, using structured
  query/request fields rather than FNV digests.
- [x] Checkpoints, generation fences, change budgets, typed wire envelopes and
  `Pending` are described as safety mechanisms for that transition.
- [x] Python wire, oracle, trace, metrics, differential checks and archive
  tooling are labeled as local evidence or adapter support, not as a generic
  RPC, replay, logging, performance or workflow product.
- [x] HTTP/TLS/OAuth/SSE, SMTP/IMAP/MIME, generic JSON/RPC and arbitrary
  query builders remain outside the public scope.

The release gate therefore reviews depth of the mail-view transition and its
certificate before counting supporting scripts. A passing archive smoke test
cannot turn a neighboring generic capability into a MoonJMAP feature claim.

## Source archive gate

Run from the project root:

```sh
python3 scripts/build_source_archive.py --output-dir dist
python3 scripts/release_smoke_test.py dist/moonjmap-0.1.0-src.tar.gz
python3 scripts/release_smoke_test.py dist/moonjmap-0.1.0-src.zip
```

The archive builder uses an explicit source allowlist, stable path ordering,
normalized timestamps and ownership, and a manifest with per-file SHA-256
digests. It excludes `_build/`, `work/`, `dist/`, `.DS_Store`, Python cache
directories, generated local reports, and any untracked machine state. The
archive is therefore a reproducible local source artifact rather than a
binary or registry package.

## Smoke checks

The smoke test must verify all of the following inside a fresh temporary
extraction directory:

- [x] archive paths cannot escape their package root;
- [x] required MoonBit, Python, documentation, license, fixture, and manifest
  files are present;
- [x] manifest digests match the extracted files;
- [x] `src/jmap` imports through `PYTHONPATH=src`;
- [x] `cmd/differential` and its MoonBit package metadata are included in the
  archive so the bounded cross-implementation trace can be rerun after
  extraction;
- [x] all packaged Python regression tests (including fixed wire and synthetic
  metrics invariants) pass;
- [x] vector replay and codec round-trip examples pass.
- [x] the bounded cross-implementation trace harness passes all C01–C15 cases:

  ```sh
  python3 scripts/run_differential.py
  ```

  The result is recorded in
  `outputs/MoonJMAP-跨实现逐步对拍-2026-10-25.json`. Read
  `docs/differential-harness.md` before interpreting this as evidence: it is
  a common-projection comparison with explicit known boundaries, not a full
  equivalence proof or a real-server result.

The smoke test does not claim that a real JMAP server, HTTP transport, TLS,
OAuth, native linker, or Mooncakes registry is available.

## External completion gates

The following are separate gates and must not be marked complete from a local
archive smoke test alone:

- [x] a real service interop record with redacted requests and responses for
  Stalwart Server v0.16.27; see
  `outputs/real-interop-stalwart-v0.16.27/record-seeded-object-level-20261026.json`.
- [x] a measured performance report against five synthetic messages on that
  real service; see
  `outputs/real-benchmark/stalwart-local-real-20261026-seeded.json`.
- a full cross-implementation equivalence proof (the bounded C01–C15 common
  projection harness is complete, but its documented abstraction boundaries
  remain);
- [x] a read-only audit of the 31 publicly discoverable contest candidates;
  the audit is recorded in
  `outputs/contest-public-inventory-2026-10-26.md` and
  `outputs/contest-source-audit-public-candidates-expanded/audit.md`. The
  official contest roster is not public, so the audit is not a full-entrant
  comparison and does not decide contest eligibility or judging.
- [x] public source repository: https://github.com/001-Elsa/jmap-mbt.
- [x] Mooncakes upload: `001-Elsa/moonjmap@0.1.0`, successful server build and
  independent exact-version installation; see [release record](mooncakes-release-0.1.0.md).
- a version tag or contest submission, if requested separately.

## Registry publication procedure

The initial registry module is `001-Elsa/moonjmap@0.1.0`. `.moonignore`
replaces `.gitignore` for registry selection and excludes historical `outputs/`,
local `work/`, `dist/`, build products, cache files and credentials.

```sh
moon whoami
moon package --frozen --list
moon publish --dry-run
moon publish
moon view 001-Elsa/moonjmap@0.1.0 --json
```

Inspect the actual `_build/publish/001-Elsa-moonjmap-0.1.0.zip` before
publishing. After publication, create a fresh external module, install the exact
version with `moon add 001-Elsa/moonjmap@0.1.0`, and compile and run tests using
all three public packages (`src/email`, `src/jmap`, `src/sync`). Registry metadata,
the downloaded ZIP checksum and the independent consumer result are separate
checks from the local test suite.
