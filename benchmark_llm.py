import json
import time
import pandas as pd
from ollama import chat

# ─── CONFIG ───────────────────────────────────────────────────────────────────
MODELS = [
    "tinyllama:latest",
    "qwen2.5:0.5b",
    "qwen2.5:1.5b",
    "phi3:mini",
    "gemma2:2b",
]

TEST_QUERIES = [
    "top 5 prospects",
    "top 3 prospects France",
    "prospects USA budget > 2M",
    "prospects Allemagne score > 12",
    "prospects femtoseconde France",
    "prospects laser Germany budget > 1.5M",
    "reset",
    "bonjour",
    "top 10 par budget décroissant",
    "prospects France score > 10 budget < 3M",
]

SYSTEM_PROMPT = """
Tu es un assistant de prospection laser.

Tu convertis la demande utilisateur en JSON strict.

Tu dois répondre uniquement avec un objet JSON valide.

Champs obligatoires :
intent, keywords, country, organization_contains, min_budget, max_budget, min_score, sort_by, sort_order, top_k, reply

Contraintes :
- intent ∈ ["search", "reset", "unsupported"]
- sort_by ∈ ["budget", "score", null]
- sort_order ∈ ["asc", "desc", null]
- keywords = liste de mots-clés métier uniquement
- ne jamais mettre de pays dans keywords
- "prospect" et "prospects" ne doivent jamais être dans keywords
- si salutation ou hors sujet => intent = "unsupported"
- si reset / réinitialise / recommence => intent = "reset"
- si top N => top_k = N
- sinon top_k = 10
- reply = null sauf si intent = "unsupported" ou "reset"

Normalisation pays :
- USA, US, États-Unis, Etats-Unis => "USA"
- France => "France"
- Allemagne, Germany => "Germany"
- Royaume-Uni, UK, Angleterre => "UK"

Pour min_budget et max_budget :
- "1M" = 1000000
- "2.5M" = 2500000
- "k" = milliers

Ne renvoie aucun texte hors JSON.
"""

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "country": {"type": ["string", "null"]},
        "organization_contains": {"type": ["string", "null"]},
        "min_budget": {"type": ["number", "null"]},
        "max_budget": {"type": ["number", "null"]},
        "min_score": {"type": ["number", "null"]},
        "sort_by": {"type": ["string", "null"]},
        "sort_order": {"type": ["string", "null"]},
        "top_k": {"type": ["number", "null"]},
        "reply": {"type": ["string", "null"]},
    },
    "required": [
        "intent",
        "keywords",
        "country",
        "organization_contains",
        "min_budget",
        "max_budget",
        "min_score",
        "sort_by",
        "sort_order",
        "top_k",
        "reply",
    ],
}

FEW_SHOT_MESSAGES = [
    {"role": "user", "content": "top 3 prospects France"},
    {
        "role": "assistant",
        "content": json.dumps({
            "intent": "search",
            "keywords": [],
            "country": "France",
            "organization_contains": None,
            "min_budget": None,
            "max_budget": None,
            "min_score": None,
            "sort_by": None,
            "sort_order": None,
            "top_k": 3,
            "reply": None
        }, ensure_ascii=False)
    },
    {"role": "user", "content": "prospects USA budget > 2M"},
    {
        "role": "assistant",
        "content": json.dumps({
            "intent": "search",
            "keywords": [],
            "country": "USA",
            "organization_contains": None,
            "min_budget": 2000000,
            "max_budget": None,
            "min_score": None,
            "sort_by": None,
            "sort_order": None,
            "top_k": 10,
            "reply": None
        }, ensure_ascii=False)
    },
    {"role": "user", "content": "reset"},
    {
        "role": "assistant",
        "content": json.dumps({
            "intent": "reset",
            "keywords": [],
            "country": None,
            "organization_contains": None,
            "min_budget": None,
            "max_budget": None,
            "min_score": None,
            "sort_by": None,
            "sort_order": None,
            "top_k": 10,
            "reply": "Réinitialisé."
        }, ensure_ascii=False)
    },
    {"role": "user", "content": "bonjour"},
    {
        "role": "assistant",
        "content": json.dumps({
            "intent": "unsupported",
            "keywords": [],
            "country": None,
            "organization_contains": None,
            "min_budget": None,
            "max_budget": None,
            "min_score": None,
            "sort_by": None,
            "sort_order": None,
            "top_k": 10,
            "reply": "Salut ! Dis-moi ce que tu cherches."
        }, ensure_ascii=False)
    },
]

CURRENT_FILTERS = {
    "keywords": [],
    "country": None,
    "organization_contains": None,
    "min_budget": None,
    "max_budget": None,
    "min_score": None,
    "sort_by": None,
    "sort_order": None,
    "top_k": 10,
}

# ─── OUTILS ───────────────────────────────────────────────────────────────────
def extract_json_fallback(text):
    if not text:
        return None

    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start:end + 1]

    try:
        return json.loads(candidate)
    except Exception:
        return None


def normalize_parsed(parsed):
    clean = {
        "intent": parsed.get("intent", "unsupported"),
        "keywords": parsed.get("keywords", []),
        "country": parsed.get("country", None),
        "organization_contains": parsed.get("organization_contains", None),
        "min_budget": parsed.get("min_budget", None),
        "max_budget": parsed.get("max_budget", None),
        "min_score": parsed.get("min_score", None),
        "sort_by": parsed.get("sort_by", None),
        "sort_order": parsed.get("sort_order", None),
        "top_k": parsed.get("top_k", 10),
        "reply": parsed.get("reply", None),
    }

    if not isinstance(clean["keywords"], list):
        clean["keywords"] = []

    allowed_intents = {"search", "reset", "unsupported"}
    allowed_sort_by = {"budget", "score", None}
    allowed_sort_order = {"asc", "desc", None}

    if clean["intent"] not in allowed_intents:
        clean["intent"] = "unsupported"

    if clean["sort_by"] not in allowed_sort_by:
        clean["sort_by"] = None

    if clean["sort_order"] not in allowed_sort_order:
        clean["sort_order"] = None

    try:
        if clean["top_k"] is None:
            clean["top_k"] = 10
        clean["top_k"] = int(clean["top_k"])
    except Exception:
        clean["top_k"] = 10

    if clean["top_k"] <= 0:
        clean["top_k"] = 10

    for field in ["min_budget", "max_budget", "min_score"]:
        try:
            if clean[field] is not None:
                clean[field] = float(clean[field])
        except Exception:
            clean[field] = None

    banned_keywords = {
        "prospect", "prospects", "usa", "us",
        "france", "germany", "allemagne", "uk", "angleterre"
    }

    clean_keywords = []
    for kw in clean["keywords"]:
        if isinstance(kw, str):
            kw = kw.strip()
            if kw and kw.lower() not in banned_keywords:
                clean_keywords.append(kw)

    clean["keywords"] = clean_keywords

    return clean


def score_output(parsed):
    score = 0

    if parsed["intent"] in {"search", "reset", "unsupported"}:
        score += 1

    if isinstance(parsed["keywords"], list):
        score += 1

    if parsed["sort_by"] in {"budget", "score", None}:
        score += 1

    if parsed["sort_order"] in {"asc", "desc", None}:
        score += 1

    if isinstance(parsed["top_k"], int) and parsed["top_k"] > 0:
        score += 1

    return score


def test_model(model_name, user_query):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": f"Filtres actuels: {json.dumps(CURRENT_FILTERS, ensure_ascii=False)}"},
    ]
    messages.extend(FEW_SHOT_MESSAGES)
    messages.append({"role": "user", "content": user_query})

    start = time.time()

    try:
        response = chat(
            model=model_name,
            messages=messages,
            format=JSON_SCHEMA,
            options={"temperature": 0, "num_predict": 220},
        )

        latency = round(time.time() - start, 3)
        raw_output = response["message"]["content"]

        try:
            parsed = json.loads(raw_output)
            json_valid = True
        except Exception:
            parsed = extract_json_fallback(raw_output)
            json_valid = parsed is not None

        if parsed is None:
            return {
                "model": model_name,
                "query": user_query,
                "latency_s": latency,
                "json_valid": False,
                "score_validity": 0,
                "intent": None,
                "keywords": None,
                "country": None,
                "min_budget": None,
                "max_budget": None,
                "min_score": None,
                "sort_by": None,
                "sort_order": None,
                "top_k": None,
                "reply": None,
                "error": "invalid_json"
            }

        parsed = normalize_parsed(parsed)

        return {
            "model": model_name,
            "query": user_query,
            "latency_s": latency,
            "json_valid": json_valid,
            "score_validity": score_output(parsed),
            "intent": parsed["intent"],
            "keywords": ", ".join(parsed["keywords"]) if parsed["keywords"] else "",
            "country": parsed["country"],
            "min_budget": parsed["min_budget"],
            "max_budget": parsed["max_budget"],
            "min_score": parsed["min_score"],
            "sort_by": parsed["sort_by"],
            "sort_order": parsed["sort_order"],
            "top_k": parsed["top_k"],
            "reply": parsed["reply"],
            "error": None
        }

    except Exception as e:
        latency = round(time.time() - start, 3)

        return {
            "model": model_name,
            "query": user_query,
            "latency_s": latency,
            "json_valid": False,
            "score_validity": 0,
            "intent": None,
            "keywords": None,
            "country": None,
            "min_budget": None,
            "max_budget": None,
            "min_score": None,
            "sort_by": None,
            "sort_order": None,
            "top_k": None,
            "reply": None,
            "error": str(e)
        }


# ─── BENCHMARK ────────────────────────────────────────────────────────────────
def main():
    rows = []

    for model in MODELS:
        print(f"\n===== TEST DU MODÈLE : {model} =====")

        for query in TEST_QUERIES:
            print(f"-> {query}")
            result = test_model(model, query)
            rows.append(result)

    df = pd.DataFrame(rows)

    print("\n===== RÉSULTATS DÉTAILLÉS =====")
    print(df[[
        "model",
        "query",
        "latency_s",
        "json_valid",
        "score_validity",
        "intent",
        "country",
        "min_budget",
        "max_budget",
        "min_score",
        "sort_by",
        "sort_order",
        "top_k",
        "error"
    ]].to_string(index=False))

    summary = (
        df.groupby("model")
        .agg(
            tests=("query", "count"),
            json_valid_count=("json_valid", "sum"),
            avg_latency_s=("latency_s", "mean"),
            avg_score_validity=("score_validity", "mean")
        )
        .reset_index()
    )

    summary["json_valid_rate"] = (
        summary["json_valid_count"] / summary["tests"] * 100
    ).round(1)

    summary["avg_latency_s"] = summary["avg_latency_s"].round(3)
    summary["avg_score_validity"] = summary["avg_score_validity"].round(2)

    summary = summary.sort_values(
        by=["json_valid_rate", "avg_score_validity", "avg_latency_s"],
        ascending=[False, False, True]
    )

    print("\n===== RÉSUMÉ PAR MODÈLE =====")
    print(summary.to_string(index=False))

    # CSV clean lisible
    clean_df = df[[
        "model",
        "query",
        "latency_s",
        "json_valid",
        "score_validity",
        "intent",
        "keywords",
        "country",
        "min_budget",
        "max_budget",
        "min_score",
        "sort_by",
        "sort_order",
        "top_k",
        "reply",
        "error"
    ]]

    clean_df.to_csv(
        "benchmark_llm_results_clean.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # CSV résumé
    summary.to_csv(
        "benchmark_llm_summary.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\nFichiers générés :")
    print("- benchmark_llm_results_clean.csv")
    print("- benchmark_llm_summary.csv")


if __name__ == "__main__":
    main()