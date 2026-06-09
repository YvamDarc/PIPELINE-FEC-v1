import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt

from utils.fec_utils import (
    charger_plusieurs_fec,
    calculer_solde_journalier,
    exporter_excel
)


st.title("Solde journalier FEC")


uploaded_files = st.file_uploader(
    "Importer jusqu'à 6 fichiers FEC",
    type=["txt", "csv"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("Importe un ou plusieurs fichiers FEC pour commencer.")
    st.stop()

try:
    df = charger_plusieurs_fec(uploaded_files, max_files=6)
except Exception as e:
    st.error(e)
    st.stop()

st.success(f"{len(uploaded_files)} fichier(s) FEC chargé(s).")


st.subheader("Paramètres de sélection")

col1, col2, col3 = st.columns(3)

with col1:
    compte_debut = st.text_input("Compte de début", value="7000000").strip()

with col2:
    compte_fin = st.text_input("Compte de fin", value="70999999").strip()

with col3:
    sens = st.selectbox(
        "Sens du solde",
        ["Débit - Crédit", "Crédit - Débit"]
    )

resultat, df_filtre = calculer_solde_journalier(
    df=df,
    compte_debut=compte_debut,
    compte_fin=compte_fin,
    sens=sens
)

if resultat is None:
    st.warning("Aucune écriture trouvée sur cette plage de comptes.")
    st.stop()


resultat_final = resultat[["Date", "SoldeJournalier"]].copy()
resultat_affichage = resultat_final.copy()
resultat_affichage["Date"] = resultat_affichage["Date"].dt.strftime("%d/%m/%Y")


st.subheader("Résultat")

col_info1, col_info2, col_info3 = st.columns(3)

with col_info1:
    st.metric("Nombre de jours générés", len(resultat_final))

with col_info2:
    st.metric("Solde total", f"{resultat_final['SoldeJournalier'].sum():,.2f}")

with col_info3:
    st.metric("Nombre d'années", resultat["Annee"].nunique())

st.dataframe(resultat_affichage, use_container_width=True)


st.subheader("Visualisation graphique")

type_graphique = st.radio(
    "Type de graphique",
    [
        "Solde journalier",
        "Solde mensuel",
        "Cumul annuel pour visualisation"
    ],
    horizontal=True
)

if type_graphique == "Solde journalier":
    df_graph = resultat.copy()
    y_col = "SoldeJournalier"
    titre = "Solde journalier de la plage de comptes"

elif type_graphique == "Solde mensuel":
    df_graph = (
        resultat
        .groupby("Mois", as_index=False)["SoldeJournalier"]
        .sum()
    )
    df_graph["Date"] = pd.to_datetime(df_graph["Mois"] + "-01")
    y_col = "SoldeJournalier"
    titre = "Solde mensuel de la plage de comptes"

else:
    df_graph = resultat.copy()
    df_graph["CumulAnnuel"] = (
        df_graph
        .groupby("Annee")["SoldeJournalier"]
        .cumsum()
    )
    y_col = "CumulAnnuel"
    titre = "Cumul annuel de la plage de comptes, remis à zéro chaque année"


fig = px.line(
    df_graph,
    x="Date",
    y=y_col,
    title=titre,
    markers=False
)

fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Montant",
    hovermode="x unified"
)

fig.update_xaxes(rangeslider_visible=True)

st.plotly_chart(fig, use_container_width=True)


with st.expander("Voir aussi le graphique Pyplot simple"):
    fig_matplotlib, ax = plt.subplots(figsize=(14, 5))
    ax.plot(df_graph["Date"], df_graph[y_col])
    ax.set_title(titre)
    ax.set_xlabel("Date")
    ax.set_ylabel("Montant")
    ax.grid(True)
    st.pyplot(fig_matplotlib)


with st.expander("Voir le détail des écritures prises en compte"):
    detail_ecritures = df_filtre[
        [
            "EcritureDate",
            "CompteNum",
            "Debit",
            "Credit",
            "DebitMoinsCredit",
            "CreditMoinsDebit",
            "Fichier"
        ]
    ].copy()

    detail_ecritures["EcritureDate"] = (
        detail_ecritures["EcritureDate"].dt.strftime("%d/%m/%Y")
    )

    st.dataframe(detail_ecritures, use_container_width=True)


st.subheader("Exports")

csv = resultat_affichage.to_csv(
    index=False,
    sep=";",
    decimal=","
).encode("utf-8-sig")

st.download_button(
    label="Télécharger en CSV",
    data=csv,
    file_name="solde_journalier_fec.csv",
    mime="text/csv"
)

excel = exporter_excel(resultat_affichage, sheet_name="Solde journalier")

st.download_button(
    label="Télécharger en Excel",
    data=excel,
    file_name="solde_journalier_fec.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
