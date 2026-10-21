# LinkedIn Job Filter

Public demo repository for a Python workflow that collects job listings through Apify, evaluates them with Google Gemini, and exports ranked results to CSV and JSON.

## Features

- Collects job listings using an Apify task.
- Scores role fit, compensation likelihood, AI relevance, and work sustainability.
- Records evidence, inferences, unknowns, strengths, and risks.
- Exports CSV and JSON locally.
- Includes a manually triggered GitHub Actions workflow.

## Configuration

For local execution, set these environment variables:

- `APIFY_API_TOKEN` — Apify API credential.
- `APIFY_TASK_ID` — ID of the Apify task to run.
- `GEMINI_API_KEY` — Google Gemini API credential.
- Optional: `GEMINI_MODEL` (defaults to `gemini-3.5-flash-lite`).

Create a local `job_search_profile.md` containing your own profile. Use `job_search_profile.example.md` as a template. Do not commit personal job-search criteria or API credentials.

### GitHub Actions setup

In **Settings → Secrets and variables → Actions**, create these **repository secrets**:

- `APIFY_API_TOKEN`
- `GEMINI_API_KEY`
- `JOB_SEARCH_PROFILE` — the full text of your profile, which the workflow writes to a temporary `job_search_profile.md` file during the run.

Create this **repository variable** (not a secret):

- `APIFY_TASK_ID` — the ID of the Apify task to run. A task ID is configuration, not an API credential.

Optionally create the repository variable `GEMINI_MODEL` to override the default model.

The workflow is manual only. On completion, it uploads the `results/` directory as the `linkedin-job-filter-results` artifact, retained for 14 days. Download it from the workflow run page.

## Privacy

Public repositories and their commit history are visible to everyone. Do not add personal profiles, search results, or credentials to tracked files. Store your profile in the `JOB_SEARCH_PROFILE` secret when using GitHub Actions.

## License

No license is provided. Public visibility alone does not grant permission to reuse or distribute this code.
