# Security

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository (Security tab, then Report a vulnerability). Do not
open a public issue for a security problem. Include what you found, how to reproduce it, and what it lets an attacker
do. You will get a reply within a week. Fixes are released as soon as they are tested, with credit if you want it.

## What Hirelane stores and where

| Item | Where | Notes |
| --- | --- | --- |
| AI provider key | OS keyring, service `hirelane`, name `ai-api-key` | Never written to a file or a log |
| Web interface token | OS keyring, name `web-token` | Optional on loopback, required elsewhere |
| Google OAuth client and token | OS keyring, names `google-client` and `google-token` | Only after `hirelane google connect` |
| Resume, facts, answers, profile | Plain files under `HIRELANE_HOME` | Your own data, kept on your machine |
| Jobs, questions, replies, runs | SQLite under `HIRELANE_HOME/data` | Local only |

The keyring is Keychain on macOS, Secret Service on Linux and Credential Manager on Windows. Containers usually have
none, so a secret can be passed as `HIRELANE_SECRET_<NAME>`, for example `HIRELANE_SECRET_WEB_TOKEN`. That variable
takes priority and is meant only for such hosts.

## Network use

- Public job board APIs are read without credentials.
- Application forms are opened in a separate browser profile (`data/browser-profile`) so your own logins are never
  exposed. The browser refuses to leave the ATS domain it was sent to.
- Resume text and posting text are sent to your AI provider only if you configure one. Text from postings and emails
  is wrapped as data in every request, and a model reply is validated in code before anything uses it.
- Google calls happen only after you connect an account, with these scopes: spreadsheets, Gmail read, Gmail send
  and Calendar read. Gmail send is used for one thing, the digest to your own address.

## Web interface

It listens on loopback by default. It refuses to start on another address without a token. With a token, pages need a
signed session cookie (HTTP only, same-site strict), and form posts must come from the same origin. For access from a
phone, put it behind Tailscale or another private network and keep the token on. Do not expose it to the internet.

## Safety limits that are also security limits

- Review mode is the default. Live submission needs two switches.
- A submit click is recorded before it happens, so a crash cannot cause a second submission.
- Only the job's own resume file is uploaded, and its hash is checked against the one that passed the ATS gate.
- A required question with no rule is never filled with a guess.

## Supported versions

Only the latest release gets fixes.
