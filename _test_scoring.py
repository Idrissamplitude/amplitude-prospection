# -*- coding: utf-8 -*-
"""Verification rapide du nouveau systeme de scoring."""
import pandas as pd

KEYWORDS_WEIGHTS = {
    "femtosecond": 5,
    "ultrafast": 4,
    "ultrashort": 4,
    "ablation": 4,
    "multiphoton": 4,
    "two-photon": 3,
    "biophotonics": 3,
    "photonics": 3,
    "nonlinear": 3,
    "pulsed laser": 3,
    "fiber laser": 3,
    "lidar": 2,
    "micromachining": 2,
    "laser": 2,
    "spectroscopy": 2,
    "waveguide": 2,
    "optics": 1,
    "optical": 1,
}

SCORE_MAX = sum(w * 3 for w in KEYWORDS_WEIGHTS.values())
SCORE_MIN_FILTER = 5


def compute_score(title, description):
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


print(f"SCORE_MAX theorique : {SCORE_MAX}\n")

# --- Cas de test unitaires ---
cas = [
    # (titre, description, score_attendu_min, commentaire)
    (
        "Femtosecond laser ablation of biological tissue",
        "Ultrafast pulsed laser system for multiphoton imaging and biophotonics",
        30,
        "Projet ideal Amplitude : beaucoup de kw haute valeur"
    ),
    (
        "Ultrafast fiber laser for micromachining applications",
        "Development of a femtosecond pulsed laser source for nonlinear optics",
        20,
        "Projet pertinent : titre fort + desc riche"
    ),
    (
        "Photonics and optics research",
        "Study of optical waveguide nonlinear effects in spectroscopy",
        0,  # pas de minimum strict
        "Projet tangent : pertinence moyenne"
    ),
    (
        "Laser Focus Group Annual Report",
        "This report summarizes laser-sharp business strategies and laser management",
        0,
        "Faux positif potentiel : laser hors contexte"
    ),
    (
        "Generic project title",
        "No relevant keywords here at all",
        0,
        "Projet non pertinent : score doit etre 0"
    ),
]

print("=== TESTS UNITAIRES ===\n")
for titre, desc, min_attendu, commentaire in cas:
    score, matched = compute_score(titre, desc)
    passe = "OK" if score >= min_attendu else "ATTENTION"
    print(f"[{passe}] Score={score:3d} | {commentaire}")
    print(f"       Titre : {titre[:60]}")
    print(f"       Matchs: {matched}")
    print()

# --- Verification ponderation titre vs description ---
print("=== TEST PONDERERATION TITRE 2x ===\n")
score_titre, _ = compute_score("femtosecond ablation", "")
score_desc, _  = compute_score("", "femtosecond ablation")
score_both, _  = compute_score("femtosecond ablation", "femtosecond ablation")
print(f"  'femtosecond ablation' en titre seul : {score_titre}")
print(f"  'femtosecond ablation' en desc seule  : {score_desc}")
print(f"  'femtosecond ablation' dans les deux  : {score_both}")
assert score_titre == score_desc * 2, "ERREUR : le titre devrait valoir 2x la description"
assert score_both == score_titre + score_desc, "ERREUR : titre + desc devrait sommer"
print("  Ponderations correctes.\n")

# --- Re-scoring du CSV existant ---
print("=== RE-SCORING CSV EXISTANT ===\n")
try:
    df = pd.read_csv("leads_laser.csv")
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)

    old_scores = df["score"].copy()
    new_scores = df.apply(
        lambda r: compute_score(str(r.get("title", "")), str(r.get("description", "")))[0],
        axis=1
    )

    print(f"  Nb prospects dans le CSV : {len(df)}")
    print(f"  Score moyen ancien : {old_scores.mean():.1f}")
    print(f"  Score moyen nouveau : {new_scores.mean():.1f}")
    print(f"  Score max ancien : {int(old_scores.max())}")
    print(f"  Score max nouveau : {int(new_scores.max())}")
    print(f"  Prospects qui passeraient le nouveau filtre ({SCORE_MIN_FILTER}+) : {(new_scores >= SCORE_MIN_FILTER).sum()}")

    ameliores = (new_scores > old_scores).sum()
    degrade = (new_scores < old_scores).sum()
    identiques = (new_scores == old_scores).sum()
    print(f"\n  Score augmente : {ameliores} projets")
    print(f"  Score diminue  : {degrade} projets")
    print(f"  Score identique: {identiques} projets")

    print("\n  Top 5 nouveaux scores :")
    df["new_score"] = new_scores
    top5 = df.nlargest(5, "new_score")[["title", "source", "new_score"]]
    for _, row in top5.iterrows():
        print(f"    [{row['source']}] {row['new_score']:3d} pts — {str(row['title'])[:70]}")

except FileNotFoundError:
    print("  leads_laser.csv introuvable — lance d'abord un Rafraichissement dans l'app.")

print("\nDone.")
