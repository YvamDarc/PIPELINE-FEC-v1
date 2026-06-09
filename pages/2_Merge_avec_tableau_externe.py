import streamlit as st
import pandas as pd
import plotly.express as px

from utils.fec_utils import (
    charger_plusieurs_fec,
    calculer_solde_journalier,
    exporter_excel
)

from utils.file_utils import (
    lire_fichier_externe,
    normaliser_date,
    proposer_formats_date,
    nettoyer_colonne_pour_merge
)


st.title("Merge du solde journalier FEC avec un tableau externe")


# --------------------------------------------------
# Fonctions locales
# --------------------------------------------------

def convertir_numerique_possible(serie):
    return pd.to_numeric(
        serie
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace("\u202f", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce"
    )


def detecter_colonnes_numeriques(df):
    colonnes_numeriques = []

    for col in df.columns:
        serie_num = convertir_numerique_possible(df[col])

        if serie_num.notna().sum() > 0:
            colonnes_numeriques.append(col)

    return colonnes_numeriques


def detecter_colonnes_dates(df):
    colonnes_dates = []

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            colonnes_dates.append(col)

    return colonnes_dates


# --------------------------------------------------
# 1. Choix de la source principale
# --------------------------------------------------

st.header("1. Choix de la source principale")

sources = []

if "df_solde_journalier" in st.session_state:
    sources.append("Utiliser le solde journalier généré en page 1")

sources.append("Importer de nouveaux FEC et recalculer un solde journalier")

source_principale = st.radio(
    "Source du tableau principal",
    sources,
    horizontal=False
)


# --------------------------------------------------
# 2. Récupération ou calcul du solde journalier
# --------------------------------------------------

if source_principale == "Utiliser le solde journalier généré en page 1":

    st.header("2. Récupération du solde journalier")

    df_solde = st.session_state["df_solde_journalier"].copy()

    if "Date" in df_solde.columns:
        df_solde["Date"] = pd.to_datetime(
            df_solde["Date"],
            errors="coerce",
            dayfirst=True
        )

    st.success("Solde journalier récupéré depuis la page 1.")

    if "parametres_page_1" in st.session_state:
        params = st.session_state["parametres_page_1"]

        st.caption(
            f"Paramètres page 1 : comptes {params.get('compte_debut')} à "
            f"{params.get('compte_fin')} — sens {params.get('sens')} — "
            f"{params.get('nombre_fec')} FEC."
        )

    st.write("Aperçu du solde journalier récupéré :")
    st.dataframe(
        df_solde.head(30),
        use_container_width=True
    )

else:

    st.header("2. Import de nouveaux FEC")

    uploaded_files = st.file_uploader(
        "Importer jusqu'à 6 fichiers FEC",
        type=["txt", "csv"],
        accept_multiple_files=True,
        key="fec_files_merge"
    )

    if not uploaded_files:
        st.info("Importe un ou plusieurs FEC pour continuer.")
        st.stop()

    try:
        df_fec = charger_plusieurs_fec(uploaded_files, max_files=6)
    except Exception as e:
        st.error(e)
        st.stop()

    st.success(f"{len(uploaded_files)} fichier(s) FEC chargé(s).")

    st.subheader("Paramètres du solde journalier FEC")

    col1, col2, col3 = st.columns(3)

    with col1:
        compte_debut = st.text_input(
            "Compte de début",
            value="7000000",
            key="merge_compte_debut"
        ).strip()

    with col2:
        compte_fin = st.text_input(
            "Compte de fin",
            value="70999999",
            key="merge_compte_fin"
        ).strip()

    with col3:
        sens = st.selectbox(
            "Sens du solde",
            ["Débit - Crédit", "Crédit - Débit"],
            key="merge_sens"
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

    df_solde = resultat_fec[["Date", "SoldeJournalier"]].copy()

    st.session_state["df_solde_journalier_page_2"] = df_solde
    st.session_state["df_fec_brut_page_2"] = df_fec
    st.session_state["df_filtre_fec_page_2"] = df_filtre

    st.success("Nouveau solde journalier calculé.")

    st.write("Aperçu du solde journalier calculé :")
    st.dataframe(
        df_solde.head(30),
        use_container_width=True
    )


# --------------------------------------------------
# 3. Import du tableau externe
# --------------------------------------------------

st.header("3. Import du tableau externe à fusionner")

fichier_externe = st.file_uploader(
    "Importer un deuxième fichier Excel ou CSV",
    type=["xlsx", "xls", "csv"],
    key="fichier_externe"
)

if not fichier_externe:
    st.info("Importe le tableau externe à fusionner avec le solde journalier.")
    st.stop()

try:
    df_externe = lire_fichier_externe(fichier_externe)
except Exception as e:
    st.error(e)
    st.stop()

st.success("Tableau externe chargé.")

st.write("Aperçu du tableau externe :")
st.dataframe(
    df_externe.head(30),
    use_container_width=True
)


# --------------------------------------------------
# 4. Paramétrage de la fusion
# --------------------------------------------------

st.header("4. Paramétrage de la fusion")

st.write("""
Choisis la colonne du tableau principal et la colonne du tableau externe à utiliser pour la fusion.

Dans la plupart des cas :
- côté tableau principal : **Date**
- côté tableau externe : une colonne date, par exemple **Date**, **Jour**, **Période**, etc.
""")

colonnes_principal = list(df_solde.columns)
colonnes_externe = list(df_externe.columns)

col_merge1, col_merge2 = st.columns(2)

with col_merge1:
    colonne_principal = st.selectbox(
        "Colonne côté tableau principal",
        colonnes_principal,
        index=colonnes_principal.index("Date") if "Date" in colonnes_principal else 0
    )

with col_merge2:
    colonne_externe = st.selectbox(
        "Colonne côté tableau externe",
        colonnes_externe
    )

type_fusion = st.selectbox(
    "Type de fusion",
    [
        "left : conserver toutes les lignes du tableau principal",
        "right : conserver toutes les lignes du tableau externe",
        "inner : uniquement les lignes communes",
        "outer : tout conserver"
    ]
)

mapping_type_fusion = {
    "left : conserver toutes les lignes du tableau principal": "left",
    "right : conserver toutes les lignes du tableau externe": "right",
    "inner : uniquement les lignes communes": "inner",
    "outer : tout conserver": "outer"
}

how = mapping_type_fusion[type_fusion]


# --------------------------------------------------
# 5. Gestion des clés de fusion
# --------------------------------------------------

st.subheader("Reconnaissance des clés de fusion")

fusion_sur_date = st.checkbox(
    "Les colonnes sélectionnées sont des dates",
    value=True
)

df_principal_merge = df_solde.copy()
df_externe_merge = df_externe.copy()

if fusion_sur_date:
    formats = proposer_formats_date()

    col_date1, col_date2 = st.columns(2)

    with col_date1:
        format_principal = st.selectbox(
            "Format date côté tableau principal",
            formats,
            index=0
        )

    with col_date2:
        format_externe = st.selectbox(
            "Format date côté tableau externe",
            formats,
            index=0
        )

    df_principal_merge["_cle_merge"] = normaliser_date(
        df_principal_merge[colonne_principal],
        format_date=format_principal
    ).dt.normalize()

    df_externe_merge["_cle_merge"] = normaliser_date(
        df_externe_merge[colonne_externe],
        format_date=format_externe
    ).dt.normalize()

else:
    df_principal_merge["_cle_merge"] = nettoyer_colonne_pour_merge(
        df_principal_merge[colonne_principal]
    )

    df_externe_merge["_cle_merge"] = nettoyer_colonne_pour_merge(
        df_externe_merge[colonne_externe]
    )


# --------------------------------------------------
# 6. Contrôle avant fusion
# --------------------------------------------------

st.subheader("Contrôle des clés de fusion")

cles_principal = df_principal_merge["_cle_merge"].dropna()
cles_externe = df_externe_merge["_cle_merge"].dropna()

col_controle1, col_controle2, col_controle3, col_controle4 = st.columns(4)

with col_controle1:
    st.metric(
        "Clés principal reconnues",
        cles_principal.shape[0]
    )

with col_controle2:
    st.metric(
        "Clés externe reconnues",
        cles_externe.shape[0]
    )

with col_controle3:
    nb_cles_communes = len(
        set(cles_principal)
        & set(cles_externe)
    )
    st.metric("Clés communes", nb_cles_communes)

with col_controle4:
    st.metric(
        "Clés externes uniques",
        df_externe_merge["_cle_merge"].nunique(dropna=True)
    )


with st.expander("Voir les clés non reconnues côté tableau externe"):
    non_reconnues_externe = df_externe_merge[
        df_externe_merge["_cle_merge"].isna()
    ].copy()

    st.dataframe(
        non_reconnues_externe.head(100),
        use_container_width=True
    )

with st.expander("Voir les clés non reconnues côté tableau principal"):
    non_reconnues_principal = df_principal_merge[
        df_principal_merge["_cle_merge"].isna()
    ].copy()

    st.dataframe(
        non_reconnues_principal.head(100),
        use_container_width=True
    )


# --------------------------------------------------
# 7. Fusion
# --------------------------------------------------

st.header("5. Résultat de la fusion")

df_merge = df_principal_merge.merge(
    df_externe_merge,
    on="_cle_merge",
    how=how,
    suffixes=("_PRINCIPAL", "_EXTERNE")
)

# On conserve une vraie colonne Date_Merge si la fusion est faite sur date
if fusion_sur_date:
    df_merge["Date_Merge"] = df_merge["_cle_merge"]

df_merge = df_merge.drop(columns=["_cle_merge"])

st.write(f"Nombre de lignes après fusion : **{len(df_merge)}**")

st.dataframe(
    df_merge,
    use_container_width=True
)


# --------------------------------------------------
# 8. Filtre de date après fusion
# --------------------------------------------------

st.header("6. Filtre de date après fusion")

df_filtre_date = df_merge.copy()

colonnes_dates = detecter_colonnes_dates(df_filtre_date)

if "Date_Merge" in df_filtre_date.columns:
    colonne_date_filtre_defaut = "Date_Merge"
elif "Date" in df_filtre_date.columns:
    colonne_date_filtre_defaut = "Date"
else:
    colonne_date_filtre_defaut = colonnes_dates[0] if colonnes_dates else None

if colonne_date_filtre_defaut is not None:
    colonne_date_filtre = st.selectbox(
        "Colonne date à utiliser pour le filtre",
        colonnes_dates,
        index=colonnes_dates.index(colonne_date_filtre_defaut)
        if colonne_date_filtre_defaut in colonnes_dates
        else 0
    )

    date_min = df_filtre_date[colonne_date_filtre].min()
    date_max = df_filtre_date[colonne_date_filtre].max()

    if pd.notna(date_min) and pd.notna(date_max):
        col_date_min, col_date_max = st.columns(2)

        with col_date_min:
            date_debut = st.date_input(
                "Date début",
                value=date_min.date()
            )

        with col_date_max:
            date_fin = st.date_input(
                "Date fin",
                value=date_max.date()
            )

        date_debut = pd.to_datetime(date_debut)
        date_fin = pd.to_datetime(date_fin)

        df_filtre_date = df_filtre_date[
            (df_filtre_date[colonne_date_filtre] >= date_debut)
            & (df_filtre_date[colonne_date_filtre] <= date_fin)
        ].copy()

        st.success(
            f"Filtre appliqué : {date_debut.strftime('%d/%m/%Y')} "
            f"au {date_fin.strftime('%d/%m/%Y')}"
        )

    else:
        st.info("La colonne date sélectionnée ne contient pas de dates exploitables.")
else:
    st.info("Aucune colonne date détectée pour filtrer.")

st.write(f"Nombre de lignes après filtre de date : **{len(df_filtre_date)}**")

st.dataframe(
    df_filtre_date,
    use_container_width=True
)


# --------------------------------------------------
# 9. Stockage pour la page 3
# --------------------------------------------------

st.session_state["df_merge"] = df_filtre_date.copy()

st.success("Le tableau fusionné filtré est disponible pour la page 3 Data Engineering.")


# --------------------------------------------------
# 10. Visualisations après fusion
# --------------------------------------------------

st.header("7. Visualisations après fusion")

colonnes_numeriques_possibles = detecter_colonnes_numeriques(df_filtre_date)

if colonnes_numeriques_possibles:

    onglet_ligne, onglet_barres, onglet_nuage = st.tabs(
        [
            "Courbe temporelle",
            "Barres par période",
            "Nuage de points"
        ]
    )

    with onglet_ligne:
        st.subheader("Courbe temporelle")

        colonnes_dates_graph = detecter_colonnes_dates(df_filtre_date)

        if colonnes_dates_graph:
            col_graph1, col_graph2 = st.columns(2)

            with col_graph1:
                colonne_x = st.selectbox(
                    "Colonne date X",
                    colonnes_dates_graph,
                    index=colonnes_dates_graph.index("Date_Merge")
                    if "Date_Merge" in colonnes_dates_graph
                    else 0,
                    key="ligne_x"
                )

            with col_graph2:
                colonne_y = st.selectbox(
                    "Colonne Y numérique",
                    colonnes_numeriques_possibles,
                    index=colonnes_numeriques_possibles.index("SoldeJournalier")
                    if "SoldeJournalier" in colonnes_numeriques_possibles
                    else 0,
                    key="ligne_y"
                )

            df_graph = df_filtre_date.copy()
            df_graph["_y_graph"] = convertir_numerique_possible(
                df_graph[colonne_y]
            )

            fig = px.line(
                df_graph,
                x=colonne_x,
                y="_y_graph",
                title=f"{colonne_y} par {colonne_x}"
            )

            fig.update_layout(
                xaxis_title=colonne_x,
                yaxis_title=colonne_y,
                hovermode="x unified"
            )

            fig.update_xaxes(rangeslider_visible=True)

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        else:
            st.info("Aucune colonne date détectée pour une courbe temporelle.")

    with onglet_barres:
        st.subheader("Barres par période")

        colonnes_dates_graph = detecter_colonnes_dates(df_filtre_date)

        if colonnes_dates_graph:
            col_bar1, col_bar2, col_bar3 = st.columns(3)

            with col_bar1:
                colonne_date_bar = st.selectbox(
                    "Colonne date",
                    colonnes_dates_graph,
                    index=colonnes_dates_graph.index("Date_Merge")
                    if "Date_Merge" in colonnes_dates_graph
                    else 0,
                    key="bar_date"
                )

            with col_bar2:
                colonne_valeur_bar = st.selectbox(
                    "Valeur numérique",
                    colonnes_numeriques_possibles,
                    index=colonnes_numeriques_possibles.index("SoldeJournalier")
                    if "SoldeJournalier" in colonnes_numeriques_possibles
                    else 0,
                    key="bar_valeur"
                )

            with col_bar3:
                frequence = st.selectbox(
                    "Période",
                    ["Jour", "Mois", "Année"],
                    index=1,
                    key="bar_freq"
                )

            df_bar = df_filtre_date.copy()
            df_bar["_valeur_bar"] = convertir_numerique_possible(
                df_bar[colonne_valeur_bar]
            )

            if frequence == "Jour":
                df_bar["_periode"] = df_bar[colonne_date_bar].dt.strftime("%d/%m/%Y")
            elif frequence == "Mois":
                df_bar["_periode"] = df_bar[colonne_date_bar].dt.to_period("M").astype(str)
            else:
                df_bar["_periode"] = df_bar[colonne_date_bar].dt.year.astype(str)

            df_bar_group = (
                df_bar
                .groupby("_periode", as_index=False)["_valeur_bar"]
                .sum()
            )

            fig_bar = px.bar(
                df_bar_group,
                x="_periode",
                y="_valeur_bar",
                title=f"{colonne_valeur_bar} par {frequence.lower()}"
            )

            fig_bar.update_layout(
                xaxis_title=frequence,
                yaxis_title=colonne_valeur_bar
            )

            st.plotly_chart(
                fig_bar,
                use_container_width=True
            )

        else:
            st.info("Aucune colonne date détectée pour regrouper par période.")

    with onglet_nuage:
        st.subheader("Nuage de points")

        if len(colonnes_numeriques_possibles) >= 2:
            col_scatter1, col_scatter2 = st.columns(2)

            with col_scatter1:
                colonne_x_scatter = st.selectbox(
                    "Variable X",
                    colonnes_numeriques_possibles,
                    index=0,
                    key="scatter_x"
                )

            with col_scatter2:
                colonne_y_scatter = st.selectbox(
                    "Variable Y",
                    colonnes_numeriques_possibles,
                    index=1,
                    key="scatter_y"
                )

            df_scatter = df_filtre_date.copy()
            df_scatter["_x_scatter"] = convertir_numerique_possible(
                df_scatter[colonne_x_scatter]
            )
            df_scatter["_y_scatter"] = convertir_numerique_possible(
                df_scatter[colonne_y_scatter]
            )

            fig_scatter = px.scatter(
                df_scatter,
                x="_x_scatter",
                y="_y_scatter",
                title=f"{colonne_y_scatter} en fonction de {colonne_x_scatter}"
            )

            fig_scatter.update_layout(
                xaxis_title=colonne_x_scatter,
                yaxis_title=colonne_y_scatter
            )

            st.plotly_chart(
                fig_scatter,
                use_container_width=True
            )

        else:
            st.info("Il faut au moins deux colonnes numériques pour générer un nuage de points.")

else:
    st.info("Aucune colonne numérique détectée pour générer des graphiques.")


# --------------------------------------------------
# 11. Exports
# --------------------------------------------------

st.subheader("Exports")

df_export = df_filtre_date.copy()

for col in df_export.columns:
    if pd.api.types.is_datetime64_any_dtype(df_export[col]):
        df_export[col] = df_export[col].dt.strftime("%d/%m/%Y")

csv = df_export.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="Télécharger le fichier fusionné filtré en CSV",
    data=csv,
    file_name="fusion_fec_tableau_externe.csv",
    mime="text/csv"
)

excel = exporter_excel(
    df_export,
    sheet_name="Fusion"
)

st.download_button(
    label="Télécharger le fichier fusionné filtré en Excel",
    data=excel,
    file_name="fusion_fec_tableau_externe.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
