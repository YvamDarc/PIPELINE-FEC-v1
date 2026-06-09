import pandas as pd
import numpy as np
import holidays


def convertir_colonne_numerique(serie):
    """
    Convertit une série en numérique.
    Gère les virgules françaises, les espaces et les chaînes vides.
    """
    return (
        serie
        .fillna("0")
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace("\u202f", "", regex=False)
        .str.replace(",", ".", regex=False)
        .replace("", "0")
        .pipe(pd.to_numeric, errors="coerce")
    )


def convertir_colonne_date(serie, format_date=None, dayfirst=True):
    """
    Convertit une colonne en date.
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
        dayfirst=dayfirst
    )


def ajouter_variables_calendaires(df, colonne_date):
    """
    Ajoute des variables calendaires classiques.
    """
    df = df.copy()

    df["Annee"] = df[colonne_date].dt.year
    df["Mois"] = df[colonne_date].dt.month
    df["Jour"] = df[colonne_date].dt.day
    df["JourSemaine_Num"] = df[colonne_date].dt.weekday
    df["JourSemaine_Nom"] = df[colonne_date].dt.day_name(locale=None)
    df["Semaine_ISO"] = df[colonne_date].dt.isocalendar().week.astype(int)
    df["Trimestre"] = df[colonne_date].dt.quarter
    df["JourAnnee"] = df[colonne_date].dt.dayofyear

    df["Est_Weekend"] = df["JourSemaine_Num"].isin([5, 6]).astype(int)

    df["Debut_Mois"] = df[colonne_date].dt.is_month_start.astype(int)
    df["Fin_Mois"] = df[colonne_date].dt.is_month_end.astype(int)

    df["Debut_Trimestre"] = df[colonne_date].dt.is_quarter_start.astype(int)
    df["Fin_Trimestre"] = df[colonne_date].dt.is_quarter_end.astype(int)

    df["Debut_Annee"] = df[colonne_date].dt.is_year_start.astype(int)
    df["Fin_Annee"] = df[colonne_date].dt.is_year_end.astype(int)

    return df


def ajouter_lags(df, colonne_valeur, lags):
    """
    Ajoute des variables de retard.
    Exemple : J-1, J-7, J-30.
    """
    df = df.copy()

    for lag in lags:
        df[f"{colonne_valeur}_Lag_{lag}j"] = df[colonne_valeur].shift(lag)

    return df


def ajouter_moyennes_mobiles(df, colonne_valeur, fenetres):
    """
    Ajoute des moyennes mobiles.
    """
    df = df.copy()

    for fenetre in fenetres:
        df[f"{colonne_valeur}_MM_{fenetre}j"] = (
            df[colonne_valeur]
            .rolling(window=fenetre, min_periods=1)
            .mean()
        )

    return df


def ajouter_sommes_mobiles(df, colonne_valeur, fenetres):
    """
    Ajoute des sommes mobiles.
    Utile pour obtenir un CA glissant 7j, 30j, etc.
    """
    df = df.copy()

    for fenetre in fenetres:
        df[f"{colonne_valeur}_SommeMobile_{fenetre}j"] = (
            df[colonne_valeur]
            .rolling(window=fenetre, min_periods=1)
            .sum()
        )

    return df


def ajouter_ecarts(df, colonne_valeur, lags):
    """
    Ajoute des écarts par rapport aux périodes précédentes.
    """
    df = df.copy()

    for lag in lags:
        col_lag = f"{colonne_valeur}_Lag_{lag}j"

        if col_lag not in df.columns:
            df[col_lag] = df[colonne_valeur].shift(lag)

        df[f"{colonne_valeur}_Ecart_{lag}j"] = (
            df[colonne_valeur] - df[col_lag]
        )

    return df


def ajouter_variations_pourcentage(df, colonne_valeur, lags):
    """
    Ajoute des variations en pourcentage par rapport aux périodes précédentes.
    """
    df = df.copy()

    for lag in lags:
        col_lag = f"{colonne_valeur}_Lag_{lag}j"

        if col_lag not in df.columns:
            df[col_lag] = df[colonne_valeur].shift(lag)

        variation = (
            (df[colonne_valeur] - df[col_lag])
            / df[col_lag].replace(0, np.nan)
        ) * 100

        df[f"{colonne_valeur}_Variation_{lag}j_%"] = variation

    return df


def ajouter_cumuls(df, colonne_date, colonne_valeur):
    """
    Ajoute des cumuls mensuels et annuels.
    """
    df = df.copy()

    df["_Annee_Temp"] = df[colonne_date].dt.year
    df["_Mois_Temp"] = df[colonne_date].dt.to_period("M")

    df[f"{colonne_valeur}_Cumul_Mensuel"] = (
        df
        .groupby("_Mois_Temp")[colonne_valeur]
        .cumsum()
    )

    df[f"{colonne_valeur}_Cumul_Annuel"] = (
        df
        .groupby("_Annee_Temp")[colonne_valeur]
        .cumsum()
    )

    df = df.drop(columns=["_Annee_Temp", "_Mois_Temp"])

    return df


def ajouter_jours_feries_france(df, colonne_date):
    """
    Ajoute une colonne indiquant si le jour est férié en France.
    """
    df = df.copy()

    annees = sorted(df[colonne_date].dt.year.dropna().unique())

    jours_feries = holidays.France(years=annees)

    df["Est_Jour_Ferie"] = df[colonne_date].dt.date.isin(jours_feries).astype(int)

    df["Nom_Jour_Ferie"] = df[colonne_date].dt.date.map(
        lambda x: jours_feries.get(x, "")
    )

    return df


def ajouter_indicateurs_zero(df, colonne_valeur):
    """
    Ajoute des indicateurs liés aux jours à zéro.
    """
    df = df.copy()

    df[f"{colonne_valeur}_Est_Zero"] = (df[colonne_valeur] == 0).astype(int)
    df[f"{colonne_valeur}_Est_Positif"] = (df[colonne_valeur] > 0).astype(int)
    df[f"{colonne_valeur}_Est_Negatif"] = (df[colonne_valeur] < 0).astype(int)

    return df


def ajouter_valeurs_absolues(df, colonne_valeur):
    """
    Ajoute la valeur absolue.
    Utile pour comparer des flux débit/crédit sans tenir compte du signe.
    """
    df = df.copy()

    df[f"{colonne_valeur}_Abs"] = df[colonne_valeur].abs()

    return df


def completer_dates_manquantes(df, colonne_date, colonne_valeur, frequence="D"):
    """
    Complète les dates manquantes entre la date min et max.
    Les valeurs absentes sont mises à zéro.
    """
    df = df.copy()

    date_min = df[colonne_date].min()
    date_max = df[colonne_date].max()

    calendrier = pd.DataFrame({
        colonne_date: pd.date_range(date_min, date_max, freq=frequence)
    })

    df = calendrier.merge(
        df,
        on=colonne_date,
        how="left"
    )

    df[colonne_valeur] = df[colonne_valeur].fillna(0)

    return df
