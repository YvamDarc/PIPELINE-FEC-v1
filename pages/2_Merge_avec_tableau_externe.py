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


st.title("Ajout de données externes au solde journalier")


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


def convertir_dates_export(df):
    df_export = df.copy()

    for col in df_export.columns:
        if pd.api.types.is_datetime64_any_dtype(df_export[col]):
            df_export[col] = df_export[col].dt.strftime("%d/%m/%Y")

    return df_export


def preparer_cle_date(df, colonne, format_date):
    """
    Crée une clé de fusion date propre, normalisée à minuit.
    """
    df = df.copy()

    df["_cle_merge"] = normaliser_date(
        df[colonne],
        format_date=format_date
    ).dt.normalize()

    return df


def preparer_cle_texte(df, colonne):
    """
    Crée une clé de fusion texte propre.
    """
    df = df.copy()

    df["_cle_merge"] = nettoyer_colonne_pour_merge(
        df[colonne]
    )

    return df


def agreger_tableau_externe(df_externe_merge, cle="_cle_merge"):
    """
    Agrège le tableau externe par clé de fusion.
    Les colonnes numériques sont additionnées.
    Les colonnes texte gardent la première valeur non vide.
    """

    df = df_externe_merge.copy()

    colonnes_hors_cle = [
        col for col in df.columns
        if col != cle
    ]

    agg_dict = {}

    for col in colonnes_hors_cle:
        serie_num = convertir_numerique_possible(df[col])

        nb_num = serie_num.notna().sum()
        nb_total = df[col].notna().sum()

        if nb_total > 0 and nb_num / nb_total >= 0.8:
            df[col] = serie_num
            agg_dict[col] = "sum"
        else:
            agg_dict[col] = "first"

    df_agrege = (
        df
        .groupby(cle, as_index=False)
        .agg(agg_dict)
    )

    return df_agrege


# --------------------------------------------------
# 1. Choix de la source principale
# --------------------------------------------------

st.header("1. Choix du tableau principal")

st.write("""
Le tableau principal est celui que l'on veut conserver.

En général, c'est le solde journalier issu de la page 1.
Le tableau externe servira seulement à ajouter des colonnes.
""")

sources = []

if "df_solde_journalier" in st.session_state:
    sources.append("Utiliser le solde journalier généré en page 1")

sources.append("Importer de nouveaux FEC et recalculer un solde journalier")

source_principale = st.radio(
    "Source du tableau principal",
    sources
)


# --------------------------------------------------
# 2. Récupération ou calcul du tableau principal
# --------------------------------------------------

if source_principale == "Utiliser le solde journalier généré en page 1":

    df_principal = st.session_state["df_solde_journalier"].copy()

    if "Date" in df_principal.columns:
        df_principal["Date"] = pd.to_datetime(
            df_principal["Date"],
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

else:

    st.subheader("Import de nouveaux FEC")

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

    df_principal = resultat_fec[["Date", "SoldeJournalier"]].copy()

    st.session_state["df_solde_journalier_page_2"] = df_principal
    st.session_state["df_fec_brut_page_2"] = df_fec
    st.session_state["df_filtre_fec_page_2"] = df_filtre

    st.success("Nouveau solde journalier calculé.")


st.subheader("Aperçu du tableau principal")

st.write(f"Nombre de lignes du tableau principal : **{len(df_principal)}**")

st.dataframe(
    df_principal.head(50),
    use_container_width=True
)


# --------------------------------------------------
# 3. Import du tableau externe
# --------------------------------------------------

st.header("2. Import du tableau externe")

st.write("""
Ce tableau va servir à ajouter des colonnes au tableau principal.

Exemples :
- nombre de couverts ;
- météo ;
- prix ;
- fréquentation ;
- jours spéciaux ;
- commentaires.
""")

fichier_externe = st.file_uploader(
    "Importer le tableau externe Excel ou CSV",
    type=["xlsx", "xls", "csv"],
    key="fichier_externe"
)

if not fichier_externe:
    st.info("Importe le tableau externe à ajouter au tableau principal.")
    st.stop()

try:
    df_externe = lire_fichier_externe(fichier_externe)
except Exception as e:
    st.error(e)
    st.stop()

st.success("Tableau externe chargé.")

st.write(f"Nombre de lignes du tableau externe : **{len(df_externe)}**")

st.dataframe(
    df_externe.head(50),
    use_container_width=True
)


# --------------------------------------------------
# 4. Paramétrage de la clé de fusion
# --------------------------------------------------

st.header("3. Paramétrage de la clé de fusion")

st.write("""
Choisis la colonne du tableau principal et celle du tableau externe qui doivent correspondre.

Dans ton cas, ce sera le plus souvent :
- **Date** côté tableau principal ;
- **Date**, **Jour** ou **Période** côté tableau externe.
""")

colonnes_principal = list(df_principal.columns)
colonnes_externe = list(df_externe.columns)

col_merge1, col_merge2 = st.columns(2)

with col_merge1:
    colonne_principal = st.selectbox(
        "Colonne de correspondance côté principal",
        colonnes_principal,
        index=colonnes_principal.index("Date") if "Date" in colonnes_principal else 0
    )

with col_merge2:
    colonne_externe = st.selectbox(
        "Colonne de correspondance côté externe",
        colonnes_externe
    )

fusion_sur_date = st.checkbox(
    "La clé de fusion est une date",
    value=True
)


# --------------------------------------------------
# 5. Reconnaissance des dates ou des clés texte
# --------------------------------------------------

df_principal_merge = df_principal.copy()
df_externe_merge = df_externe.copy()

if fusion_sur_date:

    st.subheader("Formats de date")

    formats = proposer_formats_date()

    col_format1, col_format2 = st.columns(2)

    with col_format1:
        format_principal = st.selectbox(
            "Format date côté principal",
            formats,
            index=0,
            key="format_date_principal"
        )

    with col_format2:
        format_externe = st.selectbox(
            "Format date côté externe",
            formats,
            index=0,
            key="format_date_externe"
        )

    df_principal_merge = preparer_cle_date(
        df_principal_merge,
        colonne=colonne_principal,
        format_date=format_principal
    )

    df_externe_merge = preparer_cle_date(
        df_externe_merge,
        colonne=colonne_externe,
        format_date=format_externe
    )

else:

    df_principal_merge = preparer_cle_texte(
        df_principal_merge,
        colonne=colonne_principal
    )

    df_externe_merge = preparer_cle_texte(
        df_externe_merge,
        colonne=colonne_externe
    )


# --------------------------------------------------
# 6. Contrôle des clés avant fusion
# --------------------------------------------------

st.header("4. Contrôle avant fusion")

cles_principal = df_principal_merge["_cle_merge"].dropna()
cles_externe = df_externe_merge["_cle_merge"].dropna()

cles_communes = set(cles_principal) & set(cles_externe)
cles_principal_sans_match = set(cles_principal) - set(cles_externe)
cles_externe_sans_match = set(cles_externe) - set(cles_principal)

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Clés principal reconnues", len(cles_principal))

with c2:
    st.metric("Clés externe reconnues", len(cles_externe))

with c3:
    st.metric("Clés communes", len(cles_communes))

with c4:
    taux_match = 0

    if len(set(cles_principal)) > 0:
        taux_match = len(cles_communes) / len(set(cles_principal)) * 100

    st.metric("Taux de match principal", f"{taux_match:.1f} %")


with st.expander("Voir les dates / clés du principal sans correspondance externe"):
    df_sans_match_principal = df_principal_merge[
        df_principal_merge["_cle_merge"].isin(cles_principal_sans_match)
    ].copy()

    st.write(f"Lignes principales sans correspondance : **{len(df_sans_match_principal)}**")

    st.dataframe(
        df_sans_match_principal.head(200),
        use_container_width=True
    )


with st.expander("Voir les dates / clés externes sans correspondance principale"):
    df_sans_match_externe = df_externe_merge[
        df_externe_merge["_cle_merge"].isin(cles_externe_sans_match)
    ].copy()

    st.write(f"Lignes externes sans correspondance : **{len(df_sans_match_externe)}**")

    st.dataframe(
        df_sans_match_externe.head(200),
        use_container_width=True
    )


with st.expander("Voir les lignes externes avec date / clé non reconnue"):
    df_externe_non_reconnue = df_externe_merge[
        df_externe_merge["_cle_merge"].isna()
    ].copy()

    st.write(f"Lignes externes non reconnues : **{len(df_externe_non_reconnue)}**")

    st.dataframe(
        df_externe_non_reconnue.head(200),
        use_container_width=True
    )


# --------------------------------------------------
# 7. Gestion des doublons côté externe
# --------------------------------------------------

st.header("5. Gestion des doublons du tableau externe")

st.write("""
Si le tableau externe contient plusieurs lignes pour une même date,
un merge simple peut dupliquer les lignes du tableau principal.

Pour éviter cela, tu peux agréger le tableau externe par date avant fusion.
""")

nb_doublons_externe = df_externe_merge.duplicated(subset=["_cle_merge"]).sum()

st.write(f"Nombre de doublons côté externe sur la clé : **{nb_doublons_externe}**")

agreger_externe = st.checkbox(
    "Agréger le tableau externe par clé avant fusion",
    value=True,
    help="Recommandé si tu veux garder une seule ligne par jour dans le tableau principal."
)

if agreger_externe:
    df_externe_pour_merge = agreger_tableau_externe(
        df_externe_merge,
        cle="_cle_merge"
    )

    st.success("Tableau externe agrégé par clé avant fusion.")
else:
    df_externe_pour_merge = df_externe_merge.copy()

st.write(f"Lignes externes utilisées pour la fusion : **{len(df_externe_pour_merge)}**")


# --------------------------------------------------
# 8. Type de fusion
# --------------------------------------------------

st.header("6. Type de fusion")

st.write("""
Par défaut, utilise **left**.

C'est le bon choix quand tu veux conserver toutes les lignes du tableau principal
et simplement ajouter des colonnes externes.
""")

type_fusion = st.selectbox(
    "Type de fusion",
    [
        "left : conserver toutes les lignes du tableau principal et ajouter les colonnes externes",
        "inner : garder uniquement les lignes qui matchent dans les deux tableaux",
        "outer : tout conserver des deux tableaux",
        "right : conserver toutes les lignes du tableau externe"
    ],
    index=0
)

mapping_type_fusion = {
    "left : conserver toutes les lignes du tableau principal et ajouter les colonnes externes": "left",
    "inner : garder uniquement les lignes qui matchent dans les deux tableaux": "inner",
    "outer : tout conserver des deux tableaux": "outer",
    "right : conserver toutes les lignes du tableau externe": "right"
}

how = mapping_type_fusion[type_fusion]


if how == "inner":
    st.warning(
        "Attention : le mode inner supprime toutes les lignes du tableau principal "
        "qui n'ont pas de correspondance exacte dans le tableau externe."
    )


# --------------------------------------------------
# 9. Fusion propre
# --------------------------------------------------

st.header("7. Résultat de la fusion")

# On évite de dupliquer inutilement les colonnes de clé originales si elles existent déjà.
df_merge = df_principal_merge.merge(
    df_externe_pour_merge,
    on="_cle_merge",
    how=how,
    suffixes=("_PRINCIPAL", "_EXTERNE")
)

if fusion_sur_date:
    df_merge["Date_Merge"] = df_merge["_cle_merge"]

df_merge = df_merge.drop(columns=["_cle_merge"])

st.write(f"Nombre de lignes après fusion : **{len(df_merge)}**")

if how == "left":
    st.caption(
        "Mode left : toutes les lignes du tableau principal sont conservées. "
        "Les colonnes externes sont ajoutées lorsqu'une correspondance existe."
    )

st.dataframe(
    df_merge,
    use_container_width=True
)


# --------------------------------------------------
# 10. Filtre de date après fusion
# --------------------------------------------------

st.header("8. Filtre de date après fusion")

df_filtre_date = df_merge.copy()

colonnes_dates = detecter_colonnes_dates(df_filtre_date)

if "Date_Merge" in df_filtre_date.columns:
    colonne_date_defaut = "Date_Merge"
elif "Date" in df_filtre_date.columns and pd.api.types.is_datetime64_any_dtype(df_filtre_date["Date"]):
    colonne_date_defaut = "Date"
else:
    colonne_date_defaut = colonnes_dates[0] if colonnes_dates else None

if colonne_date_defaut is not None:

    colonne_date_filtre = st.selectbox(
        "Colonne date à filtrer",
        colonnes_dates,
        index=colonnes_dates.index(colonne_date_defaut)
        if colonne_date_defaut in colonnes_dates
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
    st.info("Aucune colonne date détectée pour filtrer.")

st.write(f"Nombre de lignes après filtre : **{len(df_filtre_date)}**")

st.dataframe(
    df_filtre_date,
    use_container_width=True
)


# --------------------------------------------------
# 11. Stockage pour la page 3
# --------------------------------------------------

st.session_state["df_merge"] = df_filtre_date.copy()

st.success("Le tableau fusionné est disponible pour la page 3.")


# --------------------------------------------------
# 12. Visualisations
# --------------------------------------------------

st.header("9. Visualisations")

colonnes_numeriques = detecter_colonnes_numeriques(df_filtre_date)
colonnes_dates_graph = detecter_colonnes_dates(df_filtre_date)

if colonnes_numeriques and colonnes_dates_graph:

    onglet_ligne, onglet_barres, onglet_nuage = st.tabs(
        [
            "Courbe temporelle",
            "Barres par période",
            "Nuage de points"
        ]
    )

    with onglet_ligne:
        col_graph1, col_graph2 = st.columns(2)

        with col_graph1:
            colonne_x = st.selectbox(
                "Colonne date",
                colonnes_dates_graph,
                index=colonnes_dates_graph.index("Date_Merge")
                if "Date_Merge" in colonnes_dates_graph
                else 0,
                key="ligne_x"
            )

        with col_graph2:
            colonne_y = st.selectbox(
                "Colonne numérique",
                colonnes_numeriques,
                index=colonnes_numeriques.index("SoldeJournalier")
                if "SoldeJournalier" in colonnes_numeriques
                else 0,
                key="ligne_y"
            )

        df_graph = df_filtre_date.copy()
        df_graph["_y_graph"] = convertir_numerique_possible(df_graph[colonne_y])

        fig = px.line(
            df_graph,
            x=colonne_x,
            y="_y_graph",
            title=f"{colonne_y} par date"
        )

        fig.update_layout(
            xaxis_title=colonne_x,
            yaxis_title=colonne_y,
            hovermode="x unified"
        )

        fig.update_xaxes(rangeslider_visible=True)

        st.plotly_chart(fig, use_container_width=True)

    with onglet_barres:
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
                colonnes_numeriques,
                index=colonnes_numeriques.index("SoldeJournalier")
                if "SoldeJournalier" in colonnes_numeriques
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

        st.plotly_chart(fig_bar, use_container_width=True)

    with onglet_nuage:
        if len(colonnes_numeriques) >= 2:
            col_scatter1, col_scatter2 = st.columns(2)

            with col_scatter1:
                colonne_x_scatter = st.selectbox(
                    "Variable X",
                    colonnes_numeriques,
                    index=0,
                    key="scatter_x"
                )

            with col_scatter2:
                colonne_y_scatter = st.selectbox(
                    "Variable Y",
                    colonnes_numeriques,
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

            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.info("Il faut au moins deux colonnes numériques pour le nuage de points.")

else:
    st.info("Il faut au moins une colonne date et une colonne numérique pour générer les graphiques.")


# --------------------------------------------------
# 13. Exports
# --------------------------------------------------

st.header("10. Exports")

df_export = convertir_dates_export(df_filtre_date)

csv = df_export.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="Télécharger le fichier fusionné en CSV",
    data=csv,
    file_name="fusion_tableau_principal_externe.csv",
    mime="text/csv"
)

excel = exporter_excel(
    df_export,
    sheet_name="Fusion"
)

st.download_button(
    label="Télécharger le fichier fusionné en Excel",
    data=excel,
    file_name="fusion_tableau_principal_externe.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
