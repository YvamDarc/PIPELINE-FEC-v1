import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

from utils.file_utils import (
    lire_fichier_externe,
    proposer_formats_date
)

from utils.data_engineering_utils import (
    convertir_colonne_numerique,
    convertir_colonne_date,
    completer_dates_manquantes,
    ajouter_variables_calendaires,
    ajouter_lags,
    ajouter_moyennes_mobiles,
    ajouter_sommes_mobiles,
    ajouter_ecarts,
    ajouter_variations_pourcentage,
    ajouter_cumuls,
    ajouter_jours_feries_france,
    ajouter_indicateurs_zero,
    ajouter_valeurs_absolues
)


st.title("Data Engineering sur série temporelle")

st.write("""
Cette page permet d'enrichir un tableau générique contenant une date et une valeur.

Elle peut être utilisée avec les exports des pages précédentes, par exemple :

- `Date | SoldeJournalier`
- `Date | SoldeJournalier | Nombre de couverts | CA caisse`
- `Date | Montant | Commentaire`
""")


# --------------------------------------------------
# Fonctions locales
# --------------------------------------------------

def exporter_excel(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data engineering")

    return output.getvalue()


def texte_vers_liste_entiers(texte):
    """
    Transforme une saisie du type '1, 7, 30' en liste [1, 7, 30].
    """
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


# --------------------------------------------------
# 1. Import du fichier
# --------------------------------------------------

st.header("1. Import du tableau")

fichier = st.file_uploader(
    "Importer un fichier CSV ou Excel",
    type=["csv", "xlsx", "xls"]
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

st.write("Aperçu du fichier importé :")
st.dataframe(df_original.head(30), use_container_width=True)


# --------------------------------------------------
# 2. Sélection des colonnes
# --------------------------------------------------

st.header("2. Sélection des colonnes principales")

colonnes = list(df_original.columns)

col1, col2 = st.columns(2)

with col1:
    colonne_date = st.selectbox(
        "Colonne date",
        colonnes
    )

with col2:
    colonne_valeur = st.selectbox(
        "Colonne valeur à enrichir",
        colonnes,
        index=1 if len(colonnes) > 1 else 0
    )


# --------------------------------------------------
# 3. Paramétrage date et valeur
# --------------------------------------------------

st.header("3. Paramétrage des formats")

formats = proposer_formats_date()

col_format1, col_format2, col_format3 = st.columns(3)

with col_format1:
    format_date = st.selectbox(
        "Format de la date",
        formats,
        index=0
    )

with col_format2:
    dayfirst = st.checkbox(
        "Dates françaises jour/mois/année",
        value=True
    )

with col_format3:
    completer_jours = st.checkbox(
        "Compléter les dates manquantes",
        value=True
    )

df = df_original.copy()

df[colonne_date] = convertir_colonne_date(
    df[colonne_date],
    format_date=format_date,
    dayfirst=dayfirst
)

df[colonne_valeur] = convertir_colonne_numerique(
    df[colonne_valeur]
)

df = df.dropna(subset=[colonne_date])
df = df.sort_values(colonne_date).reset_index(drop=True)


if completer_jours:
    df = completer_dates_manquantes(
        df=df,
        colonne_date=colonne_date,
        colonne_valeur=colonne_valeur,
        frequence="D"
    )

    df = df.sort_values(colonne_date).reset_index(drop=True)


st.subheader("Contrôle après préparation")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Nombre de lignes", len(df))

with c2:
    st.metric("Date début", df[colonne_date].min().strftime("%d/%m/%Y"))

with c3:
    st.metric("Date fin", df[colonne_date].max().strftime("%d/%m/%Y"))

with c4:
    st.metric("Total valeur", f"{df[colonne_valeur].sum():,.2f}")


# --------------------------------------------------
# 4. Choix des transformations
# --------------------------------------------------

st.header("4. Transformations à générer")

st.write("Coche uniquement les transformations que tu souhaites ajouter au tableau.")

col_transfo1, col_transfo2 = st.columns(2)

with col_transfo1:
    ajouter_calendrier = st.checkbox(
        "Variables calendaires",
        value=True
    )

    ajouter_jours_feries = st.checkbox(
        "Jours fériés France",
        value=True
    )

    ajouter_zero = st.checkbox(
        "Indicateurs zéro / positif / négatif",
        value=True
    )

    ajouter_abs = st.checkbox(
        "Valeur absolue",
        value=False
    )

    ajouter_cumul = st.checkbox(
        "Cumuls mensuel et annuel",
        value=True
    )

with col_transfo2:
    ajouter_lag = st.checkbox(
        "Variables de retard, lags",
        value=True
    )

    ajouter_mm = st.checkbox(
        "Moyennes mobiles",
        value=True
    )

    ajouter_somme_mobile = st.checkbox(
        "Sommes mobiles",
        value=False
    )

    ajouter_ecart = st.checkbox(
        "Écarts avec périodes précédentes",
        value=True
    )

    ajouter_var_pct = st.checkbox(
        "Variations en %",
        value=False
    )


st.subheader("Paramètres avancés")

col_param1, col_param2, col_param3 = st.columns(3)

with col_param1:
    lags_texte = st.text_input(
        "Lags à générer, en jours",
        value="1, 7, 30, 365",
        help="Exemple : 1, 7, 30, 365"
    )

with col_param2:
    moyennes_texte = st.text_input(
        "Fenêtres de moyennes mobiles",
        value="7, 30, 90",
        help="Exemple : 7, 30, 90"
    )

with col_param3:
    sommes_texte = st.text_input(
        "Fenêtres de sommes mobiles",
        value="7, 30",
        help="Exemple : 7, 30"
    )

lags = texte_vers_liste_entiers(lags_texte)
fenetres_moyennes = texte_vers_liste_entiers(moyennes_texte)
fenetres_sommes = texte_vers_liste_entiers(sommes_texte)


# --------------------------------------------------
# 5. Application des transformations
# --------------------------------------------------

st.header("5. Résultat enrichi")

df_enrichi = df.copy()

if ajouter_calendrier:
    df_enrichi = ajouter_variables_calendaires(
        df_enrichi,
        colonne_date=colonne_date
    )

if ajouter_jours_feries:
    df_enrichi = ajouter_jours_feries_france(
        df_enrichi,
        colonne_date=colonne_date
    )

if ajouter_zero:
    df_enrichi = ajouter_indicateurs_zero(
        df_enrichi,
        colonne_valeur=colonne_valeur
    )

if ajouter_abs:
    df_enrichi = ajouter_valeurs_absolues(
        df_enrichi,
        colonne_valeur=colonne_valeur
    )

if ajouter_lag and lags:
    df_enrichi = ajouter_lags(
        df_enrichi,
        colonne_valeur=colonne_valeur,
        lags=lags
    )

if ajouter_mm and fenetres_moyennes:
    df_enrichi = ajouter_moyennes_mobiles(
        df_enrichi,
        colonne_valeur=colonne_valeur,
        fenetres=fenetres_moyennes
    )

if ajouter_somme_mobile and fenetres_sommes:
    df_enrichi = ajouter_sommes_mobiles(
        df_enrichi,
        colonne_valeur=colonne_valeur,
        fenetres=fenetres_sommes
    )

if ajouter_ecart and lags:
    df_enrichi = ajouter_ecarts(
        df_enrichi,
        colonne_valeur=colonne_valeur,
        lags=lags
    )

if ajouter_var_pct and lags:
    df_enrichi = ajouter_variations_pourcentage(
        df_enrichi,
        colonne_valeur=colonne_valeur,
        lags=lags
    )

if ajouter_cumul:
    df_enrichi = ajouter_cumuls(
        df_enrichi,
        colonne_date=colonne_date,
        colonne_valeur=colonne_valeur
    )


st.write(f"Nombre de colonnes initiales : **{len(df.columns)}**")
st.write(f"Nombre de colonnes après enrichissement : **{len(df_enrichi.columns)}**")

st.dataframe(df_enrichi, use_container_width=True)


# --------------------------------------------------
# 6. Visualisation
# --------------------------------------------------

st.header("6. Visualisation")

colonnes_numeriques = []

for col in df_enrichi.columns:
    if pd.api.types.is_numeric_dtype(df_enrichi[col]):
        colonnes_numeriques.append(col)

if colonnes_numeriques:
    col_graph1, col_graph2 = st.columns(2)

    with col_graph1:
        colonne_y = st.selectbox(
            "Variable à visualiser",
            colonnes_numeriques,
            index=colonnes_numeriques.index(colonne_valeur)
            if colonne_valeur in colonnes_numeriques
            else 0
        )

    with col_graph2:
        afficher_points = st.checkbox(
            "Afficher les points",
            value=False
        )

    fig = px.line(
        df_enrichi,
        x=colonne_date,
        y=colonne_y,
        title=f"{colonne_y} dans le temps",
        markers=afficher_points
    )

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title=colonne_y,
        hovermode="x unified"
    )

    fig.update_xaxes(rangeslider_visible=True)

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Aucune colonne numérique disponible pour la visualisation.")


# --------------------------------------------------
# 7. Analyse rapide des colonnes générées
# --------------------------------------------------

with st.expander("Voir la liste des colonnes générées"):
    colonnes_generees = pd.DataFrame({
        "Colonnes": df_enrichi.columns
    })

    st.dataframe(colonnes_generees, use_container_width=True)


with st.expander("Voir les lignes avec valeurs manquantes"):
    lignes_na = df_enrichi[df_enrichi.isna().any(axis=1)]

    st.write(f"Nombre de lignes avec au moins une valeur manquante : **{len(lignes_na)}**")

    st.dataframe(
        lignes_na.head(100),
        use_container_width=True
    )


# --------------------------------------------------
# 8. Exports
# --------------------------------------------------

st.header("7. Exports")

df_export = df_enrichi.copy()

for col in df_export.columns:
    if pd.api.types.is_datetime64_any_dtype(df_export[col]):
        df_export[col] = df_export[col].dt.strftime("%d/%m/%Y")

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
