# 4. Inject the session

- **Status:** Accepted
- **Date:** 2026-08-01

## Context

[ADR 0001](0001-selective-retries-and-connection-pooling.md) moved retries into
the session's `HTTPAdapter` and recorded the consequence: retries became
invisible to the obvious mock. They run inside urllib3, below
`requests.Session.request`, so patching that name cannot observe them. The
project had already shipped a false claim on exactly that mistake — "a `POST`
is never silently re-sent", asserted against such a mock, and wrong.

The mitigation ADR 0001 chose was documentation: `CONTRIBUTING.md` names the
trap, and the two ways around it are a real socket
(`TestRetryAgainstRealServer`) or an assertion about the `Retry` object
(`TestRetryPolicy`).

That accepted the hazard as permanent, and the reason it looked permanent was a
missing seam rather than anything about retries. `HTTPClient.__init__`
constructed its own session — `self.session = self._build_session(retries)` —
so the client declared no point at which its transport could be replaced.
Substitution could only happen by patching, and the only name available to
patch, `requests.Session.request`, sits in the gap between the client's
interface and the adapter: below the thing being tested, above the thing that
does the retrying. Eleven tests patch it. For the behaviour those eleven cover
— method validation, exception translation, the progress delegation — it is the
right tool. For retries it is a trap with a warning sign on it.

## Decision

**Accept a session instead of only constructing one.**

```python
def __init__(self, timeout=30, retries=3, verbose=False, show_progress=False,
             session: requests.Session | None = None) -> None:
```

`_build_session(retries)` stays and remains the default, so the out-of-the-box
client is unchanged. The parameter is last, so existing positional calls are
unaffected.

**A client closes only a session it built.** `__init__` records whether it
built the session; `close()` — and therefore `__exit__` — is a no-op for one it
was given. A caller may be sharing that session with other clients or with code
that outlives this one, and closing it would pull the pool out from under them.

**`retries` does not apply to a session that was passed in.** The retry policy
and the connection pool both come from the session's mounted adapters, so they
arrive with the session. `retries` builds the default session and nothing else.
It remains validated and remains readable on `client.retries`.

**Passing `retries` and `session` together is not an error.** The two are not
contradictory: a caller who mounts a five-attempt adapter may reasonably want
`client.retries` to report `5`, since that attribute is public and documented.
The interaction is stated in the constructor docstring, in the API reference,
and in `CONTRIBUTING.md` instead.

**This supersedes the mitigation in ADR 0001's Consequences, not its decision.**
Retries still live in the adapter; they are still invisible to a
`requests.Session.request` mock; the method asymmetry is unchanged. What changes
is that "test against a real socket or against the `Retry` object" is no longer
the complete list of options.

## Consequences

Retry behaviour is observable at Snaffle's own interface without a socket.
`TestRetryWithoutASocket` mounts a real `HTTPAdapter`, carrying the client's own
`Retry`, over a pool whose every connection attempt fails before a socket is
opened, and counts the attempts. It shows a `POST` being re-attempted three
times on connection failure — the claim that was once asserted falsely — in
about the time a mock takes.

That test reaches into urllib3: the retry loop lives inside
`HTTPConnectionPool.urlopen`, so the double has to sit under `urlopen`, and the
lowest point above the socket is the private `_new_conn`. The coupling is
narrower than it looks — one method, one exception type — but it is coupling to
a private name, and it is recorded in the double's docstring.
`TestRetryAgainstRealServer` stays, and remains the only test that exercises the
whole stack.

The eleven `@patch("requests.Session.request")` tests were left alone. The mock
is still correct above the adapter, and rewriting them would have churned every
test in the module for no change in what is covered. The trap they can fall
into is unchanged, and so is the warning in `CONTRIBUTING.md`.

**The public interface now names a `requests` type.** This is the real cost.
[ADR 0002](0002-lazy-imports-on-the-cli-help-path.md) works to keep `requests`
off the import path, and `HTTPClient.__init__` now has a parameter annotated
`requests.Session | None`. There is no new start-up cost — `http_client.py`
already imports `requests` at module scope, and `http_client` is itself imported
lazily, which is what ADR 0002 actually protects; the guards in
`tests/test_init.py` and `tests/test_cli.py` still pass unchanged. But the
*interface* now mentions a third-party type on the way in, where before it did
so only on the way out, as the `requests.Response` every request method returns.
Snaffle is a thin layer over `requests` and has never hidden it, so this states
something that was already true; it is still a widening of what the constructor
commits to.

Two rules now have to be documented rather than inferred: that a supplied
session does not get `retries`, and that the client will not close it. Both are
in the class docstring, the constructor docstring, the API reference, and
`CONTRIBUTING.md`. A rule that lives only in the code is a rule that gets
broken, and this one has a footgun on the other side of it.

## Alternatives considered

**Keep patch-only substitution.** The status quo, and it costs nothing to
leave alone. It also leaves the seam in the one place where it cannot see the
behaviour ADR 0001 exists for, and leaves `CONTRIBUTING.md` warning contributors
away from the only substitution point the client offers. A warning is a weaker
guarantee than a seam: it works exactly as long as everyone reads it, and this
project has already shipped the failure it warns about.

**Take a `Retry` or an `HTTPAdapter` instead of a session.** Narrower, and it
looks like it dodges the ADR 0002 cost — but it does not, since both are also
third-party types, and it dodges nothing else either. Adapters are mounted per
scheme, so accepting one means deciding on the caller's behalf where it is
mounted, and it still would not let a test replace the transport as a whole.

**Take a callable instead — a `send` function or a protocol Snaffle defines.**
Would keep `requests` out of the signature. It would also mean inventing an
interface for a library that already has one, converting between it and
`requests` at the boundary, and giving callers a seam that fits nothing they
already own. Speculative abstraction to avoid naming a type the module already
imports.

**Raise `ValueError` when `retries` and `session` are passed together.** The
case for it is that silently inert configuration is the same class of hazard
this ADR closes. The case against won: `retries` has a real default, so the only
implementable check compares the value against `3` and would let an explicit
`retries=3` through while rejecting a legitimate `retries=5` that a caller
passed to describe their own adapter. Detecting intent instead would mean a
sentinel default, which changes the documented signature for a check nobody
asked for. The interaction is documented and tested
(`test_retries_do_not_reach_an_injected_session`) instead.

**Close the injected session anyway**, so `close()` means one thing. Simpler to
describe and worse to use: a shared session closed by whichever client finished
first is a bug the caller cannot see coming, and it makes a client
non-composable with any code that owns a session. The asymmetry is worth its two
lines.
