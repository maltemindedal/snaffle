# 1. Selective retries and a pooled session

- **Status:** Accepted
- **Date:** 2026-07-23 (shipped in 1.1.0)

## Context

The original client created a `requests` session per request and retried every
failure three times in a hand-written loop. Two consequences followed.

Every request paid a fresh TCP and TLS handshake, even when hitting the same
host repeatedly. Two hundred requests opened two hundred connections.

And every failure was retried regardless of whether retrying could help. A
`404` cost three round trips to arrive at the same answer it would have given
on the first. A `POST` that failed after reaching the server was re-sent, which
risks acting on the request twice.

## Decision

**Keep one pooled `requests.Session` for the client's lifetime.** An
`HTTPAdapter` with `pool_connections=16` and `pool_maxsize=16` is mounted on
both `http://` and `https://`.

**Move retries into that adapter** as a `urllib3.util.retry.Retry` with
`total=retries - 1`, `backoff_factor=0.3`, `respect_retry_after_header=True`,
and `raise_on_status=False`.

**Restrict retryable statuses** to `{408, 425, 429, 500, 502, 503, 504}`.

**Accept urllib3's method asymmetry rather than flattening it.** urllib3
applies its idempotent-method filter to read errors and to retryable statuses,
but not to connection errors:

| Failure | `GET`, `HEAD`, `PUT`, `DELETE`, `OPTIONS` | `POST`, `PATCH` |
| --- | --- | --- | 
| Connection never established | retried | **retried** |
| Read failure after the request landed | retried | not retried |
| Retryable status | retried | not retried |

A request that never reached the server cannot have been acted on twice, so
retrying it is safe for any method. Once the request is on the wire, a `POST`
may already have been processed, so it is never replayed.

**Stop streaming `GET` by default.** Streaming is enabled only when a progress
bar is being fed. A caller who passes `stream=True` explicitly still gets an
unconsumed response.

**Raise `DOWNLOAD_CHUNK_SIZE` from 8 KiB to 64 KiB.**

## Consequences

A client now owns an operating-system resource. It supports the context manager
protocol and has a `close()` method, and code that creates a client per request
holds sockets open until garbage collection. This is the one breaking change in
the decision, and it was released as a minor version because the previous
behaviour was still correct, only wasteful.

Retries now cost latency they did not before: exponential backoff adds roughly
half a second across the default three attempts for a request destined to fail.
That is the deliberate trade — not hammering a server that is already
struggling.

Retries became untestable through the obvious mock. They happen inside the
adapter, below `Session.request`, so patching `requests.Session.request` cannot
observe them. An earlier revision asserted "a `POST` is never silently re-sent"
against such a mock and shipped a false claim in the README on the strength of
it. The project now tests retry behaviour against a real socket
(`TestRetryAgainstRealServer`) or against the `Retry` object directly
(`TestRetryPolicy`), and `CONTRIBUTING.md` records the trap.
[ADR 0004](0004-inject-the-session.md) adds a third option — passing a session
to the constructor — and supersedes this mitigation, though not the decision
above.

`--progress` downloads hold a larger working set, from the bigger chunk size.

Measured improvements, on the commit that introduced this change:

| Scenario | Before | After |
| --- | --- | --- |
| Repeat HTTPS request to the same host | 24.5 ms | 6.2 ms |
| 100 sequential local GETs (per request) | 1.47 ms | 0.57 ms |
| TCP connections opened per 200 requests | 200 | 1 |
| Request returning a 404 | 4.78 ms | 0.60 ms |

> **TODO(verify):** these figures come from the 1.1.0 changelog entry
> (2026-07-23), measured against `https://example.com` as a median of six
> requests and against a local server. No benchmark script is committed, so
> they cannot be reproduced from the repository. Either commit the harness or
> treat the numbers as a historical record.

## Alternatives considered

**Retry everything, as before.** Simple, and wrong for dead-end statuses. The
`404` case alone tripled latency for a class of request that is common.

**Retry nothing.** Would have removed the backoff latency but given up on
transient failures, which are exactly the case where a retry pays.

**Force idempotency filtering onto connection errors too**, so `POST` is never
retried under any circumstance. Rejected: it would make Snaffle less reliable
than urllib3's default for no safety gain, since a connection that was never
established carries no risk of duplicate processing.
