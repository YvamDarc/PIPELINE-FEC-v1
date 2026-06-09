import pandas as pd
from io import BytesIO


def lire_fec(uploaded_file):
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
    return (
        serie.fillna("0")
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .replace("", "0")
        .astype(float)
    )


def preparer_fec(df, nom_fichier):
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


def charger_plusieurs_fec(uploaded_files, max_files=6):
    if len(uploaded_files) > max_files:
        raise ValueError(f"Tu peux importer {max_files} FEC maximum.")

    fecs = []

    for fichier in uploaded_files:
        df_brut = lire_fec(fichier)
        df_prepare = preparer_fec(df_brut, fichier.name)
        fecs.append(df_prepare)

    return pd.concat(fecs, ignore_index=True)


def creer_calendrier_complet(df):
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

    return calendrier, annees


def calculer_solde_journalier(df, compte_debut, compte_fin, sens):
    colonne_montant = (
        "DebitMoinsCredit"
        if sens == "Débit - Crédit"
        else "CreditMoinsDebit"
    )

    df_filtre = df[
        (df["CompteNum"] >= compte_debut)
        & (df["CompteNum"] <= compte_fin)
    ].copy()

    if df_filtre.empty:
        return None, None

    calendrier, annees = creer_calendrier_complet(df)

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

    return resultat, df_filtre


def exporter_excel(df, sheet_name="Export"):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

    return output.getvalue()
