import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
from io import BytesIO


st.set_page_config(
    page_title="Solde journalier FEC",
    layout="wide"
)

st.title("Solde journalier par plage de comptes depuis plusieurs FEC")


# --------------------------------------------------
# Fonctions
# --------------------------------------------------

def lire_fec(uploaded_file):
    """
    Lecture d'un FEC.
    Le FEC est normalement séparé par tabulation.
    """
    try:
        uploaded_file.seek(0)
        df = pd.read_csv(
            uploaded_file,
            sep="\t",
            dtype=str,
            encoding="utf-8"
        )
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        df = pd.read_csv(
            uploaded_file,
            sep="\t",
            dtype=str,
            encoding="latin1"
        )

    df.columns = df.columns.str.strip()
    return df


def convertir_montant(serie):
    """
    Convertit les montants du FEC en nombres.
    Gère les virgules françaises.
    """
    return (
        serie.fillna("0")
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .replace("", "0")
        .astype(float)
    )


def preparer_fec(df, nom_fichier):
    """
    Préparation du FEC :
    - contrôle des colonnes utiles
    - conversion de la date
    - conversion des montants
    - calcul débit - crédit et crédit - débit
    """

    colonnes_obligatoires = [
        "CompteNum",
        "EcritureDate",
        "Debit",
        "Credit"
    ]

    colonnes_manquantes = [
        col for col in colonnes_obligatoires
        if col not in df.columns
    ]

    if colonnes_manquantes:
        raise ValueError(
            f"Colonnes manquantes dans {nom_fichier} : {colonnes_manquantes}"
        )

    df = df.copy()

    df["CompteNum"] = df["CompteNum"].astype(str).str.strip()

    df["EcritureDate"] = pd.to_datetime(
        df["EcritureDate"],
        format="%Y%m%d",
        errors="coerce"
    )

    df["Debit"] = convertir_montant(df["Debit"])
    df["Credit"] = convertir_montant(df["Credit"])

    df["DebitMoinsCredit"] = df["Debit"] - df["Credit"]
    df["CreditMoinsDebit"] = df["Credit"] - df["Debit"]

    df["Fichier"] = nom_fichier

    df = df.dropna(subset=["EcritureDate"])

    return df


def exporter_excel(df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Solde journalier")

    return output.getvalue()


# --------------------------------------------------
# Import fichiers
# --------------------------------------------------

uploaded_files = st.file_uploader(
    "Importer jusqu'à 6 fichiers FEC",
    type=["txt", "csv"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("Importe un ou plusieurs fichiers FEC pour commencer.")
    st.stop()

if len(uploaded_files) > 6:
    st.error("Tu peux importer 6 FEC maximum.")
    st.stop()


# --------------------------------------------------
# Lecture des FEC
# --------------------------------------------------

fecs = []

for fichier in uploaded_files:
    try:
        df_brut = lire_fec(fichier)
        df_prepare = preparer_fec(df_brut, fichier.name)
        fecs.append(df_prepare)
    except Exception as e:
        st.error(f"Erreur sur le fichier {fichier.name} : {e}")
        st.stop()

df = pd.concat(fecs, ignore_index=True)

st.success(f"{len(uploaded_files)} fichier(s) FEC chargé(s).")


# --------------------------------------------------
# Paramètres utilisateur
# --------------------------------------------------

st.subheader("Paramètres de sélection")

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
        [
            "Débit - Crédit",
            "Crédit - Débit"
        ]
    )

colonne_montant = (
    "DebitMoinsCredit"
    if sens == "Débit - Crédit"
    else "CreditMoinsDebit"
)


# --------------------------------------------------
# Filtre par plage de comptes
# --------------------------------------------------

df_filtre = df[
    (df["CompteNum"] >= compte_debut)
    & (df["CompteNum"] <= compte_fin)
].copy()

if df_filtre.empty:
    st.warning("Aucune écriture trouvée sur cette plage de comptes.")
    st.stop()


# --------------------------------------------------
# Création du calendrier complet
# --------------------------------------------------

annees = sorted(df["EcritureDate"].dt.year.dropna().unique())

calendriers = []

for annee in annees:
    debut = pd.Timestamp(year=int(annee), month=1, day=1)
    fin = pd.Timestamp(year=int(annee), month=12, day=31)

    calendrier_annee = pd.DataFrame({
        "Date": pd.date_range(debut, fin, freq="D")
    })

    calendriers.append(calendrier_annee)

calendrier = pd.concat(calendriers, ignore_index=True)


# --------------------------------------------------
# Solde journalier
# --------------------------------------------------

soldes_journaliers = (
    df_filtre
    .groupby("EcritureDate", as_index=False)[colonne_montant]
    .sum()
    .rename(columns={
        "EcritureDate": "Date",
        colonne_montant: "SoldeJournalier"
    })
)

resultat = calendrier.merge(
    soldes_journaliers,
    on="Date",
    how="left"
)

resultat["SoldeJournalier"] = resultat["SoldeJournalier"].fillna(0)

resultat["Annee"] = resultat["Date"].dt.year
resultat["Mois"] = resultat["Date"].dt.to_period("M").astype(str)

resultat_final = resultat[["Date", "SoldeJournalier"]].copy()
resultat_final_affichage = resultat_final.copy()
resultat_final_affichage["Date"] = resultat_final_affichage["Date"].dt.strftime("%d/%m/%Y")


# --------------------------------------------------
# Affichage du résultat
# --------------------------------------------------

st.subheader("Résultat")

col_info1, col_info2, col_info3 = st.columns(3)

with col_info1:
    st.metric("Nombre de jours générés", len(resultat_final))

with col_info2:
    st.metric("Solde total de la période", f"{resultat_final['SoldeJournalier'].sum():,.2f}")

with col_info3:
    st.metric("Nombre d'années", len(annees))

st.write(
    f"Plage sélectionnée : **{compte_debut} à {compte_fin}**"
)

st.dataframe(
    resultat_final_affichage,
    use_container_width=True
)


# --------------------------------------------------
# Graphique interactif
# --------------------------------------------------

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

fig.update_xaxes(
    rangeslider_visible=True
)

st.plotly_chart(
    fig,
    use_container_width=True
)

st.caption(
    "Le graphique Plotly permet de zoomer, dézoomer, sélectionner une période et afficher les valeurs au survol."
)


# --------------------------------------------------
# Option matplotlib / pyplot
# --------------------------------------------------

with st.expander("Voir aussi le graphique Pyplot simple"):
    st.write(
        "Ce graphique est statique. Pour zoomer, utilise plutôt le graphique interactif juste au-dessus."
    )

    fig_matplotlib, ax = plt.subplots(figsize=(14, 5))

    if type_graphique == "Solde mensuel":
        ax.plot(df_graph["Date"], df_graph[y_col])
    else:
        ax.plot(df_graph["Date"], df_graph[y_col])

    ax.set_title(titre)
    ax.set_xlabel("Date")
    ax.set_ylabel("Montant")
    ax.grid(True)

    st.pyplot(fig_matplotlib)


# --------------------------------------------------
# Contrôle / détail des écritures
# --------------------------------------------------

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

    st.dataframe(
        detail_ecritures,
        use_container_width=True
    )


with st.expander("Voir le détail journalier avec les jours à zéro"):
    detail_journalier = resultat.copy()
    detail_journalier["Date"] = detail_journalier["Date"].dt.strftime("%d/%m/%Y")

    st.dataframe(
        detail_journalier[["Date", "SoldeJournalier"]],
        use_container_width=True
    )


# --------------------------------------------------
# Exports
# --------------------------------------------------

st.subheader("Exports")

csv = resultat_final_affichage.to_csv(
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

excel = exporter_excel(resultat_final_affichage)

st.download_button(
    label="Télécharger en Excel",
    data=excel,
    file_name="solde_journalier_fec.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
