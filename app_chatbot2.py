import json
import re
import pandas as pd
import streamlit as st
from ollama import chat

st.set_page_config(page_title="Prospection Laser", layout="wide")

# -----------------------------
# Données d'exemple
# -----------------------------
data = [
    {
        "title": "Ultrafast laser machining for biomedical devices",
        "organization": "MIT",
        "country": "USA",
        "budget": 2500000,
        "score": 18,
        "keywords": "ultrafast laser femtosecond biomedical photonics"
    },
    {
        "title": "Photonics platform for industrial optics",
        "organization": "Fraunhofer",
        "country": "Germany",
        "budget": 1800000,
        "score": 15,
        "keywords": "photonics optics industrial laser"
    },
    {
        "title": "Laser ablation for advanced materials",
        "organization": "Stanford University",
        "country": "USA",
        "budget": 3200000,
        "score": 19,
        "keywords": "laser ablation materials ultrafast"
    },
    {
        "title": "Medical imaging with optics",
        "organization": "Institut Pasteur",
        "country": "France",
        "budget": 900000,
        "score": 11,
        "keywords": "medical imaging optics"
    },
    {
        "title": "Femtosecond laser platform for semiconductor processing",
        "organization": "Caltech",
        "country": "USA",
        "budget": 4100000,
        "score": 20,
        "keywords": "femtosecond laser semiconductor ultrafast photonics"
    },
    {
        "title": "Advanced photonics for aerospace optics",
        "organization": "ONERA",
        "country": "France",
        "budget": 2200000,
        "score": 16,
        "keywords": "photonics aerospace optics laser"
    }
]

df = pd.DataFrame(data)

# -----------------------------
# Etat initial
# -----------------------------
DEFAULT_FILTERS = {
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

if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_filters" not in st.session_state:
    st.session_state.current_filters = DEFAULT_FILTERS.copy()

if "last_results" not in st.session_state:
    st.session_state.last_results = pd.DataFrame()

# -----------------------------
# Schéma JSON
# -----------------------------
schema = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["search", "reset", "unsupported"]
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"}
        },
        "country": {
            "type": ["string", "null"]
        },
        "organization_contains": {
            "type": ["string", "null"]
        },
        "min_budget": {
            "type": ["number", "null"]
        },
        "max_budget": {
            "type": ["number", "null"]
        },
        "min_score": {
            "type": ["number", "null"]
        },
        "sort_by": {
            "type": ["string", "null"],
            "enum": ["budget", "score", "title", None]
        },
        "sort_order": {
            "type": ["string", "null"],
            "enum": ["asc", "desc", None]
        },
        "top_k": {
            "type": ["integer", "null"]
        },
        "reply": {
            "type": ["string", "null"]
        }
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
        "reply"
    ]
}

SYSTEM_PROMPT = """
Tu es un assistant métier de prospection laser.

Tu dois analyser le message utilisateur et renvoyer UNIQUEMENT un JSON valide.

Tu reçois aussi les filtres actuels pour garder le contexte.

Intentions possibles :
- "search" : si l'utilisateur cherche, filtre, trie, affine ou compare des prospects
- "reset" : si l'utilisateur veut réinitialiser, recommencer, repartir à zéro
- "unsupported" : si le message n'est pas une vraie demande métier exploitable

Règles :
- Réponds uniquement en JSON valide
- Pas d'explication hors JSON
- "reply" doit être court et en français seulement si intent = "unsupported" ou "reset"
- si intent = "search", "reply" peut être null
- "keywords" = mots-clés utiles pour la recherche
- Ne mets jamais de pays dans keywords
- Ne mets jamais "prospect", "prospects", "client", "clients" dans keywords
- Si le message contient USA, US, Etats-Unis, America => country = USA
- Si le message contient France => country = France
- Si le message contient Allemagne ou Germany => country = Germany
- Conserve le contexte si l'utilisateur affine la recherche
- Si l'utilisateur dit "seulement", "garde juste", "affine", considère que c'est une modification des filtres existants
- Si l'utilisateur demande un nombre de résultats, remplis top_k
"""

# -----------------------------
# Règles ultra rapides
# -----------------------------
def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())

def quick_rule_response(user_query: str):
    q = normalize_text(user_query)

    greetings = {"salut", "bonjour", "bonsoir", "hello", "coucou", "yo", "hey", "wsh"}
    thanks = {"merci", "merci beaucoup", "thx", "thanks"}
    help_words = {
        "aide", "help", "tu peux m'aider", "tu peux aider",
        "que peux-tu faire", "qu'est-ce que tu peux faire",
        "tu sers à quoi", "comment ça marche"
    }
    reset_words = {
        "reset", "réinitialise", "reinitialise", "réinitialiser",
        "repartons de zéro", "repartir de zéro", "efface",
        "recommence", "recommencer"
    }
    smalltalk = {
        "ça va", "ca va", "cv", "tu vas bien", "comment ça va",
        "comment ca va"
    }

    if q in greetings:
        return {
            "type": "other",
            "reply": "Salut. Je peux vous aider à rechercher, filtrer et trier des prospects laser."
        }

    if q in thanks:
        return {
            "type": "other",
            "reply": "Avec plaisir."
        }

    if q in smalltalk:
        return {
            "type": "other",
            "reply": "Je suis prêt à vous aider sur la recherche de prospects laser."
        }

    if q in help_words:
        return {
            "type": "other",
            "reply": (
                "Je peux rechercher, filtrer et trier des prospects. "
                "Exemples : prospects aux USA, budget supérieur à 2 millions, tri par score, garde les 5 meilleurs."
            )
        }

    if q in reset_words:
        return {
            "type": "reset",
            "reply": "C’est réinitialisé. Vous pouvez repartir sur une nouvelle recherche."
        }

    return None

# -----------------------------
# Appel Ollama
# -----------------------------
def parse_message_with_ollama(user_query: str, current_filters: dict, model: str = "mistral") -> dict:
    context_message = f"Filtres actuels : {json.dumps(current_filters, ensure_ascii=False)}"

    response = chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "assistant", "content": context_message},
            {"role": "user", "content": user_query}
        ],
        format=schema,
        options={
            "temperature": 0,
            "num_predict": 150
        }
    )

    return json.loads(response["message"]["content"])

# -----------------------------
# Métier
# -----------------------------
def merge_filters(current_filters: dict, new_filters: dict) -> dict:
    merged = current_filters.copy()

    for key in [
        "keywords",
        "country",
        "organization_contains",
        "min_budget",
        "max_budget",
        "min_score",
        "sort_by",
        "sort_order",
        "top_k"
    ]:
        value = new_filters.get(key)

        if key == "keywords":
            if value:
                cleaned_keywords = [
                    kw for kw in value
                    if kw.lower() not in [
                        "prospect",
                        "prospects",
                        "client",
                        "clients",
                        "usa",
                        "us",
                        "france",
                        "germany",
                        "allemagne"
                    ]
                ]
                if cleaned_keywords:
                    merged[key] = cleaned_keywords
        else:
            if value is not None:
                merged[key] = value

    if merged.get("top_k") is None:
        merged["top_k"] = 10

    return merged

def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    result = df.copy()

    keywords = filters.get("keywords") or []
    if keywords:
        mask = pd.Series(False, index=result.index)
        for kw in keywords:
            mask = mask | result["keywords"].str.contains(kw, case=False, na=False)
            mask = mask | result["title"].str.contains(kw, case=False, na=False)
            mask = mask | result["organization"].str.contains(kw, case=False, na=False)
        result = result[mask]

    if filters.get("country"):
        result = result[result["country"].str.lower() == filters["country"].lower()]

    if filters.get("organization_contains"):
        result = result[
            result["organization"].str.contains(
                filters["organization_contains"],
                case=False,
                na=False
            )
        ]

    if filters.get("min_budget") is not None:
        result = result[result["budget"] >= filters["min_budget"]]

    if filters.get("max_budget") is not None:
        result = result[result["budget"] <= filters["max_budget"]]

    if filters.get("min_score") is not None:
        result = result[result["score"] >= filters["min_score"]]

    sort_by = filters.get("sort_by")
    sort_order = filters.get("sort_order", "desc")

    if sort_by in ["budget", "score", "title"]:
        ascending = sort_order == "asc"
        result = result.sort_values(by=sort_by, ascending=ascending)

    top_k = filters.get("top_k") or 10
    return result.head(top_k)

def format_results_for_display(results: pd.DataFrame) -> pd.DataFrame:
    display_df = results.copy()

    if "budget" in display_df.columns:
        display_df["budget"] = display_df["budget"].apply(
            lambda x: f"{int(x):,} €".replace(",", " ")
        )

    return display_df.rename(columns={
        "title": "Projet",
        "organization": "Organisation",
        "country": "Pays",
        "budget": "Budget",
        "score": "Score",
        "keywords": "Mots-clés"
    })

def build_search_message(filters: dict, results_count: int) -> str:
    parts = []

    if filters.get("country"):
        parts.append(f"pays : {filters['country']}")
    if filters.get("keywords"):
        parts.append("mots-clés : " + ", ".join(filters["keywords"]))
    if filters.get("min_budget") is not None:
        parts.append(f"budget min : {int(filters['min_budget']):,} €".replace(",", " "))
    if filters.get("max_budget") is not None:
        parts.append(f"budget max : {int(filters['max_budget']):,} €".replace(",", " "))
    if filters.get("sort_by"):
        order = "croissant" if filters.get("sort_order") == "asc" else "décroissant"
        parts.append(f"tri : {filters['sort_by']} {order}")
    if filters.get("top_k"):
        parts.append(f"limite : {filters['top_k']}")

    if parts:
        return f"Critères appliqués : {' | '.join(parts)}. Résultats trouvés : {results_count}."
    return f"Recherche effectuée. Résultats trouvés : {results_count}."

# -----------------------------
# UI
# -----------------------------
st.title("Prospection Laser")
st.write("Assistant de recherche de prospects laser.")

col1, col2 = st.columns([5, 1])

with col2:
    if st.button("Réinitialiser", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_filters = DEFAULT_FILTERS.copy()
        st.session_state.last_results = pd.DataFrame()
        st.rerun()

st.caption("Exemples :")
st.markdown("- Trouve-moi les prospects aux USA")
st.markdown("- Seulement ceux avec un budget supérieur à 2 millions")
st.markdown("- Trie par score décroissant")
st.markdown("- Garde juste les 3 meilleurs")
st.markdown("- Réinitialise")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("results") is not None and not msg["results"].empty:
            st.dataframe(
                format_results_for_display(msg["results"]),
                use_container_width=True
            )

user_query = st.chat_input("Écrivez votre demande")

if user_query:
    st.session_state.messages.append({
        "role": "user",
        "content": user_query
    })

    with st.chat_message("user"):
        st.write(user_query)

    try:
        quick_response = quick_rule_response(user_query)

        if quick_response is not None:
            if quick_response["type"] == "reset":
                st.session_state.current_filters = DEFAULT_FILTERS.copy()
                st.session_state.last_results = pd.DataFrame()

            assistant_message = quick_response["reply"]
            results = None

        else:
            with st.spinner("Recherche en cours..."):
                parsed = parse_message_with_ollama(
                    user_query=user_query,
                    current_filters=st.session_state.current_filters,
                    model="mistral"
                )

            intent = parsed.get("intent", "unsupported")

            if intent == "reset":
                st.session_state.current_filters = DEFAULT_FILTERS.copy()
                st.session_state.last_results = pd.DataFrame()
                assistant_message = "C’est réinitialisé. Vous pouvez repartir sur une nouvelle recherche."
                results = None

            elif intent == "unsupported":
                assistant_message = parsed.get("reply") or "Je peux vous aider à rechercher et filtrer des prospects laser."
                results = None

            else:
                merged_filters = merge_filters(
                    current_filters=st.session_state.current_filters,
                    new_filters=parsed
                )

                results = apply_filters(df, merged_filters)

                st.session_state.current_filters = merged_filters
                st.session_state.last_results = results

                assistant_message = build_search_message(merged_filters, len(results))

        with st.chat_message("assistant"):
            st.write(assistant_message)

            if results is not None:
                if results.empty:
                    st.warning("Aucun prospect ne correspond à votre demande.")
                else:
                    st.dataframe(
                        format_results_for_display(results),
                        use_container_width=True
                    )

        st.session_state.messages.append({
            "role": "assistant",
            "content": assistant_message,
            "results": results
        })

    except Exception as e:
        error_message = f"Erreur lors du traitement : {e}"

        with st.chat_message("assistant"):
            st.error(error_message)

        st.session_state.messages.append({
            "role": "assistant",
            "content": error_message,
            "results": None
        })