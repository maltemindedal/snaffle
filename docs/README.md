# Snaffle documentation

Everything written about Snaffle, grouped by what you are trying to do. If you
are not sure where to start, start with [Getting started](getting-started.md).

The documentation follows the [Diátaxis](https://diataxis.fr/) split: learning,
tasks, lookup, understanding.

## Tutorial — learning

For a first pass. Read top to bottom, at a keyboard.

| Document | What it covers | Who it is for |
| --- | --- | --- |
| [Getting started](getting-started.md) | Clone to first request in nine steps: install with uv, make CLI requests, send a JSON body, add headers, read an error, then do the same from Python. | Anyone using Snaffle for the first time. |

## How-to guides — tasks

For a specific goal, when you already know your way around.

| Document | What it covers | Who it is for |
| --- | --- | --- |
| [Use Snaffle as a library](guides/using-as-a-library.md) | Client lifetime, batching requests over one connection, error handling, non-JSON bodies, tuning timeouts and retries, overriding defaults by subclassing. | Developers calling `HTTPClient` from Python. |
| [Download large files](guides/downloading-large-files.md) | Progress bars, what `--progress` actually does, streaming to disk from Python, and the `speedups` extra. | Anyone moving payloads big enough to care. |
| [Troubleshooting](guides/troubleshooting.md) | Symptom-first fixes: `command not found`, import errors, JSON and header parse failures, hangs, missing progress bars, retries that will not reproduce in tests. | Anyone with something not working. |

## Reference — lookup

Exhaustive and factual. Not meant to be read end to end.

| Document | What it covers | Who it is for |
| --- | --- | --- |
| [CLI reference](reference/cli.md) | Every command, alias, and flag; output format; exit codes; what the CLI deliberately does not expose. | Anyone writing a command line or a script. |
| [Python API reference](reference/python-api.md) | `HTTPClient` constructor arguments, attributes, class constants, and methods; the exception hierarchy; the retry table. | Developers integrating the library. |

There is no configuration reference: Snaffle reads no environment variables and
no configuration files. Its entire configuration surface is CLI flags,
constructor arguments, and the class constants documented above.

## Explanation — understanding

The why. Read when you want to know how the pieces fit or why something is the
way it is.

| Document | What it covers | Who it is for |
| --- | --- | --- |
| [Architecture overview](architecture/overview.md) | System context and request-flow diagrams, module responsibilities, the four design commitments, testing strategy, and explicit non-goals. | Contributors, and anyone deciding whether Snaffle fits. |

### Decision records

| ADR | Decision |
| --- | --- |
| [0001 — Selective retries and a pooled session](architecture/decisions/0001-selective-retries-and-connection-pooling.md) | Why retries moved into the adapter, why only seven statuses are retried, why a `POST` is retried on connection failure but never replayed, and why a client must now be closed. |
| [0002 — Lazy imports on the CLI help path](architecture/decisions/0002-lazy-imports-on-the-cli-help-path.md) | Why `requests` is imported in three unusual places, and what guards the saving. |
| [0003 — src-layout and a lowercase package name](architecture/decisions/0003-src-layout-and-a-lowercase-package-name.md) | Why the package moved under `src/`, why it was renamed twice, and why both renames were major versions. |

## Project documents

Outside `docs/`, at the repository root.

| Document | What it covers |
| --- | --- |
| [README](../README.md) | Front door: what Snaffle is, quick start, links back here. |
| [CONTRIBUTING](../CONTRIBUTING.md) | Development setup, conventions, the four checks CI runs, and the retry-testing trap. |
| [CHANGELOG](../CHANGELOG.md) | Every user-visible change, [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format, semantic versioning. |
| [LICENSE](../LICENSE) | MIT License. |

`AGENTS.md` is not project documentation — it holds behavioural guidelines for
LLM coding assistants working in this repository.

## Keeping this index accurate

Every file under `docs/` appears in a table above. Adding a document means
adding a row; the index is the map, and a map missing a road is worse than no
map.
