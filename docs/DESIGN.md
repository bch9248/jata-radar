# Design, data and maintenance

## Pipeline

1. Load validated config and enabled sources.
2. Collect internship titles from ATS listings or country-matched community tables. Rotate optional regional Web Search queries.
3. Canonicalize URLs and deduplicate. Workday requisitions survive locale/path variants; identity parameters such as `gh_jid` are retained.
4. Fetch structured Workday / Greenhouse / Lever or single-job JSON-LD details. HTML-only pages remain candidates for review.
5. Require actual Japan/Taiwan workplace, internship signal, SWE or MLE/AI title, explicit summer and target internship year for automatic confirmation. Graduation / joining-year sentences are ignored. Unknowns are retained for manual review.
6. Save atomic JSON, generate README/category tables and CSV, record source failures and deferred requests. Recheck due links separately.

## Deliberate conservative behavior

- Classification primarily uses the role title. An AI company recruiting a backend intern stays SWE; an ML engineer or AI researcher title goes in MLE/AI. A generic researcher title can need review.
- Unknown visa support, language and degree eligibility are not invented. PhD titles and Japanese/visa mentions are hints. No profile or graduation-date match is claimed.
- 2027 new-graduate entry is distinct from a 2027 internship; real summer 2026 postings are rejected. Yearless/flexible internships remain review candidates.
- Generic HTML or a listing page cannot automatically confirm a job. JSON-LD with multiple JobPosting objects is treated as a listing page.
- Imported candidates are unverified, even if they contain text saying summer 2027; manual confirmation is required.
- Search result URLs without an independently fetchable page are transient; manually add an inaccessible role if you want it retained.
- Cross-platform semantic deduplication is not guaranteed. The same requisition on 104 and an employer ATS may appear twice. Manual rejection can suppress a duplicate; it survives future sync.
- A successful detail request marks a listing open, but a site returning a 200 “job closed” HTML page can remain uncertain. `check` requires two consecutive HTTP 404/410 checks to close; network errors/403/429 never close. Expired structured `validThrough` dates can close after `check`. Manual closure is available.
- A manual classification decision persists; live fetches may refresh link availability. `review reset` restores automatic classification.
- Per-source pagination and per-run detail/search budgets protect cost/runtime. Exhausted pages are marked truncated. Details rotate to reduce starvation; query groups rotate across runs. Broader discovery isn't exhaustive.

## Files

| Path | Contents |
|---|---|
| `config.json` | Target and budgets, optional AI model |
| `sources.json` | Direct discovery adapters |
| `search-queries.json` | Multilingual regional query rotation |
| `data/jobs.json` | Public job evidence, timestamps, source names, decisions and manual review |
| `data/state.json` | Search/detail rotation cursors |
| `data/source-health.json` | Last discovery run, errors and budget totals |
| `data/check-health.json` | Last link recheck |
| `data/jobs.csv` | Generated public metadata; CSV formula prefixes escaped |
| `job-postings/*.md` | Generated SWE / MLE-AI / review / closed boards |
| `.local/applications.json` | Private local application states and notes |
| `.local/notified.json` | Local notification deduplication |
| `.env` | Ignored credentials, auto-loaded without executing code |

Run one local writer at a time. Atomic file replacement prevents partial files but this is not a multi-process database. Actions concurrency serializes scheduled runs. Pull before manual changes to avoid conflicts with bot commits. Use `git revert` to undo unwanted public changes.

## Network and privacy

Standard-library HTTPS with TLS verification, bounded response size/timeouts, limited retries, per-host delays, explicit redirect handling and public-address checks. Public HTML reads respect robots.txt; unknown policies are skipped. Tokens never follow redirects. DNS public-address checks reduce SSRF exposure but do not implement a hardened pinned-IP proxy; run this personal tool on a normal user workstation/Actions runner, not as an untrusted multi-user service.

No credentials, personal applications or notifications from the supplied original repo are reused. Automated workflows receive only the optional search/AI keys; tests never use live secrets or the network. Pull-request workflows have read-only permissions and no configured secrets. Issues are suggestions, not privileged shell commands: maintainers manually add/verify them.

AI is opt-in; only validated verbatim excerpts are stored and classification remains deterministic. Do not paste confidential applicant data into public job records or imported descriptions. Optional SMTP sending is separate from sync and requires an explicit CLI command.

## Maintenance and tests

Tests cover target filtering, Japanese cohort years, multilingual classification, Workday URL identity, structured/detail parsers, listing adapters, pagination, errors, review persistence, private state, rendering and a fixture-based complete sync. `doctor` validates the editable source configuration. The runtime has no third-party dependencies; CI checks Python 3.11–3.13.

If a website changes: inspect health; reproduce one source using `sync --source SOURCE_ID`; update its URL/adapter; add a fixture for the new response; run the suite. Disable a broken source while keeping manual/search discovery. Do not force-push to resolve Actions conflicts.
