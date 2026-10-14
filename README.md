# 🌏 InternRadar — Japan & Taiwan · Summer 2027

**SWE and MLE / AI internships, with separate Japan and Taiwan tables.**

Inspired by [JobRadar-AI](https://github.com/Donkey0322/JobRadar-AI). This is a new, complete Python implementation of the tracking workflow rather than a configuration-only copy of the US tracker. No US jobs, original author's addresses, API keys, or old job database are carried over.

[Setup / 中文操作指南](installation.md) · [Sources](docs/SOURCES.md) · [Commands](docs/COMMANDS.md) · [Design & limitations](docs/DESIGN.md) · [Validation](docs/VALIDATION.md)

- Automated ATS + international-list discovery, English / Japanese / Chinese web search.
- Conservative **2027 summer** filtering; Japanese graduation / joining year is not internship year.
- Persistent deduplication, evidence, first-seen date, source health, manual review and closed-job archive.
- GitHub Actions daily updates; CSV export. Private local application progress; optional explicit email alerts.
- **Python 3.11+; no third-party runtime packages.** Search and AI are optional and independent.

```bash
python3 -m tracker doctor
python3 -m unittest discover -s tests -v
python3 -m tracker sync
```

With no API keys, configured ATS and community-list sources still run. Broad regional discovery requires `BRAVE_API_KEY` in `.env` or GitHub Actions Secrets. AI is disabled by default; it only extracts evidence and never approves jobs. See [installation.md](installation.md).

> This ZIP starts with an empty job database. It does not claim that every company has opened 2027 summer hiring. Run a live sync in your environment to populate it. Unknown dates/eligibility remain visible in the review queue. A complete tracker cannot guarantee exhaustive market coverage.

<!-- JOBS:START -->

## SWE — Software Engineering

[Full list](job-postings/swe.md) · 2 listings

### Japan

| Company | Role | Location | Year / season | Eligibility hints | Status | Apply | First seen |
|---|---|---|---|---|---|---|---|
| — | No confirmed listings yet | — | — | — | — | — | — |

### Taiwan

| Company | Role | Location | Year / season | Eligibility hints | Status | Apply | First seen |
|---|---|---|---|---|---|---|---|
| NVIDIA | System Software Engineering Intern, GPU and SOC - Summer 2027 | Taiwan, Taipei | 2027 / summer | Unknown — read JD | open | [Apply](https://nvidia.wd5.myworkdayjobs.com/nvidiaexternalcareersite/job/Taiwan-Taipei/System-Software-Engineering-Intern--GPU-and-SOC---Summer-2027_JR2026406) | 2026-10-14 |
| Nvidia | System Software Engineering Intern, GPU and SOC - Summer 2027 | Taiwan, Taipei, TW | 2027 / summer | Unknown — read JD | open | [Apply](https://www.dreamworkhq.com/job/ac2dc067-93ab-4253-afdf-5829a71a5aa1) | 2026-10-14 |

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

71 candidates · [Review queue](job-postings/review.md). Unknown year, summer dates, location or page structure is never silently approved.

## Source health

| Source | Last result | Candidates | Note |
|---|---|---|---|
| nvidia | ok | 9 | — |
| rakuten | ok | — | — |
| sony-japan | ok | 9 | — |
| speedyapply-international | ok | 23 | — |
| dreamwork-taiwan | ok | 36 | — |
| brave | skipped | — | BRAVE_API_KEY not set |

Last sync: 2026-10-14T01:05:35+00:00 · requests: 87

Only a successful job-detail fetch marks a listing open. Source absence, HTTP 403/429 and network failures do not mark it closed. Run `check` weekly; dynamic closed-page messages can still require manual review.

<!-- JOBS:END -->

## Operating the board

Use `python3 -m tracker list --decision review` to inspect candidates, and `show JOB_ID` to read evidence. Confirm only after verifying the actual 2027 summer internship period. PhD-only titles, Japanese mentions and visa mentions are flagged, not assumed to match your eligibility. There is no citizenship or visa auto-exclusion.

Tables exclude closed and rejected listings. All records remain in `data/jobs.json`; `data/jobs.csv` is regenerated automatically. [Closed archive](job-postings/archive.md). Applicant notes live in ignored `.local/` files and never enter the public board.

MIT license; see [NOTICE](NOTICE) for attribution. Third-party job postings and data remain subject to their owners' terms.
