# Command reference

Run from the extracted repository root. No installation is needed.

| Command | Purpose |
|---|---|
| `python3 -m tracker doctor` | Validate config and report credential presence, never print key values |
| `python3 -m tracker sync` | Direct sources + optional rotating web search + detail fetch + render |
| `python3 -m tracker sync --no-search` | Direct sources only |
| `python3 -m tracker sync --source nvidia` | One enabled source, no search |
| `python3 -m tracker sync --offline` | Render existing data without network |
| `python3 -m tracker render` | Generate README, category pages, review/archive and CSV |
| `python3 -m tracker list --country Japan --category MLE_AI` | Filter records |
| `python3 -m tracker list --decision review` | List review candidates |
| `python3 -m tracker show JOB_ID` | Show description and classification/evidence/audit record |
| `python3 -m tracker add URL` | Fetch one job and store it; failure leaves a review candidate |
| `python3 -m tracker add URL --title TITLE --location LOCATION --company COMPANY --no-fetch` | Manual hint for blocked pages |
| `python3 -m tracker import FILE.json` | Import array of candidate job objects; never auto-confirms imports |
| `python3 -m tracker review JOB_ID confirmed --country Japan --category MLE_AI --reason "Verified summer 2027 dates"` | Audited manual confirmation |
| `python3 -m tracker review JOB_ID rejected --reason "Full-time new-graduate position"` | Reject; preserved across future sync |
| `python3 -m tracker review JOB_ID reset --reason "Re-evaluate automatically"` | Remove manual decision |
| `python3 -m tracker check` | Recheck due records, budget-limited |
| `python3 -m tracker check --id JOB_ID --force` | Recheck one record now |
| `python3 -m tracker close JOB_ID closed --reason "Employer removed the position"` | Manual closure; can use open/unknown instead |
| `python3 -m tracker application JOB_ID applied --notes "Submitted CV"` | Private local state |
| `python3 -m tracker list --applications` | Include private application status |
| `python3 -m tracker notify --preview` | Preview notification without sending or marking sent |
| `python3 -m tracker notify` | Explicit SMTP send, independent from scheduled sync |
| `python3 -m unittest discover -s tests -v` | Offline regression suite |

Application states: `saved`, `applied`, `interview`, `offer`, `rejected`, `withdrawn`.

The `data/jobs.csv` export contains public job metadata only. For importing use a JSON array of objects with `url`, `title`, and optionally `company`, `location`, `description`, `employment_type`. Example (fictional, not an actual listing):

```json
[
  {
    "url": "https://example.org/jobs/123",
    "company": "Example Company",
    "title": "Software Engineering Intern — Summer 2027",
    "location": "Tokyo, Japan",
    "description": "Internship runs in July and August 2027."
  }
]
```

Run `render` after editing existing public data. Prefer CLI review commands over directly changing computed classification fields, which sync recalculates.
