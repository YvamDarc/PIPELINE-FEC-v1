import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

from utils.fec_utils import (
    charger_plusieurs_fec,
    calculer_solde_journalier,
    exporter_excel
)


st.title("Ajout de données externes au tableau principal")


# --------------------------------------------------
# Fonctions robustes
# --------------------------------------------------

def lire_tableau_externe_robuste(uploaded_file):
    """
    Lecture robuste CSV / Excel.
    Pour les CSV, on laisse pandas détecter le séparateur.
    """
    nom = uploaded_file.name.lower()

    if nom.endswith(".xlsx") or nom.endswith(".xls"):
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, dtype=str)

    if nom.endswith(".csv"):
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(
                uploaded_file,
                sep=None,
                engine="python",
                dtype=str,
                encoding="utf-8"
            )
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            df = pd.read_csv(
                uploaded_file,
                sep=None,
                engine="python",
                dtype=str,
                encoding="latin1"
            )

        df.columns = df.columns.astype(str).str.strip()
        return df

    raise ValueError("Format non pris en charge. Utilise CSV, XLS ou XLSX.")


def convertir_numerique_possible(serie):
    return pd.to_numeric(
        serie
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace("\u202f", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce"
    )


def parser_date_robuste(serie, format_choisi="Auto"):
    """
    Convertit une série en date de manière robuste.

    Gère notamment :
    - 01/01/2022
    - 2022-01-01
    - 20220101
    - 01-01-2022
    - datetime déjà reconnu
    - dates Excel numériques
    """

    # Si la colonne est déjà datetime
    if pd.api.types.is_datetime64_any_dtype(serie):
        return pd.to_datetime(serie, errors="coerce").dt.normalize()

    s = serie.copy()

    # On garde une version texte nettoyée
    s_txt = (
        s
        .astype(str)
        .str.strip()
        .str.replace("\u202f", "", regex=False)
        .str.replace("\xa0", "", regex=False)
    )

    # Supprimer les heures si elles existent : 2022-01-01 00:00:00
    s_txt = s_txt.str.replace(r"\s+00:00:00$", "", regex=True)

    # Résultat vide au départ
    resultat = pd.Series(pd.NaT, index=s_txt.index, dtype="datetime64[ns]")

    formats = {
        "JJ/MM/AAAA : 01/01/2022": "%d/%m/%Y",
        "AAAA-MM-JJ : 2022-01-01": "%Y-%m-%d",
        "AAAAMMJJ : 20220101": "%Y%m%d",
        "JJ-MM-AAAA : 01-01-2022": "%d-%m-%Y",
        "MM/JJ/AAAA : 01/31/2022": "%m/%d/%Y",
    }

    if format_choisi != "Auto":
        fmt = formats[format_choisi]
        return pd.to_datetime(
            s_txt,
            format=fmt,
            errors="coerce"
        ).dt.normalize()

    # Auto robuste : on essaye plusieurs formats dans le bon ordre
    formats_a_tester = [
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%Y%m%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%d/%m/%y",
        "%Y/%m/%d",
    ]

    for fmt in formats_a_tester:
        masque_vide = resultat.isna()
        if masque_vide.sum() == 0:
            break

        tentative = pd.to_datetime(
            s_txt[masque_vide],
            format=fmt,
            errors="coerce"
        )

        resultat.loc[masque_vide] = tentative

    # Dernière tentative pandas avec dayfirst=True
    masque_vide = resultat.isna()

    if masque_vide.sum() > 0:
        tentative = pd.to_datetime(
            s_txt[masque_vide],
            errors="coerce",
            dayfirst=True
        )

        resultat.loc[masque_vide] = tentative

    # Gestion des dates Excel numériques éventuelles
    masque_vide = resultat.isna()

    if masque_vide.sum() > 0:
        s_num = pd.to_numeric(s_txt[masque_vide], errors="coerce")

        masque_excel = s_num.between(20000, 80000)

        if masque_excel.sum() > 0:
            dates_excel = pd.to_datetime(
                s_num[masque_excel],
                unit="D",
                origin="1899-12-30",
                errors="coerce"
            )

            resultat.loc[dates_excel.index] = dates_excel

    return pd.to_datetime(resultat, errors="coerce").dt.normalize()


def detecter_colonnes_dates(df):
    return [
        col for col in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[col])
    ]


def detecter_colonnes_numeriques(df):
    colonnes = []

    for col in df.columns:
        serie_num = convertir_numerique_possible(df[col])

        if serie_num.notna().sum() > 0:
            colonnes.append(col)

    return colonnes


def agreger_externe_par_cle(df, cle="_cle_merge"):
    """
    Agrège le tableau externe pour avoir une seule ligne par date / clé.

    - colonnes numériques : somme
    - colonnes texte : première valeur non vide
    """
    df = df.copy()

    colonnes = [col for col in df.columns if col != cle]

    agg = {}

    for col in colonnes:
        serie_num = convertir_numerique_possible(df[col])
        nb_num = serie_num.notna().sum()
        nb_total = df[col].notna().sum()

        if nb_total > 0 and nb_num / nb_total >= 0.8:
            df[col] = serie_num
            agg[col] = "sum"
        else:
            agg[col] = "first"

    return (
        df
        .groupby(cle, as_index=False)
        .agg(agg)
    )


def exporter_excel_local(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Fusion")

    return output.getvalue()


def preparer_export(df):
    df_export = df.copy()

    for col in df_export.columns:
        if pd.api.types.is_datetime64_any_dtype(df_export[col]):
            df_export[col] = df_export[col].dt.strftime("%d/%m/%Y")

    return df_export


# --------------------------------------------------
# 1. Source du tableau principal
# --------------------------------------------------

st.header("1. Tableau principal")

st.write("""
Le tableau principal est celui que l'on veut conserver.
Le tableau externe va seulement ajouter des colonnes dessus.

Dans ton cas, le tableau principal est généralement le solde journalier généré en page 1.
""")

sources = []

if "df_solde_journalier" in st.session_state:
    sources.append("Utiliser le solde journalier généré en page 1")

sources.append("Importer de nouveaux FEC et recalculer un solde journalier")

source = st.radio(
    "Source du tableau principal",
    sources
)


if source == "Utiliser le solde journalier généré en page 1":

    df_principal = st.session_state["df_solde_journalier"].copy()

    st.success("Tableau principal récupéré depuis la page 1.")

else:

    uploaded_files = st.file_uploader(
        "Importer jusqu'à 6 fichiers FEC",
        type=["txt", "csv"],
        accept_multiple_files=True,
        key="fec_files_page_2"
    )

    if not uploaded_files:
        st.info("Importe un ou plusieurs FEC.")
        st.stop()

    try:
        df_fec = charger_plusieurs_fec(uploaded_files, max_files=6)
    except Exception as e:
        st.error(e)
        st.stop()

    st.success(f"{len(uploaded_files)} FEC chargé(s).")

    col1, col2, col3 = st.columns(3)

    with col1:
        compte_debut = st.text_input(
            "Compte de début",
            value="7000000"
        ).strip()

    with col2:
        compte_fin = st.text_input(
            "Compte de fin",
            value="70999999"
        ).strip()

    with col3:
        sens = st.selectbox(
            "Sens du solde",
            ["Débit - Crédit", "Crédit - Débit"]
        )

    resultat_fec, df_filtre = calculer_solde_journalier(
        df=df_fec,
        compte_debut=compte_debut,
        compte_fin=compte_fin,
        sens=sens
    )

    if resultat_fec is None:
        st.warning("Aucune écriture trouvée sur cette plage de comptes.")
        st.stop()

    df_principal = resultat_fec[["Date", "SoldeJournalier"]].copy()

    st.session_state["df_solde_journalier_page_2"] = df_principal.copy()


st.subheader("Aperçu du tableau principal")

st.write(f"Lignes du tableau principal : **{len(df_principal)}**")

st.dataframe(
    df_principal.head(50),
    use_container_width=True
)


# --------------------------------------------------
# 2. Tableau externe
# --------------------------------------------------

st.header("2. Tableau externe à ajouter")

fichier_externe = st.file_uploader(
    "Importer un fichier externe CSV / Excel",
    type=["csv", "xlsx", "xls"],
    key="tableau_externe_page_2"
)

if not fichier_externe:
    st.info("Importe le tableau externe à ajouter.")
    st.stop()

try:
    df_externe = lire_tableau_externe_robuste(fichier_externe)
except Exception as e:
    st.error(f"Erreur lecture tableau externe : {e}")
    st.stop()

st.success("Tableau externe chargé.")

st.write(f"Lignes du tableau externe : **{len(df_externe)}**")

st.dataframe(
    df_externe.head(50),
    use_container_width=True
)


# --------------------------------------------------
# 3. Choix des colonnes de correspondance
# --------------------------------------------------

st.header("3. Colonnes de correspondance")

colonnes_principal = list(df_principal.columns)
colonnes_externe = list(df_externe.columns)

col1, col2 = st.columns(2)

with col1:
    colonne_principal = st.selectbox(
        "Colonne date côté tableau principal",
        colonnes_principal,
        index=colonnes_principal.index("Date") if "Date" in colonnes_principal else 0
    )

with col2:
    colonne_externe = st.selectbox(
        "Colonne date côté tableau externe",
        colonnes_externe,
        index=colonnes_externe.index("date") if "date" in colonnes_externe else 0
    )


formats_date = [
    "Auto",
    "JJ/MM/AAAA : 01/01/2022",
    "AAAA-MM-JJ : 2022-01-01",
    "AAAAMMJJ : 20220101",
    "JJ-MM-AAAA : 01-01-2022",
    "MM/JJ/AAAA : 01/31/2022",
]

st.subheader("Format des dates")

col_fmt1, col_fmt2 = st.columns(2)

with col_fmt1:
    format_principal = st.selectbox(
        "Format côté principal",
        formats_date,
        index=formats_date.index("JJ/MM/AAAA : 01/01/2022")
        if df_principal[colonne_principal].dtype == "object"
        else 0
    )

with col_fmt2:
    format_externe = st.selectbox(
        "Format côté externe",
        formats_date,
        index=formats_date.index("AAAA-MM-JJ : 2022-01-01")
        if df_externe[colonne_externe].astype(str).str.contains("-", regex=False).any()
        else 0
    )


# --------------------------------------------------
# 4. Création des clés de fusion
# --------------------------------------------------

df_principal_merge = df_principal.copy()
df_externe_merge = df_externe.copy()

df_principal_merge["_cle_merge"] = parser_date_robuste(
    df_principal_merge[colonne_principal],
    format_choisi=format_principal
)

df_externe_merge["_cle_merge"] = parser_date_robuste(
    df_externe_merge[colonne_externe],
    format_choisi=format_externe
)


st.header("4. Contrôle des dates reconnues")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric(
        "Dates principal reconnues",
        df_principal_merge["_cle_merge"].notna().sum()
    )

with c2:
    st.metric(
        "Dates externe reconnues",
        df_externe_merge["_cle_merge"].notna().sum()
    )

cles_principal = set(df_principal_merge["_cle_merge"].dropna())
cles_externe = set(df_externe_merge["_cle_merge"].dropna())
cles_communes = cles_principal & cles_externe

with c3:
    st.metric("Dates communes", len(cles_communes))

with c4:
    taux = 0

    if len(cles_principal) > 0:
        taux = len(cles_communes) / len(cles_principal) * 100

    st.metric("Taux de match principal", f"{taux:.1f} %")


st.subheader("Aperçu des clés générées")

col_ctrl1, col_ctrl2 = st.columns(2)

with col_ctrl1:
    st.write("Principal")
    st.dataframe(
        df_principal_merge[[colonne_principal, "_cle_merge"]].head(40),
        use_container_width=True
    )

with col_ctrl2:
    st.write("Externe")
    st.dataframe(
        df_externe_merge[[colonne_externe, "_cle_merge"]].head(40),
        use_container_width=True
    )


with st.expander("Voir les lignes principales sans date reconnue"):
    st.dataframe(
        df_principal_merge[df_principal_merge["_cle_merge"].isna()].head(200),
        use_container_width=True
    )

with st.expander("Voir les lignes externes sans date reconnue"):
    st.dataframe(
        df_externe_merge[df_externe_merge["_cle_merge"].isna()].head(200),
        use_container_width=True
    )


if df_principal_merge["_cle_merge"].notna().sum() == 0:
    st.error(
        "Aucune date reconnue côté principal. "
        "Essaie de changer le format côté principal, par exemple JJ/MM/AAAA."
    )
    st.stop()

if df_externe_merge["_cle_merge"].notna().sum() == 0:
    st.error(
        "Aucune date reconnue côté externe. "
        "Essaie de changer le format côté externe, par exemple AAAA-MM-JJ."
    )
    st.stop()


# --------------------------------------------------
# 5. Colonnes externes à ajouter
# --------------------------------------------------

st.header("5. Colonnes externes à ajouter")

colonnes_externes_ajoutables = [
    col for col in df_externe_merge.columns
    if col not in [colonne_externe, "_cle_merge"]
]

colonnes_a_ajouter = st.multiselect(
    "Colonnes du tableau externe à ajouter",
    colonnes_externes_ajoutables,
    default=colonnes_externes_ajoutables
)

if not colonnes_a_ajouter:
    st.warning("Sélectionne au moins une colonne externe à ajouter.")
    st.stop()

df_externe_merge = df_externe_merge[
    ["_cle_merge"] + colonnes_a_ajouter
].copy()


# --------------------------------------------------
# 6. Gestion des doublons côté externe
# --------------------------------------------------

st.header("6. Doublons côté tableau externe")

nb_doublons = df_externe_merge.duplicated(subset=["_cle_merge"]).sum()

st.write(f"Doublons de date côté externe : **{nb_doublons}**")

agreger = st.checkbox(
    "Agréger le tableau externe par date avant fusion",
    value=True,
    help="Recommandé pour éviter de dupliquer les lignes du tableau principal."
)

if agreger:
    df_externe_pour_merge = agreger_externe_par_cle(
        df_externe_merge,
        cle="_cle_merge"
    )
else:
    df_externe_pour_merge = df_externe_merge.copy()

st.write(f"Lignes externes utilisées pour la fusion : **{len(df_externe_pour_merge)}**")


# --------------------------------------------------
# 7. Fusion LEFT propre
# --------------------------------------------------

st.header("7. Fusion")

st.write("""
La fusion est faite en **LEFT JOIN**.

Cela signifie :
- toutes les lignes du tableau principal sont conservées ;
- les colonnes externes sont ajoutées quand une date correspond ;
- les dates sans correspondance externe restent présentes avec des valeurs vides.
""")

df_merge = df_principal_merge.merge(
    df_externe_pour_merge,
    on="_cle_merge",
    how="left"
)

df_merge["Date_Merge"] = df_merge["_cle_merge"]

df_merge = df_merge.drop(columns=["_cle_merge"])

st.success("Fusion effectuée en LEFT JOIN.")

st.write(f"Lignes avant fusion : **{len(df_principal)}**")
st.write(f"Lignes après fusion : **{len(df_merge)}**")

if len(df_merge) != len(df_principal):
    st.warning(
        "Attention : le nombre de lignes a changé. "
        "Cela peut arriver si le tableau externe contient plusieurs lignes par date "
        "et que l'agrégation n'est pas activée."
    )

st.dataframe(
    df_merge,
    use_container_width=True
)


# --------------------------------------------------
# 8. Contrôle des lignes non matchées
# --------------------------------------------------

st.header("8. Contrôle des correspondances")

colonnes_externes_resultat = [
    col for col in colonnes_a_ajouter
    if col in df_merge.columns
]

if colonnes_externes_resultat:
    masque_aucune_donnee_externe = df_merge[colonnes_externes_resultat].isna().all(axis=1)

    st.write(
        f"Lignes du principal sans donnée externe ajoutée : "
        f"**{masque_aucune_donnee_externe.sum()}**"
    )

    with st.expander("Voir les lignes sans correspondance externe"):
        st.dataframe(
            df_merge[masque_aucune_donnee_externe].head(300),
            use_container_width=True
        )


# --------------------------------------------------
# 9. Filtre date
# --------------------------------------------------

st.header("9. Filtre de date")

df_filtre = df_merge.copy()

date_min = df_filtre["Date_Merge"].min()
date_max = df_filtre["Date_Merge"].max()

if pd.notna(date_min) and pd.notna(date_max):

    col_date1, col_date2 = st.columns(2)

    with col_date1:
        date_debut = st.date_input(
            "Date début",
            value=date_min.date()
        )

    with col_date2:
        date_fin = st.date_input(
            "Date fin",
            value=date_max.date()
        )

    date_debut = pd.to_datetime(date_debut)
    date_fin = pd.to_datetime(date_fin)

    df_filtre = df_filtre[
        (df_filtre["Date_Merge"] >= date_debut)
        & (df_filtre["Date_Merge"] <= date_fin)
    ].copy()

st.write(f"Lignes après filtre : **{len(df_filtre)}**")

st.dataframe(
    df_filtre,
    use_container_width=True
)


# --------------------------------------------------
# 10. Stockage pour page 3
# --------------------------------------------------

st.session_state["df_merge"] = df_filtre.copy()

st.success("Tableau fusionné stocké pour la page 3.")


# --------------------------------------------------
# 11. Graphiques
# --------------------------------------------------

st.header("10. Graphiques")

colonnes_numeriques = detecter_colonnes_numeriques(df_filtre)

if colonnes_numeriques:

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        colonne_y = st.selectbox(
            "Colonne numérique à afficher",
            colonnes_numeriques,
            index=colonnes_numeriques.index("SoldeJournalier")
            if "SoldeJournalier" in colonnes_numeriques
            else 0
        )

    with col_g2:
        type_graph = st.selectbox(
            "Type de graphique",
            ["Courbe journalière", "Barres mensuelles"]
        )

    df_graph = df_filtre.copy()
    df_graph["_valeur_graph"] = convertir_numerique_possible(df_graph[colonne_y])

    if type_graph == "Courbe journalière":
        fig = px.line(
            df_graph,
            x="Date_Merge",
            y="_valeur_graph",
            title=f"{colonne_y} par jour"
        )

        fig.update_xaxes(rangeslider_visible=True)

    else:
        df_graph["_Mois"] = df_graph["Date_Merge"].dt.to_period("M").astype(str)

        df_mois = (
            df_graph
            .groupby("_Mois", as_index=False)["_valeur_graph"]
            .sum()
        )

        fig = px.bar(
            df_mois,
            x="_Mois",
            y="_valeur_graph",
            title=f"{colonne_y} par mois"
        )

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title=colonne_y,
        hovermode="x unified"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

else:
    st.info("Aucune colonne numérique détectée pour les graphiques.")


# --------------------------------------------------
# 12. Exports
# --------------------------------------------------

st.header("11. Exports")

df_export = preparer_export(df_filtre)

csv = df_export.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="Télécharger en CSV",
    data=csv,
    file_name="tableau_principal_avec_donnees_externes.csv",
    mime="text/csv"
)

excel = exporter_excel_local(df_export)

st.download_button(
    label="Télécharger en Excel",
    data=excel,
    file_name="tableau_principal_avec_donnees_externes.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
