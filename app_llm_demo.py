import json
import pandas as pd
import streamlit as st
from ollama import chat

st.set_page_config(page_title="Laser Prospects", layout="wide")

# ─── CONFIG LLM ───────────────────────────────────────────────────────────────
MODEL_NAME = "phi"

# ─── DONNÉES FICTIVES ─────────────────────────────────────────────────────────
data = [
    {"source": "NSF", "title": "Ultrafast femtosecond laser for micro-machining", "organization": "MIT", "country": "USA", "budget": 2500000, "score": 15, "contact": "John Smith", "email": "j.smith@mit.edu", "keywords": "femtosecond ultrafast laser"},
    {"source": "CORDIS", "title": "Photonics platform for industrial optics", "organization": "Fraunhofer", "country": "Germany", "budget": 1800000, "score": 12, "contact": "Hans Müller", "email": "h.muller@fraunhofer.de", "keywords": "photonics optics laser"},
    {"source": "NSF", "title": "Laser ablation for advanced materials", "organization": "Stanford", "country": "USA", "budget": 3200000, "score": 14, "contact": "Sarah Lee", "email": "s.lee@stanford.edu", "keywords": "ablation laser ultrafast"},
    {"source": "NSF", "title": "Femtosecond laser for semiconductor processing", "organization": "Caltech", "country": "USA", "budget": 4100000, "score": 15, "contact": "David Chen", "email": "d.chen@caltech.edu", "keywords": "femtosecond semiconductor laser"},
    {"source": "NIH", "title": "Medical imaging with ultrafast optics", "organization": "Institut Pasteur", "country": "France", "budget": 900000, "score": 9, "contact": "Marie Dupont", "email": "m.dupont@pasteur.fr", "keywords": "medical imaging optics ultrafast"},
    {"source": "CORDIS", "title": "Advanced photonics for aerospace", "organization": "ONERA", "country": "France", "budget": 2200000, "score": 11, "contact": "Pierre Martin", "email": "p.martin@onera.fr", "keywords": "photonics aerospace laser"},
    {"source": "CORDIS", "title": "Laser microfabrication for biomedical devices", "organization": "ETH Zurich", "country": "Switzerland", "budget": 1500000, "score": 13, "contact": "Anna Weber", "email": "a.weber@ethz.ch", "keywords": "laser microfabrication biomedical femtosecond"},
    {"source": "CORDIS", "title": "Ultrafast spectroscopy for material science", "organization": "Max Planck", "country": "Germany", "budget": 2800000, "score": 13, "contact": "Klaus Schmidt", "email": "k.schmidt@mpg.de", "keywords": "ultrafast spectroscopy laser"},
    {"source": "CORDIS", "title": "Laser cutting for industrial manufacturing", "organization": "Siemens Research", "country": "Germany", "budget": 3500000, "score": 10, "contact": "Erik Bauer", "email": "e.bauer@siemens.com", "keywords": "laser manufacturing optics"},
    {"source": "CORDIS", "title": "Photonic quantum computing with laser", "organization": "Oxford University", "country": "UK", "budget": 5000000, "score": 14, "contact": "James Wilson", "email": "j.wilson@ox.ac.uk", "keywords": "photonics quantum laser"},
    {"source": "NIH", "title": "Femtosecond laser surgery system", "organization": "Mayo Clinic", "country": "USA", "budget": 2100000, "score": 12, "contact": "Dr. Emily Brown", "email": "e.brown@mayo.edu", "keywords": "femtosecond laser medical surgery"},
    {"source": "CORDIS", "title": "High power laser for defense applications", "organization": "Thales", "country": "France", "budget": 6000000, "score": 11, "contact": "François Leblanc", "email": "f.leblanc@thales.com", "keywords": "laser defense optics"},
    {"source": "CORDIS", "title": "Ultrafast laser deposition for thin films", "organization": "CNRS", "country": "France", "budget": 1200000, "score": 13, "contact": "Sophie Bernard", "email": "s.bernard@cnrs.fr", "keywords": "ultrafast laser ablation thin films"},
    {"source": "CORDIS", "title": "Laser-based 3D printing for ceramics", "organization": "TU Munich", "country": "Germany", "budget": 1700000, "score": 10, "contact": "Markus Fischer", "email": "m.fischer@tum.de", "keywords": "laser manufacturing photonics"},
    {"source": "CORDIS", "title": "Photonics for autonomous vehicle sensors", "organization": "Bosch Research", "country": "Germany", "budget": 4500000, "score": 12, "contact": "Laura Hoffman", "email": "l.hoffman@bosch.com", "keywords": "photonics laser optics sensors"},
]

df = pd.DataFrame(data)

# ─── ÉTAT ─────────────────────────────────────────────────────────────────────
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

if "messages_nsf" not in st.session_state:
    st.session_state.messages_nsf = []

if "messages_europe" not in st.session_state:
    st.session_state.messages_europe = []

if "filters_nsf" not in st.session_state:
    st.session_state.filters_nsf = DEFAULT_FILTERS.copy()

if "filters_europe" not in st.session_state:
    st.session_state.filters_europe = DEFAULT_FILTERS.copy()

# ─── PROMPT LLM ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Tu es un assistant de prospection laser.
Analyse le message utilisateur et réponds UNIQUEMENT en JSON valide avec ces champs :
{
  "intent": "search",
  "keywords": [],
  "country": null,
  "organization_contains": null,
  "min_budget": null,
  "max_budget": null,
  "min_score": null,
  "sort_by": null,
  "sort_order": null,
  "top_k": 10,
  "reply": null
}

Intent possible : "search", "reset", "unsupported".

Règles :
- USA, US, Etats-Unis, États-Unis -> country = "USA"
- France -> country = "France"
- Allemagne, Germany -> country = "Germany"
- Royaume-Uni, UK, Angleterre -> country = "UK"
- Si l'utilisateur demande "top 3" ou "top 5", mets top_k correctement
- Si l'utilisateur demande un tri décroissant sans préciser, mets sort_order = "desc"
- sort_by peut être "budget" ou "score"
- Réponds UNIQUEMENT en JSON, sans texte autour."""

# ─── QUICK RULES ──────────────────────────────────────────────────────────────
def quick_rule(q):
    q = q.lower().strip()

    if q in ["salut", "bonjour", "hello", "coucou", "hey"]:
        return {
            "type": "other",
            "reply": "Salut ! Exemples : 'top 5 par score', 'prospects femtoseconde', 'budget > 1M'."
        }

    if any(r in q for r in ["reset", "réinitialise", "recommence", "repartir"]):
        return {
            "type": "reset",
            "reply": "Réinitialisé. Nouvelle recherche ?"
        }

    if any(h in q for h in ["aide", "help", "que peux-tu", "comment"]):
        return {
            "type": "other",
            "reply": "Tu peux chercher par technologie, pays, budget ou score. Exemple : 'top 3 femtoseconde par budget'."
        }

    return None

# ─── JSON PARSER ──────────────────────────────────────────────────────────────
def safe_extract_json(text):
    if not text:
        return None

    text = text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None

# ─── LLM ──────────────────────────────────────────────────────────────────────
def call_llm(user_query, current_filters):
    fallback = {
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
        "reply": None
    }

    try:
        response = chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "assistant", "content": f"Filtres actuels: {json.dumps(current_filters, ensure_ascii=False)}"},
                {"role": "user", "content": user_query}
            ],
            options={
                "temperature": 0,
                "num_predict": 200
            }
        )

        parsed = safe_extract_json(response["message"]["content"])

        if parsed is None:
            fallback["reply"] = f"Le modèle '{MODEL_NAME}' a répondu dans un format invalide."
            return fallback

        for key in fallback:
            parsed.setdefault(key, fallback[key])

        return parsed

    except Exception as e:
        fallback["reply"] = f"Erreur LLM : {e}"
        return fallback

# ─── FILTRAGE ─────────────────────────────────────────────────────────────────
def apply_filters(dataframe, filters):
    result = dataframe.copy()

    if filters.get("keywords"):
        mask = pd.Series(False, index=result.index)

        for kw in filters["keywords"]:
            mask |= result["keywords"].str.contains(kw, case=False, na=False)
            mask |= result["title"].str.contains(kw, case=False, na=False)

        result = result[mask]

    if filters.get("country"):
        result = result[result["country"].str.lower() == filters["country"].lower()]

    if filters.get("organization_contains"):
        result = result[
            result["organization"].str.contains(filters["organization_contains"], case=False, na=False)
        ]

    if filters.get("min_budget") is not None:
        result = result[result["budget"] >= filters["min_budget"]]

    if filters.get("max_budget") is not None:
        result = result[result["budget"] <= filters["max_budget"]]

    if filters.get("min_score") is not None:
        result = result[result["score"] >= filters["min_score"]]

    if filters.get("sort_by") in ["budget", "score"]:
        ascending = filters.get("sort_order") == "asc"
        result = result.sort_values(filters["sort_by"], ascending=ascending)

    return result.head(filters.get("top_k") or 10)

def merge_filters(current, new):
    merged = current.copy()

    for key in DEFAULT_FILTERS:
        val = new.get(key)

        if key == "keywords" and val:
            banned = ["prospect", "prospects", "usa", "france", "germany", "uk"]
            cleaned = [
                kw.strip()
                for kw in val
                if isinstance(kw, str) and kw.lower().strip() not in banned
            ]

            if cleaned:
                merged[key] = cleaned

        elif val is not None:
            merged[key] = val

    return merged

# ─── COMPOSANT INTERFACE ──────────────────────────────────────────────────────
def render_interface(title, caption, dataframe, messages_key, filters_key):
    st.subheader(title)
    st.caption(caption)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total prospects", len(dataframe))
    k2.metric("Avec email", len(dataframe[dataframe["email"] != ""]))
    k3.metric("Budget moyen", f"${dataframe['budget'].mean():,.0f}" if len(dataframe) > 0 else "$0")
    k4.metric("Score max", dataframe["score"].max() if len(dataframe) > 0 else 0)

    st.dataframe(
        dataframe[["source", "title", "organization", "country", "budget", "score", "contact", "email"]],
        use_container_width=True
    )

    st.divider()
    st.caption("Exemples : 'top 5 par score' | 'femtoseconde' | 'budget > 1M' | 'reset'")

    for msg in st.session_state[messages_key]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

            if msg.get("results") is not None and not msg["results"].empty:
                st.dataframe(
                    msg["results"][["source", "title", "organization", "country", "budget", "score", "contact", "email"]],
                    use_container_width=True
                )

    user_query = st.chat_input(f"Question pour {title}...")

    if user_query:
        st.session_state[messages_key].append({
            "role": "user",
            "content": user_query
        })

        with st.chat_message("user"):
            st.write(user_query)

        quick = quick_rule(user_query)

        if quick:
            if quick["type"] == "reset":
                st.session_state[filters_key] = DEFAULT_FILTERS.copy()

            reply = quick["reply"]
            results = pd.DataFrame()

        else:
            with st.spinner("Analyse..."):
                parsed = call_llm(user_query, st.session_state[filters_key])

            intent = parsed.get("intent", "unsupported")

            if intent == "reset":
                st.session_state[filters_key] = DEFAULT_FILTERS.copy()
                reply = parsed.get("reply") or "Réinitialisé."
                results = pd.DataFrame()

            elif intent == "unsupported":
                reply = parsed.get("reply") or "Je n'ai pas compris. Reformule ta demande."
                results = pd.DataFrame()

            else:
                merged = merge_filters(st.session_state[filters_key], parsed)
                results = apply_filters(dataframe, merged)
                st.session_state[filters_key] = merged
                reply = f"**{len(results)} prospect(s) trouvé(s)** avec les filtres appliqués."

        with st.chat_message("assistant"):
            st.write(reply)

            if results is not None and not results.empty:
                st.dataframe(
                    results[["source", "title", "organization", "country", "budget", "score", "contact", "email"]],
                    use_container_width=True
                )
            elif results is not None and results.empty and "trouvé" in reply:
                st.warning("Aucun prospect ne correspond.")

        st.session_state[messages_key].append({
            "role": "assistant",
            "content": reply,
            "results": results
        })

# ─── APP PRINCIPALE ───────────────────────────────────────────────────────────
st.title("🔬 Laser Prospects — Assistant IA")
st.caption(f"Modèle utilisé : {MODEL_NAME}")

df_nsf = df[df["source"] == "NSF"].reset_index(drop=True)
df_europe = df[df["source"].isin(["CORDIS", "NIH"])].reset_index(drop=True)

tab_nsf, tab_europe = st.tabs(["🇺🇸 Interface NSF", "🇪🇺 Interface Europe / CORDIS + NIH"])

with tab_nsf:
    if st.button("🔄 Réinitialiser NSF", use_container_width=True):
        st.session_state.messages_nsf = []
        st.session_state.filters_nsf = DEFAULT_FILTERS.copy()
        st.rerun()

    render_interface(
        title="Interface NSF",
        caption="Prospects issus de NSF uniquement.",
        dataframe=df_nsf,
        messages_key="messages_nsf",
        filters_key="filters_nsf"
    )

with tab_europe:
    if st.button("🔄 Réinitialiser Europe / CORDIS + NIH", use_container_width=True):
        st.session_state.messages_europe = []
        st.session_state.filters_europe = DEFAULT_FILTERS.copy()
        st.rerun()

    render_interface(
        title="Interface Europe / CORDIS + NIH",
        caption="Prospects issus de CORDIS et NIH.",
        dataframe=df_europe,
        messages_key="messages_europe",
        filters_key="filters_europe"
    )