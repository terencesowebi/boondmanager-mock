"""Écriture : créer et modifier des opportunités et des candidats."""

from __future__ import annotations

from typing import Any

from conftest import JWT


def _opportunite(**attributs: Any) -> dict[str, Any]:
    return {"data": {"type": "opportunity", "attributes": {"title": "Refonte data", **attributs}}}


def _candidat(**attributs: Any) -> dict[str, Any]:
    return {
        "data": {
            "type": "candidate",
            "attributes": {"firstName": "Awa", "lastName": "Diop", **attributs},
        }
    }


def test_creer_une_opportunite_la_rend_et_la_sert_ensuite(client) -> None:
    corps = _opportunite(place="Lyon")
    corps["data"]["relationships"] = {"company": {"data": {"id": "4", "type": "company"}}}

    reponse = client.post("/api/opportunities", json=corps, headers=JWT)

    assert reponse.status_code == 200
    cree = reponse.json()["data"]
    assert cree["type"] == "opportunity"
    assert cree["attributes"]["title"] == "Refonte data"
    assert cree["attributes"]["place"] == "Lyon"
    assert cree["relationships"]["company"]["data"] == {"id": "4", "type": "company"}
    relu = client.get(f"/api/opportunities/{cree['id']}", headers=JWT).json()["data"]
    assert relu["attributes"]["title"] == "Refonte data"


def test_une_creation_a_la_forme_des_fiches_du_jeu(client) -> None:
    existante = client.get("/api/opportunities/1", headers=JWT).json()["data"]

    cree = client.post("/api/opportunities", json=_opportunite(), headers=JWT).json()["data"]

    assert set(cree["attributes"]) == set(existante["attributes"])
    assert set(cree["relationships"]) == set(existante["relationships"])
    assert cree["relationships"]["mainManager"]["data"] == {"id": "1", "type": "resource"}


def test_une_creation_passe_au_dessus_du_curseur_incremental(client) -> None:
    dates = [
        o["attributes"]["updateDate"]
        for o in client.get("/api/opportunities?maxResults=500", headers=JWT).json()["data"]
    ]

    cree = client.post("/api/opportunities", json=_opportunite(), headers=JWT).json()["data"]

    assert cree["attributes"]["updateDate"] > max(dates)
    assert cree["attributes"]["creationDate"] == cree["attributes"]["updateDate"]


def test_creer_un_candidat(client) -> None:
    reponse = client.post("/api/candidates", json=_candidat(email1="awa@exemple.fr"), headers=JWT)

    assert reponse.status_code == 200
    cree = reponse.json()["data"]
    assert (cree["attributes"]["firstName"], cree["attributes"]["lastName"]) == ("Awa", "Diop")
    assert client.get(f"/api/candidates/{cree['id']}", headers=JWT).status_code == 200


def test_deux_creations_ont_deux_identifiants(client) -> None:
    premier = client.post("/api/candidates", json=_candidat(), headers=JWT).json()["data"]
    second = client.post("/api/candidates", json=_candidat(), headers=JWT).json()["data"]

    assert premier["id"] != second["id"]


def test_un_champ_obligatoire_manquant_donne_422(client) -> None:
    reponse = client.post(
        "/api/candidates",
        json={"data": {"type": "candidate", "attributes": {"firstName": "Awa"}}},
        headers=JWT,
    )

    assert reponse.status_code == 422
    assert reponse.json()["errors"][0]["status"] == "422"


def test_un_attribut_inconnu_est_refuse_pas_ignore(client) -> None:
    reponse = client.post("/api/opportunities", json=_opportunite(titre="faute"), headers=JWT)

    assert reponse.status_code == 422


def test_une_relation_vers_une_entite_inconnue_donne_422(client) -> None:
    corps = _opportunite()
    corps["data"]["relationships"] = {"company": {"data": {"id": "999999", "type": "company"}}}

    reponse = client.post("/api/opportunities", json=corps, headers=JWT)

    assert reponse.status_code == 422
    assert reponse.json()["errors"][0]["source"]["parameter"] == "data/relationships/company"


def test_un_type_qui_ne_correspond_pas_a_la_route_donne_422(client) -> None:
    corps = _candidat()
    corps["data"]["type"] = "opportunity"

    assert client.post("/api/candidates", json=corps, headers=JWT).status_code == 422


def test_un_corps_qui_n_est_pas_du_json_donne_422(client) -> None:
    reponse = client.post(
        "/api/candidates",
        content=b"pas du json",
        headers={**JWT, "Content-Type": "application/json"},
    )

    assert reponse.status_code == 422


def test_modifier_une_opportunite_change_ses_attributs_et_son_horodatage(client) -> None:
    avant = client.get("/api/opportunities/1", headers=JWT).json()["data"]
    corps = {
        "data": {
            "id": "1",
            "type": "opportunity",
            "attributes": {"state": 2, "place": "Rennes"},
            "relationships": {"contact": {"data": {"id": "11", "type": "contact"}}},
        }
    }

    reponse = client.put("/api/opportunities/1/information", json=corps, headers=JWT)

    assert reponse.status_code == 200
    apres = client.get("/api/opportunities/1", headers=JWT).json()["data"]
    assert (apres["attributes"]["state"], apres["attributes"]["place"]) == (2, "Rennes")
    assert apres["attributes"]["title"] == avant["attributes"]["title"]
    assert apres["relationships"]["contact"]["data"] == {"id": "11", "type": "contact"}
    assert apres["attributes"]["updateDate"] > avant["attributes"]["updateDate"]


def test_modifier_un_candidat_ne_stocke_pas_les_options_d_import(client) -> None:
    corps = {
        "data": {
            "id": "1",
            "type": "candidate",
            "attributes": {"town": "Lille", "importResumes": True},
        }
    }

    reponse = client.put("/api/candidates/1/information", json=corps, headers=JWT)

    assert reponse.status_code == 200
    attributs = client.get("/api/candidates/1", headers=JWT).json()["data"]["attributes"]
    assert attributs["town"] == "Lille"
    assert "importResumes" not in attributs


def test_modifier_une_fiche_inconnue_donne_404(client) -> None:
    corps = {"data": {"id": "999999", "type": "candidate", "attributes": {"town": "Lille"}}}

    assert (
        client.put("/api/candidates/999999/information", json=corps, headers=JWT).status_code == 404
    )


def test_un_identifiant_qui_ne_correspond_pas_a_la_route_donne_422(client) -> None:
    corps = {"data": {"id": "2", "type": "candidate", "attributes": {"town": "Lille"}}}

    assert client.put("/api/candidates/1/information", json=corps, headers=JWT).status_code == 422


def test_ecrire_exige_d_etre_authentifie(client) -> None:
    assert client.post("/api/opportunities", json=_opportunite()).status_code == 401


def test_une_collection_hors_perimetre_refuse_l_ecriture(client, monkeypatch) -> None:
    from boondmanager_mock.settings import settings

    monkeypatch.setattr(settings, "forbidden_collections", frozenset({"opportunities"}))

    assert client.post("/api/opportunities", json=_opportunite(), headers=JWT).status_code == 403


def _societe(nom: str) -> dict[str, Any]:
    return {"data": {"type": "company", "attributes": {"name": nom}}}


def _contact(societe_id: str, **attributs: Any) -> dict[str, Any]:
    return {
        "data": {
            "type": "contact",
            "attributes": {"firstName": "Léa", "lastName": "Martin", **attributs},
            "relationships": {"company": {"data": {"id": societe_id, "type": "company"}}},
        }
    }


def test_creer_une_societe_puis_un_de_ses_contacts(client) -> None:
    societe = client.post("/api/companies", json=_societe("Boréal Conseil"), headers=JWT)
    assert societe.status_code == 200
    societe_id = societe.json()["data"]["id"]

    contact = client.post(
        "/api/contacts", json=_contact(societe_id, email1="lea@boreal.fr"), headers=JWT
    )

    assert contact.status_code == 200
    cree = contact.json()["data"]
    assert cree["attributes"]["email1"] == "lea@boreal.fr"
    assert cree["relationships"]["company"]["data"] == {"id": societe_id, "type": "company"}
    contacts = client.get(f"/api/companies/{societe_id}/contacts", headers=JWT).json()
    assert [c["id"] for c in contacts["data"]] == [cree["id"]]
    assert contacts["meta"]["totals"]["rows"] == 1


def test_un_contact_exige_sa_societe(client) -> None:
    corps = _contact("1")
    del corps["data"]["relationships"]

    assert client.post("/api/contacts", json=corps, headers=JWT).status_code == 422


def test_un_contact_d_une_societe_inconnue_donne_422(client) -> None:
    assert client.post("/api/contacts", json=_contact("999999"), headers=JWT).status_code == 422


def test_une_societe_exige_son_nom(client) -> None:
    corps = {"data": {"type": "company", "attributes": {}}}

    assert client.post("/api/companies", json=corps, headers=JWT).status_code == 422


def test_les_contacts_d_une_societe_inconnue_donnent_404(client) -> None:
    assert client.get("/api/companies/999999/contacts", headers=JWT).status_code == 404


def test_rechercher_une_societe_par_son_nom_seulement(client) -> None:
    client.post("/api/companies", json=_societe("Nébuleuse Ingénierie"), headers=JWT)

    par_nom = client.get("/api/companies?keywordsType=name&keywords=nébuleuse", headers=JWT).json()[
        "data"
    ]

    assert [s["attributes"]["name"] for s in par_nom] == ["Nébuleuse Ingénierie"]


def test_retrouver_une_opportunite_par_sa_reference(client) -> None:
    client.post("/api/opportunities", json=_opportunite(reference="malt::ao-4242"), headers=JWT)

    trouvees = client.get("/api/opportunities?keywords=malt::ao-4242", headers=JWT).json()["data"]

    assert [o["attributes"]["reference"] for o in trouvees] == ["malt::ao-4242"]
