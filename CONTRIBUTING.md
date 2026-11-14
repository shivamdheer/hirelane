# Contributing

Thanks for looking at hirelane. This file covers how to set it up, what a change should include, and the few rules
that protect users.

## Set up

```
git clone <your fork>
cd hirelane
make install
make browsers      # Chromium for the browser tests, about 100 MB
make lint test
```

Python 3.11 or newer. `make demo` starts the web interface on invented data so you can look at every page.

## What a change should include

- A test. Tests use fixtures and the fictional candidate Alex Rivera in `tests/profile_fixture.py` and
  `tests/bank_fixture.py`. Nothing in the suite may use the network. Board APIs are mocked with `httpx.MockTransport`
  and forms are local HTML files under `tests/fixtures/forms`.
- Type hints on public functions. `mypy hirelane` is clean and CI runs it.
- No new dependency unless it removes more code than it adds. Optional features go behind an extra in `pyproject.toml`.
- Comments only where they explain why. Names should say what.

## Rules that protect users

These are the parts of the design that a change must not weaken. A pull request that touches one needs a clear
reason and a test.

1. **Truthfulness.** A resume line must come from the fact bank. Rewording goes through `truth.check_rewrite`, and
   `ats_gate.check_pdf` audits the finished file. Anything new becomes a proposal for the user to confirm.
2. **Review mode is the default.** Live submission needs both `submit_mode: live` and `HIRELANE_ALLOW_LIVE=1`.
3. **CAPTCHAs go to a person.** There is no code path that solves one and there will not be.
4. **No guessing.** A required form question with no answer rule goes to the user. It is never filled with a plausible
   value.
5. **Secrets stay in the keyring.** Nothing secret goes in a config file, the database, a log or a test fixture.
6. **The digest goes to the profile's address and nowhere else.** There is no setting for another recipient.

## Adding a job board

An adapter is a small class in `hirelane/submit/`. It names the form URL, the submit button and the confirmation
text, and the shared base does the scanning, planning and filling. A source for a new board's public API goes in
`hirelane/sources/` with a `parse` function that is tested on a saved response. See `docs/ARCHITECTURE.md`.

## Commits and pull requests

Short imperative subjects, under 60 characters, with a plain body when the reason is not obvious. Keep a pull request
to one idea. The template asks what changed, why, and how it was checked.

## Reporting a problem

Bugs and ideas go in issues. Security problems go through the process in `SECURITY.md`, never a public issue.
