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
# 1. Import FEC
# --------------------------------------------------

st.header("1. Import des FEC")

uploaded_files = st.file_uploader(
    "Importer jusqu'à 6 fichiers FEC",
    type=["txt", "csv"],
    accept_multiple_files=True,
    key="fec_files_merge"
)

if not uploaded_files:
    st.info("Importe d'abord un ou plusieurs FEC.")
    st.stop()

try:
    df_fec = charger_plusieurs_fec(uploaded_files, max_files=6)
except Exception as e:
    st.error(e)
    st.stop()

st.success(f"{len(uploaded_files)} fichier(s) FEC chargé(s).")


# --------------------------------------------------
# 2. Paramètres FEC
# --------------------------------------------------

st.header("2. Calcul du solde journalier FEC")

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

st.write("Aperçu du solde journalier FEC :")
st.dataframe(
    df_solde.head(20),
    use_container_width=True
)


# --------------------------------------------------
# 3. Import tableau externe
# --------------------------------------------------

st.header("3. Import du tableau externe à fusionner")

fichier_externe = st.file_uploader(
    "Importer un fichier Excel ou CSV",
    type=["xlsx", "xls", "csv"],
    key="fichier_externe"
)

if not fichier_externe:
    st.info("Importe ensuite le tableau externe à fusionner.")
    st.stop()

try:
    df_externe = lire_fichier_externe(fichier_externe)
except Exception as e:
    st.error(e)
    st.stop()

st.success("Tableau externe chargé.")

st.write("Aperçu du tableau externe :")
st.dataframe(df_externe.head(20), use_container_width=True)


# --------------------------------------------------
# 4. Paramétrage du merge
# --------------------------------------------------

st.header("4. Paramétrage de la fusion")

st.write("""
Choisis la colonne du FEC et la colonne du tableau externe à utiliser pour la fusion.

Dans la plupart des cas :
- côté FEC : **Date**
- côté tableau externe : une colonne date, par exemple **Date**, **Jour**, **Période**, etc.
""")

colonnes_fec = list(df_solde.columns)
colonnes_externe = list(df_externe.columns)

col_merge1, col_merge2 = st.columns(2)

with col_merge1:
    colonne_fec = st.selectbox(
        "Colonne côté FEC",
        colonnes_fec,
        index=colonnes_fec.index("Date") if "Date" in colonnes_fec else 0
    )

with col_merge2:
    colonne_externe = st.selectbox(
        "Colonne côté tableau externe",
        colonnes_externe
    )


type_fusion = st.selectbox(
    "Type de fusion",
    [
        "left : conserver toutes les lignes FEC",
        "right : conserver toutes les lignes du tableau externe",
        "inner : uniquement les lignes communes",
        "outer : tout conserver"
    ]
)

mapping_type_fusion = {
    "left : conserver toutes les lignes FEC": "left",
    "right : conserver toutes les lignes du tableau externe": "right",
    "inner : uniquement les lignes communes": "inner",
    "outer : tout conserver": "outer"
}

how = mapping_type_fusion[type_fusion]


# --------------------------------------------------
# 5. Gestion des dates
# --------------------------------------------------

st.subheader("Reconnaissance des dates")

fusion_sur_date = st.checkbox(
    "Les colonnes sélectionnées sont des dates",
    value=True
)

if fusion_sur_date:
    formats = proposer_formats_date()

    col_date1, col_date2 = st.columns(2)

    with col_date1:
        format_fec = st.selectbox(
            "Format date côté FEC",
            formats,
            index=0
        )

    with col_date2:
        format_externe = st.selectbox(
            "Format date côté tableau externe",
            formats,
            index=0
        )

    df_solde_merge = df_solde.copy()
    df_externe_merge = df_externe.copy()

    df_solde_merge["_cle_merge"] = normaliser_date(
        df_solde_merge[colonne_fec],
        format_date=format_fec
    ).dt.normalize()

    df_externe_merge["_cle_merge"] = normaliser_date(
        df_externe_merge[colonne_externe],
        format_date=format_externe
    ).dt.normalize()

else:
    df_solde_merge = df_solde.copy()
    df_externe_merge = df_externe.copy()

    df_solde_merge["_cle_merge"] = nettoyer_colonne_pour_merge(
        df_solde_merge[colonne_fec]
    )

    df_externe_merge["_cle_merge"] = nettoyer_colonne_pour_merge(
        df_externe_merge[colonne_externe]
    )


# --------------------------------------------------
# 6. Contrôle avant fusion
# --------------------------------------------------

st.subheader("Contrôle des clés de fusion")

col_controle1, col_controle2, col_controle3 = st.columns(3)

with col_controle1:
    st.metric(
        "Clés FEC reconnues",
        df_solde_merge["_cle_merge"].notna().sum()
    )

with col_controle2:
    st.metric(
        "Clés tableau externe reconnues",
        df_externe_merge["_cle_merge"].notna().sum()
    )

with col_controle3:
    nb_cles_communes = len(
        set(df_solde_merge["_cle_merge"].dropna())
        & set(df_externe_merge["_cle_merge"].dropna())
    )

    st.metric("Clés communes", nb_cles_communes)


with st.expander("Voir les clés non reconnues côté tableau externe"):
    non_reconnues = df_externe_merge[
        df_externe_merge["_cle_merge"].isna()
    ].copy()

    st.dataframe(non_reconnues.head(50), use_container_width=True)


# --------------------------------------------------
# 7. Fusion
# --------------------------------------------------

st.header("5. Résultat de la fusion")

df_merge = df_solde_merge.merge(
    df_externe_merge,
    on="_cle_merge",
    how=how,
    suffixes=("_FEC", "_EXTERNE")
)

df_merge = df_merge.drop(columns=["_cle_merge"])

st.write(f"Nombre de lignes après fusion : **{len(df_merge)}**")

st.dataframe(df_merge, use_container_width=True)


# --------------------------------------------------
# 8. Graphique simple après fusion
# --------------------------------------------------

st.subheader("Visualisation après fusion")

colonnes_numeriques_possibles = []

for col in df_merge.columns:
    serie_num = pd.to_numeric(
        df_merge[col].astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )

    if serie_num.notna().sum() > 0:
        colonnes_numeriques_possibles.append(col)

if colonnes_numeriques_possibles:
    col_graph1, col_graph2 = st.columns(2)

    with col_graph1:
        colonne_x = st.selectbox(
            "Colonne X du graphique",
            list(df_merge.columns),
            index=0
        )

    with col_graph2:
        colonne_y = st.selectbox(
            "Colonne Y numérique",
            colonnes_numeriques_possibles,
            index=colonnes_numeriques_possibles.index("SoldeJournalier")
            if "SoldeJournalier" in colonnes_numeriques_possibles
            else 0
        )

    df_graph = df_merge.copy()

    df_graph["_y_graph"] = pd.to_numeric(
        df_graph[colonne_y].astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
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

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Aucune colonne numérique détectée pour générer un graphique.")


# --------------------------------------------------
# 9. Exports
# --------------------------------------------------

st.subheader("Exports")

csv = df_merge.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="Télécharger le fichier fusionné en CSV",
    data=csv,
    file_name="fusion_fec_tableau_externe.csv",
    mime="text/csv"
)

excel = exporter_excel(df_merge, sheet_name="Fusion")

st.download_button(
    label="Télécharger le fichier fusionné en Excel",
    data=excel,
    file_name="fusion_fec_tableau_externe.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
