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
    convertir_colonne_date
)


st.title("Data Engineering simple")

st.write("""
Cette page enrichit un tableau existant sans supprimer ni regrouper les lignes.

Elle permet principalement :
- d'améliorer les colonnes dates ;
- de choisir une colonne de valeur ;
- d'ajouter des moyennes mobiles ;
- d'ajouter des écarts.
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
    Transforme une saisie du type '7, 30, 90' en liste [7, 30, 90].
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


def detecter_colonnes_dates_probables(df):
    """
    Propose d'abord les colonnes déjà au format date,
    puis les colonnes contenant date, jour ou période dans leur nom.
    """
    colonnes = list(df.columns)

    colonnes_datetime = [
        col for col in colonnes
        if pd.api.types.is_datetime64_any_dtype(df[col])
    ]

    colonnes_nom_date = [
        col for col in colonnes
        if any(mot in col.lower() for mot in ["date", "jour", "periode", "période"])
        and col not in colonnes_datetime
    ]

    autres = [
        col for col in colonnes
        if col not in colonnes_datetime
        and col not in colonnes_nom_date
    ]

    return colonnes_datetime + colonnes_nom_date + autres


def detecter_colonnes_numeriques_probables(df):
    """
    Détecte les colonnes qui peuvent être converties en numérique.
    """
    colonnes_numeriques = []

    for col in df.columns:
        serie_num = (
            df[col]
            .fillna("")
            .astype(str)
            .str.replace(" ", "", regex=False)
            .str.replace("\u202f", "", regex=False)
            .str.replace(",", ".", regex=False)
        )

        serie_num = pd.to_numeric(serie_num, errors="coerce")

        if serie_num.notna().sum() > 0:
            colonnes_numeriques.append(col)

    return colonnes_numeriques


def convertir_date_safe(df, colonne, format_date, dayfirst):
    """
    Convertit une colonne en date sans supprimer de ligne.
    Ajoute :
    - colonne_DateConvertie
    - colonne_Date_OK
    """
    df = df.copy()

    nouvelle_colonne = f"{colonne}_DateConvertie"
    colonne_controle = f"{colonne}_Date_OK"

    df[nouvelle_colonne] = convertir_colonne_date(
        df[colonne],
        format_date=format_date,
        dayfirst=dayfirst
    )

    df[colonne_controle] = df[nouvelle_colonne].notna().astype(int)

    return df, nouvelle_colonne


def ajouter_moyennes_mobiles_simples(df, colonne_date, colonne_valeur, fenetres):
    """
    Ajoute des moyennes mobiles sans regrouper les lignes.
    Le calcul suit l'ordre de la colonne date principale.
    """
    df = df.copy()
    df = df.sort_values(colonne_date).reset_index(drop=True)

    for fenetre in fenetres:
        df[f"{colonne_valeur}_MoyenneMobile_{fenetre}"] = (
            df[colonne_valeur]
            .rolling(window=fenetre, min_periods=1)
            .mean()
        )

    return df


def ajouter_ecarts_simples(df, colonne_date, colonne_valeur, decalages):
    """
    Ajoute des écarts simples par rapport aux lignes précédentes.
    Exemple :
    - écart 1 = valeur du jour - valeur de la ligne précédente
    - écart 7 = valeur du jour - valeur 7 lignes avant
    """
    df = df.copy()
    df = df.sort_values(colonne_date).reset_index(drop=True)

    for decalage in decalages:
        col_lag = f"{colonne_valeur}_Valeur_Precedente_{decalage}"
        col_ecart = f"{colonne_valeur}_Ecart_{decalage}"

        df[col_lag] = df[colonne_valeur].shift(decalage)
        df[col_ecart] = df[colonne_valeur] - df[col_lag]

    return df


def format_dates_pour_export(df):
    df_export = df.copy()

    for col in df_export.columns:
        if pd.api.types.is_datetime64_any_dtype(df_export[col]):
            df_export[col] = df_export[col].dt.strftime("%d/%m/%Y")

    return df_export


# --------------------------------------------------
# 1. Choix de la source
# --------------------------------------------------

st.header("1. Choix de la source")

sources_disponibles = []

if "df_solde_journalier" in st.session_state:
    sources_disponibles.append("Utiliser le solde journalier généré en page 1")

if "df_merge" in st.session_state:
    sources_disponibles.append("Utiliser le tableau fusionné généré en page 2")

sources_disponibles.append("Importer un nouveau fichier CSV / Excel")

source = st.radio(
    "Source du tableau",
    sources_disponibles
)

if source == "Utiliser le solde journalier généré en page 1":
    df_original = st.session_state["df_solde_journalier"].copy()
    st.success("Solde journalier récupéré depuis la page 1.")

elif source == "Utiliser le tableau fusionné généré en page 2":
    df_original = st.session_state["df_merge"].copy()
    st.success("Tableau fusionné récupéré depuis la page 2.")

else:
    fichier = st.file_uploader(
        "Importer un fichier CSV ou Excel",
        type=["csv", "xlsx", "xls"],
        key="data_engineering_import_simple"
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

st.write(f"Nombre de lignes source : **{len(df_original)}**")
st.write(f"Nombre de colonnes source : **{len(df_original.columns)}**")

st.dataframe(
    df_original.head(50),
    use_container_width=True
)


# --------------------------------------------------
# 2. Amélioration des dates
# --------------------------------------------------

st.header("2. Amélioration des dates")

st.write("""
Sélectionne les colonnes qui doivent être reconnues comme des dates.
Aucune ligne n'est supprimée : une colonne convertie est simplement ajoutée.
""")

colonnes = list(df_original.columns)

colonnes_dates_suggerees = detecter_colonnes_dates_probables(df_original)

colonnes_dates_a_convertir = st.multiselect(
    "Colonnes à convertir en date",
    colonnes,
    default=[
        col for col in colonnes_dates_suggerees
        if any(mot in col.lower() for mot in ["date", "jour", "periode", "période"])
    ][:3]
)

formats = proposer_formats_date()

col_date_param1, col_date_param2 = st.columns(2)

with col_date_param1:
    format_date = st.selectbox(
        "Format de date",
        formats,
        index=0
    )

with col_date_param2:
    dayfirst = st.checkbox(
        "Interprétation française : jour/mois/année",
        value=True,
        help="À laisser coché pour les dates du type 13/01/2025."
    )


df_prepare = df_original.copy()
colonnes_dates_converties = []

for col in colonnes_dates_a_convertir:
    df_prepare, nouvelle_colonne_date = convertir_date_safe(
        df_prepare,
        colonne=col,
        format_date=format_date,
        dayfirst=dayfirst
    )

    colonnes_dates_converties.append(nouvelle_colonne_date)


if colonnes_dates_a_convertir:
    st.subheader("Contrôle de conversion des dates")

    controles = []

    for col in colonnes_dates_a_convertir:
        col_ok = f"{col}_Date_OK"
        col_convertie = f"{col}_DateConvertie"

        controles.append({
            "Colonne source": col,
            "Colonne date créée": col_convertie,
            "Dates reconnues": int(df_prepare[col_ok].sum()),
            "Dates non reconnues": int((df_prepare[col_ok] == 0).sum())
        })

    st.dataframe(
        pd.DataFrame(controles),
        use_container_width=True
    )

    with st.expander("Voir les lignes avec dates non reconnues"):
        masque_non_reconnues = pd.Series(False, index=df_prepare.index)

        for col in colonnes_dates_a_convertir:
            masque_non_reconnues = masque_non_reconnues | (
                df_prepare[f"{col}_Date_OK"] == 0
            )

        st.dataframe(
            df_prepare.loc[masque_non_reconnues].head(200),
            use_container_width=True
        )

else:
    st.info("Aucune colonne date sélectionnée pour conversion.")


# --------------------------------------------------
# 3. Choix de la date principale et de la valeur
# --------------------------------------------------

st.header("3. Choix de la date principale et de la valeur")

colonnes_dates_utilisables = [
    col for col in df_prepare.columns
    if pd.api.types.is_datetime64_any_dtype(df_prepare[col])
]

if not colonnes_dates_utilisables:
    st.warning(
        "Aucune colonne date exploitable n'a été détectée. "
        "Sélectionne au moins une colonne date à convertir dans l'étape précédente."
    )
    st.stop()

colonnes_numeriques_probables = detecter_colonnes_numeriques_probables(df_prepare)

if not colonnes_numeriques_probables:
    st.warning("Aucune colonne numérique exploitable détectée.")
    st.stop()

col_principal1, col_principal2 = st.columns(2)

with col_principal1:
    colonne_date_principale = st.selectbox(
        "Date principale pour trier et calculer",
        colonnes_dates_utilisables,
        index=0
    )

with col_principal2:
    colonne_valeur = st.selectbox(
        "Colonne numérique à enrichir",
        colonnes_numeriques_probables,
        index=colonnes_numeriques_probables.index("SoldeJournalier")
        if "SoldeJournalier" in colonnes_numeriques_probables
        else 0
    )


df_prepare[colonne_valeur] = convertir_colonne_numerique(
    df_prepare[colonne_valeur]
)

# On ne supprime pas les lignes.
# On trie seulement les lignes qui ont une date principale.
# Les lignes sans date principale restent à la fin.

df_prepare["_Date_Principale_NA"] = df_prepare[colonne_date_principale].isna()

df_prepare = (
    df_prepare
    .sort_values(
        by=["_Date_Principale_NA", colonne_date_principale],
        ascending=[True, True]
    )
    .drop(columns=["_Date_Principale_NA"])
    .reset_index(drop=True)
)

st.subheader("Aperçu après préparation simple")

st.write(f"Nombre de lignes conservées : **{len(df_prepare)}**")

st.dataframe(
    df_prepare.head(100),
    use_container_width=True
)


# --------------------------------------------------
# 4. Transformations simples
# --------------------------------------------------

st.header("4. Transformations simples")

st.write("""
Les calculs sont faits dans l'ordre de la date principale.
Ils ne regroupent pas les lignes et ne complètent pas les jours manquants.
""")

col_transfo1, col_transfo2 = st.columns(2)

with col_transfo1:
    generer_moyennes = st.checkbox(
        "Générer des moyennes mobiles",
        value=True
    )

    fenetres_moyennes_txt = st.text_input(
        "Fenêtres moyennes mobiles",
        value="7, 30, 90",
        help="Exemple : 7, 30, 90"
    )

with col_transfo2:
    generer_ecarts = st.checkbox(
        "Générer des écarts",
        value=True
    )

    decalages_ecarts_txt = st.text_input(
        "Décalages pour les écarts",
        value="1, 7, 30",
        help="Exemple : 1, 7, 30"
    )


fenetres_moyennes = texte_vers_liste_entiers(fenetres_moyennes_txt)
decalages_ecarts = texte_vers_liste_entiers(decalages_ecarts_txt)


df_enrichi = df_prepare.copy()

if generer_moyennes and fenetres_moyennes:
    df_enrichi = ajouter_moyennes_mobiles_simples(
        df_enrichi,
        colonne_date=colonne_date_principale,
        colonne_valeur=colonne_valeur,
        fenetres=fenetres_moyennes
    )

if generer_ecarts and decalages_ecarts:
    df_enrichi = ajouter_ecarts_simples(
        df_enrichi,
        colonne_date=colonne_date_principale,
        colonne_valeur=colonne_valeur,
        decalages=decalages_ecarts
    )


# Stockage session
st.session_state["df_data_engineering"] = df_enrichi.copy()

st.success("Tableau enrichi généré et stocké en mémoire.")

st.subheader("Résultat enrichi")

st.write(f"Nombre de lignes : **{len(df_enrichi)}**")
st.write(f"Nombre de colonnes : **{len(df_enrichi.columns)}**")

st.dataframe(
    df_enrichi,
    use_container_width=True
)


# --------------------------------------------------
# 5. Visualisation simple
# --------------------------------------------------

st.header("5. Visualisation")

colonnes_numeriques = [
    col for col in df_enrichi.columns
    if pd.api.types.is_numeric_dtype(df_enrichi[col])
]

if colonnes_numeriques:
    colonne_y = st.selectbox(
        "Variable à afficher",
        colonnes_numeriques,
        index=colonnes_numeriques.index(colonne_valeur)
        if colonne_valeur in colonnes_numeriques
        else 0
    )

    df_graph = df_enrichi.dropna(subset=[colonne_date_principale]).copy()

    fig = px.line(
        df_graph,
        x=colonne_date_principale,
        y=colonne_y,
        title=f"{colonne_y} dans le temps"
    )

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title=colonne_y,
        hovermode="x unified"
    )

    fig.update_xaxes(
        rangeslider_visible=True
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )
else:
    st.info("Aucune colonne numérique disponible pour le graphique.")


# --------------------------------------------------
# 6. Contrôles
# --------------------------------------------------

st.header("6. Contrôles")

with st.expander("Voir les colonnes générées"):
    st.dataframe(
        pd.DataFrame({"Colonnes": df_enrichi.columns}),
        use_container_width=True
    )

with st.expander("Voir les lignes sans date principale reconnue"):
    lignes_sans_date = df_enrichi[
        df_enrichi[colonne_date_principale].isna()
    ]

    st.write(f"Nombre de lignes sans date principale : **{len(lignes_sans_date)}**")

    st.dataframe(
        lignes_sans_date.head(200),
        use_container_width=True
    )


# --------------------------------------------------
# 7. Exports
# --------------------------------------------------

st.header("7. Exports")

df_export = format_dates_pour_export(df_enrichi)

csv = df_export.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="Télécharger le tableau enrichi en CSV",
    data=csv,
    file_name="tableau_data_engineering_simple.csv",
    mime="text/csv"
)

excel = exporter_excel(df_export)

st.download_button(
    label="Télécharger le tableau enrichi en Excel",
    data=excel,
    file_name="tableau_data_engineering_simple.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
