# LinkedIn Job Filter

Public demo repository for a Python workflow that collects job listings through Apify, evaluates them with Google Gemini, and exports ranked results to CSV and JSON.

## Tests

Run the automated tests locally with `python -m unittest discover -s tests -v`. They use mocked API responses and do not require API credentials or incur external API costs. A successful unit-test run does not replace a live workflow run with valid Apify and Gemini configuration.

## Features

- Collects job listings using an Apify task.
- Screens jobs first; only retained listings receive the detailed assessment and appear in the final CSV/JSON. A retained job can still receive a detailed `SKIP` recommendation.
- Scores role fit, compensation likelihood, AI relevance, and work sustainability.
- Records evidence, inferences, unknowns, strengths, and risks.
- Exports CSV and JSON locally.
- GitHub Actions runs unit tests on pushes and pull requests. A live Apify/Gemini run is separately and manually enabled to avoid accidental API usage.

## Configuration

For local execution, set these environment variables:

- `APIFY_API_TOKEN` — Apify API credential.
- `APIFY_TASK_ID` — ID of the Apify task to run.
- `GEMINI_API_KEY` — Google Gemini API credential.
- Optional: `GEMINI_MODEL` (defaults to `gemini-3.5-flash-lite`).

Create a local `job_search_profile.md` containing your own profile. The program uses this file when it exists; otherwise, it falls back to `job_search_profile.example.md`. Do not commit personal job-search criteria or API credentials.

### GitHub Actions setup

In **Settings → Secrets and variables → Actions**, create these two **repository secrets**:

- `APIFY_API_TOKEN`
- `GEMINI_API_KEY`

Create this **repository variable** (not a secret):

- `APIFY_TASK_ID` — the ID of the Apify task to run. A task ID is configuration, not an API credential.

Optionally create the repository variable `GEMINI_MODEL` to override the default model.

The workflow uses `job_search_profile.example.md` automatically. No `JOB_SEARCH_PROFILE` secret is required. This means the public workflow evaluates jobs against the generic example criteria, not your personal profile. To use personal criteria in GitHub Actions, run the workflow from a private repository containing your private `job_search_profile.md`, or deliberately configure a private profile-delivery mechanism; do not commit personal criteria to a public repository.

The workflow runs mocked unit tests on pushes and pull requests without API credentials or external API costs. To run against Apify and Gemini, open **Actions → Job filter → Run workflow** and explicitly set **run_live** to true. This live run requires the secrets and variable listed above and may consume API credits. On completion, it uploads the `results/` directory as the `linkedin-job-filter-results` artifact, retained for 14 days.

### Ranking logic

Results are sorted hierarchically, not by a single combined score: `fit_score` first, then `income_score`, then `ai_score`, then `low_stress_score`, all descending. A higher fit score therefore takes precedence over a higher score in a later criterion. The CSV does not currently contain a calculated composite score.

## Privacy

Public repositories and their commit history are visible to everyone. Do not add personal profiles, search results, or credentials to tracked files.

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE) for the full text.
