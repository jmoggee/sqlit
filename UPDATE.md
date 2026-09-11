# Fork maintenance guide

This fork (`jmoggee/sqlit`) carries one behavioral patch on top of upstream
`Maxteabag/sqlit`, plus this maintenance guide. `main` is the integration
branch. Upstream is `origin`; the writable fork is `fork`. Never push to
`origin`.

## Current upstream changes

The 2026-09-13 update fetched both remotes and found `origin/main` unchanged at
`5ad4559`, so no new upstream functionality arrived since the prior run. That
upstream commit added the Vesper theme and made result rendering preserve safe
UTF-8 byte values as text while falling back to hexadecimal for unsafe bytes.
It also fixed byte-field previews and removed filter highlighting from cell
preview tooltips. These changes do not overlap the executor race fix.

## Carried behavior: one executor per session

### What it does

`ConnectionSession.executor` returns one shared `DatabaseExecutor` even when
several threads first access the property concurrently. This preserves the
session contract that all work for one DB-API connection is serialized.

### Why the fork needs it

Schema indexing starts concurrent workers for tables, views, and procedures.
Each worker immediately accesses the lazily initialized executor. Without a
lock, multiple workers can each create a single-thread executor, allowing them
to run concurrently on the same DB-API connection. PyMySQL then desynchronizes
its wire protocol and schema loading silently loses tables and procedures.

### How it is implemented

Each `ConnectionSession` owns a `threading.Lock`. The executor property uses
double-checked locking: initialized sessions keep the lock-free fast path, and
only concurrent first access is serialized. The winning thread constructs and
stores the executor; every caller then receives that instance.

### Regression test

`tests/test_session_executor_race.py` releases eight threads from a barrier,
collects the executors returned by one session, and asserts that all eight
references identify the same instance.

### Upstream equivalent

No. Reviewed `origin/main` at `5ad4559` on 2026-09-13. Despite the new theme
and result-rendering work, it still performs an unsynchronized
`if self._executor is None` followed by construction and assignment.

If upstream introduces an equivalent guarantee, drop the fork commit only after
confirming the regression test passes against upstream's implementation.

## Updating

```bash
git fetch origin
git fetch fork
git log origin/main..HEAD
git log HEAD..origin/main
# Reconcile main with fork/main before rebasing; investigate any divergence.
git rebase origin/main
```

Resolve conflicts while preserving the executor invariant, then run:

```bash
nix develop --command pytest tests/test_session_executor_race.py -v
nix develop --command pytest tests/ -v -k sqlite
nix develop --command ruff check \
  sqlit/domains/connections/app/session.py \
  tests/test_session_executor_race.py
```

If any check fails, create a detached pristine worktree at the exact
`origin/main` commit and run the identical command there. A failure is a
baseline only when it reproduces unchanged in that pristine worktree during
the current update; historical failures are not an allowlist. Any fork-only
failure blocks the push.

If a conflict or fork-only failure cannot be resolved confidently, abort the
rebase if one is active, send the documented `Fork sync stopped` notification,
and stop without pushing.

Only after all checks pass:

```bash
git push --force-with-lease fork main
```
