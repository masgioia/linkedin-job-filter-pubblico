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
    response = requests.post(
        GEMINI_URL,
        headers={
            "x-goog-api-key": os.environ["GEMINI_API_KEY"],
            "Content-Type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=90,
    )
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


def main():
    for key in ("APIFY_API_TOKEN", "APIFY_TASK_ID", "GEMINI_API_KEY"):
        if not os.environ.get(key, "").strip():
            raise RuntimeError(f"Variabile mancante: {key}")
    profile_path = Path("job_search_profile.md")
    if not profile_path.is_file():
        raise FileNotFoundError("Crea job_search_profile.md con il tuo profilo.")
    profile = profile_path.read_text(encoding="utf-8").strip()
    if not profile:
        raise ValueError("Il profilo professionale è vuoto.")

    print("Avvio raccolta annunci...")
    jobs = get_jobs(start_apify())
    print(f"Annunci ricevuti: {len(jobs)}")
    results, seen = [], set()
    save(results)
    for index, raw in enumerate(jobs, 1):
        job = normalize(raw)
        if not job["title"] or not job["description"]:
            continue
        if job["url"] and job["url"] in seen:
            continue
        if job["url"]:
            seen.add(job["url"])
        print(f"Valutazione annuncio {index}/{len(jobs)}")
        results.append({**job, **evaluate(profile, job)})
        save(results)

    results.sort(
        key=lambda r: (
            r["fit_score"], r["income_score"], r["ai_score"], r["low_stress_score"]
        ),
        reverse=True,
    )
    save(results)
    print(f"Completato: {len(results)} annunci valutati.")
    print("Risultati salvati localmente in results/.")


if __name__ == "__main__":
    main()
