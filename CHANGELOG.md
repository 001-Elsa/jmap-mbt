# Changelog

All notable changes to MoonJMAP are recorded here. The project is currently
at the `0.1.0` source-delivery stage. The public source repository is
https://github.com/001-Elsa/jmap-mbt; Mooncakes publication remains separate.

## Registry release - 2026-10-26

- Publish `001-Elsa/moonjmap@0.1.0` to Mooncakes, verify the live archive
  checksum and successful server build, and pass three downstream consumer
  tests on both wasm and wasm-gc. See docs/mooncakes-release-0.1.0.md.

- Set the owned module namespace to `001-Elsa/moonjmap` for the initial
  `0.1.0` registry release, updating package imports and generated interfaces.
- Add a dedicated `.moonignore` to keep historical investigation outputs,
  local work and build artifacts out of registry packages.
- Document registry installation and public package imports; link historical
  evidence to the GitHub repository so it remains available outside the package.

## Repository import - 2026-10-26

- Organize the existing source snapshot into 20 non-empty commits by feature
  and source-file chronology, using the actual import time for Git timestamps.
- Add the repository URL, portable MoonBit tool discovery, cache exclusions
  and a reviewed subset of redacted Markdown/JSON evidence.
- Preserve historical report conclusions and source-archive hashes; publication
  changes to evidence URLs are described in docs/repository-import.md.

## Local domain refactor - 2026-10-26

- Rebuild queryChanges prefixes by final-rank merge over retained Email IDs and
  server-supplied added ranks; unknown ranks still require a refresh.
- Replace generic remove/add certificate scripts with per-result-slot before
  position references or introduced IDs. Compare structured QueryKey and complete
  typed Request fields directly; remove FNV and request/query digest fields.
- Remove the early ChangesData / ChangesResponseEnvelope / ChangesResult
  two-array compatibility API. Email object changes now use only the RFC
  created/updated/destroyed model; queryChanges removed/added remains unchanged.
- Keep constructor/verifier function spellings, but record the incompatible
  certificate fields and response migration in docs/decision-certificates.md
  and docs/support-matrix.md. Existing local archives remain historical snapshots.
- Preserve independent state chains, same-state fill, recovery, budgets, stale
  response rejection and Ready gates. Shared safety and verification patterns
  remain shared; this refactor does not establish zero similarity or originality.

## Local corrections - 2026-10-26

- Keep the existing ID transition certificate API and repair partial reorder
  witnesses so stationary IDs are retained. Exhaustively check all 4,225
  transitions between ordered subsets of four IDs.
- Tighten query page/fill, queryChanges growth and resource counter boundaries
  found during contract review. These are corrections to existing sync behavior.
- Recheck the frozen proposal against the current 3,331-module Mooncakes
  snapshot. The proposed new payload/trace auditing layer was withdrawn after
  confirming strong architecture peers; it is absent from active source and API.
  No zero-similarity or contest-adjudication guarantee is made.

## [0.1.0] - 2026-10-25

### Added

#### 主功能：JMAP 邮件查询前缀一致性

- A MoonBit core for two fixed, read-only Email query views: latest mail in a
  mailbox and unread mail in a mailbox.
- Independent Email-history and query-history frontiers with strict
  `Email/changes`/`Email/queryChanges` coordination, ordered-prefix repair,
  same-query-state fill, ID-based `Email/get` placement, and explicit
  `Ready`/`Pending`/`NeedsRefresh` decisions.
- A JMAP-specific `JmapEmailPrefixCertificate` (`DecisionCertificate` compatibility spelling) that records remove/add witnesses,
  query/email state boundaries, generation, completeness and reason, then
  replays the ordered-prefix transition in a pure MoonBit verifier. This is
  the project's domain feature; it is not a general patch, journal, workflow,
  or RPC audit product.

#### 内部支撑：只为主功能提供安全边界

- Typed account-bound response envelopes, checked generation transitions,
  cumulative `Email/changes` budgets, and resumable checkpoints. These
  mechanisms prevent a false `Ready`, skipped history, or stale response from
  changing the mail view; they are not separate product claims.
- A finite Python wire model for the four JMAP methods with strict tuple,
  reference, property, and response-shape validation. It is an adapter boundary
  for the fixed views, not a general JSON/RPC framework.

#### 证据和交付工具：不作为功能卖点

- Language-neutral fixtures, an independent Python oracle, bounded
  MoonBit/Python differential checks over C01–C15, and redacted synthetic
  traces. They document and test the prefix/frontier/ certificate behavior;
  they are not a generic replay, metrics, or performance platform.
- A current-snapshot Mooncakes comparison record, deterministic local source
  archive builder, and archive smoke test. These produce reviewable local
  evidence and do not publish or register a package.

### Validation boundary

- MoonBit `wasm`, `wasm-gc`, and bundled-Node JS tests are recorded separately
  in `outputs/MoonJMAP-本地向量验收报告-2026-10-25.md`.
- Real-server JMAP interoperability and a measured performance baseline are
  now evidenced for the official Stalwart Server v0.16.27 binary running on
  loopback with five synthetic messages. The redacted object-level record and
  benchmark are linked from `outputs/MoonJMAP-真实服务互操作与性能验证-2026-10-26.md`.
  This is a read-only, single-implementation baseline; it is not a claim about
  JMAP write/change coverage, hosted services, or production SLOs.
- A public-source audit covers 31 discoverable contest candidates, but the
  organizer has not published a verifiable complete roster. It therefore does
  not establish comparison against every entrant or a contest no-overlap
  decision. Mooncakes publication and contest adjudication remain separate
  external events.
