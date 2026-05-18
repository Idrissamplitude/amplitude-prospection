import streamlit as st
import pandas as pd
import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv
import ollama

st.set_page_config(page_title="Laser Prospects", page_icon="🔬", layout="wide")

# ─── CONFIG API ───────────────────────────────────────────────────────────────
load_dotenv()

# ─── AUTHENTIFICATION ─────────────────────────────────────────────────────────
def check_password():
    app_password = os.getenv("APP_PASSWORD", "")

    if not app_password:
        return True

    if st.session_state.get("authenticated"):
        return True

    st.title("🔬 Laser Prospects")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Connexion")
        pwd = st.text_input("Mot de passe", type="password", key="pwd_input")
        if st.button("Se connecter", use_container_width=True):
            if pwd == app_password:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")

    return False

if not check_password():
    st.stop()

OLLAMA_MODEL = "mistral"

# ─── CONFIG PIPELINE ──────────────────────────────────────────────────────────
KEYWORD = "laser"
MAX_PROJECTS = 500

KEYWORDS_WEIGHTS = {
    # Très haute pertinence — cœur de métier Amplitude
    "femtosecond": 5,
    "ultrafast": 4,
    "ultrashort": 4,
    "ablation": 4,
    "multiphoton": 4,
    "high energy": 4,
    "laser based acceleration": 4,
    "inertial confinement fusion": 4,
    # Haute pertinence
    "two-photon": 3,
    "biophotonics": 3,
    "photonics": 3,
    "nonlinear": 3,
    "pulsed laser": 3,
    "fiber laser": 3,
    # Pertinence moyenne
    "lidar": 2,
    "micromachining": 2,
    "laser": 2,
    "spectroscopy": 2,
    "waveguide": 2,
    # Pertinence faible
    "optics": 1,
    "optical": 1,
}

# Score max théorique : chaque mot-clé en titre (×2) + description (×1)
SCORE_MAX = sum(w * 3 for w in KEYWORDS_WEIGHTS.values())
SCORE_MIN_FILTER = 5


def compute_score(title: str, description: str) -> tuple:
    """Titre vaut 2× la description. Description complète utilisée (non tronquée)."""
    title_lower = title.lower()
    desc_lower = description.lower()
    score = 0
    matched = []

    for kw, weight in KEYWORDS_WEIGHTS.items():
        kw_score = 0
        if kw in title_lower:
            kw_score += weight * 2
        if kw in desc_lower:
            kw_score += weight
        if kw_score > 0:
            score += kw_score
            matched.append(kw)

    return score, matched

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
        score, matched = compute_score(title, description)

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
            "keywords_matched": str(matched),
            "description": description,
            "end_date": exp_date,
            "link": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award.get('id', '')}" if award.get("id") else ""
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= SCORE_MIN_FILTER]

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
                    "search_text": "femtosecond laser ultrafast ablation photonics ultrashort multiphoton biophotonics nonlinear pulsed fiber lidar micromachining high energy laser acceleration inertial confinement fusion"
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
            description = project.get("abstract_text", "") or ""
            score, matched = compute_score(title, description)

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
                "keywords_matched": str(matched),
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
    return df[df["score"] >= SCORE_MIN_FILTER]

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
        score, matched = compute_score(title, description)
        ref = project.get("relatedProjectReference", "") or project.get("reference", "") or ""

        if not ref:
            continue

        rows.append({
            "source": "CORDIS",
            "title": title,
            "organization": project.get("relatedProjectAcronym", "") or project.get("acronym", ""),
            "country": "Europe (UE)",
            "budget_usd": None,
            "contact_name": "",
            "contact_email": "",
            "score": score,
            "keywords_matched": str(matched),
            "description": description,
            "end_date": project.get("endDate", "") or "",
            "link": f"https://cordis.europa.eu/project/id/{ref}" if ref else ""
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return df[df["score"] >= SCORE_MIN_FILTER]

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

# ─── STATUTS PROSPECTS ───────────────────────────────────────────────────────
STATUS_FILE = "prospect_status.csv"
STATUTS = ["—", "À contacter", "Contacté", "Pas intéressé", "À recontacter"]



def load_status() -> dict:
    if not os.path.exists(STATUS_FILE):
        return {}
    try:
        df = pd.read_csv(STATUS_FILE)
        return {
            str(row["link"]): {"status": str(row["status"]), "note": str(row.get("note", "") or "")}
            for _, row in df.iterrows()
        }
    except Exception:
        return {}


def save_status(link: str, title: str, status: str, note: str):
    if os.path.exists(STATUS_FILE):
        df = pd.read_csv(STATUS_FILE)
    else:
        df = pd.DataFrame(columns=["link", "title", "status", "note", "updated_at"])

    df = df[df["link"] != link]

    if status != "—":
        new_row = pd.DataFrame([{
            "link": link,
            "title": title,
            "status": status,
            "note": note,
            "updated_at": datetime.today().strftime("%Y-%m-%d %H:%M")
        }])
        df = pd.concat([df, new_row], ignore_index=True)

    df.to_csv(STATUS_FILE, index=False)


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

# ─── CHATBOT OLLAMA ───────────────────────────────────────────────────────────
def call_ollama_chatbot(user_message: str, df: pd.DataFrame, history: list, interface_name: str):
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
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2}
        )
        return response["message"]["content"].strip()

    except Exception as e:
        return f"Erreur Ollama : {e}"

# ─── COMPOSANT INTERFACE ──────────────────────────────────────────────────────
def render_prospect_interface(df_base: pd.DataFrame, interface_name: str, chat_key: str, export_name: str, show_budget_email: bool = True):
    st.subheader(interface_name)

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total", len(df_base))
    col2.metric("NSF", len(df_base[df_base["source"] == "NSF"]))
    col3.metric("NIH", len(df_base[df_base["source"] == "NIH"]))
    col4.metric("CORDIS", len(df_base[df_base["source"] == "CORDIS"]))
    col5.metric("Score max", int(df_base["score"].max()) if len(df_base) > 0 else 0)

    st.divider()

    # ─── FILTRES & TRI (expander) ─────────────────────────────────────────────
    search_query = st.text_input(
        "🔎 Recherche libre (titre, description, organisation)",
        value="",
        placeholder="ex: photonics, Stanford, ablation...",
        key=f"{chat_key}_search"
    )

    with st.expander("🎛️ Filtres & Tri", expanded=False):
        max_score = int(df_base["score"].max()) if len(df_base) > 0 else 15

        if show_budget_email:
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
        else:
            col_e1, col_e2 = st.columns(2)

            with col_e1:
                score_min = st.slider(
                    "Score minimum",
                    0,
                    max_score,
                    5,
                    key=f"{chat_key}_score_min"
                )

            with col_e2:
                available_countries = sorted(df_base["country"].dropna().unique().tolist())
                available_countries = [c for c in available_countries if c]
                country_filter = st.multiselect(
                    "Filtrer par pays",
                    available_countries,
                    default=[],
                    key=f"{chat_key}_country_filter"
                )

            email_only = False
            budget_only = False
            budget_range = (0, 15_000_000)

        if show_budget_email:
            country_filter = []

        col_f5, col_s1, col_s2 = st.columns(3)

        with col_f5:
            statut_filter = st.multiselect(
                "Filtrer par statut",
                STATUTS[1:],
                default=[],
                key=f"{chat_key}_statut_filter"
            )

        with col_s1:
            sort_options = ["Score", "Budget", "Date de fin"] if show_budget_email else ["Score", "Date de fin"]
            sort_by = st.selectbox(
                "Trier par",
                sort_options,
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

    statuses = load_status()

    filtered = df_base[df_base["score"] >= score_min].copy()
    filtered["statut"] = filtered["link"].map(lambda l: statuses.get(l, {}).get("status", "—"))

    if search_query.strip():
        q = search_query.strip().lower()
        mask = (
            filtered["title"].str.lower().str.contains(q, na=False) |
            filtered["description"].str.lower().str.contains(q, na=False) |
            filtered["organization"].str.lower().str.contains(q, na=False)
        )
        filtered = filtered[mask]

    if statut_filter:
        filtered = filtered[filtered["statut"].isin(statut_filter)]

    if country_filter:
        filtered = filtered[filtered["country"].isin(country_filter)]

    if show_budget_email:
        if email_only:
            filtered = filtered[filtered["contact_email"] != ""]

        if budget_only:
            filtered = filtered[pd.to_numeric(filtered["budget_usd"], errors="coerce").notna()]

        budget_numeric = pd.to_numeric(filtered["budget_usd"], errors="coerce")
        filtered = filtered[
            budget_numeric.isna() |
            ((budget_numeric >= budget_range[0]) & (budget_numeric <= budget_range[1]))
        ]

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

    # ─── TOP 5 CARTES ─────────────────────────────────────────────────────────
    st.subheader("🏆 Top 5 prospects")

    top5 = filtered.head(5) if not filtered.empty else pd.DataFrame()

    if not top5.empty:
        cols = st.columns(min(len(top5), 5))
        for col, (_, row) in zip(cols, top5.iterrows()):
            with col:
                with st.container(border=True):
                    score_val = int(row["score"])
                    statut_val = row.get("statut", "—")
                    st.markdown(f"**{row['source']}** · {row['country']}")
                    st.markdown(f"_{row['title'][:60]}..._" if len(row['title']) > 60 else f"_{row['title']}_")
                    st.caption(row["organization"][:40] if row["organization"] else "—")
                    if show_budget_email:
                        budget = row.get("budget_usd")
                        budget_str = f"${int(float(budget)):,}" if pd.notna(budget) and budget != "" else "—"
                        m1, m2 = st.columns(2)
                        m1.metric("Score", score_val)
                        m2.metric("Budget", budget_str)
                    else:
                        st.metric("Score", score_val)
                    if statut_val != "—":
                        st.caption(f"📌 {statut_val}")
    else:
        st.info("Aucun prospect à afficher.")

    st.divider()

    # ─── TABLEAU ──────────────────────────────────────────────────────────────
    st.subheader("📋 Prospects qualifiés")

    if show_budget_email:
        display_cols = [
            "statut", "source", "title", "organization", "country", "budget_usd",
            "contact_name", "contact_email", "score", "keywords_matched",
            "end_date", "link"
        ]
        col_config = {
            "statut": st.column_config.TextColumn("Statut"),
            "source": st.column_config.TextColumn("Source"),
            "title": st.column_config.TextColumn("Projet", width="large"),
            "organization": st.column_config.TextColumn("Organisation"),
            "country": st.column_config.TextColumn("Pays"),
            "budget_usd": st.column_config.NumberColumn("Budget ($)", format="$%d"),
            "contact_name": st.column_config.TextColumn("Contact"),
            "contact_email": st.column_config.TextColumn("Email"),
            "score": st.column_config.NumberColumn("Score"),
            "keywords_matched": st.column_config.TextColumn("Mots-clés"),
            "end_date": st.column_config.TextColumn("Fin projet"),
            "link": st.column_config.LinkColumn("Lien projet"),
        }
    else:
        display_cols = [
            "statut", "source", "title", "organization", "country",
            "contact_name", "score", "keywords_matched",
            "end_date", "link"
        ]
        col_config = {
            "statut": st.column_config.TextColumn("Statut"),
            "source": st.column_config.TextColumn("Source"),
            "title": st.column_config.TextColumn("Projet", width="large"),
            "organization": st.column_config.TextColumn("Organisation"),
            "country": st.column_config.TextColumn("Pays"),
            "contact_name": st.column_config.TextColumn("Contact"),
            "score": st.column_config.NumberColumn("Score"),
            "keywords_matched": st.column_config.TextColumn("Mots-clés"),
            "end_date": st.column_config.TextColumn("Fin projet"),
            "link": st.column_config.LinkColumn("Lien projet"),
        }

    st.dataframe(
        filtered[display_cols],
        width="stretch",
        height=400,
        column_config=col_config
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
        if show_budget_email:
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
        else:
            st.markdown("**Répartition par pays**")
            if not filtered.empty:
                country_dist = (
                    filtered["country"]
                    .value_counts()
                    .rename_axis("Pays")
                    .rename("Nombre de prospects")
                )
                st.bar_chart(country_dist, width="stretch")
            else:
                st.info("Aucune donnée à afficher.")

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

            if show_budget_email:
                budget = row["budget_usd"]
                st.markdown(
                    f"**Budget :** {'Non disponible' if pd.isna(budget) or budget == '' else f'${int(float(budget)):,}'}"
                )

            st.markdown(f"**Fin projet :** {row['end_date'] or 'Non disponible'}")
            st.markdown(f"**Score :** {int(row['score'])}")
            st.markdown(f"**Mots-clés :** {row['keywords_matched']}")

        with c2:
            st.markdown(f"**Contact :** {row['contact_name'] or 'Non disponible'}")
            if show_budget_email:
                st.markdown(f"**Email :** {row['contact_email'] or 'Non disponible'}")

            if row["link"]:
                st.markdown(f"**Lien projet :** [Voir le projet]({row['link']})")

        st.markdown("**Résumé du projet :**")
        st.info(row["description"])

        st.divider()
        st.markdown("**Statut commercial**")

        prospect_key = row["link"] or row["title"]
        current = statuses.get(prospect_key, {})
        current_status = current.get("status", "—")
        current_note = current.get("note", "")

        s_col1, s_col2 = st.columns([1, 2])

        with s_col1:
            new_status = st.selectbox(
                "Statut",
                STATUTS,
                index=STATUTS.index(current_status) if current_status in STATUTS else 0,
                key=f"{chat_key}_status_{selected_idx}"
            )

        with s_col2:
            new_note = st.text_input(
                "Note",
                value=current_note,
                key=f"{chat_key}_note_{selected_idx}"
            )

        if st.button("Enregistrer le statut", key=f"{chat_key}_save_{selected_idx}"):
            save_status(prospect_key, row["title"], new_status, new_note)
            st.success("Statut enregistré.")
            st.rerun()

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
            response = call_ollama_chatbot(
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

df_usa = df[df["source"].isin(["NSF", "NIH"])].copy()
df_europe = df[df["source"] == "CORDIS"].copy()

tab_usa, tab_europe = st.tabs([
    "🇺🇸 Interface USA (NSF + NIH)",
    "🇪🇺 Interface Europe (CORDIS)"
])

with tab_usa:
    render_prospect_interface(
        df_base=df_usa,
        interface_name="Interface USA — NSF + NIH",
        chat_key="chat_history_usa",
        export_name="prospects_usa_export.csv"
    )

with tab_europe:
    render_prospect_interface(
        df_base=df_europe,
        interface_name="Interface Europe — CORDIS",
        chat_key="chat_history_europe",
        export_name="prospects_europe_cordis_export.csv",
        show_budget_email=False
    )