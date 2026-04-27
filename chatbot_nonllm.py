import streamlit as st
import pandas as pd
import requests
import time
import os
from datetime import datetime

st.set_page_config(page_title="Laser Prospects", page_icon="🔬", layout="wide")

KEYWORD = "laser"
MAX_PROJECTS = 500
KEYWORDS_WEIGHTS = {
    "femtosecond": 5, "ultrafast": 4, "ablation": 4,
    "photonics": 3, "laser": 2, "optics": 1
}

def collect_nsf():
    all_awards = []
    for offset in range(0, MAX_PROJECTS, 25):
        params = {
            "keyword": KEYWORD, "offset": offset,
            "printFields": "id,title,abstractText,fundsObligatedAmt,awardeeName,piFirstName,piLastName,piEmail,expDate"
        }
        try:
            r = requests.get("https://api.nsf.gov/services/v1/awards.json", params=params, timeout=10)
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
            except:
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
            "contact_name": f"{award.get('piFirstName','') or ''} {award.get('piLastName','') or ''}".strip(),
            "contact_email": award.get("piEmail", "") or "",
            "score": score,
            "keywords_matched": str([kw for kw in KEYWORDS_WEIGHTS if kw in text]),
            "description": description[:300],
            "end_date": exp_date,
            "link": f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={award.get('id','')}" if award.get("id") else ""
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= 5]

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
            "fields": ["project_num", "project_title", "abstract_text", "total_cost", "org_name", "org_country", "principal_investigators", "project_end_date"]
        }
        try:
            r = requests.post("https://api.reporter.nih.gov/v2/projects/search", json=payload, timeout=15)
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
                contact_name = f"{pis[0].get('first_name','') or ''} {pis[0].get('last_name','') or ''}".strip()
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
        except:
            continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df[df["score"] >= 5]

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
        except:
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

@st.cache_data
def load_data():
    df = pd.read_csv("leads_laser.csv")
    for col in ["source", "title", "organization", "country", "contact_name", "contact_email", "keywords_matched", "description", "end_date", "link"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    return df

def chatbot_local(question, df):
    q = question.lower().strip()
    top = df.sort_values("score", ascending=False)

    if any(q == mot for mot in ["salut", "bonjour", "hello", "coucou", "hey", "yo"]):
        return "Salut ! Essaie : 'top 5 prospects', 'résumé', 'prospects femtoseconde'."

    if any(mot in q for mot in ["aide", "help", "que peux"]):
        return """Je peux répondre à :
- **"Top N prospects"** → les meilleurs par score
- **"Prospects femtoseconde / ultrafast / ablation"** → par technologie
- **"Prospects USA / France / Europe"** → par pays/source
- **"Prospects avec email"** → contacts disponibles
- **"Prospects avec budget"** → classés par financement
- **"Résumé"** → statistiques générales"""

    if any(mot in q for mot in ["meilleur", "top", "mieux", "priorité", "premier"]):
        n = 3
        for i in range(10, 0, -1):
            if str(i) in q:
                n = i
                break
        results = top.head(n)
        response = f"**🏆 Top {n} prospects :**\n\n"
        for idx, (_, row) in enumerate(results.iterrows(), 1):
            budget = f"${int(float(row['budget_usd'])):,}" if pd.notna(row['budget_usd']) else "N/A"
            response += f"**#{idx} — {row['title'][:70]}**\n"
            response += f"- 🏛️ {row['organization']} ({row['country']})\n"
            response += f"- 💰 {budget} | 🎯 Score : {int(row['score'])}/15\n"
            response += f"- 👤 {row['contact_name'] or 'N/A'} — {row['contact_email'] or 'N/A'}\n\n"
        return response

    pays_map = {
        "france": "France", "usa": "USA", "etats-unis": "USA",
        "états-unis": "USA", "allemagne": "Germany", "uk": "United Kingdom"
    }
    for key, val in pays_map.items():
        if key in q:
            results = top[top["country"].str.contains(val, case=False, na=False)].head(5)
            if results.empty:
                return f"Aucun prospect trouvé pour **{val}**."
            response = f"**🌍 Prospects en {val} :**\n\n"
            for _, row in results.iterrows():
                response += f"- **{row['title'][:60]}** — {row['organization']} — Score: {int(row['score'])}/15\n"
            return response

    if "nsf" in q:
        results = top[top["source"] == "NSF"].head(5)
        response = "**🇺🇸 Top 5 NSF :**\n\n"
        for _, row in results.iterrows():
            budget = f"${int(float(row['budget_usd'])):,}" if pd.notna(row['budget_usd']) else "N/A"
            response += f"- **{row['title'][:60]}** — {budget} — Score: {int(row['score'])}/15\n"
        return response

    if any(mot in q for mot in ["cordis", "europe", "européen"]):
        results = top[top["source"] == "CORDIS"].head(5)
        response = "**🇪🇺 Top 5 CORDIS :**\n\n"
        for _, row in results.iterrows():
            response += f"- **{row['title'][:60]}** — {row['country']} — Score: {int(row['score'])}/15\n"
        return response

    if any(mot in q for mot in ["nih", "médical", "medical"]):
        results = top[top["source"] == "NIH"].head(5)
        response = "**🔬 Top 5 NIH :**\n\n"
        for _, row in results.iterrows():
            response += f"- **{row['title'][:60]}** — Score: {int(row['score'])}/15\n"
        return response

    for mot in ["femtosecond", "ultrafast", "ablation", "photonics", "optics"]:
        if mot in q:
            results = top[top["keywords_matched"].str.contains(mot, case=False, na=False)].head(5)
            if results.empty:
                return f"Aucun prospect avec **{mot}**."
            response = f"**🔍 Prospects '{mot}' :**\n\n"
            for _, row in results.iterrows():
                budget = f"${int(float(row['budget_usd'])):,}" if pd.notna(row['budget_usd']) else "N/A"
                response += f"- **{row['title'][:60]}** — {budget} — Score: {int(row['score'])}/15\n"
            return response

    if any(mot in q for mot in ["email", "contact", "contacter"]):
        results = top[top["contact_email"] != ""].head(5)
        response = "**📧 Contacts disponibles :**\n\n"
        for _, row in results.iterrows():
            response += f"- **{row['contact_name']}** — {row['contact_email']} — {row['organization']}\n"
        return response

    if any(mot in q for mot in ["budget", "financement", "argent"]):
        results = top[pd.to_numeric(top["budget_usd"], errors="coerce").notna()]
        results = results.sort_values("budget_usd", ascending=False).head(5)
        response = "**💰 Plus grands budgets :**\n\n"
        for _, row in results.iterrows():
            response += f"- **{row['title'][:60]}** — ${int(float(row['budget_usd'])):,}\n"
        return response

    if any(mot in q for mot in ["résumé", "resume", "bilan", "combien", "total", "statistique"]):
        budget_mean = pd.to_numeric(df["budget_usd"], errors="coerce").mean()
        return f"""**📊 Résumé :**

- Total : **{len(df)} prospects**
- 🇺🇸 NSF : **{len(df[df['source']=='NSF'])}**
- 🔬 NIH : **{len(df[df['source']=='NIH'])}**
- 🇪🇺 CORDIS : **{len(df[df['source']=='CORDIS'])}**
- 📧 Avec email : **{len(df[df['contact_email']!=''])}**
- 💰 Budget moyen : **${budget_mean:,.0f}**
- 🏆 Score max : **{int(df['score'].max())}/15**"""

    return """Je n'ai pas compris. Essaie :
- **"Top 5 prospects"**
- **"Prospects femtoseconde"**
- **"Prospects en USA"**
- **"Résumé"**
- **"aide"**"""

# ─── INTERFACE ────────────────────────────────────────────────────────────────
st.title("🔬 Laser Prospects — Prospection intelligente")
st.caption("NSF + NIH (USA) + CORDIS (Europe) — actifs uniquement")

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

if not os.path.exists("leads_laser.csv"):
    st.warning("⚠️ Pas de données. Clique sur Rafraîchir.")
    st.stop()

df = load_data()
st.divider()

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total", len(df))
col2.metric("NSF", len(df[df["source"] == "NSF"]))
col3.metric("NIH", len(df[df["source"] == "NIH"]))
col4.metric("CORDIS", len(df[df["source"] == "CORDIS"]))
col5.metric("Avec email", df[df["contact_email"] != ""].shape[0])
col6.metric("Score max", int(df["score"].max()) if len(df) > 0 else 0)
st.divider()

st.subheader("🎛️ Filtres")
col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
with col_f1:
    score_min = st.slider("Score minimum", 0, int(df["score"].max()) if len(df) > 0 else 15, 5)
with col_f2:
    budget_range = st.slider("Budget ($)", 0, 15_000_000, (0, 15_000_000), 100_000, format="$%d")
with col_f3:
    sources = st.multiselect("Source", ["NSF", "NIH", "CORDIS"], default=["NSF", "NIH", "CORDIS"])
with col_f4:
    email_only = st.checkbox("Email uniquement", value=False)
with col_f5:
    budget_only = st.checkbox("Budget uniquement", value=False)

filtered = df[df["score"] >= score_min]
filtered = filtered[filtered["source"].isin(sources)]
if email_only:
    filtered = filtered[filtered["contact_email"] != ""]
if budget_only:
    filtered = filtered[pd.to_numeric(filtered["budget_usd"], errors="coerce").notna()]
budget_numeric = pd.to_numeric(filtered["budget_usd"], errors="coerce")
filtered = filtered[budget_numeric.isna() | ((budget_numeric >= budget_range[0]) & (budget_numeric <= budget_range[1]))]

# ─── TRI ──────────────────────────────────────────────────────────────────────
st.subheader("🔃 Tri")
col_s1, col_s2 = st.columns(2)
with col_s1:
    sort_by = st.selectbox(
        "Trier par",
        ["Score", "Budget", "Date de fin"],
        index=0
    )
with col_s2:
    sort_order = st.selectbox(
        "Ordre",
        ["Décroissant ↓", "Croissant ↑"],
        index=0
    )

ascending = sort_order == "Croissant ↑"
filtered = filtered.copy()

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

st.subheader("📋 Prospects qualifiés")
display_cols = ["source", "title", "organization", "country", "budget_usd", "contact_name", "contact_email", "score", "keywords_matched", "end_date", "link"]
st.dataframe(
    filtered[display_cols],
    use_container_width=True, height=400,
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

st.subheader("🔍 Détail d'un prospect")
if len(filtered) > 0:
    options = {i: f"#{i} — {row['title'][:60]}..." for i, row in filtered.iterrows()}
    selected_idx = st.selectbox("Sélectionne un prospect", list(options.keys()), format_func=lambda x: options[x])
    row = filtered.loc[selected_idx]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**# Prospect :** {selected_idx}")
        st.markdown(f"**Titre :** {row['title']}")
        st.markdown(f"**Source :** {row['source']}")
        st.markdown(f"**Organisation :** {row['organization']}")
        st.markdown(f"**Pays :** {row['country']}")
        budget = row["budget_usd"]
        st.markdown(f"**Budget :** {'Non disponible' if pd.isna(budget) or budget == '' else f'${int(float(budget)):,}'}")
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

st.subheader("🤖 Assistant commercial")
st.caption("Exemples : 'Top 5 prospects' | 'Prospects femtoseconde' | 'Résumé' | 'aide'")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

question = st.chat_input("Pose ta question...")
if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        response = chatbot_local(question, df)
        st.markdown(response)
    st.session_state.chat_history.append({"role": "assistant", "content": response})
st.divider()

st.subheader("⬇️ Export")
csv = filtered.to_csv(index=False, sep=";").encode("utf-8-sig")
st.download_button("📥 Télécharger les prospects (CSV)", data=csv, file_name="prospects_export.csv", mime="text/csv")