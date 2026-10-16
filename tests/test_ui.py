"""La vitrine HTML : voir le contenu du mock, sans jamais passer pour Boond."""

from __future__ import annotations

from conftest import JWT

BANDEAU = "ceci n'est PAS Boond"


def test_l_accueil_liste_les_collections_sous_le_bandeau(client) -> None:
    page = client.get("/")

    assert page.status_code == 200
    assert BANDEAU in page.text
    assert "href='/opportunities'" in page.text


def test_une_collection_liste_ses_fiches(client) -> None:
    page = client.get("/companies")

    assert BANDEAU in page.text
    assert "/companies/1/information" in page.text


def test_la_recherche_filtre_les_fiches(client) -> None:
    client.post(
        "/api/companies",
        json={"data": {"type": "company", "attributes": {"name": "Vitrine Zéphyr"}}},
        headers=JWT,
    )

    page = client.get("/companies?q=zéphyr")

    assert "Vitrine Zéphyr" in page.text
    assert "(1)" in page.text


def test_une_fiche_s_ouvre_au_chemin_de_l_interface_boond(client) -> None:
    cree = client.post(
        "/api/opportunities",
        json={
            "data": {
                "type": "opportunity",
                "attributes": {"title": "Dev Java", "reference": "malt::ao-1"},
            }
        },
        headers=JWT,
    ).json()["data"]

    page = client.get(f"/opportunities/{cree['id']}/information")

    assert BANDEAU in page.text
    assert "Dev Java" in page.text
    assert "malt::ao-1" in page.text


def test_une_fiche_se_lit_comme_un_texte(client) -> None:
    """Retours à la ligne interprétés, liens cliquables, valeurs sans guillemets
    JSON, champs vides rangés à part."""
    description = "Refonte du SI.\n\nClient : ENGIE\n\nAnnonce :\nhttps://malt.fr/ao-42."
    cree = client.post(
        "/api/opportunities",
        json={"data": {"type": "opportunity", "attributes": {"title": "Dev Java"}}},
        headers=JWT,
    ).json()["data"]
    client.put(
        f"/api/opportunities/{cree['id']}/information",
        json={
            "data": {
                "id": cree["id"],
                "type": "opportunity",
                "attributes": {"description": description},
            }
        },
        headers=JWT,
    )

    page = client.get(f"/opportunities/{cree['id']}/information").text

    assert "<div class='texte'>Refonte du SI.\n\nClient : ENGIE" in page
    assert "\\n" not in page
    assert "<a href='https://malt.fr/ao-42'>https://malt.fr/ao-42</a>." in page
    assert "<span class='valeur'>Dev Java</span>" in page
    assert "Champs vides" in page


def test_une_fiche_inconnue_le_dit(client) -> None:
    assert "Fiche introuvable" in client.get("/opportunities/999999/information").text
    assert "Collection inconnue" in client.get("/inconnue").text


def test_la_vitrine_n_entre_pas_au_contrat_de_l_api(client) -> None:
    chemins = client.get("/openapi.json").json()["paths"]

    assert all(chemin.startswith(("/api", "/health")) for chemin in chemins)
