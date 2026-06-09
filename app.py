import streamlit as st
import pandas as pd
from io import BytesIO


st.set_page_config(
    page_title="Cumul journalier FEC",
    layout="wide"
)

st.title("Cumul journalier par plage de comptes depuis plusieurs FEC")


# -----------------------------
# Fonctions utilitaires
# -----------------------------

def lire_fec(uploaded_file: BytesIO) -> pd.DataFrame:
    """
    Lecture robuste d'un fichier FEC.
    Le FEC est généralement séparé par tabulation.
    """
    try:
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


def convertir_montant(serie: pd.Series) -> pd.Series:
    """
    Convertit les montants FEC en nombre.
    Gère les virgules décimales françaises.
    """
    return (
        serie.fillna("0")
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .replace("", "0")
        .astype(float)
    )


def preparer_fec(df: pd.DataFrame, nom_fichier: str) -> pd.DataFrame:
    """
    Prépare un FEC :
    - vérifie les colonnes utiles
    - convertit date, compte, débit, crédit
    - calcule le montant net débit - crédit
    """

    colonnes_obligatoires = [
        "CompteNum",
        "EcritureDate",
        "Debit",
        "Credit"
    ]

    colonnes_manquantes = [
        col for col in colonnes_obligatoires if col not in df.columns
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

    df["MontantDebitCredit"] = df["Debit"] - df["Credit"]
    df["MontantCreditDebit"] = df["Credit"] - df["Debit"]

    df["Fichier"] = nom_fichier

    df = df.dropna(subset=["EcritureDate"])

    return df


def exporter_excel(df: pd.DataFrame) -> bytes:
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Cumul journalier")

    return output.getvalue()


# -----------------------------
# Import des FEC
# -----------------------------

uploaded_files = st.file_uploader(
    "Importer jusqu'à 6 fichiers FEC",
    type=["txt", "csv"],
    accept_multiple_files=True
)

if uploaded_files:

    if len(uploaded_files) > 6:
        st.error("Tu peux importer 6 FEC maximum.")
        st.stop()

    fecs = []

    for fichier in uploaded_files:
        try:
            df_brut = lire_fec(fichier)
            df_pret = preparer_fec(df_brut, fichier.name)
            fecs.append(df_pret)
        except Exception as e:
            st.error(f"Erreur sur le fichier {fichier.name} : {e}")
            st.stop()

    df = pd.concat(fecs, ignore_index=True)

    st.success(f"{len(uploaded_files)} fichier(s) FEC chargé(s).")

    # -----------------------------
    # Paramètres utilisateur
    # -----------------------------

    st.subheader("Paramètres de sélection")

    col1, col2, col3 = st.columns(3)

    with col1:
        compte_debut = st.text_input(
            "Compte de début",
            value="600000000"
        )

    with col2:
        compte_fin = st.text_input(
            "Compte de fin",
            value="699999999"
        )

    with col3:
        sens = st.selectbox(
            "Sens du montant",
            [
                "Débit - Crédit",
                "Crédit - Débit"
            ]
        )

    montant_col = (
        "MontantDebitCredit"
        if sens == "Débit - Crédit"
        else "MontantCreditDebit"
    )

    # -----------------------------
    # Filtre par plage de comptes
    # -----------------------------

    df_filtre = df[
        (df["CompteNum"] >= compte_debut)
        & (df["CompteNum"] <= compte_fin)
    ].copy()

    if df_filtre.empty:
        st.warning("Aucune écriture trouvée sur cette plage de comptes.")
        st.stop()

    # -----------------------------
    # Détermination des années complètes
    # -----------------------------

    annees = sorted(df["EcritureDate"].dt.year.dropna().unique())

    calendrier = []

    for annee in annees:
        debut = pd.Timestamp(year=int(annee), month=1, day=1)
        fin = pd.Timestamp(year=int(annee), month=12, day=31)

        calendrier_annee = pd.DataFrame({
            "Date": pd.date_range(debut, fin, freq="D")
        })

        calendrier.append(calendrier_annee)

    calendrier = pd.concat(calendrier, ignore_index=True)

    # -----------------------------
    # Cumul journalier
    # -----------------------------

    mouvements_journaliers = (
        df_filtre
        .groupby("EcritureDate", as_index=False)[montant_col]
        .sum()
        .rename(columns={
            "EcritureDate": "Date",
            montant_col: "MontantJour"
        })
    )

    resultat = calendrier.merge(
        mouvements_journaliers,
        on="Date",
        how="left"
    )

    resultat["MontantJour"] = resultat["MontantJour"].fillna(0)

    resultat["MontantCumule"] = resultat["MontantJour"].cumsum()

    resultat_final = resultat[["Date", "MontantCumule"]].copy()

    resultat_final["Date"] = resultat_final["Date"].dt.strftime("%d/%m/%Y")

    # -----------------------------
    # Affichage
    # -----------------------------

    st.subheader("Résultat")

    st.write(
        f"Nombre de jours générés : **{len(resultat_final)}**"
    )

    st.dataframe(
        resultat_final,
        use_container_width=True
    )

    # -----------------------------
    # Détail optionnel
    # -----------------------------

    with st.expander("Voir le détail avec le montant du jour"):
        detail = resultat.copy()
        detail["Date"] = detail["Date"].dt.strftime("%d/%m/%Y")

        st.dataframe(
            detail[["Date", "MontantJour", "MontantCumule"]],
            use_container_width=True
        )

    # -----------------------------
    # Exports
    # -----------------------------

    st.subheader("Exports")

    csv = resultat_final.to_csv(
        index=False,
        sep=";",
        decimal=","
    ).encode("utf-8-sig")

    st.download_button(
        label="Télécharger en CSV",
        data=csv,
        file_name="cumul_journalier_fec.csv",
        mime="text/csv"
    )

    excel = exporter_excel(resultat_final)

    st.download_button(
        label="Télécharger en Excel",
        data=excel,
        file_name="cumul_journalier_fec.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Importe un ou plusieurs fichiers FEC pour commencer.")
