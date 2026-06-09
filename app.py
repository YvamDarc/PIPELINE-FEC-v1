import streamlit as st

st.set_page_config(
    page_title="Analyse FEC",
    layout="wide"
)

st.title("Application d'analyse FEC")

st.write("""
Bienvenue dans l'application d'analyse FEC.

Utilise le menu latéral pour accéder aux différentes pages :

- **Solde journalier FEC** : calcul du solde jour par jour d'une plage de comptes.
- **Merge avec tableau externe** : calcul du solde journalier puis fusion avec un fichier Excel ou CSV externe.
""")
