import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO

try:
    import holidays
except ImportError:
    holidays = None

from utils.file_utils import lire_fichier_externe


st.title("Data Engineering avancé sur série temporelle")


# --------------------------------------------------
# Fonctions locales
# --------------------------------------------------

def exporter_excel(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data engineering")

    return output.getvalue()


def texte_vers_liste_entiers(texte):
    if not texte:
        return []

    valeurs = []

    for element in texte.split(","):
        element = element.strip()

        if element:
            try:
                valeurs.append(int(element))
            except ValueError:
                pass

    return sorted(list(set(valeurs)))


def convertir_numerique(serie):
    return pd.to_numeric(
        serie
        .fillna("")
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace("\u202f", "", regex=False)
        .str.replace("\xa0", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce"
    )


def parser_date_robuste(serie, format_choisi="Auto"):
    """
    Conversion robuste des dates.

    Gère :
    - 01/01/2022
    - 2022-01-01
    - 20220101
    - 01-01-2022
    - dates déjà datetime
    - dates Excel numériques
    """

    if pd.api.types.is_datetime64_any_dtype(serie):
        return pd.to_datetime(serie, errors="coerce").dt.normalize()

    s_txt = (
        serie
        .astype(str)
        .str.strip()
        .str.replace("\u202f", "", regex=False)
        .str.replace("\xa0", "", regex=False)
    )

    s_txt = s_txt.str.replace(r"\s+00:00:00$", "", regex=True)

    formats = {
        "Auto": None,
        "JJ/MM/AAAA : 01/01/2022": "%d/%m/%Y",
        "AAAA-MM-JJ : 2022-01-01": "%Y-%m-%d",
        "AAAAMMJJ : 20220101": "%Y%m%d",
        "JJ-MM-AAAA : 01-01-2022": "%d-%m-%Y",
        "MM/JJ/AAAA : 01/31/2022": "%m/%d/%Y",
    }

    if format_choisi != "Auto":
        return pd.to_datetime(
            s_txt,
            format=formats[format_choisi],
            errors="coerce"
        ).dt.normalize()

    resultat = pd.Series(pd.NaT, index=s_txt.index, dtype="datetime64[ns]")

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
        masque = resultat.isna()

        if masque.sum() == 0:
            break

        tentative = pd.to_datetime(
            s_txt[masque],
            format=fmt,
            errors="coerce"
        )

        resultat.loc[masque] = tentative

    masque = resultat.isna()

    if masque.sum() > 0:
        tentative = pd.to_datetime(
            s_txt[masque],
            errors="coerce",
            dayfirst=True
        )

        resultat.loc[masque] = tentative

    masque = resultat.isna()

    if masque.sum() > 0:
        s_num = pd.to_numeric(s_txt[masque], errors="coerce")
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


def detecter_colonnes_numeriques(df):
    colonnes = []

    for col in df.columns:
        serie_num = convertir_numerique(df[col])

        if serie_num.notna().sum() > 0:
            colonnes.append(col)

    return colonnes


def detecter_colonnes_dates_probables(df):
    colonnes = list(df.columns)

    colonnes_datetime = [
        col for col in colonnes
        if pd.api.types.is_datetime64_any_dtype(df[col])
    ]

    colonnes_nom = [
        col for col in colonnes
        if any(mot in col.lower() for mot in ["date", "jour", "periode", "période"])
        and col not in colonnes_datetime
    ]

    autres = [
        col for col in colonnes
        if col not in colonnes_datetime
        and col not in colonnes_nom
    ]

    return colonnes_datetime + colonnes_nom + autres


def completer_dates_manquantes(df, colonne_date, colonnes_valeurs):
    """
    Complète les dates manquantes entre min et max.
    Les colonnes numériques sélectionnées sont mises à 0.
    Les autres colonnes restent vides.
    """
    df = df.copy()

    date_min = df[colonne_date].min()
    date_max = df[colonne_date].max()

    calendrier = pd.DataFrame({
        colonne_date: pd.date_range(date_min, date_max, freq="D")
    })

    df = calendrier.merge(
        df,
        on=colonne_date,
        how="left"
    )

    for col in colonnes_valeurs:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    return df


def ajouter_variables_calendaires(df, colonne_date):
    df = df.copy()

    df["Annee"] = df[colonne_date].dt.year
    df["Mois"] = df[colonne_date].dt.month
    df["Jour"] = df[colonne_date].dt.day
    df["JourSemaine_Num"] = df[colonne_date].dt.weekday
    df["Semaine_ISO"] = df[colonne_date].dt.isocalendar().week.astype("Int64")
    df["Trimestre"] = df[colonne_date].dt.quarter
    df["JourAnnee"] = df[colonne_date].dt.dayofyear

    noms_jours = {
        0: "Lundi",
        1: "Mardi",
        2: "Mercredi",
        3: "Jeudi",
        4: "Vendredi",
        5: "Samedi",
        6: "Dimanche",
    }

    df["JourSemaine_Nom"] = df["JourSemaine_Num"].map(noms_jours)

    df["Est_Weekend"] = df["JourSemaine_Num"].isin([5, 6]).astype(int)
    df["Debut_Mois"] = df[colonne_date].dt.is_month_start.astype(int)
    df["Fin_Mois"] = df[colonne_date].dt.is_month_end.astype(int)
    df["Debut_Trimestre"] = df[colonne_date].dt.is_quarter_start.astype(int)
    df["Fin_Trimestre"] = df[colonne_date].dt.is_quarter_end.astype(int)
    df["Debut_Annee"] = df[colonne_date].dt.is_year_start.astype(int)
    df["Fin_Annee"] = df[colonne_date].dt.is_year_end.astype(int)

    return df


def ajouter_jours_feries_france(df, colonne_date):
    df = df.copy()

    if holidays is None:
        df["Est_Jour_Ferie"] = 0
        df["Nom_Jour_Ferie"] = ""
        return df

    annees = sorted(df[colonne_date].dt.year.dropna().unique())

    jours_feries = holidays.France(years=annees)

    df["Est_Jour_Ferie"] = df[colonne_date].dt.date.isin(jours_feries).astype(int)
    df["Nom_Jour_Ferie"] = df[colonne_date].dt.date.map(
        lambda x: jours_feries.get(x, "")
    )

    return df


def ajouter_lags(df, colonne_valeur, lags):
    df = df.copy()

    for lag in lags:
        df[f"{colonne_valeur}_Lag_{lag}j"] = df[colonne_valeur].shift(lag)

    return df


def ajouter_moyennes_mobiles(df, colonne_valeur, fenetres):
    df = df.copy()

    for fenetre in fenetres:
        df[f"{colonne_valeur}_MoyenneMobile_{fenetre}j"] = (
            df[colonne_valeur]
            .rolling(window=fenetre, min_periods=1)
            .mean()
        )

    return df


def ajouter_sommes_mobiles(df, colonne_valeur, fenetres):
    df = df.copy()

    for fenetre in fenetres:
        df[f"{colonne_valeur}_SommeMobile_{fenetre}j"] = (
            df[colonne_valeur]
            .rolling(window=fenetre, min_periods=1)
            .sum()
        )

    return df


def ajouter_ecarts(df, colonne_valeur, lags):
    df = df.copy()

    for lag in lags:
        col_lag = f"{colonne_valeur}_Lag_{lag}j"

        if col_lag not in df.columns:
            df[col_lag] = df[colonne_valeur].shift(lag)

        df[f"{colonne_valeur}_Ecart_{lag}j"] = (
            df[colonne_valeur] - df[col_lag]
        )

    return df


def ajouter_variations_pourcentage(df, colonne_valeur, lags):
    df = df.copy()

    for lag in lags:
        col_lag = f"{colonne_valeur}_Lag_{lag}j"

        if col_lag not in df.columns:
            df[col_lag] = df[colonne_valeur].shift(lag)

        df[f"{colonne_valeur}_Variation_{lag}j_%"] = (
            (df[colonne_valeur] - df[col_lag])
            / df[col_lag].replace(0, np.nan)
        ) * 100

    return df


def ajouter_cumuls(df, colonne_date, colonne_valeur):
    df = df.copy()

    df["_Annee_Temp"] = df[colonne_date].dt.year
    df["_Mois_Temp"] = df[colonne_date].dt.to_period("M")

    df[f"{colonne_valeur}_Cumul_Mensuel"] = (
        df.groupby("_Mois_Temp")[colonne_valeur].cumsum()
    )

    df[f"{colonne_valeur}_Cumul_Annuel"] = (
        df.groupby("_Annee_Temp")[colonne_valeur].cumsum()
    )

    df = df.drop(columns=["_Annee_Temp", "_Mois_Temp"])

    return df


def ajouter_indicateurs_zero(df, colonne_valeur):
    df = df.copy()

    df[f"{colonne_valeur}_Est_Zero"] = (df[colonne_valeur] == 0).astype(int)
    df[f"{colonne_valeur}_Est_Positif"] = (df[colonne_valeur] > 0).astype(int)
    df[f"{colonne_valeur}_Est_Negatif"] = (df[colonne_valeur] < 0).astype(int)

    return df


def ajouter_valeur_absolue(df, colonne_valeur):
    df = df.copy()

    df[f"{colonne_valeur}_Abs"] = df[colonne_valeur].abs()

    return df


def preparer_export(df):
    df_export = df.copy()

    for col in df_export.columns:
        if pd.api.types.is_datetime64_any_dtype(df_export[col]):
            df_export[col] = df_export[col].dt.strftime("%d/%m/%Y")

    return df_export


# --------------------------------------------------
# 1. Choix de la source
# --------------------------------------------------

st.header("1. Choix de la source de données")

sources = []

if "df_solde_journalier" in st.session_state:
    sources.append("Solde journalier généré en page 1")

if "df_merge" in st.session_state:
    sources.append("Tableau fusionné généré en page 2")

sources.append("Importer un nouveau fichier CSV / Excel")

source = st.radio(
    "Source du tableau à enrichir",
    sources
)

if source == "Solde journalier généré en page 1":

    df_original = st.session_state["df_solde_journalier"].copy()
    st.success("Solde journalier récupéré depuis la page 1.")

elif source == "Tableau fusionné généré en page 2":

    df_original = st.session_state["df_merge"].copy()
    st.success("Tableau fusionné récupéré depuis la page 2.")

else:

    fichier = st.file_uploader(
        "Importer un fichier CSV ou Excel",
        type=["csv", "xlsx", "xls"],
        key="data_engineering_import"
    )

    if not fichier:
        st.info("Importe un fichier pour commencer.")
        st.stop()

    try:
        df_original = lire_fichier_externe(fichier)
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier : {e}")
        st.stop()

    st.success("Fichier chargé.")


st.subheader("Aperçu du tableau source")

st.write(f"Lignes : **{len(df_original)}**")
st.write(f"Colonnes : **{len(df_original.columns)}**")

st.dataframe(
    df_original.head(50),
    use_container_width=True
)


# --------------------------------------------------
# 2. Sélection date et valeur
# --------------------------------------------------

st.header("2. Sélection de la date et des valeurs")

colonnes = list(df_original.columns)

colonnes_dates_ordre = detecter_colonnes_dates_probables(df_original)
colonnes_numeriques = detecter_colonnes_numeriques(df_original)

if not colonnes_numeriques:
    st.warning("Aucune colonne numérique détectée.")
    st.stop()

formats_date = [
    "Auto",
    "JJ/MM/AAAA : 01/01/2022",
    "AAAA-MM-JJ : 2022-01-01",
    "AAAAMMJJ : 20220101",
    "JJ-MM-AAAA : 01-01-2022",
    "MM/JJ/AAAA : 01/31/2022",
]

col1, col2, col3 = st.columns(3)

with col1:
    colonne_date_source = st.selectbox(
        "Colonne date source",
        colonnes_dates_ordre,
        index=0
    )

with col2:
    format_date = st.selectbox(
        "Format de date",
        formats_date,
        index=0
    )

with col3:
    nom_colonne_date = st.text_input(
        "Nom de la colonne date convertie",
        value="Date_DE"
    )


colonnes_valeurs = st.multiselect(
    "Colonnes numériques à enrichir",
    colonnes_numeriques,
    default=["SoldeJournalier"] if "SoldeJournalier" in colonnes_numeriques else colonnes_numeriques[:1]
)

if not colonnes_valeurs:
    st.warning("Sélectionne au moins une colonne numérique.")
    st.stop()


# --------------------------------------------------
# 3. Préparation des données
# --------------------------------------------------

st.header("3. Préparation des données")

df = df_original.copy()

df[nom_colonne_date] = parser_date_robuste(
    df[colonne_date_source],
    format_choisi=format_date
)

for col in colonnes_valeurs:
    df[col] = convertir_numerique(df[col])

dates_reconnues = df[nom_colonne_date].notna().sum()
dates_non_reconnues = df[nom_colonne_date].isna().sum()

c1, c2, c3 = st.columns(3)

with c1:
    st.metric("Dates reconnues", dates_reconnues)

with c2:
    st.metric("Dates non reconnues", dates_non_reconnues)

with c3:
    st.metric("Lignes avant préparation", len(df))

with st.expander("Voir les lignes avec date non reconnue"):
    st.dataframe(
        df[df[nom_colonne_date].isna()].head(200),
        use_container_width=True
    )


# Suppression uniquement si demandé explicitement.
supprimer_dates_vides = st.checkbox(
    "Supprimer les lignes sans date reconnue",
    value=True
)

if supprimer_dates_vides:
    df = df.dropna(subset=[nom_colonne_date]).copy()


# Regroupement optionnel
regrouper_par_date = st.checkbox(
    "Regrouper par date avant enrichissement",
    value=False,
    help="À utiliser si plusieurs lignes existent pour un même jour. Les valeurs numériques sélectionnées seront additionnées."
)

if regrouper_par_date:
    autres_colonnes = [
        col for col in df.columns
        if col not in colonnes_valeurs + [nom_colonne_date]
    ]

    agg_dict = {col: "sum" for col in colonnes_valeurs}
    agg_dict.update({col: "first" for col in autres_colonnes})

    df = (
        df
        .groupby(nom_colonne_date, as_index=False)
        .agg(agg_dict)
    )


# Complétion optionnelle
completer_jours = st.checkbox(
    "Compléter les jours manquants entre la date min et max",
    value=False,
    help="Les colonnes numériques sélectionnées seront mises à 0 sur les jours absents."
)

if completer_jours:
    df = completer_dates_manquantes(
        df=df,
        colonne_date=nom_colonne_date,
        colonnes_valeurs=colonnes_valeurs
    )


df = df.sort_values(nom_colonne_date).reset_index(drop=True)

st.success("Données préparées.")

c1, c2, c3 = st.columns(3)

with c1:
    st.metric("Lignes après préparation", len(df))

with c2:
    st.metric("Date début", df[nom_colonne_date].min().strftime("%d/%m/%Y"))

with c3:
    st.metric("Date fin", df[nom_colonne_date].max().strftime("%d/%m/%Y"))

st.dataframe(
    df.head(100),
    use_container_width=True
)


# --------------------------------------------------
# 4. Choix des transformations
# --------------------------------------------------

st.header("4. Transformations à générer")

col_transfo1, col_transfo2 = st.columns(2)

with col_transfo1:
    generer_calendrier = st.checkbox("Variables calendaires", value=True)
    generer_jours_feries = st.checkbox("Jours fériés France", value=True)
    generer_zero = st.checkbox("Indicateurs zéro / positif / négatif", value=True)
    generer_abs = st.checkbox("Valeur absolue", value=False)
    generer_cumuls = st.checkbox("Cumuls mensuel et annuel", value=True)

with col_transfo2:
    generer_lags = st.checkbox("Lags", value=True)
    generer_moyennes = st.checkbox("Moyennes mobiles", value=True)
    generer_sommes_mobiles = st.checkbox("Sommes mobiles", value=False)
    generer_ecarts = st.checkbox("Écarts", value=True)
    generer_variations = st.checkbox("Variations en %", value=False)


st.subheader("Paramètres des fenêtres")

col_param1, col_param2, col_param3 = st.columns(3)

with col_param1:
    lags_txt = st.text_input(
        "Lags / écarts",
        value="1, 7, 30, 365"
    )

with col_param2:
    moyennes_txt = st.text_input(
        "Moyennes mobiles",
        value="7, 30, 90"
    )

with col_param3:
    sommes_txt = st.text_input(
        "Sommes mobiles",
        value="7, 30"
    )

lags = texte_vers_liste_entiers(lags_txt)
fenetres_moyennes = texte_vers_liste_entiers(moyennes_txt)
fenetres_sommes = texte_vers_liste_entiers(sommes_txt)


# --------------------------------------------------
# 5. Application des transformations
# --------------------------------------------------

st.header("5. Résultat enrichi")

df_enrichi = df.copy()

if generer_calendrier:
    df_enrichi = ajouter_variables_calendaires(
        df_enrichi,
        colonne_date=nom_colonne_date
    )

if generer_jours_feries:
    df_enrichi = ajouter_jours_feries_france(
        df_enrichi,
        colonne_date=nom_colonne_date
    )

for col_valeur in colonnes_valeurs:

    if generer_zero:
        df_enrichi = ajouter_indicateurs_zero(
            df_enrichi,
            colonne_valeur=col_valeur
        )

    if generer_abs:
        df_enrichi = ajouter_valeur_absolue(
            df_enrichi,
            colonne_valeur=col_valeur
        )

    if generer_lags and lags:
        df_enrichi = ajouter_lags(
            df_enrichi,
            colonne_valeur=col_valeur,
            lags=lags
        )

    if generer_moyennes and fenetres_moyennes:
        df_enrichi = ajouter_moyennes_mobiles(
            df_enrichi,
            colonne_valeur=col_valeur,
            fenetres=fenetres_moyennes
        )

    if generer_sommes_mobiles and fenetres_sommes:
        df_enrichi = ajouter_sommes_mobiles(
            df_enrichi,
            colonne_valeur=col_valeur,
            fenetres=fenetres_sommes
        )

    if generer_ecarts and lags:
        df_enrichi = ajouter_ecarts(
            df_enrichi,
            colonne_valeur=col_valeur,
            lags=lags
        )

    if generer_variations and lags:
        df_enrichi = ajouter_variations_pourcentage(
            df_enrichi,
            colonne_valeur=col_valeur,
            lags=lags
        )

    if generer_cumuls:
        df_enrichi = ajouter_cumuls(
            df_enrichi,
            colonne_date=nom_colonne_date,
            colonne_valeur=col_valeur
        )


st.session_state["df_data_engineering"] = df_enrichi.copy()

st.success("Tableau enrichi généré et stocké en mémoire.")

st.write(f"Nombre de colonnes avant : **{len(df.columns)}**")
st.write(f"Nombre de colonnes après : **{len(df_enrichi.columns)}**")

st.dataframe(
    df_enrichi,
    use_container_width=True
)


# --------------------------------------------------
# 6. Visualisations
# --------------------------------------------------

st.header("6. Visualisations")

colonnes_num_finales = [
    col for col in df_enrichi.columns
    if pd.api.types.is_numeric_dtype(df_enrichi[col])
]

if colonnes_num_finales:

    onglet_ligne, onglet_barres, onglet_corr = st.tabs(
        ["Courbe temporelle", "Barres par période", "Corrélation"]
    )

    with onglet_ligne:
        col1, col2 = st.columns(2)

        with col1:
            y_line = st.selectbox(
                "Variable à afficher",
                colonnes_num_finales,
                index=colonnes_num_finales.index(colonnes_valeurs[0])
                if colonnes_valeurs[0] in colonnes_num_finales
                else 0,
                key="line_y"
            )

        with col2:
            afficher_points = st.checkbox(
                "Afficher les points",
                value=False
            )

        fig = px.line(
            df_enrichi,
            x=nom_colonne_date,
            y=y_line,
            title=f"{y_line} dans le temps",
            markers=afficher_points
        )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title=y_line,
            hovermode="x unified"
        )

        fig.update_xaxes(rangeslider_visible=True)

        st.plotly_chart(fig, use_container_width=True)

    with onglet_barres:
        col1, col2 = st.columns(2)

        with col1:
            y_bar = st.selectbox(
                "Variable à regrouper",
                colonnes_num_finales,
                index=colonnes_num_finales.index(colonnes_valeurs[0])
                if colonnes_valeurs[0] in colonnes_num_finales
                else 0,
                key="bar_y"
            )

        with col2:
            periode = st.selectbox(
                "Période",
                ["Jour", "Mois", "Année"],
                index=1
            )

        df_bar = df_enrichi.copy()

        if periode == "Jour":
            df_bar["_periode"] = df_bar[nom_colonne_date].dt.strftime("%d/%m/%Y")
        elif periode == "Mois":
            df_bar["_periode"] = df_bar[nom_colonne_date].dt.to_period("M").astype(str)
        else:
            df_bar["_periode"] = df_bar[nom_colonne_date].dt.year.astype(str)

        df_bar_group = (
            df_bar
            .groupby("_periode", as_index=False)[y_bar]
            .sum()
        )

        fig_bar = px.bar(
            df_bar_group,
            x="_periode",
            y=y_bar,
            title=f"{y_bar} par {periode.lower()}"
        )

        st.plotly_chart(fig_bar, use_container_width=True)

    with onglet_corr:
        if len(colonnes_num_finales) >= 2:
            col1, col2 = st.columns(2)

            with col1:
                x_corr = st.selectbox(
                    "Variable X",
                    colonnes_num_finales,
                    index=0,
                    key="corr_x"
                )

            with col2:
                y_corr = st.selectbox(
                    "Variable Y",
                    colonnes_num_finales,
                    index=1,
                    key="corr_y"
                )

            df_corr = df_enrichi[[x_corr, y_corr]].dropna()

            if not df_corr.empty:
                correlation = df_corr[x_corr].corr(df_corr[y_corr])

                st.metric("Corrélation", f"{correlation:.4f}")

                fig_corr = px.scatter(
                    df_corr,
                    x=x_corr,
                    y=y_corr,
                    title=f"{y_corr} en fonction de {x_corr}"
                )

                st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.info("Il faut au moins deux colonnes numériques.")

else:
    st.info("Aucune colonne numérique disponible pour les graphiques.")


# --------------------------------------------------
# 7. Contrôles
# --------------------------------------------------

st.header("7. Contrôles")

with st.expander("Liste des colonnes générées"):
    st.dataframe(
        pd.DataFrame({"Colonnes": df_enrichi.columns}),
        use_container_width=True
    )

with st.expander("Lignes avec valeurs manquantes"):
    lignes_na = df_enrichi[df_enrichi.isna().any(axis=1)]

    st.write(f"Lignes avec au moins une valeur manquante : **{len(lignes_na)}**")

    st.dataframe(
        lignes_na.head(200),
        use_container_width=True
    )

with st.expander("Statistiques descriptives"):
    st.dataframe(
        df_enrichi.describe(include="all").transpose(),
        use_container_width=True
    )


# --------------------------------------------------
# 8. Exports
# --------------------------------------------------

st.header("8. Exports")

df_export = preparer_export(df_enrichi)

csv = df_export.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="Télécharger le tableau enrichi en CSV",
    data=csv,
    file_name="tableau_data_engineering.csv",
    mime="text/csv"
)

excel = exporter_excel(df_export)

st.download_button(
    label="Télécharger le tableau enrichi en Excel",
    data=excel,
    file_name="tableau_data_engineering.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
