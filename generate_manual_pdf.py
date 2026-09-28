from fpdf import FPDF
import os

class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, "Amplitude Laser - Manuel d'utilisation Laser Prospects", align="L")
        self.cell(0, 8, f"p. {self.page_no() - 1}", align="R")
        self.ln(2)
        self.set_draw_color(220, 220, 220)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(180, 180, 180)
        self.cell(0, 8, "Document confidentiel - Amplitude Laser © 2026", align="C")
        # Mini logo bottom right
        self.image("U:/APP/LOGOS AMPLITUDE/Amplitude_RVB mini.png",
                   x=184, y=272, w=20)

# ── COLORS ──
NAVY    = (15, 52, 96)
RED     = (233, 69, 96)
DARK    = (26, 26, 46)
GRAY    = (100, 100, 100)
LGRAY   = (245, 247, 250)
WHITE   = (255, 255, 255)
BLUE_L  = (232, 244, 253)

pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(18, 22, 18)

# ══════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════
pdf.add_page()
pdf.set_fill_color(*DARK)
pdf.rect(0, 0, 210, 297, "F")

# Large logo centered at top
pdf.image("U:/APP/LOGOS AMPLITUDE/Amplitude_RVB.png", x=65, y=48, w=80)

pdf.set_y(152)
pdf.set_font("Helvetica", "B", 26)
pdf.set_text_color(*WHITE)
pdf.cell(0, 16, "APPLICATION LASER PROSPECTS", align="C")

pdf.set_y(178)
pdf.set_font("Helvetica", "", 13)
pdf.set_text_color(*RED)
pdf.cell(0, 10, "Amplitude Laser", align="C")

pdf.set_y(205)
pdf.set_font("Helvetica", "B", 16)
pdf.set_text_color(*WHITE)
pdf.cell(0, 10, "Manuel d'utilisation", align="C")

pdf.set_y(220)
pdf.set_font("Helvetica", "", 11)
pdf.set_text_color(168, 178, 216)
pdf.cell(0, 8, "Version 1", align="C")

pdf.set_y(234)
pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(168, 178, 216)
pdf.cell(0, 8, "Idriss PASCOTTO", align="C")

pdf.set_y(252)
pdf.set_draw_color(80, 80, 100)
pdf.line(30, pdf.get_y(), 180, pdf.get_y())
pdf.ln(6)
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(168, 178, 216)
pdf.cell(0, 6, "Document interne · Amplitude Laser · 2026", align="C")
pdf.ln(4)
pdf.cell(0, 6, "Confidentiel - usage interne uniquement", align="C")


def section_title(pdf, text):
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, text)
    pdf.ln(1)
    pdf.set_draw_color(*RED)
    pdf.set_line_width(0.8)
    pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(5)


def sub_title(pdf, text):
    pdf.ln(4)
    pdf.set_fill_color(*RED)
    pdf.rect(18, pdf.get_y(), 2.5, 6, "F")
    pdf.set_x(23)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, text)
    pdf.ln(5)


def body(pdf, text, indent=0):
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    if indent:
        pdf.set_x(18 + indent)
    pdf.multi_cell(0, 5.5, text)
    pdf.ln(1)


def box(pdf, title, text, bg=(232, 244, 253), border=(33, 150, 243)):
    pdf.ln(2)
    # Estimate height needed and force page break before drawing if too close to bottom
    n_lines = text.count('\n') + max(1, len(text) // 65) + 1
    est_h = 5.5 + 4 + n_lines * 5.5 + 8
    if pdf.get_y() + est_h > 279:
        pdf.add_page()
    pdf.ln(2)
    start_y = pdf.get_y()
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*DARK)
    pdf.set_x(22)
    pdf.cell(0, 5.5, title)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_x(22)
    pdf.multi_cell(165, 5, text)
    end_y = pdf.get_y()
    # bg rect
    pdf.set_fill_color(*bg)
    pdf.rect(18.6, start_y, 173, end_y - start_y + 3, "F")
    # left border
    pdf.set_draw_color(*border)
    pdf.set_line_width(1.2)
    pdf.line(18, start_y, 18, end_y + 2)
    pdf.set_line_width(0.2)
    # redraw text on top of bg
    pdf.set_y(start_y)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*DARK)
    pdf.set_x(22)
    pdf.cell(0, 5.5, title)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_x(22)
    pdf.multi_cell(165, 5, text)
    pdf.ln(4)


def table(pdf, headers, rows, col_widths):
    pdf.ln(2)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 9)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, fill=True, border=0)
    pdf.ln()
    for ri, row in enumerate(rows):
        pdf.set_fill_color(*LGRAY if ri % 2 == 0 else WHITE)
        pdf.set_text_color(*DARK)
        pdf.set_font("Helvetica", "", 9)
        max_h = 1
        # measure height needed
        for i, cell in enumerate(row):
            lines = pdf.get_string_width(cell) / col_widths[i]
            max_h = max(max_h, int(lines) + 1)
        h = max(6, max_h * 5)
        # draw row bg
        total_w = sum(col_widths)
        pdf.set_fill_color(*LGRAY if ri % 2 == 0 else WHITE)
        pdf.rect(18, pdf.get_y(), total_w, h + 2, "F")
        row_y = pdf.get_y()
        for i, cell in enumerate(row):
            pdf.set_xy(18 + sum(col_widths[:i]), row_y)
            pdf.multi_cell(col_widths[i], 5.5, cell, border=0)
        pdf.set_y(row_y + h + 2)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.ln(4)


# ══════════════════════════════════════════════════════
# PAGE 2 - TABLE OF CONTENTS
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "Table des matières")

toc = [
    ("1.", "Contexte & objectif du projet", 3),
    ("2.", "Accès à l'application", 4),
    ("3.", "Sources de données", 4),
    ("4.", "Vue d'ensemble de l'interface", 5),
    ("5.", "Fonctionnalités détaillées", 5),
    ("   a.", "Rafraîchissement des données", 5),
    ("   b.", "Mots-clés de scoring", 5),
    ("   c.", "Mots-clés d'exclusion", 6),
    ("   d.", "Recherche libre", 6),
    ("   e.", "Filtres & Tri", 6),
    ("   f.", "Métriques et tableau de bord", 7),
    ("   g.", "Top 5 Prospects", 7),
    ("   h.", "Tableau des prospects", 7),
    ("   i.", "Graphiques", 8),
    ("   j.", "Détail d'un prospect", 8),
    ("   k.", "Statut commercial", 8),
    ("   l.", "Export CSV", 9),
    ("   m.", "Onglet TED - Appels d'offres", 9),
    ("   n.", "Import ERC manuel", 9),
    ("6.", "Algorithme de scoring", 10),
    ("7.", "Liens utiles", 11),
]
pdf.set_font("Helvetica", "", 10)
for num, title, pg in toc:
    pdf.set_text_color(*NAVY if not num.startswith(" ") else GRAY)
    weight = "B" if not num.startswith(" ") else ""
    pdf.set_font("Helvetica", weight, 10 if not num.startswith(" ") else 9.5)
    pdf.cell(12, 6.5, num)
    pdf.cell(155, 6.5, title)
    pdf.set_text_color(*GRAY)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6.5, str(pg), align="R")
    pdf.ln()

# ══════════════════════════════════════════════════════
# S1 - CONTEXTE
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "1. Contexte & objectif du projet")

sub_title(pdf, "Problème de prospection")
body(pdf, "Identifier des prospects qualifiés dans le domaine laser représente un travail manuel considérable : les appels à projets et les financements de recherche sont dispersés sur des dizaines de portails publics (NSF, NIH, CORDIS, UKRI, TED, NSERC, CIHR...), dans des formats hétérogènes et en plusieurs langues.")
body(pdf, "Sans outil dédié, un commercial doit consulter chaque base manuellement, lire les résumés de projets et évaluer leur pertinence pour Amplitude - un processus très chronophage et peu reproductible.")

sub_title(pdf, "L'objectif de l'application")
body(pdf, "Laser Prospects automatise cette veille en agrégeant en temps réel les données de 7 sources publiques de financement de la recherche. Chaque projet est automatiquement scoré selon sa pertinence pour Amplitude (présence de mots-clés laser dans le titre et la description), puis présenté dans une interface de prospection commerciale.")

box(pdf,
    "En résumé, l'application permet de :",
    "- Collecter des centaines de projets de recherche financés en quelques minutes\n"
    "- Les classer automatiquement par pertinence laser (score de 0 à 100+)\n"
    "- Filtrer, rechercher et exporter les prospects les plus intéressants\n"
    "- Suivre l'état commercial de chaque contact (à contacter, contacté, pas intéressé)",
    bg=(232, 248, 232), border=(76, 175, 80))

# ══════════════════════════════════════════════════════
# S2 - ACCÈS
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "2. Accès à l'application")

body(pdf, "L'application est hébergée sur Streamlit Cloud et accessible depuis n'importe quel navigateur web.")

# credential box
pdf.ln(2)
pdf.set_fill_color(*DARK)
pdf.rect(18, pdf.get_y(), 174, 22, "F")
y0 = pdf.get_y() + 4
pdf.set_y(y0)
pdf.set_font("Helvetica", "B", 9)
pdf.set_text_color(168, 178, 216)
pdf.set_x(24); pdf.cell(30, 5.5, "URL")
pdf.set_text_color(100, 220, 200)
pdf.set_font("Helvetica", "", 10)
pdf.cell(0, 5.5, "[URL_A_COMPLETER]")
pdf.ln(7)
pdf.set_font("Helvetica", "B", 9)
pdf.set_text_color(168, 178, 216)
pdf.set_x(24); pdf.cell(30, 5.5, "Mot de passe")
pdf.set_text_color(*RED)
pdf.set_font("Helvetica", "B", 11)
pdf.cell(0, 5.5, "Ampl1tude2026!")
pdf.ln(8)

box(pdf, "Navigateurs compatibles",
    "Chrome, Edge, Firefox, Safari.",
    bg=BLUE_L, border=(33, 150, 243))

box(pdf, "Première connexion",
    "Au premier chargement, si aucune donnée n'est encore présente, un message d'avertissement s'affiche. "
    "Cliquez sur le bouton [Refresh All] pour lancer la collecte initiale.",
    bg=(255, 248, 225), border=(255, 152, 0))

sub_title(pdf, "Fréquence de mise à jour recommandée")
body(pdf, "Les données ne se rafraîchissent pas automatiquement. Recommandation : une fois par semaine, cliquez sur [Refresh All] pour mettre à jour l'ensemble de la base de prospects.")

# ══════════════════════════════════════════════════════
# S3 - SOURCES
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "3. Sources de données")

body(pdf, "L'application agrège automatiquement les données de 7 sources publiques de financement de la recherche, couvrant les USA, l'Europe, le Royaume-Uni et le Canada.")

table(pdf,
    ["Source", "Zone", "Type de données", "Site officiel"],
    [
        ["NSF", "USA", "Projets de recherche universitaire financés", "nsf.gov/awardsearch"],
        ["NIH", "USA", "Projets de recherche biomédicale et scientifique", "reporter.nih.gov"],
        ["CORDIS", "UE", "Projets financés par Horizon Europe", "cordis.europa.eu"],
        ["UKRI", "UK", "Projets financés par les conseils britanniques", "gtr.ukri.org"],
        ["TED", "UE", "Appels d'offres publics européens", "ted.europa.eu"],
        ["NSERC", "Canada", "Subventions en sciences naturelles et génie", "nserc-crsng.gc.ca"],
        ["CIHR", "Canada", "Projets de recherche en santé", "open.canada.ca"],
        ["ERC", "UE", "Projets ERC (import manuel)", "erc.europa.eu"],
    ],
    [22, 18, 82, 52]
)

box(pdf, "Note sur l'ERC",
    "Les données ERC ne sont pas accessibles via API. Elles doivent être importées manuellement "
    "depuis le dashboard officiel (voir section 5n).",
    bg=BLUE_L, border=(33, 150, 243))

# ══════════════════════════════════════════════════════
# S4 - VUE D'ENSEMBLE
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "4. Vue d'ensemble de l'interface")

body(pdf, "L'application est organisée en quatre onglets, un par zone géographique :")

table(pdf,
    ["Onglet", "Sources incluses", "Bouton de rafraîchissement"],
    [
        ["USA (NSF + NIH)", "NSF, NIH", "Refresh USA"],
        ["Europe - CORDIS + UKRI + ERC", "CORDIS, UKRI, ERC", "Refresh Europe"],
        ["Europe - Tenders (TED)", "TED", "Refresh TED"],
        ["Canada - NSERC + CIHR", "NSERC, CIHR", "Refresh Canada"],
    ],
    [60, 70, 44]
)

body(pdf, "Chaque onglet contient les mêmes sections dans l'ordre suivant :")

sections = [
    "1. Bouton de rafraîchissement",
    "2. Mots-clés de scoring (paramétrable)",
    "3. Mots-clés d'exclusion (paramétrable)",
    "4. Recherche libre + Filtres & Tri",
    "5. Métriques (compteurs dynamiques)",
    "6. Top 5 Prospects (cartes)",
    "7. Tableau complet des prospects",
    "8. Graphiques",
    "9. Détail d'un prospect + Statut commercial",
    "10. Export CSV",
]
for s in sections:
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    pdf.set_x(24)
    pdf.cell(0, 5.5, s)
    pdf.ln()

pdf.ln(2)
box(pdf, "Astuce",
    "Le bouton [Refresh All] en haut de page rafraîchit toutes les sources en une seule fois. "
    "Utilisez les boutons par onglet pour des mises à jour partielles.",
    bg=(232, 248, 232), border=(76, 175, 80))

# ══════════════════════════════════════════════════════
# S5 - FONCTIONNALITÉS
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "5. Fonctionnalités détaillées")

sub_title(pdf, "a. Rafraîchissement des données")
body(pdf, "Deux niveaux de rafraîchissement sont disponibles :")
body(pdf, "- [Refresh All] (en-tête de page) : lance la collecte complète sur toutes les sources simultanément. A utiliser pour une mise à jour globale.", indent=4)
body(pdf, "- [Refresh par onglet] : rafraîchit uniquement les sources de l'onglet concerné, sans modifier les autres. Plus rapide. A utiliser pour cibler une zone géographique spécifique.", indent=4)
body(pdf, "Après chaque rafraîchissement, la date et l'heure de la dernière mise à jour sont affichées sous le bouton Refresh All.")

sub_title(pdf, "b. Mots-clés de scoring")
body(pdf, "L'expander [Scoring Keywords] permet de personnaliser les mots-clés utilisés pour calculer le score de pertinence de chaque prospect. Chaque mot-clé est associé à un poids (1 a 10). Le titre d'un projet compte double par rapport a la description.")
body(pdf, "- [Apply] - applique les modifications et recalcule tous les scores immédiatement", indent=4)
body(pdf, "- [Default] - restaure la liste de mots-clés par défaut d'Amplitude", indent=4)
body(pdf, "Il est possible d'ajouter de nouvelles lignes ou de supprimer des mots-clés existants directement dans le tableau.")

box(pdf, "Important",
    "Les modifications de scoring sont appliquées à la session en cours uniquement. "
    "Elles ne modifient pas le fichier CSV source. Un rafraîchissement des données recharge les scores par défaut.",
    bg=(255, 248, 225), border=(255, 152, 0))

sub_title(pdf, "c. Mots-clés d'exclusion")
body(pdf, "L'expander [Exclusion Keywords] permet de masquer des projets non pertinents. Tout projet dont le titre ou la description contient un mot de cette liste est automatiquement exclu de l'affichage. Format : un mot ou une expression par ligne (insensible à la casse).")

box(pdf, "Exemple d'utilisation",
    "Ajouter 'printer', 'imprimante', 'inkjet' pour éliminer les projets liés à l'impression 3D "
    "qui utilisent le terme 'laser' mais ne sont pas pertinents pour Amplitude.",
    bg=(232, 248, 232), border=(76, 175, 80))

# ── PAGE ──
pdf.add_page()
section_title(pdf, "5. Fonctionnalités détaillées (suite)")

sub_title(pdf, "d. Recherche libre")
body(pdf, "La barre [Free search] filtre en temps réel les prospects dont le titre, la description ou l'organisation contient le texte saisi. Exemples : 'femtosecond', 'MIT', 'ablation laser', 'Stanford University'.")
body(pdf, "La recherche se cumule avec les filtres actifs dans le panneau Filters & Sort.")

sub_title(pdf, "e. Filtres & Tri")
body(pdf, "L'expander [Filters & Sort] regroupe tous les filtres avancés :")

table(pdf,
    ["Filtre", "Description"],
    [
        ["Minimum score", "Seuil minimum de pertinence (défaut : 5). Augmenter pour afficher uniquement les prospects très pertinents."],
        ["Budget", "Plage de budget. Les prospects sans budget connu restent toujours affichés."],
        ["Email only", "N'affiche que les prospects avec un email de contact disponible."],
        ["Budget only", "N'affiche que les prospects avec un montant de financement renseigné."],
        ["Filter by status", "Filtre par statut commercial : To contact, Contacted, Not interested."],
        ["Filter by source", "Filtre par source de données (NSF, NIH, CORDIS, etc.)."],
        ["Sort by", "Trier par : Score, Budget, ou End Date (date de fin du projet)."],
        ["Order", "Ordre croissant ou decroissant."],
    ],
    [42, 132]
)

sub_title(pdf, "f. Métriques")
body(pdf, "Juste sous les filtres, une rangée de métriques affiche dynamiquement les statistiques après application de tous les filtres actifs :")
body(pdf, "- Total : nombre total de prospects correspondant aux filtres", indent=4)
body(pdf, "- Par source (NSF, NIH, CORDIS...) - nombre de prospects par source dans les résultats filtrés", indent=4)
body(pdf, "- Max score : score maximum parmi les prospects affiches", indent=4)

sub_title(pdf, "g. Top 5 Prospects")
body(pdf, "La section [Top 5 Prospects] affiche les 5 meilleurs prospects sous forme de cartes compactes, avec source, pays, titre, organisation, score, budget et statut commercial. Le Top 5 reflète toujours l'ordre de tri actif.")

# ── PAGE ──
pdf.add_page()
section_title(pdf, "5. Fonctionnalités détaillées (suite)")

sub_title(pdf, "h. Tableau des prospects")
body(pdf, "La section [Qualified Prospects] présente tous les prospects filtrés dans un tableau interactif. Les colonnes disponibles sont :")

table(pdf,
    ["Colonne", "Description"],
    [
        ["Call Type (TED)", "Ouvert / Attribué / À venir"],
        ["Status", "Statut commercial renseigné par l'utilisateur"],
        ["Source", "Origine de la donnée (NSF, NIH, CORDIS...)"],
        ["Project", "Intitulé du projet de recherche"],
        ["Organisation", "Institution ou entreprise portant le projet"],
        ["Country", "Pays de l'institution"],
        ["Budget", "Montant du financement (USD, EUR ou CAD selon l'onglet)"],
        ["Contact", "Nom du chercheur principal (PI)"],
        ["Email", "Email du contact (disponible principalement pour NSF)"],
        ["Score", "Score de pertinence calculé (5 minimum par défaut)"],
        ["Keywords", "Mots-clés laser détectés dans ce projet"],
        ["End Date", "Date de fin du projet ou date limite de soumission"],
        ["Project Link", "Lien cliquable vers la page officielle du projet"],
    ],
    [42, 132]
)

sub_title(pdf, "i. Graphiques")
body(pdf, "La section [Charts] présente 2 à 3 visualisations selon l'onglet :")
body(pdf, "- Score Distribution - histogramme de la répartition des scores de pertinence", indent=4)
body(pdf, "- Top 10 Prospects by Budget - les 10 projets les mieux financés", indent=4)
body(pdf, "- Distribution by Country - répartition géographique (onglets Europe et Canada)", indent=4)
body(pdf, "Les graphiques s'adaptent automatiquement aux filtres actifs.")

sub_title(pdf, "j. Détail d'un prospect")
body(pdf, "La section [Prospect Detail] affiche la fiche complète d'un prospect sélectionné : titre, source, organisation, pays, budget, date de fin, score, mots-clés, contact, email, lien officiel et résumé complet du projet.")

# ── PAGE ──
pdf.add_page()
section_title(pdf, "5. Fonctionnalités détaillées (suite)")

sub_title(pdf, "k. Statut commercial")
body(pdf, "Directement sous la fiche prospect, la section [Commercial Status] permet d'enregistrer le suivi commercial :")

table(pdf,
    ["Statut", "Signification"],
    [
        ["- (defaut)", "Aucun suivi initié"],
        ["To contact", "Prospect identifié, à contacter prochainement"],
        ["Contacted", "Un premier contact a ete etabli"],
        ["Not interested", "Prospect contacté mais sans suite commerciale"],
    ],
    [45, 129]
)

body(pdf, "Un champ [Note] libre permet d'ajouter des observations (nom d'interlocuteur, date de contact, résultat d'un appel, etc.). Cliquez sur [Save status] pour enregistrer.")

box(pdf, "Persistance des statuts",
    "Les statuts sont sauvegardés dans le fichier prospect_status.csv sur le serveur. "
    "Ils sont conservés même après un rafraîchissement des données. "
    "Utilisez le filtre 'Filter by status' pour retrouver rapidement vos prospects en cours.",
    bg=BLUE_L, border=(33, 150, 243))

sub_title(pdf, "l. Export CSV")
body(pdf, "Le bouton [Download Prospects (CSV)] en bas de chaque onglet exporte uniquement les prospects correspondant aux filtres actifs. Le séparateur utilisé est le point-virgule (;), compatible avec Excel.")

box(pdf, "Astuce",
    "Pour exporter uniquement les prospects avec email disponible, activez le filtre 'Email only' avant de télécharger.",
    bg=(232, 248, 232), border=(76, 175, 80))

sub_title(pdf, "m. Onglet TED - Appels d'offres")
body(pdf, "L'onglet [Europe - Tenders (TED)] est dedie aux Appels d'offres publics européens. Il dispose d'un filtre specifique [Call status] :")

table(pdf,
    ["Option", "Description"],
    [
        ["All", "Affiche tous les appels d'offres (ouverts et attribués)"],
        ["Open only", "Appels en cours d'acceptation de candidatures (Contract Notice)"],
        ["Awarded only", "Marchés déjà attribués (Contract Award Notice) - utile pour benchmark"],
    ],
    [35, 139]
)

body(pdf, "Dans le tableau, la colonne [Call Type] indique le statut de chaque notice : Ouvert, Attribué, À venir ou Qualification.")

box(pdf, "Attention - date de clôture",
    "Pour les appels ouverts, la colonne End Date indique la date limite de soumission des offres. "
    "Vérifiez toujours cette date sur le site TED avant de contacter le porteur de l'appel.",
    bg=(255, 248, 225), border=(255, 152, 0))

sub_title(pdf, "n. Import ERC manuel")
body(pdf, "Les données ERC (European Research Council) ne sont pas accessibles via API. Un module d'import manuel est disponible dans l'onglet Europe. Procédure :")
body(pdf, "1. Ouvrez le Dashboard ERC officiel : erc.europa.eu/projects-statistics", indent=4)
body(pdf, "2. Exportez les données en Excel (icône téléchargement en haut à droite du tableau)", indent=4)
body(pdf, "3. Dans l'expander [Import / update ERC data], uploadez le fichier", indent=4)
body(pdf, "4. L'application détecte automatiquement les colonnes et filtre les projets laser", indent=4)
body(pdf, "5. Cliquez sur [Add to database] pour intégrer les données", indent=4)

# ══════════════════════════════════════════════════════
# S6 - SCORING
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "6. Algorithme de scoring")

body(pdf, "Chaque projet est scoré selon la présence de mots-clés dans son titre et sa description. Le titre compte double (x2) par rapport a la description (x1). La formule est :")

pdf.ln(2)
pdf.set_fill_color(*DARK)
pdf.rect(18, pdf.get_y(), 174, 16, "F")
pdf.set_y(pdf.get_y() + 3)
pdf.set_font("Courier", "B", 10)
pdf.set_text_color(100, 220, 200)
pdf.set_x(24)
pdf.cell(0, 5, "Score = S(poids x 2) pour chaque mot-clé dans le titre")
pdf.ln(5)
pdf.set_x(24)
pdf.cell(0, 5, "       + S(poids x 1) pour chaque mot-clé dans la description")
pdf.ln(8)

body(pdf, "Un projet doit avoir un score minimum de 5 pour apparaître dans l'application. Ce seuil est ajustable via le filtre [Minimum score].")


box(pdf, "Exemple de calcul",
    "Projet ayant 'femtosecond laser' dans le titre et 'ablation' dans la description :\n"
    "Titre : 5x2 (femtosecond) + 2x2 (laser) = 14\n"
    "Description : 4x1 (ablation) = 4\n"
    "Score total = 18",
    bg=(232, 248, 232), border=(76, 175, 80))

# ══════════════════════════════════════════════════════
# S7 - LIENS
# ══════════════════════════════════════════════════════
pdf.add_page()
section_title(pdf, "7. Liens utiles")

sub_title(pdf, "Application & accès")
table(pdf,
    ["Ressource", "Lien / Information"],
    [
        ["Application Laser Prospects", "[URL_A_COMPLETER]"],
        ["Mot de passe", "Ampl1tude2026!"],
    ],
    [60, 114]
)

sub_title(pdf, "Sources de données - Portails publics")
table(pdf,
    ["Source", "Portail", "API / Accès"],
    [
        ["NSF Awards", "nsf.gov/awardsearch", "api.nsf.gov"],
        ["NIH Reporter", "reporter.nih.gov", "api.reporter.nih.gov"],
        ["CORDIS", "cordis.europa.eu", "cordis.europa.eu/api"],
        ["UKRI Gateway", "gtr.ukri.org", "gtr.ukri.org/gtr/api"],
        ["TED Tenders", "ted.europa.eu", "api.ted.europa.eu"],
        ["NSERC", "nserc-crsng.gc.ca", "CSV annuels publics"],
        ["CIHR", "open.canada.ca", "open.canada.ca/data/api"],
        ["ERC Dashboard", "erc.europa.eu/projects-statistics", "Export manuel Excel"],
    ],
    [30, 80, 64]
)

# ── FINAL NOTE ──
pdf.ln(10)
pdf.set_draw_color(220, 220, 220)
pdf.line(18, pdf.get_y(), 192, pdf.get_y())
pdf.ln(5)
pdf.set_font("Helvetica", "I", 9)
pdf.set_text_color(180, 180, 180)
pdf.cell(0, 5, "Document confidentiel - Amplitude Laser c 2026 - Tous droits reserves", align="C")

# ── SAVE ──
out = "U:/APP/manuel_utilisation.pdf"
pdf.output(out)
print(f"PDF genere : {out}")
print(f"Pages : {pdf.page}")


