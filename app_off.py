import streamlit as st
import pandas as pd
import requests
import time
import os
from datetime import datetime

# ─── CONFIG PAGE ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Laser Prospects",
    page_icon="🔬",
    layout="wide"
)

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

# ─── PIPELINE NSF ─────────────────────────────────────────────────────────────
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
                end = datetime.strptime(exp_date, "%m/%d/%Y")
                if end < today:
                    continue
            except:
                pass

        title = award.get("title", "") or ""
        description = award.get("abstractText", "") or ""
        text = (title + " " + description).lower()

        score = sum(w for kw, w in KEYWORDS_WEIGHTS.items() if kw in text)
        matched_keywords = [kw for kw in KEYWORDS_WEIGHTS if kw in text]

        first = award.get("piFirstName", "") or ""
        last = award.get("piLastName", "") or ""
        email = award.get("piEmail", "") or ""
        award_id = award.get("id", "") or ""

        budget = award.get("fundsObligatedAmt", None)
        if budget == 0:
            budget = None

        rows.append({
            "source": "NSF",
            "title": title,
            "organization": award.get("awardeeName", ""),
            "country": "USA",
            "budget_usd": budget,
            "contact_name": f"{first} {last}".strip(),
            "contact_email": email,
            "score": score,
            "keywords_matched": matched_keywords,
            "description": description[:300],
            "end_date": exp_date,
            "link": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award_id}" if award_id else ""
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= 5]

# ─── PIPELINE NIH ─────────────────────────────────────────────────────────────
def collect_nih():
    all_projects = []
    offset = 0
    limit = 50

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
            "limit": limit,
            "fields": [
                "project_num", "project_title", "abstract_text",
                "total_cost", "org_name", "org_country",
                "principal_investigators", "project_start_date",
                "project_end_date"
            ]
        }

        try:
            r = requests.post(
                "https://api.reporter.nih.gov/v2/projects/search",
                json=payload,
                timeout=15
            )
            data = r.json()
            results = data.get("results", [])
            if not results:
                break

            all_projects.extend(results)
            offset += limit
            time.sleep(0.3)

        except Exception as e:
            st.warning(f"NIH - Erreur collecte : {e}")
            break

    rows = []

    for project in all_projects:
        try:
            title = project.get("project_title", "") or ""
            description = project.get("abstract_text", "") or ""
            if description:
                description = description[:300]

            text = (title + " " + description).lower()
            score = sum(w for kw, w in KEYWORDS_WEIGHTS.items() if kw in text)
            matched_keywords = [kw for kw in KEYWORDS_WEIGHTS if kw in text]

            pis = project.get("principal_investigators", [])
            contact_name = ""

            if pis and isinstance(pis, list) and len(pis) > 0:
                pi = pis[0]
                if isinstance(pi, dict):
                    first = pi.get("first_name", "") or ""
                    last = pi.get("last_name", "") or ""
                    contact_name = f"{first} {last}".strip()

            budget = project.get("total_cost", None)
            if budget == 0:
                budget = None

            end_date = (project.get("project_end_date", "") or "")[:10]
            project_num = project.get("project_num", "") or ""
            link = f"https://reporter.nih.gov/project-details/{project_num}" if project_num else ""

            rows.append({
                "source": "NIH",
                "title": title,
                "organization": project.get("org_name", "") or "",
                "country": project.get("org_country", "USA") or "USA",
                "budget_usd": budget,
                "contact_name": contact_name,
                "contact_email": "",
                "score": score,
                "keywords_matched": matched_keywords,
                "description": description,
                "end_date": end_date,
                "link": link
            })

        except Exception as e:
            st.warning(f"NIH - Erreur projet : {e}")
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= 5]

# ─── PIPELINE CORDIS ──────────────────────────────────────────────────────────
def collect_cordis():
    all_projects = []

    for page in range(1, 21):
        try:
            url = f"https://cordis.europa.eu/api/search/results?q=laser&p={page}&num=10&format=json&archived=false"
            r = requests.get(url, timeout=10)
            data = r.json()
            results = data.get("payload", {}).get("results", [])
            if not results:
                break

            all_projects.extend(results)
            time.sleep(0.3)

        except Exception as e:
            st.warning(f"CORDIS - Erreur page {page} : {e}")
            break

    rows = []

    for project in all_projects:
        title = project.get("title", "") or ""
        description = project.get("teaser", "") or ""
        text = (title + " " + description).lower()

        score = sum(w for kw, w in KEYWORDS_WEIGHTS.items() if kw in text)
        matched_keywords = [kw for kw in KEYWORDS_WEIGHTS if kw in text]

        ref = project.get("reference", "") or ""
        end_date = project.get("endDate", "") or ""

        rows.append({
            "source": "CORDIS",
            "title": title,
            "organization": project.get("acronym", ""),
            "country": project.get("coordinatedIn", ""),
            "budget_usd": None,
            "contact_name": "",
            "contact_email": "",
            "score": score,
            "keywords_matched": matched_keywords,
            "description": description[:300],
            "end_date": end_date,
            "link": f"https://cordis.europa.eu/project/id/{ref}" if ref else ""
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= 5]

# ─── PIPELINE COMPLET ─────────────────────────────────────────────────────────
def run_pipeline():
    st.info("📡 Collecte NSF (USA)...")
    df_nsf = collect_nsf()

    st.info("🔬 Collecte NIH (USA - médical)...")
    df_nih = collect_nih()

    st.info("🇪🇺 Collecte CORDIS (Europe)...")
    df_cordis = collect_cordis()

    df_total = pd.concat([df_nsf, df_nih, df_cordis], ignore_index=True)

    if not df_total.empty:
        df_total = df_total.sort_values(by="score", ascending=False).reset_index(drop=True)

    df_total.to_csv("leads_laser.csv", index=False)
    return df_total

# ─── CHARGEMENT DATA ──────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv("leads_laser.csv")

    required_cols = [
        "source", "title", "organization", "country", "budget_usd",
        "contact_name", "contact_email", "score", "keywords_matched",
        "description", "end_date", "link"
    ]

    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")

    for col in [
        "contact_email", "contact_name", "keywords_matched",
        "description", "source", "country", "link",
        "end_date", "title", "organization"
    ]:
        df[col] = df[col].fillna("").astype(str)

    return df

# ─── HEADER ───────────────────────────────────────────────────────────────────
st.title("🔬 Laser Prospects — Prospection intelligente")
st.caption("Projets NSF + NIH (USA) + CORDIS (Europe) — actifs uniquement")

# ─── BOUTON REFRESH ───────────────────────────────────────────────────────────
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
    except:
        st.caption("Dernière mise à jour : inconnue")

# ─── CAS CSV MANQUANT ─────────────────────────────────────────────────────────
if not os.path.exists("leads_laser.csv"):
    st.warning("⚠️ Aucune donnée trouvée. Clique sur **Rafraîchir les données** pour lancer la collecte.")
    st.stop()

df = load_data()

st.divider()

# ─── KPIs ─────────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total prospects", len(df))
col2.metric("NSF (USA)", len(df[df["source"] == "NSF"]))
col3.metric("NIH (USA)", len(df[df["source"] == "NIH"]))
col4.metric("CORDIS (EU)", len(df[df["source"] == "CORDIS"]))
col5.metric("Avec email", df[df["contact_email"] != ""].shape[0])
col6.metric("Score max", int(df["score"].max()) if len(df) > 0 else 0)

st.divider()

# ─── FILTRES ──────────────────────────────────────────────────────────────────
st.subheader("🎛️ Filtres")

col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)

with col_f1:
    max_score = int(df["score"].max()) if len(df) > 0 else 15
    score_min = st.slider("Score minimum", 0, max_score, 5)

with col_f2:
    budget_range = st.slider(
        "Budget ($) — appliqué si disponible",
        min_value=0,
        max_value=15_000_000,
        value=(0, 15_000_000),
        step=100_000,
        format="$%d"
    )

with col_f3:
    sources = st.multiselect(
        "Source",
        options=["NSF", "NIH", "CORDIS"],
        default=["NSF", "NIH", "CORDIS"]
    )

with col_f4:
    email_only = st.checkbox("Avec email uniquement", value=False)

with col_f5:
    budget_only = st.checkbox("Avec budget uniquement", value=False)

# ─── APPLICATION FILTRES ──────────────────────────────────────────────────────
filtered = df[df["score"] >= score_min]
filtered = filtered[filtered["source"].isin(sources)]

if email_only:
    filtered = filtered[filtered["contact_email"] != ""]

if budget_only:
    filtered = filtered[pd.to_numeric(filtered["budget_usd"], errors="coerce").notna()]

budget_numeric = pd.to_numeric(filtered["budget_usd"], errors="coerce")

filtered = filtered[
    budget_numeric.isna() |
    ((budget_numeric >= budget_range[0]) & (budget_numeric <= budget_range[1]))
]

filtered = filtered.reset_index(drop=True)
filtered.index = filtered.index + 1

st.caption(f"**{len(filtered)} prospects** correspondent aux filtres")

st.divider()

# ─── TABLE PROSPECTS ──────────────────────────────────────────────────────────
st.subheader("📋 Prospects qualifiés")

col_sort1, col_sort2 = st.columns(2)

with col_sort1:
    sort_field = st.selectbox(
        "Trier par",
        ["Score", "Budget"],
        index=0
    )

with col_sort2:
    sort_order = st.selectbox(
        "Ordre",
        ["Décroissant", "Croissant"],
        index=0
    )

filtered = filtered.copy()
filtered["budget_sort"] = pd.to_numeric(filtered["budget_usd"], errors="coerce")

ascending = True if sort_order == "Croissant" else False

if sort_field == "Score":
    filtered = filtered.sort_values(
        by="score",
        ascending=ascending
    )
elif sort_field == "Budget":
    filtered = filtered.sort_values(
        by="budget_sort",
        ascending=ascending,
        na_position="last"
    )

filtered = filtered.drop(columns=["budget_sort"], errors="ignore")
filtered = filtered.reset_index(drop=True)
filtered.index = filtered.index + 1

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

# ─── FICHE DETAIL ─────────────────────────────────────────────────────────────
st.subheader("🔍 Détail d'un prospect")

if len(filtered) > 0:
    options = {i: f"#{i} — {row['title'][:60]}..." for i, row in filtered.iterrows()}

    selected_idx = st.selectbox(
        "Sélectionne un prospect",
        options=list(options.keys()),
        format_func=lambda x: options[x]
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
        budget_text = "Non disponible" if pd.isna(budget) or budget == "" else f"${int(float(budget)):,}"
        st.markdown(f"**Budget :** {budget_text}")

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
    st.warning("Aucun prospect ne correspond aux filtres sélectionnés.")

st.divider()

# ─── EXPORT ───────────────────────────────────────────────────────────────────
st.subheader("⬇️ Export")

csv = filtered.to_csv(index=False, sep=";").encode("utf-8-sig")
st.download_button(
    label="📥 Télécharger les prospects filtrés (CSV)",
    data=csv,
    file_name="prospects_export.csv",
    mime="text/csv"
)