# 3. src-layout and a lowercase package name

- **Status:** Accepted
- **Date:** 2026-07-23 (shipped in 2.0.0 and 3.0.0)

## Context

The package sat at the repository root and was named with a capital letter.
Both caused problems.

**Flat layout hid packaging bugs.** Because the package directory was on
`sys.path` by virtue of being the working directory, tests imported the source
tree directly. Anything that was in the repository but not in the built
distribution still passed — the tests could not tell the difference between
"works" and "works when run from the checkout".

**A capitalised import package contradicts PEP 8**, which says Python packages
should have short, all-lowercase names. It also made the import name
case-sensitively different from the distribution and console script names,
which is a reliable source of confusion.

Separately, two entry-point defects were visible:

- The console script pointed at `cli:main`, so `Ctrl+C` during a request exited
  with a `KeyboardInterrupt` traceback. `python -m snaffle` went through
  `__main__:run` and exited cleanly. The two entry points behaved differently.
- `argparse` derived its usage line from `sys.argv[0]`, so the same help text
  read `usage: snaffle`, `usage: __main__.py`, or `usage: cli.py` depending on
  how it was launched.

## Decision

**Adopt the [src-layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
recommended by the PyPA.** The package lives at `src/snaffle/`, and
`[tool.setuptools.packages.find]` is configured with `where = ["src"]`. Tests
exercise the installed distribution.

**Lowercase the import package** to `snaffle` (2.0.0), then rename the project
to Snaffle throughout — import package, distribution, and console script all
`snaffle` (3.0.0).

**Point the console script at `snaffle.__main__:run`**, not `cli:main`, so both
entry points get the same `KeyboardInterrupt` handling.

**Pin `prog="snaffle"` on the parser** so the usage line is the same regardless
of how the program was launched.

**Ship a PEP 561 `py.typed` marker** and verify in CI that the built wheel
contains it. The package had been `mypy --strict` clean for some time, but
without the marker downstream type checkers ignored every annotation.

## Consequences

Both renames are breaking changes to the public API, and both were released as
major versions. `CONTRIBUTING.md` records the rule: the import package name is
part of the public API, so renaming it is a major bump.

Code written against the old names breaks:

```python
from PyFetch import HTTPClient   # 1.x — gone
from Snaffle import HTTPClient   # never existed as such
from snaffle import HTTPClient   # 2.0.0 onward
```

Nothing bridges the gap. No compatibility shim or deprecation alias was added,
because the project has no known external consumers to protect.

`mypy` needs `mypy_path = "src"` to find the package, and needs `build/` and
`dist/` excluded — after a build those directories contain a second copy of the
package, and `mypy .` fails with "Duplicate module named 'snaffle'". Both are
configured in `pyproject.toml`. Stale `*.egg-info/` directories from before the
renames cause the same failure and have to be deleted by hand.

Running the CLI now requires the package to be installed. `python cli.py` from
the checkout no longer works, which is the point.

## Alternatives considered

**Keep the flat layout.** Cheaper, and it leaves the packaging blind spot in
place — the class of bug where the wheel is missing a file that the tests never
notice. Shipping `py.typed` without noticing it was missing from the wheel is
exactly that class.

**Rename the import package but keep the old distribution name.** Would have
halved the churn but left the import name, distribution name, and command name
disagreeing, which is the confusion the rename was meant to end.

**Add a deprecation shim** re-exporting from the old names for a release. Worth
doing for a package with users; unnecessary here.
