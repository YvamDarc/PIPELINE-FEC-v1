import pandas as pd


def lire_fichier_externe(uploaded_file):
    nom = uploaded_file.name.lower()

    if nom.endswith(".csv"):
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=";", dtype=str, encoding="utf-8")
        except Exception:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=",", dtype=str, encoding="utf-8")
    elif nom.endswith(".xlsx"):
        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, dtype=str)
    elif nom.endswith(".xls"):
        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, dtype=str)
    else:
        raise ValueError("Format non pris en charge. Utilise CSV, XLSX ou XLS.")

    df.columns = df.columns.astype(str).str.strip()

    return df


def normaliser_date(serie, format_date=None):
    """
    Convertit une colonne en date.
    Si format_date est renseigné, on force ce format.
    Sinon pandas tente de reconnaître automatiquement.
    """

    if format_date and format_date != "Reconnaissance automatique":
        return pd.to_datetime(
            serie,
            format=format_date,
            errors="coerce"
        )

    return pd.to_datetime(
        serie,
        errors="coerce",
        dayfirst=True
    )


def proposer_formats_date():
    return [
        "Reconnaissance automatique",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%Y%m%d",
        "%d-%m-%Y",
        "%m/%d/%Y"
    ]


def nettoyer_colonne_pour_merge(serie):
    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
    )
