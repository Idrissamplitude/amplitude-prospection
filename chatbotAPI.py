import streamlit as st
import pandas as pd
import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

st.set_page_config(page_title="Laser Prospects", page_icon="🔬", layout="wide")

# ─── CONFIG API ───────────────────────────────────────────────────────────────
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.0-flash-lite"

# ─── CONFIG PIPELINE ──────────────────────────────────────────────────────────
KEYWORD = "laser"
MAX_PROJECTS = 500

KEYWORDS_WEIGHTS = {
    "femtosecond": 5,
    "ultrafast": 4,
    "ablation": 4,
    "photonics": 3,
    "laser": 2,
    "optics": 1
}

# ─── COLLECTE NSF ─────────────────────────────────────────────────────────────
def collect_nsf():
    all_awards = []

    for offset in range(0, MAX_PROJECTS, 25):
        params = {
            "keyword": KEYWORD,
            "offset": offset,
            "printFields": "id,title,abstractText,fundsObligatedAmt,awardeeName,piFirstName,piLastName,piEmail,expDate"
        }

        try:
            r = requests.get(
                "https://api.nsf.gov/services/v1/awards.json",
                params=params,
                timeout=10
            )
            awards = r.json()["response"].get("award", [])

            if not awards:
                break

            all_awards.extend(awards)
            time.sleep(0.3)

        except Exception as e:
            st.warning(f"NSF - Erreur : {e}")
            break

    today = datetime.today()
    rows = []

    for award in all_awards:
        exp_date = award.get("expDate", "") or ""

        if exp_date:
            try:
                if datetime.strptime(exp_date, "%m/%d/%Y") < today:
                    continue
            except Exception:
                pass

        title = award.get("title", "") or ""
        description = award.get("abstractText", "") or ""
        text = (title + " " + description).lower()
        score = sum(w for kw, w in KEYWORDS_WEIGHTS.items() if kw in text)

        budget = award.get("fundsObligatedAmt", None)
        if budget == 0:
            budget = None

        rows.append({
            "source": "NSF",
            "title": title,
            "organization": award.get("awardeeName", ""),
            "country": "USA",
            "budget_usd": budget,
            "contact_name": f"{award.get('piFirstName', '') or ''} {award.get('piLastName', '') or ''}".strip(),
            "contact_email": award.get("piEmail", "") or "",
            "score": score,
            "keywords_matched": str([kw for kw in KEYWORDS_WEIGHTS if kw in text]),
            "description": description[:300],
            "end_date": exp_date,
            "link": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award.get('id', '')}" if award.get("id") else ""
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= 5]

# ─── COLLECTE NIH ─────────────────────────────────────────────────────────────
def collect_nih():
    all_projects = []
    offset = 0

    while offset < 500:
        payload = {
            "criteria": {
                "fiscal_years": [2023, 2024, 2025, 2026],
                "advanced_text_search": {
                    "operator": "or",
                    "search_field": "all",
                    "search_text": "femtosecond laser ultrafast ablation photonics"
                }
            },
            "offset": offset,
            "limit": 50,
            "fields": [
                "project_num",
                "project_title",
                "abstract_text",
                "total_cost",
                "org_name",
                "org_country",
                "principal_investigators",
                "project_end_date"
            ]
        }

        try:
            r = requests.post(
                "https://api.reporter.nih.gov/v2/projects/search",
                json=payload,
                timeout=15
            )
            results = r.json().get("results", [])

            if not results:
                break

            all_projects.extend(results)
            offset += 50
            time.sleep(0.3)

        except Exception as e:
            st.warning(f"NIH - Erreur : {e}")
            break

    rows = []

    for project in all_projects:
        try:
            title = project.get("project_title", "") or ""
            description = (project.get("abstract_text", "") or "")[:300]
            text = (title + " " + description).lower()
            score = sum(w for kw, w in KEYWORDS_WEIGHTS.items() if kw in text)

            pis = project.get("principal_investigators", [])
            contact_name = ""

            if pis and isinstance(pis, list) and isinstance(pis[0], dict):
                contact_name = f"{pis[0].get('first_name', '') or ''} {pis[0].get('last_name', '') or ''}".strip()

            budget = project.get("total_cost", None)
            if budget == 0:
                budget = None

            project_num = project.get("project_num", "") or ""

            rows.append({
                "source": "NIH",
                "title": title,
                "organization": project.get("org_name", "") or "",
                "country": "USA",
                "budget_usd": budget,
                "contact_name": contact_name,
                "contact_email": "",
                "score": score,
                "keywords_matched": str([kw for kw in KEYWORDS_WEIGHTS if kw in text]),
                "description": description,
                "end_date": (project.get("project_end_date", "") or "")[:10],
                "link": f"https://reporter.nih.gov/project-details/{project_num}" if project_num else ""
            })

        except Exception:
            continue

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= 5]

# ─── COLLECTE CORDIS ──────────────────────────────────────────────────────────
def collect_cordis():
    all_projects = []

    for page in range(1, 21):
        try:
            r = requests.get(
                f"https://cordis.europa.eu/api/search/results?q=laser&p={page}&num=10&format=json&archived=false",
                timeout=10
            )
            results = r.json().get("payload", {}).get("results", [])

            if not results:
                break

            all_projects.extend(results)
            time.sleep(0.3)

        except Exception:
            break

    rows = []

    for project in all_projects:
        title = project.get("title", "") or ""
        description = project.get("teaser", "") or ""
        text = (title + " " + description).lower()
        score = sum(w for kw, w in KEYWORDS_WEIGHTS.items() if kw in text)
        ref = project.get("reference", "") or ""

        rows.append({
            "source": "CORDIS",
            "title": title,
            "organization": project.get("acronym", ""),
            "country": project.get("coordinatedIn", ""),
            "budget_usd": None,
            "contact_name": "",
            "contact_email": "",
            "score": score,
            "keywords_matched": str([kw for kw in KEYWORDS_WEIGHTS if kw in text]),
            "description": description[:300],
            "end_date": project.get("endDate", "") or "",
            "link": f"https://cordis.europa.eu/project/id/{ref}" if ref else ""
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return df[df["score"] >= 5]

# ─── PIPELINE GLOBAL ──────────────────────────────────────────────────────────
def run_pipeline():
    st.info("📡 Collecte NSF...")
    df_nsf = collect_nsf()

    st.info("🔬 Collecte NIH...")
    df_nih = collect_nih()

    st.info("🇪🇺 Collecte CORDIS...")
    df_cordis = collect_cordis()

    df_total = pd.concat([df_nsf, df_nih, df_cordis], ignore_index=True)

    if not df_total.empty:
        df_total = df_total.sort_values("score", ascending=False).reset_index(drop=True)

    df_total.to_csv("leads_laser.csv", index=False)
    return df_total

# ─── CHARGEMENT DONNÉES ───────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("leads_laser.csv")

    for col in [
        "source", "title", "organization", "country", "contact_name",
        "contact_email", "keywords_matched", "description", "end_date", "link"
    ]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")

    return df

# ─── CONTEXTE POUR GEMINI ─────────────────────────────────────────────────────
def dataframe_context(df: pd.DataFrame, max_rows: int = 40) -> str:
    if df.empty:
        return "Aucun prospect disponible."

    cols = [
        "source", "title", "organization", "country", "budget_usd",
        "contact_name", "contact_email", "score",
        "keywords_matched", "description", "end_date", "link"
    ]

    safe_df = df.copy()

    for col in cols:
        if col not in safe_df.columns:
            safe_df[col] = ""

    safe_df = safe_df[cols].head(max_rows).fillna("")
    return safe_df.to_json(orient="records", force_ascii=False)

# ─── CHATBOT GEMINI ───────────────────────────────────────────────────────────
def call_gemini_chatbot(user_message: str, df: pd.DataFrame, history: list, interface_name: str):
    if not GEMINI_API_KEY:
        return "Clé API Gemini absente. Ajoute GEMINI_API_KEY dans le fichier .env."

    history_text = ""

    for msg in history[-10:]:
        role = "Utilisateur" if msg["role"] == "user" else "Assistant"
        history_text += f"{role} : {msg['content']}\n"

    prompt = f"""
Tu es un assistant commercial spécialisé dans la prospection laser.

Interface actuelle :
{interface_name}

Objectif :
- aider l'utilisateur à identifier les prospects/projets laser les plus intéressants
- répondre naturellement en français
- t'appuyer uniquement sur les données fournies
- tenir compte de l'historique récent de la conversation

Consignes :
- si l'utilisateur demande "les plus pertinents", considère par défaut les meilleurs scores
- si l'utilisateur demande "d'autres", "pas les mêmes", "autres prospects", évite de répéter les éléments déjà mentionnés dans la conversation si possible
- si la demande est floue, pose UNE question de clarification courte
- sois concret, utile et synthétique
- quand tu proposes des prospects, cite le titre, l'organisation, le pays, le budget si disponible, le score et le contact si disponible
- ne dis jamais juste "je n'ai pas compris" sans essayer d'aider
- si aucune donnée ne correspond clairement, explique-le simplement
- ne t'invente aucun prospect
- ne parle que des prospects présents dans cette interface

Historique récent :
{history_text}

Base prospects disponible :
{dataframe_context(df)}

Question utilisateur :
{user_message}
""".strip()

    try:
        model = genai.GenerativeModel(MODEL_NAME)

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 400
            }
        )

        answer = response.text.strip() if hasattr(response, "text") else ""

        if not answer:
            return "Je n'ai pas pu générer de réponse."

        return answer

    except Exception as e:
        return f"Erreur Gemini : {e}"

# ─── COMPOSANT INTERFACE ──────────────────────────────────────────────────────
def render_prospect_interface(df_base: pd.DataFrame, interface_name: str, chat_key: str, export_name: str):
    st.subheader(interface_name)

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total", len(df_base))
    col2.metric("NSF", len(df_base[df_base["source"] == "NSF"]))
    col3.metric("NIH", len(df_base[df_base["source"] == "NIH"]))
    col4.metric("CORDIS", len(df_base[df_base["source"] == "CORDIS"]))
    col5.metric("Score max", int(df_base["score"].max()) if len(df_base) > 0 else 0)

    st.divider()

    # ─── FILTRES ──────────────────────────────────────────────────────────────
    st.subheader("🎛️ Filtres")

    max_score = int(df_base["score"].max()) if len(df_base) > 0 else 15

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)

    with col_f1:
        score_min = st.slider(
            "Score minimum",
            0,
            max_score,
            5,
            key=f"{chat_key}_score_min"
        )

    with col_f2:
        budget_range = st.slider(
            "Budget ($)",
            0,
            15_000_000,
            (0, 15_000_000),
            100_000,
            format="$%d",
            key=f"{chat_key}_budget"
        )

    with col_f3:
        email_only = st.checkbox(
            "Email uniquement",
            value=False,
            key=f"{chat_key}_email"
        )

    with col_f4:
        budget_only = st.checkbox(
            "Budget uniquement",
            value=False,
            key=f"{chat_key}_budget_only"
        )

    filtered = df_base[df_base["score"] >= score_min].copy()

    if email_only:
        filtered = filtered[filtered["contact_email"] != ""]

    if budget_only:
        filtered = filtered[pd.to_numeric(filtered["budget_usd"], errors="coerce").notna()]

    budget_numeric = pd.to_numeric(filtered["budget_usd"], errors="coerce")
    filtered = filtered[
        budget_numeric.isna() |
        ((budget_numeric >= budget_range[0]) & (budget_numeric <= budget_range[1]))
    ]

    # ─── TRI ──────────────────────────────────────────────────────────────────
    st.subheader("🔃 Tri")

    col_s1, col_s2 = st.columns(2)

    with col_s1:
        sort_by = st.selectbox(
            "Trier par",
            ["Score", "Budget", "Date de fin"],
            index=0,
            key=f"{chat_key}_sort_by"
        )

    with col_s2:
        sort_order = st.selectbox(
            "Ordre",
            ["Décroissant ↓", "Croissant ↑"],
            index=0,
            key=f"{chat_key}_sort_order"
        )

    ascending = sort_order == "Croissant ↑"

    if sort_by == "Score":
        filtered = filtered.sort_values("score", ascending=ascending)

    elif sort_by == "Budget":
        filtered["_budget_sort"] = pd.to_numeric(filtered["budget_usd"], errors="coerce")
        filtered = filtered.sort_values("_budget_sort", ascending=ascending, na_position="last")
        filtered = filtered.drop(columns=["_budget_sort"])

    elif sort_by == "Date de fin":
        filtered["_date_sort"] = pd.to_datetime(filtered["end_date"], errors="coerce")
        filtered = filtered.sort_values("_date_sort", ascending=ascending, na_position="last")
        filtered = filtered.drop(columns=["_date_sort"])

    filtered = filtered.reset_index(drop=True)
    filtered.index = filtered.index + 1

    st.caption(f"**{len(filtered)} prospects** correspondent aux filtres")
    st.divider()

    # ─── TABLEAU ──────────────────────────────────────────────────────────────
    st.subheader("📋 Prospects qualifiés")

    display_cols = [
        "source", "title", "organization", "country", "budget_usd",
        "contact_name", "contact_email", "score", "keywords_matched",
        "end_date", "link"
    ]

    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        height=400,
        column_config={
            "source": st.column_config.TextColumn("Source"),
            "title": st.column_config.TextColumn("Projet", width="large"),
            "organization": st.column_config.TextColumn("Organisation"),
            "country": st.column_config.TextColumn("Pays"),
            "budget_usd": st.column_config.NumberColumn("Budget ($)", format="$%d"),
            "contact_name": st.column_config.TextColumn("Contact"),
            "contact_email": st.column_config.TextColumn("Email"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=15),
            "keywords_matched": st.column_config.TextColumn("Mots-clés"),
            "end_date": st.column_config.TextColumn("Fin projet"),
            "link": st.column_config.LinkColumn("Lien projet"),
        }
    )

    st.divider()

    # ─── VISUALISATIONS ───────────────────────────────────────────────────────
    st.subheader("📊 Visualisations")

    viz_col1, viz_col2 = st.columns(2)

    with viz_col1:
        st.markdown("**Distribution des scores**")
        if not filtered.empty:
            score_dist = (
                filtered["score"]
                .value_counts()
                .sort_index()
                .rename_axis("Score")
                .rename("Nombre de prospects")
            )
            st.bar_chart(score_dist, width="stretch")
        else:
            st.info("Aucune donnée à afficher.")

    with viz_col2:
        st.markdown("**Top 10 prospects par budget**")
        df_budget = filtered.copy()
        df_budget["budget_usd"] = pd.to_numeric(df_budget["budget_usd"], errors="coerce")
        top10 = (
            df_budget.dropna(subset=["budget_usd"])
            .nlargest(10, "budget_usd")[["title", "budget_usd"]]
        )
        if not top10.empty:
            top10 = top10.copy()
            top10["label"] = top10["title"].str[:35] + "…"
            st.bar_chart(top10.set_index("label")["budget_usd"], width="stretch")
        else:
            st.info("Aucun prospect avec budget disponible.")

    st.divider()

    # ─── DÉTAIL PROSPECT ──────────────────────────────────────────────────────
    st.subheader("🔍 Détail d'un prospect")

    if len(filtered) > 0:
        options = {i: f"#{i} — {row['title'][:60]}..." for i, row in filtered.iterrows()}

        selected_idx = st.selectbox(
            "Sélectionne un prospect",
            list(options.keys()),
            format_func=lambda x: options[x],
            key=f"{chat_key}_selected_prospect"
        )

        row = filtered.loc[selected_idx]

        c1, c2 = st.columns(2)

        with c1:
            st.markdown(f"**# Prospect :** {selected_idx}")
            st.markdown(f"**Titre :** {row['title']}")
            st.markdown(f"**Source :** {row['source']}")
            st.markdown(f"**Organisation :** {row['organization']}")
            st.markdown(f"**Pays :** {row['country']}")

            budget = row["budget_usd"]
            st.markdown(
                f"**Budget :** {'Non disponible' if pd.isna(budget) or budget == '' else f'${int(float(budget)):,}'}"
            )

            st.markdown(f"**Fin projet :** {row['end_date'] or 'Non disponible'}")
            st.markdown(f"**Score :** {int(row['score'])}/15")
            st.markdown(f"**Mots-clés :** {row['keywords_matched']}")

        with c2:
            st.markdown(f"**Contact :** {row['contact_name'] or 'Non disponible'}")
            st.markdown(f"**Email :** {row['contact_email'] or 'Non disponible'}")

            if row["link"]:
                st.markdown(f"**Lien projet :** [Voir le projet]({row['link']})")

        st.markdown("**Résumé du projet :**")
        st.info(row["description"])

    else:
        st.warning("Aucun prospect ne correspond aux filtres.")

    st.divider()

    # ─── CHAT IA ──────────────────────────────────────────────────────────────
    st.subheader("🤖 Assistant commercial IA")
    st.caption("Exemples : 'Quels sont les prospects les plus pertinents ?' | 'Montre-moi d'autres prospects avec un gros budget'")

    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input(
        f"Pose ta question pour {interface_name}...",
        key=f"{chat_key}_input"
    )

    if question:
        st.session_state[chat_key].append({
            "role": "user",
            "content": question
        })

        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            response = call_gemini_chatbot(
                user_message=question,
                df=filtered if len(filtered) > 0 else df_base,
                history=st.session_state[chat_key],
                interface_name=interface_name
            )
            st.markdown(response)

        st.session_state[chat_key].append({
            "role": "assistant",
            "content": response
        })

    st.divider()

    # ─── EXPORT ───────────────────────────────────────────────────────────────
    st.subheader("⬇️ Export")

    csv = filtered.to_csv(index=False, sep=";").encode("utf-8-sig")

    st.download_button(
        "📥 Télécharger les prospects (CSV)",
        data=csv,
        file_name=export_name,
        mime="text/csv",
        key=f"{chat_key}_download"
    )

# ─── INTERFACE PRINCIPALE ─────────────────────────────────────────────────────
st.title("🔬 Laser Prospects — Prospection intelligente")
st.caption("NSF + NIH + CORDIS — interfaces séparées")

col_refresh, col_info = st.columns([1, 4])

with col_refresh:
    if st.button("🔄 Rafraîchir les données"):
        with st.spinner("Collecte en cours... (~2 min)"):
            df = run_pipeline()
            st.cache_data.clear()

        st.success(f"✅ {len(df)} prospects mis à jour !")
        st.rerun()

with col_info:
    try:
        last_modified = os.path.getmtime("leads_laser.csv")
        last_date = datetime.fromtimestamp(last_modified).strftime("%d/%m/%Y à %H:%M")
        st.caption(f"Dernière mise à jour : {last_date}")
    except Exception:
        st.caption("Dernière mise à jour : inconnue")

if not os.path.exists("leads_laser.csv"):
    st.warning("⚠️ Pas de données. Clique sur Rafraîchir.")
    st.stop()

df = load_data()

df_nsf = df[df["source"] == "NSF"].copy()
df_europe = df[df["source"].isin(["CORDIS", "NIH"])].copy()

tab_nsf, tab_europe = st.tabs([
    "🇺🇸 Interface NSF",
    "🇪🇺 Interface Europe / CORDIS + NIH"
])

with tab_nsf:
    render_prospect_interface(
        df_base=df_nsf,
        interface_name="Interface NSF",
        chat_key="chat_history_nsf",
        export_name="prospects_nsf_export.csv"
    )

with tab_europe:
    render_prospect_interface(
        df_base=df_europe,
        interface_name="Interface Europe / CORDIS + NIH",
        chat_key="chat_history_europe",
        export_name="prospects_europe_cordis_nih_export.csv"
    )