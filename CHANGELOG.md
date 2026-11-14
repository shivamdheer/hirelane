# Changelog

All notable changes are listed here. The format follows Keep a Changelog and the project uses semantic versioning.

## [0.1.0] - 2026-11-14

First public release.

### Added
- Sourcing from public Greenhouse, Lever and Ashby boards with level, location, freshness, pay and knockout filters
  and a deterministic match score.
- A fact bank in YAML and truthful tailoring that only chooses, orders and rewords approved facts. New material is a
  proposal the user confirms.
- One-page ATS-friendly PDF resumes with a gate that audits every line against the fact bank.
- Form filling for the three boards with a verification gate, review mode by default and CAPTCHA handoff.
- Reply tracking, a daily digest, and an optional Google connection for Sheets, Gmail and Calendar.
- A phone-friendly web interface, and the `hirelane demo` command with invented data.
- Pluggable AI providers, all optional: two hosted APIs and any OpenAI-compatible endpoint.
- Scheduling for launchd, systemd and Windows Task Scheduler.
- `hirelane init` to import a PDF or DOCX resume into an editable fact bank.
