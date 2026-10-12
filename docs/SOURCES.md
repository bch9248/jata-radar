# Regional sources and coverage

The executable source inventory is `sources.json`; rotating Web Search queries are in `search-queries.json`. These are intentionally separate from employer watch pages. A search/program page is not a confirmed job listing.

## Enabled direct discovery

| Source | Adapter | URL | Behavior |
|---|---|---|---|
| NVIDIA | Workday CXS | https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite | Internship listing + detailed job description; target location filtering |
| Rakuten | Workday CXS | https://rakuten.wd1.myworkdayjobs.com/RakutenInc | English and Japanese internship searches; cohort-year caution |
| Sony Japan | Workday CXS | https://sonyglobal.wd1.myworkdayjobs.com/SonyJapanCareers | Research and engineering internships; uncertain summer dates → review |
| SpeedyApply international list | Markdown / HTML tables | https://github.com/speedyapply/2027-SWE-College-Jobs/blob/main/INTERN_INTL.md | Discovery hints only, fetch actual job detail |
| Dreamwork Taiwan list | Markdown / HTML tables | https://github.com/dreamworkhq/Tech-Internships-2027/blob/main/international/taiwan.md | Taiwan-specific hints, fetch actual job detail |

Workday CXS is a site endpoint and can change or block automated traffic. Greenhouse and Lever documented public listing adapters are implemented and tested but their sample entries are disabled: there is no invented employer board ID. Community tables may change shape; zero candidates is possible and means “none parsed/matched,” not proof of no hiring.

## Regional search / manual watch links

All entries below are included in English/Japanese/Chinese queries or company-focused queries. They are not claimed to offer unrestricted scraper APIs or guaranteed summer-intern listings.

| Region | Source | Watch link |
|---|---|---|
| Taiwan | 104 | https://www.104.com.tw/jobs/search/?keyword=2027%20%E5%AF%A6%E7%BF%92 |
| Taiwan | Cake | https://www.cake.me/jobs |
| Taiwan | Yourator | https://www.yourator.co/jobs |
| Taiwan | LINE | https://careers.linecorp.com/jobs/ |
| Taiwan / Japan | Google | https://www.google.com/about/careers/applications/jobs/results/?q=2027%20intern |
| Taiwan / Japan | Amazon | https://www.amazon.jobs/en/search?base_query=2027+intern |
| Japan | Wantedly | https://www.wantedly.com/projects |
| Japan | Japan Dev | https://japan-dev.com/jobs |
| Japan | TokyoDev | https://www.tokyodev.com/jobs |
| Japan | Mercari | https://careers.mercari.com/ |
| Japan | Preferred Networks | https://www.preferred.jp/en/careers/internship/ |
| Japan | Sony internship | https://www.sony.com/ja/SonyInfo/Jobs/internship/ |
| Japan | Rakuten student events | https://global.rakuten.com/corp/careers/graduates/event/ |

Company searches also include Microsoft, MediaTek, TSMC, Appier, Trend Micro and Woven. This covers multiple discovery routes, not every employer. Japan Dev / TokyoDev tend to include many regular engineering jobs; only actual internship candidates pass this tracker's filter. Generic event/program pages can remain in review until a specific role and dates are verified.

## Adding a direct ATS source

For a Greenhouse URL like `https://job-boards.greenhouse.io/BOARD`, set `type: greenhouse`, `board: BOARD`, `company` and a unique `id`; enable it. For Lever `https://jobs.lever.co/BOARD`, use `type: lever`. Validate the board by opening it before enabling it. Copy one of the disabled example objects in `sources.json`.

For Workday, set the board-root URL (no `/job/...` suffix), `type: workday`, `company`, and `search_terms`. This implementation supports `tenant.wdN.myworkdayjobs.com/Board` URLs, not arbitrary Workday recruiting hosts. For other sites, add targeted search queries or use manual URL import.

## Search API usage

Uses the documented [Brave Web Search API](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started), `X-Subscription-Token` authentication, `q`, `count`, and `country`. Only navigates result URLs; discards search titles/snippets. Stored titles and descriptions come from independently fetched pages or user-provided imports, not a republished search-results database. Use the provider's current permitted plan and terms; no quota/rate-limit bypass is implemented.

## Reference documentation / source audit

Source URLs were researched on 2026-10-12. Direct HTTP probes reached the five enabled source URLs, and both real community table formats were parsed. The complete CLI sync still requires validation from your machine/Actions because this environment cannot resolve origin DNS for the public-address guard. See [VALIDATION.md](VALIDATION.md) for exact checks; fixture tests are not a claim of exhaustive live coverage.

- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat/create)

Do not infer “open for summer 2027” from a company having an internship website. Verify role-specific dates and requirements.
