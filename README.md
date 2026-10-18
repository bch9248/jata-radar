# 🌏 InternRadar — Japan & Taiwan · Summer 2027

**SWE and MLE / AI internships in Japan and Taiwan, listed by day, newest first.**

Inspired by [JobRadar-AI](https://github.com/Donkey0322/JobRadar-AI). This is a new, complete Python implementation of the tracking workflow rather than a configuration-only copy of the US tracker. No US jobs, original author's addresses, API keys, or old job database are carried over.

[Setup / 中文操作指南](installation.md) · [Sources](docs/SOURCES.md) · [Commands](docs/COMMANDS.md) · [Design & limitations](docs/DESIGN.md) · [Validation](docs/VALIDATION.md)

- Automated ATS + international-list discovery, English / Japanese / Chinese web search.
- Conservative **2027 summer** filtering; Japanese graduation / joining year is not internship year.
- Persistent deduplication, evidence, posting/first-seen date, source health and closed-job archive.
- GitHub Actions daily updates; CSV export. Private local application progress; optional explicit email alerts.
- **Python 3.11+; no third-party runtime packages.** Search and AI are optional and independent.

```bash
python3 -m tracker doctor
python3 -m unittest discover -s tests -v
python3 -m tracker sync
```

With no API keys, configured ATS and community-list sources still run. Broad regional discovery requires `BRAVE_API_KEY` in `.env` or GitHub Actions Secrets. AI is disabled by default; it only extracts evidence and never approves jobs. See [installation.md](installation.md).

> The board lists every open Japan/Taiwan internship found, newest first, with no manual review step. A Notes column shows what a posting has not stated yet (for example summer dates); check the posting before applying. A complete tracker cannot guarantee exhaustive market coverage.

<!-- JOBS:START -->

## SWE — Software Engineering

[Full list](job-postings/swe.md) · 1 listings

### Japan

| Company | Role | Location | Year / season | Eligibility hints | Status | Apply | First seen |
|---|---|---|---|---|---|---|---|
| — | No confirmed listings yet | — | — | — | — | — | — |

### Taiwan

| Company | Role | Location | Year / season | Eligibility hints | Status | Apply | First seen |
|---|---|---|---|---|---|---|---|
| NVIDIA | System Software Engineering Intern, GPU and SOC - Summer 2027 | Taiwan, Taipei | 2027 / summer | Unknown — read JD | open | [Apply](https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Taiwan-Taipei/System-Software-Engineering-Intern--GPU-and-SOC---Summer-2027_JR2026406) | 2026-10-14 |

## MLE / AI — Machine Learning & AI

[Full list](job-postings/mle_ai.md) · 0 listings

### Japan

| Company | Role | Location | Year / season | Eligibility hints | Status | Apply | First seen |
|---|---|---|---|---|---|---|---|
| — | No confirmed listings yet | — | — | — | — | — | — |

### Taiwan

| Company | Role | Location | Year / season | Eligibility hints | Status | Apply | First seen |
|---|---|---|---|---|---|---|---|
| — | No confirmed listings yet | — | — | — | — | — | — |

## Needs review

99 candidates · [Review queue](job-postings/review.md). Unknown year, summer dates, location or page structure is never silently approved.

## Source health

| Source | Last result | Candidates | Note |
|---|---|---|---|
| nvidia | truncated | 74 | Pagination limit reached; increase max_pages |
| rakuten | truncated | 0 | Pagination limit reached; increase max_pages |
| sony-japan | ok | 9 | — |
| speedyapply-international | ok | 25 | — |
| dreamwork-taiwan | ok | 39 | — |
| brave | skipped | 0 | BRAVE_API_KEY not set |

Last sync: 2026-10-18T05:41:56+00:00 · requests: 82

Only a successful job-detail fetch marks a listing open. Source absence, HTTP 403/429 and network failures do not mark it closed. Run `check` weekly; dynamic closed-page messages can still require manual review.

<!-- JOBS:END -->

## Operating the board

Each sync adds newly found positions under their day. `show JOB_ID` prints a job's full evidence; `review JOB_ID rejected --reason ...` hides one you don't want, and `close` hides one that is no longer open. PhD-only titles, Japanese mentions and visa mentions are flagged, not assumed to match your eligibility. There is no citizenship or visa auto-exclusion.

Tables exclude closed listings and ones out of scope (another country or year, full-time roles). All records remain in `data/jobs.json`; `data/jobs.csv` is regenerated automatically. [Closed archive](job-postings/archive.md). Applicant notes live in ignored `.local/` files and never enter the public board.

MIT license; see [NOTICE](NOTICE) for attribution. Third-party job postings and data remain subject to their owners' terms.
