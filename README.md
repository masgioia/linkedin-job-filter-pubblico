# LinkedIn Job Filter

Public demo repository for a Python workflow that collects job listings through Apify, evaluates them with Google Gemini, and exports ranked results to CSV and JSON.

## Features

- Collects job listings using an Apify task.
- Scores role fit, compensation likelihood, AI relevance, and work sustainability.
- Records evidence, inferences, unknowns, strengths, and risks.
- Exports CSV and JSON locally.
- Includes a manually triggered GitHub Actions workflow.

## Configuration

Required environment variables:

- `APIFY_API_TOKEN`
- `APIFY_TASK_ID`
- `GEMINI_API_KEY`
- Optional: `GEMINI_MODEL` (defaults to `gemini-3.5-flash-lite`)

Create a local `job_search_profile.md` containing your own profile. That file, results, environment files, and Python caches are excluded by `.gitignore`. Never commit API keys or personal job-search criteria.

Install dependencies with `pip install -r requirements.txt`, set the environment variables, and run `python app.py`.

For GitHub Actions, configure `APIFY_API_TOKEN`, `APIFY_TASK_ID`, `GEMINI_API_KEY`, and `JOB_SEARCH_PROFILE` as repository secrets. The workflow is manual only and does not upload results as artifacts.

## Privacy

Public repositories and their commit history are visible to everyone. Do not add personal profiles, search results, or credentials. The workflow avoids logging job titles and company names.

## License

No license is provided. Public visibility alone does not grant permission to reuse or distribute this code.
