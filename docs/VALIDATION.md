# Package validation — 2026-10-12

- **60 offline regression tests passed** on Python 3.12.14.
- CLI doctor, offline render and Python compilation passed.
- All GitHub workflow / issue-form YAML parsed successfully.
- Fixture-based complete sync exercised ATS discovery → detail → classification → persistent deduplication → README/category pages/CSV, including repeat sync, failure reporting and manual review/privacy behavior.
- Direct HTTP probes through the build environment's HTTP transport returned 200 from NVIDIA, Rakuten and Sony Japan listing endpoints; NVIDIA's specific JR2026298 detail returned a valid `jobPostingInfo` object. The adapter extracted Taiwan/Taipei and correctly left its year-only title in review because summer dates were not confirmed.
- Both community raw Markdown URLs returned 200. The actual source text parsed into 22 country-matched rows from SpeedyApply and 37 from Dreamwork Taiwan. These counts are discovery candidates, including non-summer/RDSS roles, **not confirmed summer 2027 jobs**. Live parsing exposed and fixed the `Posting` column + HTML link format and the linked-role/no-application-column format.
- A normal `python3 -m tracker sync --no-search` attempt was stopped by the public-address guard because direct hostname DNS resolution is unavailable in this build environment. Successful separate HTTP probes do not constitute a complete production CLI sync. The delivered networking guard remains enabled.
- Broad Brave discovery and optional OpenAI/SMTP operations were tested with mocks, not real user credentials. No emails were sent and no GitHub repository was created or published.

The packaged public database is intentionally empty, with no synthetic jobs or build-environment failure records. Your first live sync populates current data and source health. Check that first Actions/local run before relying on updates. Source interfaces and hiring availability can change.
