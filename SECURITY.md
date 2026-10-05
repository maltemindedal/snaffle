# Security policy

## Supported versions

Security fixes go into the latest release only; earlier versions do not get
backports. Snaffle is not on PyPI, so updating means pulling `main` and running
`uv sync` again.

| Version | Supported |
| --- | --- |
| 3.1.x | Yes |
| < 3.1 | No |

## Reporting a vulnerability

Do not open a public issue, discussion, or pull request for a vulnerability.
Report it privately through GitHub instead:
[open a security advisory](https://github.com/maltemindedal/snaffle/security/advisories/new)
on this repository.

Include what you can of:

- The Snaffle version (`uv run python -c "import snaffle; print(snaffle.__version__)"`),
  the Python version, and the operating system.
- The command line or a minimal script that reproduces the problem, and the
  server response it needs, if any.
- What an attacker gains: who they have to be (the server, a redirect target,
  someone on the network) and what they can read, change, or exhaust.

A confirmed vulnerability is fixed in a new release, and its `CHANGELOG.md`
entry describes it under a `Security` heading.

## Scope

Snaffle is a thin layer over `requests` and `urllib3`, and inherits some of
their defaults on purpose. The [security notes](docs/reference/cli.md#security-notes)
in the CLI reference document them: `~/.netrc` credentials replacing an
`Authorization` header, redirects followed to internal addresses, no limit on
response size on the command line, secrets visible in shell history, and what
`-v` prints. Those are known behaviour, not vulnerabilities, unless you can show
a consequence the notes do not describe.

A vulnerability in a dependency (`requests`, `urllib3`, `tqdm`, or the codecs in
the `speedups` extra) belongs to that project; report it there. Once its advisory
is public, an ordinary issue or pull request asking Snaffle to raise the version
floor is fine.
