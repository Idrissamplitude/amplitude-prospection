import streamlit as st
import pandas as pd
import requests
import time
import os
import io
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import re

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
        st.markdown("### Login")
        with st.form("login_form"):
            pwd = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
            if submitted:
                if pwd == app_password:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")

    return False

if not check_password():
    st.stop()

DATE_CUTOFF = datetime.today() - timedelta(days=365 * 2)

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

EXCLUSION_KEYWORDS_DEFAULT = [
    "printer", "imprimante", "3d printing", "inkjet", "dental", "dentaire",
    "tattoo", "tatouage", "hair removal", "épilation",
]


def compute_score(title: str, description: str, kw_dict: dict = None) -> tuple:
    """Titre vaut 2× la description. Description complète utilisée (non tronquée)."""
    if kw_dict is None:
        kw_dict = KEYWORDS_WEIGHTS
    title_lower = title.lower()
    desc_lower = description.lower()
    score = 0
    matched = []

    for kw, weight in kw_dict.items():
        kw_score = 0
        if kw in title_lower:
            kw_score += weight * 2
        if kw in desc_lower:
            kw_score += weight
        if kw_score > 0:
            score += kw_score
            matched.append(kw)

    return score, matched


def recompute_scores(df: pd.DataFrame, kw_dict: dict) -> pd.DataFrame:
    df = df.copy()
    scores, matched_list = [], []
    for _, row in df.iterrows():
        s, m = compute_score(str(row["title"]), str(row["description"]), kw_dict)
        scores.append(s)
        matched_list.append(str(m))
    df["score"] = scores
    df["keywords_matched"] = matched_list
    df = df[df["score"] >= SCORE_MIN_FILTER]
    return df.sort_values("score", ascending=False).reset_index(drop=True)

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
            st.warning(f"NSF - Error: {e}")
            break

    rows = []

    for award in all_awards:
        exp_date = award.get("expDate", "") or ""

        if exp_date:
            try:
                if datetime.strptime(exp_date, "%m/%d/%Y") < DATE_CUTOFF:
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
                "award_amount",
                "direct_cost_amt",
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
            st.warning(f"NIH - Error: {e}")
            break

    rows = []

    for project in all_projects:
        try:
            end_date_str = (project.get("project_end_date", "") or "")[:10]
            if end_date_str:
                try:
                    if datetime.strptime(end_date_str, "%Y-%m-%d") < DATE_CUTOFF:
                        continue
                except Exception:
                    pass

            title = project.get("project_title", "") or ""
            description = project.get("abstract_text", "") or ""
            score, matched = compute_score(title, description)

            pis = project.get("principal_investigators", [])
            contact_name = ""

            if pis and isinstance(pis, list) and isinstance(pis[0], dict):
                contact_name = f"{pis[0].get('first_name', '') or ''} {pis[0].get('last_name', '') or ''}".strip()

            budget = project.get("total_cost") or project.get("award_amount") or project.get("direct_cost_amt")
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

# ─── DÉTAIL PROJET CORDIS ─────────────────────────────────────────────────────
def fetch_cordis_detail(ref: str) -> tuple:
    """Retourne (budget_eur, description_complète) depuis la page projet CORDIS."""
    try:
        r = requests.get(f"https://cordis.europa.eu/project/id/{ref}", timeout=15)
        body = r.text

        budget_eur = None
        m = re.search(r'Total cost[\s\S]{0,600}?€\s*([\d\s,\.]+)', body)
        if m:
            raw = m.group(1).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
            try:
                budget_eur = float(raw)
            except ValueError:
                pass

        description = ""
        idx = body.find('id="c-objective"')
        if idx > 0:
            section = body[idx:idx + 8000]
            # Cas 1 : texte directement dans <p class="c-article__text">
            om = re.search(r'<p class="c-article__text">([\s\S]*?)</p>', section)
            if om:
                description = re.sub(r'<[^>]+>', '', om.group(1))
            else:
                # Cas 2 : texte derrière un toggler JS — chercher tout <p> de plus de 80 chars
                texts = re.findall(r'<p[^>]*>([\s\S]{80,}?)</p>', section)
                for t in texts:
                    clean = re.sub(r'<[^>]+>', '', t).strip()
                    if len(clean) > 80:
                        description = clean
                        break
            if description:
                description = description.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
                description = ' '.join(description.split())

        return budget_eur, description
    except Exception:
        return None, ""

# ─── COLLECTE CORDIS ──────────────────────────────────────────────────────────
def collect_cordis():
    all_projects = []

    for page in range(1, 21):
        try:
            r = requests.get(
                f"https://cordis.europa.eu/api/search/results?q=contenttype%3Dproject+AND+laser&p={page}&num=10&format=json&archived=false",
                timeout=10
            )
            results = r.json().get("payload", {}).get("results", [])

            if not results:
                break

            all_projects.extend(results)
            time.sleep(0.3)

        except Exception:
            break

    def _parse_cordis_date(date_str: str):
        m = re.match(r'(\d{1,2})\s+\{\{month_(\d{2})\}\}\s+(\d{4})', (date_str or "").strip())
        if m:
            try:
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except Exception:
                pass
        return None

    # Pré-filtrage : score rapide sur le teaser + filtre date avant d'appeler fetch_cordis_detail
    candidates = []
    for project in all_projects:
        title = project.get("title", "") or ""
        teaser = project.get("teaser", "") or ""
        ref = project.get("reference", "") or ""
        if not ref:
            continue

        end_dt = _parse_cordis_date(project.get("endDate", ""))
        if end_dt and end_dt < DATE_CUTOFF:
            continue
        teaser_score, _ = compute_score(title, teaser)
        if teaser_score >= SCORE_MIN_FILTER:
            candidates.append(project)

    # Fetch détails en parallèle (5 workers)
    refs = [p.get("reference", "") for p in candidates]
    details = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ref = {executor.submit(fetch_cordis_detail, ref): ref for ref in refs}
        for future in as_completed(future_to_ref):
            ref = future_to_ref[future]
            try:
                details[ref] = future.result()
            except Exception:
                details[ref] = (None, "")

    rows = []

    for project in candidates:
        title = project.get("title", "") or ""
        teaser = project.get("teaser", "") or ""
        ref = project.get("reference", "") or ""

        budget_eur, full_desc = details.get(ref, (None, ""))
        description = full_desc if full_desc else teaser
        score, matched = compute_score(title, description)

        rows.append({
            "source": "CORDIS",
            "title": title,
            "organization": project.get("acronym", ""),
            "country": project.get("coordinatedIn", "Europe (UE)"),
            "budget_usd": None,
            "budget_eur": budget_eur,
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

    df["budget_eur"] = pd.to_numeric(df["budget_eur"], errors="coerce")
    return df[df["score"] >= SCORE_MIN_FILTER]

# ─── COLLECTE TED ─────────────────────────────────────────────────────────────
TED_COUNTRY_MAP = {
    "AUT": "Autriche", "BEL": "Belgique", "BGR": "Bulgarie", "HRV": "Croatie",
    "CYP": "Chypre", "CZE": "Tchéquie", "DNK": "Danemark", "EST": "Estonie",
    "FIN": "Finlande", "FRA": "France", "DEU": "Allemagne", "GRC": "Grèce",
    "HUN": "Hongrie", "IRL": "Irlande", "ITA": "Italie", "LVA": "Lettonie",
    "LTU": "Lituanie", "LUX": "Luxembourg", "MLT": "Malte", "NLD": "Pays-Bas",
    "POL": "Pologne", "PRT": "Portugal", "ROU": "Roumanie", "SVK": "Slovaquie",
    "SVN": "Slovénie", "ESP": "Espagne", "SWE": "Suède", "GBR": "Royaume-Uni",
    "CHE": "Suisse", "NOR": "Norvège", "ISR": "Israël", "TUR": "Turquie",
}

TED_QUERY = (
    'notice-title ~ "laser" OR notice-title ~ "photonics" OR '
    'notice-title ~ "femtosecond" OR notice-title ~ "ultrafast" OR '
    'notice-title ~ "ablation" OR notice-title ~ "ultrashort" OR '
    'notice-title ~ "biophotonics" OR notice-title ~ "fiber laser" OR '
    'notice-title ~ "lidar" OR notice-title ~ "optics"'
)

TED_FIELDS = [
    "notice-title", "description-proc",
    "organisation-name-buyer", "organisation-country-buyer",
    "total-value", "estimated-value-proc",
    "publication-date", "publication-number",
    "deadline-receipt-tender-date-lot",
    "notice-type",
]

TED_NOTICE_STATUS = {
    "cn-standard":      "Ouvert",
    "cn-social":        "Ouvert",
    "cn-defence":       "Ouvert",
    "pin-cfc-standard": "À venir",
    "pin-rtl":          "À venir",
    "can-standard":     "Attribué",
    "can-social":       "Attribué",
    "can-defence":      "Attribué",
    "qu-sy":            "Qualification",
}

def collect_ted():
    all_notices = []
    date_from = DATE_CUTOFF.strftime("%Y%m%d")
    query = (
        f'(notice-title ~ "laser" OR notice-title ~ "photonics" OR '
        f'notice-title ~ "femtosecond" OR notice-title ~ "ultrafast" OR '
        f'notice-title ~ "ablation" OR notice-title ~ "ultrashort" OR '
        f'notice-title ~ "biophotonics" OR notice-title ~ "fiber laser" OR '
        f'notice-title ~ "lidar" OR notice-title ~ "optics") '
        f'AND publication-date >= {date_from}'
    )

    for page in range(1, 6):
        payload = {
            "query": query,
            "fields": TED_FIELDS,
            "page": page,
            "limit": 100,
            "scope": 1,
        }
        try:
            r = requests.post(
                "https://api.ted.europa.eu/v3/notices/search",
                json=payload,
                timeout=20
            )
            notices = r.json().get("notices", [])
            if not notices:
                break
            all_notices.extend(notices)
            time.sleep(0.3)
        except Exception as e:
            st.warning(f"TED - Error: {e}")
            break

    rows = []

    for notice in all_notices:
        title_obj = notice.get("notice-title") or {}
        title = title_obj.get("eng", "") or next(iter(title_obj.values()), "") if title_obj else ""

        desc_obj = notice.get("description-proc") or {}
        description = desc_obj.get("eng", "") or next(iter(desc_obj.values()), "") if desc_obj else ""

        org_obj = notice.get("organisation-name-buyer") or {}
        org = ""
        if org_obj:
            first_val = next(iter(org_obj.values()), [])
            org = first_val[0] if isinstance(first_val, list) and first_val else str(first_val)

        country_raw = notice.get("organisation-country-buyer") or ""
        if isinstance(country_raw, list):
            country_raw = country_raw[0] if country_raw else ""
        country = TED_COUNTRY_MAP.get(str(country_raw), str(country_raw))

        budget_raw = notice.get("total-value") or notice.get("estimated-value-proc")
        if isinstance(budget_raw, list):
            budget_raw = budget_raw[0] if budget_raw else None
        if isinstance(budget_raw, dict):
            budget = budget_raw.get("amount")
        else:
            budget = budget_raw

        pub_number = notice.get("publication-number", "") or ""
        link = (notice.get("links") or {}).get("html", {}).get("ENG", "")
        if not link and pub_number:
            link = f"https://ted.europa.eu/en/notice/-/detail/{pub_number}"

        # deadline peut arriver comme liste ['2024-02-09T23:59:59+01:00']
        deadline_raw = notice.get("deadline-receipt-tender-date-lot") or ""
        if isinstance(deadline_raw, list):
            deadline_raw = deadline_raw[0] if deadline_raw else ""
        deadline = str(deadline_raw)[:10]
        if not deadline:
            deadline = (notice.get("publication-date", "") or "")[:10]

        notice_type = notice.get("notice-type", "") or ""
        notice_status = TED_NOTICE_STATUS.get(notice_type, "Inconnu")

        score, matched = compute_score(title, description)

        rows.append({
            "source": "TED",
            "title": title,
            "organization": org,
            "country": country,
            "budget_usd": None,
            "budget_eur": budget,
            "contact_name": "",
            "contact_email": "",
            "score": score,
            "keywords_matched": str(matched),
            "description": description,
            "end_date": deadline,
            "link": link,
            "notice_status": notice_status,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["budget_eur"] = pd.to_numeric(df["budget_eur"], errors="coerce")
    return df[df["score"] >= SCORE_MIN_FILTER]

# ─── NSERC ────────────────────────────────────────────────────────────────────
NSERC_YEARS = [2023, 2024, 2025, 2026]

def collect_nserc() -> pd.DataFrame:
    """Télécharge les CSV annuels NSERC et filtre par mots-clés laser."""
    kw_pattern = "|".join(["laser", "photonic", "femtosecond", "ultrafast", "ablation", "optic", "ultrashort"])
    all_frames = []

    for year in NSERC_YEARS:
        url = f"https://www.nserc-crsng.gc.ca/opendata/NSERC_FY{year}_Expenditures.csv"
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                continue
            try:
                df_year = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig", low_memory=False)
            except UnicodeDecodeError:
                df_year = pd.read_csv(io.BytesIO(r.content), encoding="cp1252", low_memory=False)
            df_year["_year"] = year
            all_frames.append(df_year)
            time.sleep(0.3)
        except Exception:
            continue

    if not all_frames:
        return pd.DataFrame()

    df_all = pd.concat(all_frames, ignore_index=True)

    title_col = next((c for c in df_all.columns if "ApplicationTitle" in c), None)
    summary_col = next((c for c in df_all.columns if "ApplicationSummary" in c), None)

    if title_col is None:
        return pd.DataFrame()

    mask_title = df_all[title_col].str.lower().str.contains(kw_pattern, na=False)
    if summary_col:
        mask_summary = df_all[summary_col].str.lower().str.contains(kw_pattern, na=False)
        df_filtered = df_all[mask_title | mask_summary].copy()
    else:
        df_filtered = df_all[mask_title].copy()

    rows = []
    for _, row in df_filtered.iterrows():
        title = str(row.get(title_col, ""))
        description = str(row.get(summary_col, "")) if summary_col else ""
        score, matched = compute_score(title, description)
        if score < SCORE_MIN_FILTER:
            continue

        fiscal_year = str(row.get("FiscalYear-Exercice financier", row.get("_year", "")))
        end_year_str = fiscal_year.split("-")[-1].strip()
        try:
            end_date = datetime(int(end_year_str), 3, 31).strftime("%Y-%m-%d")
        except Exception:
            end_date = ""

        country = str(row.get("CountryEN", "Canada"))
        if not country or country in ("nan", ""):
            country = "Canada"

        budget_raw = row.get("AwardAmount")
        try:
            budget = float(budget_raw) if pd.notna(budget_raw) else None
            if budget == 0:
                budget = None
        except Exception:
            budget = None

        app_id = str(row.get("ApplicationID", "")).strip()
        search_term = app_id if app_id and app_id != "nan" else title[:80]
        link = f"https://nserc-crsng.canada.ca/en/awards-database?keywords={quote_plus(search_term)}"

        rows.append({
            "source": "NSERC",
            "title": title,
            "organization": str(row.get("Institution-Établissement", row.get("Institution", ""))),
            "country": country,
            "budget_usd": None,
            "budget_eur": None,
            "budget_cad": budget,
            "contact_name": str(row.get("Name-Nom", row.get("Name", ""))),
            "contact_email": "",
            "score": score,
            "keywords_matched": str(matched),
            "description": description,
            "end_date": end_date,
            "link": link,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["budget_cad"] = pd.to_numeric(df["budget_cad"], errors="coerce")
    return df.sort_values("score", ascending=False).reset_index(drop=True)

# ─── COLLECTE UKRI ────────────────────────────────────────────────────────────
def fetch_ukri_budget(proj_id: str) -> float | None:
    """Récupère le budget GBP depuis l'endpoint /funds d'un projet UKRI."""
    try:
        r = requests.get(
            f"https://gtr.ukri.org/gtr/api/projects/{proj_id}/funds",
            headers={"Accept": "application/json"},
            timeout=10,
            verify=False,
        )
        if r.status_code != 200:
            return None
        funds = r.json().get("fund", [])
        if funds and isinstance(funds, list):
            vp = funds[0].get("valuePounds") or {}
            amount = vp.get("amount")
            return float(amount) if amount else None
    except Exception:
        return None
    return None


def collect_ukri() -> pd.DataFrame:
    """Collecte les projets UKRI (UK Research and Innovation) via leur API publique."""
    search_terms = ["laser", "photonics", "femtosecond", "ultrafast", "ablation", "biophotonics", "multiphoton"]
    seen_ids: set = set()
    candidates = []

    for term in search_terms:
        page = 1
        while page <= 5:
            try:
                r = requests.get(
                    "https://gtr.ukri.org/gtr/api/projects",
                    params={"q": term, "p": page, "s": 10},
                    headers={"Accept": "application/json"},
                    timeout=15,
                    verify=False,
                )
                if r.status_code != 200:
                    break

                data = r.json()
                projects = data.get("project", [])
                total_pages = data.get("totalPages", 1)

                if not projects:
                    break

                for project in projects:
                    proj_id = project.get("id", "")
                    if proj_id in seen_ids:
                        continue
                    seen_ids.add(proj_id)

                    end_raw = (project.get("end", "") or "")
                    end_str = end_raw[:10] if end_raw else ""
                    status = (project.get("status", "") or "")
                    if end_str:
                        try:
                            if datetime.strptime(end_str, "%Y-%m-%d") < DATE_CUTOFF:
                                continue
                        except Exception:
                            pass
                    elif status == "Closed":
                        continue

                    title = project.get("title", "") or ""
                    description = project.get("abstractText", "") or ""
                    score, matched = compute_score(title, description)
                    if score < SCORE_MIN_FILTER:
                        continue

                    identifiers = (project.get("identifiers") or {}).get("identifier", [])
                    ref_num = ""
                    if isinstance(identifiers, list) and identifiers:
                        ref_num = identifiers[0].get("value", "") if isinstance(identifiers[0], dict) else ""

                    candidates.append({
                        "proj_id": proj_id,
                        "title": title,
                        "org": project.get("leadOrganisationDepartment", "") or "",
                        "description": description,
                        "score": score,
                        "matched": matched,
                        "end_str": end_str,
                        "ref_num": ref_num,
                    })

                if page >= total_pages:
                    break
                page += 1
                time.sleep(0.3)

            except Exception as e:
                st.warning(f"UKRI '{term}' p{page} — Error: {e}")
                break

    if not candidates:
        return pd.DataFrame()

    # Fetch budgets en parallèle via /funds
    budgets = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_id = {executor.submit(fetch_ukri_budget, c["proj_id"]): c["proj_id"] for c in candidates}
        for future in as_completed(future_to_id):
            proj_id = future_to_id[future]
            try:
                budgets[proj_id] = future.result()
            except Exception:
                budgets[proj_id] = None

    rows = []
    for c in candidates:
        budget_gbp = budgets.get(c["proj_id"])
        ref_num = c["ref_num"]
        link = f"https://gtr.ukri.org/projects?ref={quote_plus(ref_num)}" if ref_num else ""
        rows.append({
            "source": "UKRI",
            "title": c["title"],
            "organization": c["org"],
            "country": "UK",
            "budget_usd": None,
            "budget_eur": round(budget_gbp * 1.18, 2) if budget_gbp else None,
            "budget_gbp": budget_gbp,
            "contact_name": "",
            "contact_email": "",
            "score": c["score"],
            "keywords_matched": str(c["matched"]),
            "description": c["description"],
            "end_date": c["end_str"],
            "link": link,
        })

    df = pd.DataFrame(rows)
    df["budget_gbp"] = pd.to_numeric(df["budget_gbp"], errors="coerce")
    return (
        df.drop_duplicates(subset=["title"], keep="first")
        .sort_values("score", ascending=False)
        .reset_index(drop=True)
    )


def refresh_europe_only():
    st.info("🇪🇺 Collecting CORDIS...")
    df_cordis_new = collect_cordis()
    st.info("🇬🇧 Collecting UKRI...")
    df_ukri_new = collect_ukri()

    if os.path.exists("leads_laser.csv"):
        df_existing = pd.read_csv("leads_laser.csv")
        df_existing = df_existing[~df_existing["source"].isin(["CORDIS", "UKRI"])]
    else:
        df_existing = pd.DataFrame()

    df_total = pd.concat([df_existing, df_cordis_new, df_ukri_new], ignore_index=True)
    if not df_total.empty:
        df_total = df_total.sort_values("score", ascending=False)
        df_total = df_total.drop_duplicates(subset=["title"], keep="first")
        df_total = df_total.reset_index(drop=True)
    df_total.to_csv("leads_laser.csv", index=False)
    return df_total


# ─── COLLECTE CIHR ────────────────────────────────────────────────────────────
CIHR_KW_PATTERN = "|".join([
    "laser", "photonic", "femtosecond", "ultrafast", "ablation",
    "optic", "ultrashort", "biophotonic", "multiphoton", "lidar"
])

def collect_cihr() -> pd.DataFrame:
    """
    Collecte les projets CIHR via l'API CKAN de open.canada.ca.
    Télécharge les fichiers CSV/Excel des datasets CIHR et filtre par mots-clés laser.
    """
    rows = []
    debug = []

    try:
        r = requests.get(
            "https://open.canada.ca/data/en/api/3/action/package_search",
            params={"fq": "organization:cihr-irsc", "rows": 30},
            timeout=15
        )
        debug.append(f"CKAN search → HTTP {r.status_code}")
        if r.status_code != 200:
            st.session_state["_cihr_debug"] = debug
            return pd.DataFrame()

        datasets = r.json().get("result", {}).get("results", [])
        debug.append(f"{len(datasets)} datasets CIHR trouvés sur open.canada.ca")

        for ds in datasets:
            for res in ds.get("resources", []):
                fmt = (res.get("format") or "").upper()
                if fmt not in ("CSV", "XLS", "XLSX"):
                    continue
                url = res.get("url", "")
                if not url:
                    continue
                if url.startswith("/"):
                    url = f"https://open.canada.ca{url}"
                # Ignorer les fichiers antérieurs à 2022
                if re.search(r'_(20[01]\d|2021)', url):
                    continue
                debug.append(f"  ↳ {ds.get('title','')[:50]} — {fmt}")
                try:
                    r2 = requests.get(url, timeout=30)
                    debug.append(f"    HTTP {r2.status_code}, {len(r2.content):,} bytes")
                    if r2.status_code != 200:
                        continue

                    if fmt in ("XLS", "XLSX"):
                        df_raw = pd.read_excel(io.BytesIO(r2.content))
                    else:
                        try:
                            df_raw = pd.read_csv(io.BytesIO(r2.content), encoding="utf-8-sig", low_memory=False)
                        except Exception:
                            df_raw = pd.read_csv(io.BytesIO(r2.content), encoding="cp1252", low_memory=False)

                    def _col(df, *kws):
                        for kw in kws:
                            for c in df.columns:
                                if kw.lower() in c.lower():
                                    return c
                        return None

                    # Noms exacts du fichier CIHR (avec fallback générique)
                    title_col  = _col(df_raw, "ApplicationTitle", "title", "titre", "project_title")
                    desc_col   = _col(df_raw, "ApplicationAbstract", "abstract", "lay_abstract", "summary", "description")
                    org_col    = _col(df_raw, "InstitutionPaidNameEN", "institution", "university", "organization")
                    budget_col = _col(df_raw, "TotalAmountAwarded", "TotalAmountPaid", "amount", "awarded", "funding")
                    end_col    = _col(df_raw, "FundingEndDate", "end_date", "end_year", "completion")
                    id_col     = _col(df_raw, "FundingReferenceNumber", "FundingCode", "application_id", "reference_number")
                    fname_col  = _col(df_raw, "FirstName_Prenom", "FirstName", "Prenom")
                    lname_col  = _col(df_raw, "FamilyName_NomFamille", "FamilyName", "NomFamille")

                    debug.append(f"    Mapping → titre:{title_col} | org:{org_col} | budget:{budget_col} | id:{id_col}")

                    if title_col is None:
                        continue

                    mask = df_raw[title_col].str.lower().str.contains(CIHR_KW_PATTERN, na=False)
                    if desc_col:
                        mask |= df_raw[desc_col].str.lower().str.contains(CIHR_KW_PATTERN, na=False)
                    df_filt = df_raw[mask].copy()
                    debug.append(f"    → {len(df_filt)} projets après filtre mots-clés")

                    for _, row in df_filt.iterrows():
                        title = str(row.get(title_col, "") or "")
                        description = str(row.get(desc_col, "") or "") if desc_col else ""
                        score, matched = compute_score(title, description)
                        if score < SCORE_MIN_FILTER:
                            continue

                        # Filtre date de fin
                        end_str_cihr = str(row.get(end_col, "") or "")[:10] if end_col else ""
                        if end_str_cihr:
                            try:
                                if datetime.strptime(end_str_cihr, "%Y-%m-%d") < DATE_CUTOFF:
                                    continue
                            except Exception:
                                pass

                        link = ""

                        fname = str(row.get(fname_col, "") or "").strip() if fname_col else ""
                        lname = str(row.get(lname_col, "") or "").strip() if lname_col else ""
                        contact = f"{fname} {lname}".strip()

                        rows.append({
                            "source": "CIHR",
                            "title": title,
                            "organization": str(row.get(org_col, "") or "") if org_col else "",
                            "country": "Canada",
                            "budget_usd": None,
                            "budget_eur": None,
                            "budget_cad": pd.to_numeric(row.get(budget_col), errors="coerce") if budget_col else None,
                            "contact_name": contact,
                            "contact_email": "",
                            "score": score,
                            "keywords_matched": str(matched),
                            "description": description,
                            "end_date": str(row.get(end_col, "") or "")[:10] if end_col else "",
                            "link": link,
                        })

                    time.sleep(0.3)

                except Exception as e:
                    debug.append(f"    Erreur: {e}")
                    continue

    except Exception as e:
        debug.append(f"Erreur CKAN: {e}")

    st.session_state["_cihr_debug"] = debug

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["budget_cad"] = pd.to_numeric(df["budget_cad"], errors="coerce")
    return (
        df.drop_duplicates(subset=["title"], keep="first")
        .sort_values("score", ascending=False)
        .reset_index(drop=True)
    )


def refresh_cihr_only():
    st.info("🏥 Collecting CIHR (Canada)...")
    df_cihr_new = collect_cihr()

    if os.path.exists("leads_laser.csv"):
        df_existing = pd.read_csv("leads_laser.csv")
        df_existing = df_existing[df_existing["source"] != "CIHR"]
    else:
        df_existing = pd.DataFrame()

    df_total = pd.concat([df_existing, df_cihr_new], ignore_index=True)
    if not df_total.empty:
        df_total = df_total.sort_values("score", ascending=False)
        df_total = df_total.drop_duplicates(subset=["title"], keep="first")
        df_total = df_total.reset_index(drop=True)
    df_total.to_csv("leads_laser.csv", index=False)
    return df_total


# ─── PIPELINE GLOBAL ──────────────────────────────────────────────────────────
def run_pipeline():
    st.info("📡 Collecting NSF...")
    df_nsf = collect_nsf()

    st.info("🔬 Collecting NIH...")
    df_nih = collect_nih()

    st.info("🇪🇺 Collecting CORDIS...")
    df_cordis = collect_cordis()

    st.info("📋 Collecting TED (EU tenders)...")
    df_ted = collect_ted()

    st.info("🍁 Collecting NSERC (Canada)...")
    df_nserc = collect_nserc()

    st.info("🏥 Collecting CIHR (Canada)...")
    df_cihr = collect_cihr()

    st.info("🇬🇧 Collecting UKRI (UK)...")
    df_ukri = collect_ukri()

    df_total = pd.concat([df_nsf, df_nih, df_cordis, df_ted, df_nserc, df_cihr, df_ukri], ignore_index=True)

    if not df_total.empty:
        df_total = df_total.sort_values("score", ascending=False)
        df_total = df_total.drop_duplicates(subset=["title"], keep="first")
        df_total = df_total.reset_index(drop=True)

    df_total.to_csv("leads_laser.csv", index=False)
    return df_total


def refresh_ted_only():
    st.info("📋 Collecting TED (EU tenders)...")
    df_ted_new = collect_ted()

    if os.path.exists("leads_laser.csv"):
        df_existing = pd.read_csv("leads_laser.csv")
        df_existing = df_existing[df_existing["source"] != "TED"]
    else:
        df_existing = pd.DataFrame()

    df_total = pd.concat([df_existing, df_ted_new], ignore_index=True)

    if not df_total.empty:
        df_total = df_total.sort_values("score", ascending=False)
        df_total = df_total.drop_duplicates(subset=["title"], keep="first")
        df_total = df_total.reset_index(drop=True)

    df_total.to_csv("leads_laser.csv", index=False)
    return df_total


def refresh_usa_only():
    st.info("📡 Collecting NSF...")
    df_nsf_new = collect_nsf()
    st.info("🔬 Collecting NIH...")
    df_nih_new = collect_nih()

    if os.path.exists("leads_laser.csv"):
        df_existing = pd.read_csv("leads_laser.csv")
        df_existing = df_existing[~df_existing["source"].isin(["NSF", "NIH"])]
    else:
        df_existing = pd.DataFrame()

    df_total = pd.concat([df_existing, df_nsf_new, df_nih_new], ignore_index=True)

    if not df_total.empty:
        df_total = df_total.sort_values("score", ascending=False)
        df_total = df_total.drop_duplicates(subset=["title"], keep="first")
        df_total = df_total.reset_index(drop=True)

    df_total.to_csv("leads_laser.csv", index=False)
    return df_total


def refresh_nserc_only():
    st.info("🍁 Collecting NSERC (Canada)...")
    df_nserc_new = collect_nserc()

    if os.path.exists("leads_laser.csv"):
        df_existing = pd.read_csv("leads_laser.csv")
        df_existing = df_existing[df_existing["source"] != "NSERC"]
    else:
        df_existing = pd.DataFrame()

    df_total = pd.concat([df_existing, df_nserc_new], ignore_index=True)

    if not df_total.empty:
        df_total = df_total.sort_values("score", ascending=False)
        df_total = df_total.drop_duplicates(subset=["title"], keep="first")
        df_total = df_total.reset_index(drop=True)

    df_total.to_csv("leads_laser.csv", index=False)
    return df_total

# ─── STATUTS PROSPECTS ───────────────────────────────────────────────────────
STATUS_FILE = "prospect_status.csv"
STATUTS = ["—", "To contact", "Contacted", "Not interested"]



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

    if "notice_status" not in df.columns:
        df["notice_status"] = ""
    df["notice_status"] = df["notice_status"].fillna("").astype(str)

    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    df["budget_usd"] = pd.to_numeric(df["budget_usd"], errors="coerce")
    if "budget_eur" not in df.columns:
        df["budget_eur"] = float("nan")
    else:
        df["budget_eur"] = pd.to_numeric(df["budget_eur"], errors="coerce")
    if "budget_cad" not in df.columns:
        df["budget_cad"] = float("nan")
    else:
        df["budget_cad"] = pd.to_numeric(df["budget_cad"], errors="coerce")
    if "budget_gbp" not in df.columns:
        df["budget_gbp"] = float("nan")
    else:
        df["budget_gbp"] = pd.to_numeric(df["budget_gbp"], errors="coerce")

    return df

# ─── COMPOSANT INTERFACE ──────────────────────────────────────────────────────
def render_prospect_interface(df_base: pd.DataFrame, interface_name: str, chat_key: str, export_name: str, show_budget_email: bool = True, budget_col: str = "budget_usd", budget_symbol: str = "$", show_country_chart: bool = False, known_sources: list = None, show_notice_status: bool = False):

    with st.expander("🔑 Scoring Keywords", expanded=False):
        if "kw_df" not in st.session_state:
            st.session_state["kw_df"] = pd.DataFrame(
                [{"Keyword": k, "Weight": v} for k, v in KEYWORDS_WEIGHTS.items()]
            )

        edited_kw = st.data_editor(
            st.session_state["kw_df"],
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Keyword": st.column_config.TextColumn("Keyword"),
                "Weight": st.column_config.NumberColumn("Weight", min_value=1, max_value=10, step=1),
            },
            key=f"{chat_key}_kw_editor"
        )

        col_apply, col_reset, col_info = st.columns([1, 1, 4])
        with col_apply:
            if st.button("✅ Apply", use_container_width=True, key=f"{chat_key}_kw_apply"):
                new_kw = {
                    str(row["Keyword"]).strip(): int(row["Weight"])
                    for _, row in edited_kw.iterrows()
                    if str(row["Keyword"]).strip() and pd.notna(row["Weight"])
                }
                st.session_state["custom_keywords"] = new_kw
                st.session_state["kw_df"] = edited_kw
                st.rerun()
        with col_reset:
            if st.button("🔄 Default", use_container_width=True, key=f"{chat_key}_kw_reset"):
                for k in ("kw_df", "custom_keywords"):
                    st.session_state.pop(k, None)
                st.rerun()
        with col_info:
            active_kw = st.session_state.get("custom_keywords", KEYWORDS_WEIGHTS)
            if "custom_keywords" in st.session_state:
                st.caption(f"✏️ {len(active_kw)} custom keywords")
            else:
                st.caption(f"{len(active_kw)} default keywords")

    with st.expander("🚫 Exclusion Keywords", expanded=False):
        active_excl = st.session_state.get("exclusion_keywords", EXCLUSION_KEYWORDS_DEFAULT)
        excl_text = st.text_area(
            "One word or phrase per line — any project containing these words (title or description) will be hidden",
            value="\n".join(active_excl),
            height=130,
            key=f"{chat_key}_excl_editor"
        )
        col_excl_apply, col_excl_reset, col_excl_info = st.columns([1, 1, 4])
        with col_excl_apply:
            if st.button("✅ Apply", key=f"{chat_key}_excl_apply", use_container_width=True):
                new_excl = [w.strip().lower() for w in excl_text.splitlines() if w.strip()]
                st.session_state["exclusion_keywords"] = new_excl
                st.rerun()
        with col_excl_reset:
            if st.button("🔄 Default", key=f"{chat_key}_excl_reset", use_container_width=True):
                st.session_state.pop("exclusion_keywords", None)
                st.rerun()
        with col_excl_info:
            n_excl = len(active_excl)
            custom_excl = "exclusion_keywords" in st.session_state
            st.caption(f"{'✏️ ' if custom_excl else ''}{n_excl} excluded word(s) {'(custom)' if custom_excl else '(default)'}")

    # ─── FILTRES & TRI (expander) ─────────────────────────────────────────────
    search_query = st.text_input(
        "🔎 Free search (title, description, organisation)",
        value="",
        placeholder="e.g. photonics, Stanford, ablation...",
        key=f"{chat_key}_search"
    )

    with st.expander("🎛️ Filters & Sort", expanded=False):
        max_score = int(df_base["score"].max()) if len(df_base) > 0 else 15

        if show_budget_email:
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)

            with col_f1:
                score_min = st.slider(
                    "Minimum score",
                    0,
                    max_score,
                    5,
                    key=f"{chat_key}_score_min"
                )

            with col_f2:
                budget_range = st.slider(
                    f"Budget ({budget_symbol})",
                    0,
                    15_000_000,
                    (0, 15_000_000),
                    100_000,
                    format=f"{budget_symbol}%d",
                    key=f"{chat_key}_budget"
                )

            with col_f3:
                email_only = st.checkbox(
                    "Email only",
                    value=False,
                    key=f"{chat_key}_email"
                )

            with col_f4:
                budget_only = st.checkbox(
                    "Budget only",
                    value=False,
                    key=f"{chat_key}_budget_only"
                )
        else:
            score_min = st.slider(
                "Minimum score",
                0,
                max_score,
                5,
                key=f"{chat_key}_score_min"
            )
            email_only = False
            budget_only = False
            budget_range = (0, 15_000_000)

        col_f5, col_f6, col_s1, col_s2 = st.columns(4)

        with col_f5:
            statut_filter = st.multiselect(
                "Filter by status",
                STATUTS[1:],
                default=[],
                key=f"{chat_key}_statut_filter"
            )

        with col_f6:
            dynamic_sources = sorted(df_base["source"].dropna().unique().tolist()) if not df_base.empty else []
            available_sources = sorted(set(dynamic_sources + (known_sources or [])))
            source_filter = st.multiselect(
                "Filter by source",
                available_sources,
                default=[],
                key=f"{chat_key}_source_filter"
            )

        with col_s1:
            sort_options = ["Score", "Budget", "End Date"] if show_budget_email else ["Score", "End Date"]
            sort_by = st.selectbox(
                "Sort by",
                sort_options,
                index=0,
                key=f"{chat_key}_sort_by"
            )

        with col_s2:
            sort_order = st.selectbox(
                "Order",
                ["Descending ↓", "Ascending ↑"],
                index=0,
                key=f"{chat_key}_sort_order"
            )

    statuses = load_status()

    # Appliquer les mots-clés d'exclusion
    active_excl = st.session_state.get("exclusion_keywords", EXCLUSION_KEYWORDS_DEFAULT)
    df_filtered_base = df_base.copy()
    if active_excl:
        excl_pattern = "|".join(re.escape(w) for w in active_excl)
        mask_excl = (
            df_filtered_base["title"].str.lower().str.contains(excl_pattern, na=False) |
            df_filtered_base["description"].str.lower().str.contains(excl_pattern, na=False)
        )
        df_filtered_base = df_filtered_base[~mask_excl]

    filtered = df_filtered_base[df_filtered_base["score"] >= score_min].copy()
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

    if source_filter:
        filtered = filtered[filtered["source"].isin(source_filter)]

    if show_budget_email:
        if email_only:
            filtered = filtered[filtered["contact_email"] != ""]

        if budget_only:
            filtered = filtered[pd.to_numeric(filtered[budget_col], errors="coerce").notna()]

        budget_numeric = pd.to_numeric(filtered[budget_col], errors="coerce")
        filtered = filtered[
            budget_numeric.isna() |
            ((budget_numeric >= budget_range[0]) & (budget_numeric <= budget_range[1]))
        ]

    ascending = sort_order == "Ascending ↑"

    if sort_by == "Score":
        filtered = filtered.sort_values("score", ascending=ascending)
    elif sort_by == "Budget":
        filtered["_budget_sort"] = pd.to_numeric(filtered[budget_col], errors="coerce")
        filtered = filtered.sort_values("_budget_sort", ascending=ascending, na_position="last")
        filtered = filtered.drop(columns=["_budget_sort"])
    elif sort_by == "End Date":
        filtered["_date_sort"] = pd.to_datetime(filtered["end_date"], errors="coerce")
        filtered = filtered.sort_values("_date_sort", ascending=ascending, na_position="last")
        filtered = filtered.drop(columns=["_date_sort"])

    filtered = filtered.reset_index(drop=True)
    filtered.index = filtered.index + 1

    sources_filtered = filtered["source"].unique().tolist() if not filtered.empty else []
    source_counts_filtered = [(s, int((filtered["source"] == s).sum())) for s in sources_filtered]
    score_max_filtered = int(filtered["score"].max()) if not filtered.empty else 0

    cols = st.columns(2 + len(source_counts_filtered))
    cols[0].metric("Total", len(filtered))
    for i, (src, cnt) in enumerate(source_counts_filtered):
        cols[1 + i].metric(src, cnt)
    cols[-1].metric("Max score", score_max_filtered)

    st.divider()

    st.subheader("🏆 Top 5 Prospects")

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
                        budget = row.get(budget_col)
                        budget_str = f"{budget_symbol}{int(float(budget)):,}" if pd.notna(budget) and budget != "" else "—"
                        m1, m2 = st.columns(2)
                        m1.metric("Score", score_val)
                        m2.metric("Budget", budget_str)
                    else:
                        st.metric("Score", score_val)
                    if statut_val != "—":
                        st.caption(f"📌 {statut_val}")
    else:
        st.info("No prospects to display.")

    st.divider()

    st.subheader("📋 Qualified Prospects")

    if show_budget_email:
        display_cols = [
            "statut", "source", "title", "organization", "country", budget_col,
            "contact_name", "contact_email", "score", "keywords_matched",
            "end_date", "link"
        ]
        col_config = {
            "statut": st.column_config.TextColumn("Status"),
            "source": st.column_config.TextColumn("Source"),
            "title": st.column_config.TextColumn("Project", width="large"),
            "organization": st.column_config.TextColumn("Organisation"),
            "country": st.column_config.TextColumn("Country"),
            budget_col: st.column_config.NumberColumn(f"Budget ({budget_symbol})", format=f"{budget_symbol}%d"),
            "contact_name": st.column_config.TextColumn("Contact"),
            "contact_email": st.column_config.TextColumn("Email"),
            "score": st.column_config.NumberColumn("Score"),
            "keywords_matched": st.column_config.TextColumn("Keywords"),
            "end_date": st.column_config.TextColumn("End Date"),
            "link": st.column_config.LinkColumn("Project Link"),
        }
    else:
        display_cols = [
            "statut", "source", "title", "organization", "country",
            "contact_name", "score", "keywords_matched",
            "end_date", "link"
        ]
        col_config = {
            "statut": st.column_config.TextColumn("Status"),
            "source": st.column_config.TextColumn("Source"),
            "title": st.column_config.TextColumn("Project", width="large"),
            "organization": st.column_config.TextColumn("Organisation"),
            "country": st.column_config.TextColumn("Country"),
            "contact_name": st.column_config.TextColumn("Contact"),
            "score": st.column_config.NumberColumn("Score"),
            "keywords_matched": st.column_config.TextColumn("Keywords"),
            "end_date": st.column_config.TextColumn("End Date"),
            "link": st.column_config.LinkColumn("Project Link"),
        }

    if show_notice_status and "notice_status" in filtered.columns:
        display_cols = ["notice_status"] + display_cols
        col_config["notice_status"] = st.column_config.TextColumn("Call Type")

    st.dataframe(
        filtered[display_cols],
        width="stretch",
        height=400,
        column_config=col_config
    )

    st.divider()

    st.subheader("📊 Charts")

    if show_country_chart:
        viz_col1, viz_col2, viz_col3 = st.columns(3)
    else:
        viz_col1, viz_col2 = st.columns(2)
        viz_col3 = None

    with viz_col1:
        st.markdown("**Score Distribution**")
        if not filtered.empty:
            score_dist = (
                filtered["score"]
                .value_counts()
                .sort_index()
                .rename_axis("Score")
                .rename("Prospects")
            )
            st.bar_chart(score_dist, width="stretch")
        else:
            st.info("No data to display.")

    with viz_col2:
        if show_budget_email:
            st.markdown(f"**Top 10 Prospects by Budget ({budget_symbol})**")
            df_budget = filtered.copy()
            df_budget[budget_col] = pd.to_numeric(df_budget[budget_col], errors="coerce")
            top10 = (
                df_budget.dropna(subset=[budget_col])
                .nlargest(10, budget_col)[["title", budget_col]]
            )
            if not top10.empty:
                top10 = top10.copy()
                top10["label"] = top10["title"].str[:35] + "…"
                st.bar_chart(top10.set_index("label")[budget_col], width="stretch")
            else:
                st.info("No prospect with available budget.")
        else:
            st.markdown("**Distribution by Country**")
            if not filtered.empty:
                country_dist = (
                    filtered["country"]
                    .value_counts()
                    .rename_axis("Country")
                    .rename("Prospects")
                )
                st.bar_chart(country_dist, width="stretch")
            else:
                st.info("No data to display.")

    if show_country_chart and viz_col3 is not None:
        with viz_col3:
            st.markdown("**Distribution by Country**")
            if not filtered.empty:
                country_dist = (
                    filtered["country"]
                    .value_counts()
                    .rename_axis("Country")
                    .rename("Prospects")
                )
                st.bar_chart(country_dist, width="stretch")
            else:
                st.info("No data to display.")

    st.divider()

    st.subheader("🔍 Prospect Detail")

    if len(filtered) > 0:
        options = {i: f"#{i} — {row['title'][:60]}{'...' if len(row['title']) > 60 else ''}" for i, row in filtered.iterrows()}

        selected_idx = st.selectbox(
            "Select a prospect",
            list(options.keys()),
            format_func=lambda x: options[x],
            key=f"{chat_key}_selected_prospect"
        )

        row = filtered.loc[selected_idx]

        c1, c2 = st.columns(2)

        with c1:
            st.markdown(f"**# Prospect:** {selected_idx}")
            st.markdown(f"**Title:** {row['title']}")
            st.markdown(f"**Source:** {row['source']}")
            st.markdown(f"**Organisation:** {row['organization']}")
            st.markdown(f"**Country:** {row['country']}")

            if show_budget_email:
                budget = row[budget_col]
                st.markdown(
                    f"**Budget:** {'N/A' if pd.isna(budget) or budget == '' else f'{budget_symbol}{int(float(budget)):,}'}"
                )

            st.markdown(f"**End Date:** {row['end_date'] or 'N/A'}")
            st.markdown(f"**Score:** {int(row['score'])}")
            st.markdown(f"**Keywords:** {row['keywords_matched']}")

        with c2:
            st.markdown(f"**Contact:** {row['contact_name'] or 'N/A'}")
            if show_budget_email:
                st.markdown(f"**Email:** {row['contact_email'] or 'N/A'}")

            if row["link"]:
                st.markdown(f"**Project link:** [View project]({row['link']})")

        st.markdown("**Project Summary:**")
        st.info(row["description"])

        st.divider()
        st.markdown("**Commercial Status**")

        prospect_key = row["link"] or row["title"]
        current = statuses.get(prospect_key, {})
        current_status = current.get("status", "—")
        current_note = current.get("note", "")

        s_col1, s_col2 = st.columns([1, 2])

        with s_col1:
            new_status = st.selectbox(
                "Status",
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

        if st.button("Save status", key=f"{chat_key}_save_{selected_idx}"):
            save_status(prospect_key, row["title"], new_status, new_note)
            st.success("Status saved.")
            st.rerun()

    else:
        st.warning("No prospect matches the current filters.")

    st.divider()

    st.subheader("⬇️ Export")

    csv = filtered.to_csv(index=False, sep=";").encode("utf-8-sig")

    st.download_button(
        "📥 Download Prospects (CSV)",
        data=csv,
        file_name=export_name,
        mime="text/csv",
        key=f"{chat_key}_download"
    )

# ─── INTERFACE PRINCIPALE ─────────────────────────────────────────────────────
col_header, col_logo = st.columns([4, 1])

with col_header:
    st.title("🔬 Laser Prospects — Intelligent Prospecting")

with col_logo:
    logo_path = "LOGOS AMPLITUDE/Amplitude_RVB.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=160)

col_refresh, col_info = st.columns([1, 3])

with col_refresh:
    if st.button("🔄 Refresh All"):
        with st.spinner("Collecting data... (~2 min)"):
            df = run_pipeline()
            st.cache_data.clear()
        st.success(f"✅ {len(df)} prospects updated!")
        st.rerun()

with col_info:
    try:
        last_modified = os.path.getmtime("leads_laser.csv")
        last_date = datetime.fromtimestamp(last_modified).strftime("%d/%m/%Y at %H:%M")
        st.caption(f"Last updated: {last_date}")
    except Exception:
        st.caption("Last updated: unknown")

if not os.path.exists("leads_laser.csv"):
    st.warning("⚠️ No data. Click Refresh All.")
    st.stop()

df = load_data()

if "custom_keywords" in st.session_state:
    df = recompute_scores(df, st.session_state["custom_keywords"])

df_usa = df[df["source"].isin(["NSF", "NIH"])].copy()
df_europe = df[df["source"] == "CORDIS"].copy()
df_ted = df[df["source"] == "TED"].copy()
df_erc = df[df["source"] == "ERC"].copy()
df_canada = df[df["source"].isin(["NSERC", "CIHR"])].copy()
df_ukri = df[df["source"] == "UKRI"].copy()
df_europe_uk = pd.concat([df_europe, df_ukri, df_erc], ignore_index=True)

tab_usa, tab_europe, tab_ted, tab_canada = st.tabs([
    "🇺🇸 USA (NSF + NIH)",
    f"🇪🇺 Europe — CORDIS + UKRI + ERC ({len(df_europe_uk)})",
    "📋 Europe — Tenders (TED)",
    f"🍁 Canada — NSERC + CIHR ({len(df_canada)})",
])

with tab_usa:
    st.markdown("# 🇺🇸 USA — NSF + NIH")
    st.markdown("---")
    _col_usa_btn, _ = st.columns([1, 4])
    with _col_usa_btn:
        if st.button("🇺🇸 Refresh USA", key="btn_usa_tab"):
            with st.spinner("Collecting NSF + NIH... (~1 min)"):
                refresh_usa_only()
                st.cache_data.clear()
            st.success("✅ USA updated!")
            st.rerun()

    render_prospect_interface(
        df_base=df_usa,
        interface_name="USA — NSF + NIH",
        chat_key="chat_history_usa",
        export_name="prospects_usa_export.csv"
    )

with tab_europe:
    st.markdown("# 🇪🇺 Europe — CORDIS + UKRI + ERC")
    st.markdown("---")
    _col_eu_btn, _ = st.columns([1, 4])
    with _col_eu_btn:
        if st.button("🇪🇺 Refresh Europe", key="btn_europe_tab"):
            with st.spinner("Collecting CORDIS + UKRI... (~2 min)"):
                refresh_europe_only()
                st.cache_data.clear()
            st.success("✅ Europe updated!")
            st.rerun()

    ERC_DASHBOARD_URL = "https://dashboard.tech.ec.europa.eu/qs_digit_dashboard_mt/public/sense/app/c140622a-87e0-412e-8b29-9b5ddd857e13/sheet/61a0bd1d-cd6d-4ac8-8b55-80d8661e44c0/state/analysis"

    with st.expander("📥 Import / update ERC data", expanded=df_erc.empty):
        st.markdown(
            f"**1.** Open the ERC dashboard: [ERC Dashboard — Funded & Evaluated Projects]({ERC_DASHBOARD_URL})  \n"
            "**2.** Export to Excel (download icon in the top-right corner of the table)  \n"
            "**3.** Upload the file below"
        )

        uploaded = st.file_uploader("ERC file (CSV or Excel)", type=["csv", "xlsx", "xls"], key="erc_upload")

        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df_erc_raw = pd.read_csv(uploaded, sep=None, engine="python")
                else:
                    df_erc_raw = pd.read_excel(uploaded)

                st.caption(f"Detected columns: {list(df_erc_raw.columns)}")

                def _find_col(df, *keywords):
                    for kw in keywords:
                        for col in df.columns:
                            if kw.lower() in col.lower():
                                return col
                    return None

                col_title   = _find_col(df_erc_raw, "title", "acronym", "project")
                col_org     = _find_col(df_erc_raw, "host", "institution", "organisation", "organization")
                col_country = _find_col(df_erc_raw, "country")
                col_budget  = _find_col(df_erc_raw, "contribution", "net eu", "budget", "amount", "funding", "total cost", "total", "grant amount")
                col_desc    = _find_col(df_erc_raw, "summary", "abstract", "description", "objective")
                col_contact = _find_col(df_erc_raw, "pi ", "principal", "investigator", "researcher")
                col_end     = _find_col(df_erc_raw, "end", "duration")
                col_link    = _find_col(df_erc_raw, "url", "link", "cordis", "doi")
                st.caption(f"Mapping → title:`{col_title}` | org:`{col_org}` | country:`{col_country}` | **budget:`{col_budget}`** | desc:`{col_desc}`")

                rows_erc = []
                for _, row in df_erc_raw.iterrows():
                    title = str(row[col_title]) if col_title else ""
                    description = str(row[col_desc]) if col_desc else ""
                    score, matched = compute_score(title, description)
                    rows_erc.append({
                        "source": "ERC",
                        "title": title,
                        "organization": str(row[col_org]) if col_org else "",
                        "country": str(row[col_country]) if col_country else "",
                        "budget_usd": None,
                        "budget_eur": pd.to_numeric(row[col_budget], errors="coerce") if col_budget else None,
                        "contact_name": str(row[col_contact]) if col_contact else "",
                        "contact_email": "",
                        "score": score,
                        "keywords_matched": str(matched),
                        "description": description,
                        "end_date": str(row[col_end])[:10] if col_end else "",
                        "link": str(row[col_link]) if col_link else "",
                    })

                df_erc_import = pd.DataFrame(rows_erc)
                df_erc_import = df_erc_import[df_erc_import["score"] >= SCORE_MIN_FILTER]

                st.success(f"**{len(df_erc_import)} ERC projects** match the keywords.")
                st.dataframe(df_erc_import[["title", "organization", "country", "budget_eur", "score"]].head(10))

                if st.button("✅ Add to database", key="erc_import_btn"):
                    if os.path.exists("leads_laser.csv"):
                        df_existing = pd.read_csv("leads_laser.csv")
                        df_existing = df_existing[df_existing["source"] != "ERC"]
                    else:
                        df_existing = pd.DataFrame()
                    df_total = pd.concat([df_existing, df_erc_import], ignore_index=True)
                    df_total = df_total.sort_values("score", ascending=False)
                    df_total = df_total.drop_duplicates(subset=["title"], keep="first")
                    df_total.to_csv("leads_laser.csv", index=False)
                    st.cache_data.clear()
                    st.success("✅ ERC data imported!")
                    st.rerun()

            except Exception as e:
                st.error(f"File read error: {e}")

    render_prospect_interface(
        df_base=df_europe_uk,
        interface_name="Europe — CORDIS + UKRI + ERC",
        chat_key="chat_history_europe",
        export_name="prospects_europe_export.csv",
        show_budget_email=True,
        budget_col="budget_eur",
        budget_symbol="€",
        show_country_chart=True,
        known_sources=["CORDIS", "UKRI", "ERC"]
    )

with tab_ted:
    st.markdown("# 📋 Europe — TED Tenders")
    st.markdown("---")
    _col_ted_btn, _col_ted_radio = st.columns([1, 3])
    with _col_ted_btn:
        if st.button("📋 Refresh TED", key="btn_ted_tab"):
            with st.spinner("Collecting TED... (~10 sec)"):
                refresh_ted_only()
                st.cache_data.clear()
            st.success("✅ TED updated!")
            st.rerun()
    with _col_ted_radio:
        ted_status_filter = st.radio(
            "Call status",
            ["All", "Open only", "Awarded only"],
            horizontal=True,
            key="ted_status_radio"
        )

    df_ted_display = df_ted.copy()
    if "notice_status" in df_ted_display.columns:
        if ted_status_filter == "Open only":
            df_ted_display = df_ted_display[df_ted_display["notice_status"] == "Ouvert"]
        elif ted_status_filter == "Awarded only":
            df_ted_display = df_ted_display[df_ted_display["notice_status"] == "Attribué"]

    render_prospect_interface(
        df_base=df_ted_display,
        interface_name="Europe — TED Tenders",
        chat_key="chat_history_ted",
        export_name="prospects_ted_export.csv",
        show_budget_email=True,
        budget_col="budget_eur",
        budget_symbol="€",
        show_country_chart=True,
        show_notice_status=True
    )


with tab_canada:
    st.markdown("# 🍁 Canada — NSERC + CIHR")
    st.markdown("---")
    _col_canada_btn, _ = st.columns([1, 4])
    with _col_canada_btn:
        if st.button("🍁 Refresh Canada", key="btn_canada_tab"):
            with st.spinner("Collecting NSERC + CIHR... (~1 min)"):
                refresh_nserc_only()
                refresh_cihr_only()
                st.cache_data.clear()
            st.success("✅ Canada updated!")
            st.rerun()

    if df_canada.empty:
        st.info("No data. Click **🍁 Refresh Canada** to collect Canadian projects.")
    else:
        render_prospect_interface(
            df_base=df_canada,
            interface_name="Canada — NSERC + CIHR",
            chat_key="chat_history_canada",
            export_name="prospects_canada_export.csv",
            show_budget_email=True,
            budget_col="budget_cad",
            budget_symbol="CA$",
            show_country_chart=True
        )



