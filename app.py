import csv
import json
import os
import time
from pathlib import Path

import requests

APIFY_TASK_ID = os.environ.get("APIFY_TASK_ID", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
APIFY_API = "https://api.apify.com/v2"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)
OUTPUT_DIR = Path("results")
COLUMNS = [
    "title", "company", "location", "url", "posted_at",
    "fit_score", "income_score", "ai_score", "low_stress_score",
    "recommendation", "assessment", "evidence", "inferences",
    "unknowns", "strengths", "risks",
]


def start_apify():
    token = os.environ["APIFY_API_TOKEN"]
    if not APIFY_TASK_ID:
        raise RuntimeError("Variabile APIFY_TASK_ID mancante.")
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{APIFY_API}/actor-tasks/{APIFY_TASK_ID}/runs",
        headers=headers, timeout=60,
    )
    response.raise_for_status()
    run_id = response.json()["data"]["id"]
    print("Esecuzione Apify avviata.")

    deadline = time.monotonic() + 25 * 60
    while time.monotonic() < deadline:
        time.sleep(10)
        response = requests.get(
            f"{APIFY_API}/actor-runs/{run_id}",
            headers=headers, timeout=60,
        )
        response.raise_for_status()
        status = response.json()["data"]["status"]
        print(f"Stato Apify: {status}")
        if status == "SUCCEEDED":
            return response.json()["data"]["defaultDatasetId"]
        if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
            raise RuntimeError(f"Apify terminato con stato {status}")
    raise TimeoutError("Apify non ha terminato entro 25 minuti.")


def get_jobs(dataset_id):
    response = requests.get(
        f"{APIFY_API}/datasets/{dataset_id}/items",
        headers={"Authorization": f"Bearer {os.environ['APIFY_API_TOKEN']}"},
        params={"clean": "true", "format": "json"}, timeout=120,
    )
    response.raise_for_status()
    return response.json()


def normalize(job):
    def first(*keys):
        return next((job[k] for k in keys if job.get(k)), "")
    return {
        "title": first("title", "jobTitle", "position"),
        "company": first("companyName", "company", "company_name"),
        "location": first("location", "jobLocation"),
        "url": first("url", "jobUrl", "link"),
        "posted_at": first("postedAt", "postedDate", "date"),
        "description": first("description", "jobDescription", "descriptionText"),
    }


def evaluate(profile, job):
    prompt = f"""
Valuta questo annuncio in base al profilo professionale.

PROFILO:
{profile}

ANNUNCIO:
Titolo: {job['title']}
Azienda: {job['company']}
Località: {job['location']}
Data: {job['posted_at']}
Descrizione:
{job['description']}

Assegna punteggi interi da 1 a 5:
- fit_score: compatibilità con competenze ed esperienza.
- income_score: probabilità di raggiungere l'obiettivo retributivo.
- ai_score: rilevanza concreta di AI, ML, LLM, agenti o automazione.
- low_stress_score: sostenibilità del lavoro; alto significa minor rischio
  di urgenze, turni, reperibilità, ticket ripetitivi e pressione commerciale.

Non inventare informazioni. Distingui fatti e deduzioni.
Se mancano informazioni sullo stipendio, non presumere che sia adeguato.
Restituisci esclusivamente JSON valido con questa struttura:
{{
  "fit_score": 1, "income_score": 1, "ai_score": 1, "low_stress_score": 1,
  "assessment": "Valutazione complessiva",
  "evidence": ["Fatti espliciti"], "inferences": ["Deduzioni"],
  "unknowns": ["Informazioni mancanti"], "strengths": ["Punti di forza"],
  "risks": ["Criticità"], "recommendation": "APPLY, CONSIDER oppure SKIP"
}}
"""
    headers = {
        "x-goog-api-key": os.environ["GEMINI_API_KEY"],
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    # Retry temporary rate limits/service errors, but do not loop forever.
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            response = requests.post(
                GEMINI_URL, headers=headers, json=payload, timeout=90,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt == max_attempts - 1:
                raise
            delay = min(15 * (2 ** attempt), 120)
            print(f"Gemini: errore di rete temporaneo; nuovo tentativo tra {delay}s.")
            time.sleep(delay)
            continue

        if response.status_code in {429, 500, 502, 503, 504}:
            if attempt == max_attempts - 1:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            try:
                delay = max(0, float(retry_after)) if retry_after else None
            except (TypeError, ValueError):
                delay = None
            if delay is None:
                base_delay = 15 if response.status_code == 429 else 2
                delay = min(base_delay * (2 ** attempt), 120)
            print(
                f"Gemini: HTTP {response.status_code}; "
                f"nuovo tentativo tra {delay:g}s "
                f"(tentativo {attempt + 2}/{max_attempts})."
            )
            time.sleep(delay)
            continue

        response.raise_for_status()
        result = json.loads(
            response.json()["candidates"][0]["content"]["parts"][0]["text"]
        )
        for key in ("fit_score", "income_score", "ai_score", "low_stress_score"):
            score = result.get(key)
            if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
                raise ValueError(f"Punteggio non valido: {key}")
        if result.get("recommendation") not in {"APPLY", "CONSIDER", "SKIP"}:
            raise ValueError("Raccomandazione non valida")
        return result

    raise RuntimeError("Gemini: tentativi esauriti senza risposta valida.")


def save(results):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_DIR / "job_results.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with (OUTPUT_DIR / "job_results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for result in results:
            row = result.copy()
            for key in ("evidence", "inferences", "unknowns", "strengths", "risks"):
                if isinstance(row.get(key), list):
                    row[key] = " | ".join(map(str, row[key]))
            writer.writerow({key: row.get(key, "") for key in COLUMNS})


def load_profile():
    # A personal profile overrides the public example when supplied locally.
    personal_path = Path("job_search_profile.md")
    example_path = Path("job_search_profile.example.md")
    profile_path = personal_path if personal_path.is_file() else example_path
    if not profile_path.is_file():
        raise FileNotFoundError(
            "Nessun profilo trovato: crea job_search_profile.md "
            "oppure aggiungi job_search_profile.example.md."
        )
    profile = profile_path.read_text(encoding="utf-8").strip()
    if not profile:
        raise ValueError(f"Il profilo {profile_path} è vuoto.")
    if profile_path == example_path:
        print(
            "AVVISO: uso job_search_profile.example.md. "
            "I risultati rifletteranno il profilo generico di esempio, "
            "non criteri personali."
        )
    return profile




def screen_job(profile, job):
    """First-pass relevance screening. Only accepted jobs get a full assessment."""
    prompt = f"""
Esegui SOLO la scrematura preliminare di questo annuncio rispetto al profilo.
Non fare una valutazione approfondita e non assegnare punteggi.

PROFILO:
{profile}

ANNUNCIO:
Titolo: {job['title']}
Azienda: {job['company']}
Località: {job['location']}
Data: {job['posted_at']}
Descrizione:
{job['description']}

Decidi se l'annuncio merita di passare all'analisi approfondita.
keep=true solo se il ruolo è concretamente pertinente a competenze, esperienza,
ruoli target, retribuzione e preferenze dichiarate nel profilo. Scarta ruoli
chiaramente non pertinenti. Se le informazioni sono insufficienti ma il titolo
e la descrizione suggeriscono una possibile corrispondenza, keep=true.
Restituisci esclusivamente JSON valido:
{{"keep": true, "reason": "Motivo breve basato sull'annuncio e sul profilo"}}
"""
    headers = {
        "x-goog-api-key": os.environ["GEMINI_API_KEY"],
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    # Use the same bounded retry policy as the detailed assessment.
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            response = requests.post(
                GEMINI_URL, headers=headers, json=payload, timeout=90,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt == max_attempts - 1:
                raise
            delay = min(15 * (2 ** attempt), 120)
            print(f"Gemini scrematura: errore di rete; nuovo tentativo tra {delay}s.")
            time.sleep(delay)
            continue

        if response.status_code in {429, 500, 502, 503, 504}:
            if attempt == max_attempts - 1:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            try:
                delay = max(0, float(retry_after)) if retry_after else None
            except (TypeError, ValueError):
                delay = None
            if delay is None:
                delay = min((15 if response.status_code == 429 else 2) * (2 ** attempt), 120)
            print(f"Gemini scrematura: HTTP {response.status_code}; nuovo tentativo tra {delay:g}s.")
            time.sleep(delay)
            continue

        response.raise_for_status()
        result = json.loads(
            response.json()["candidates"][0]["content"]["parts"][0]["text"]
        )
        if not isinstance(result.get("keep"), bool):
            raise ValueError("Esito scrematura non valido: 'keep' deve essere booleano.")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            raise ValueError("Esito scrematura non valido: manca il motivo.")
        return result

    raise RuntimeError("Gemini scrematura: tentativi esauriti senza risposta valida.")

def main():
    for key in ("APIFY_API_TOKEN", "APIFY_TASK_ID", "GEMINI_API_KEY"):
        if not os.environ.get(key, "").strip():
            raise RuntimeError(f"Variabile mancante: {key}")
    profile = load_profile()

    print("Avvio raccolta annunci...")
    jobs = get_jobs(start_apify())
    print(f"Annunci ricevuti: {len(jobs)}")
    results, seen = [], set()
    save(results)
    screened_in = 0
    detailed_count = 0
    screening_count = 0

    for index, raw in enumerate(jobs, 1):
        job = normalize(raw)
        if not job["title"] or not job["description"]:
            print(f"Annuncio {index}/{len(jobs)} ignorato: titolo o descrizione mancanti.")
            continue
        if job["url"] and job["url"] in seen:
            print(f"Annuncio {index}/{len(jobs)} duplicato: ignorato.")
            continue
        if job["url"]:
            seen.add(job["url"])

        # Space out screening requests to stay below Gemini's RPM limits.
        if screening_count:
            time.sleep(5)
        print(f"Scrematura {index}/{len(jobs)}: {job['title']}")
        screening = screen_job(profile, job)
        screening_count += 1
        if not screening["keep"]:
            print(f"Scartato: {screening['reason']}")
            continue

        screened_in += 1
        print(f"Analisi approfondita {index}/{len(jobs)}: {job['title']}")
        results.append({**job, **evaluate(profile, job)})
        detailed_count += 1
        save(results)

    # Hierarchical ordering: fit first, then income, AI relevance, and sustainability.
    results.sort(
        key=lambda r: (
            r["fit_score"], r["income_score"], r["ai_score"], r["low_stress_score"]
        ),
        reverse=True,
    )
    save(results)
    print(
        f"Completato: {len(jobs)} annunci raccolti; "
        f"{len(seen)} URL univoci; {screened_in} superano la scrematura; "
        f"{detailed_count} analisi approfondite."
    )
    print("Il CSV finale contiene solo gli annunci che hanno superato la scrematura.")
    print("Risultati salvati in results/.")




if __name__ == "__main__":
    main()
