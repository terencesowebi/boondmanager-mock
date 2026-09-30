"""Persistance : l'état survit au redémarrage quand `BOOND_MOCK_DATA_FILE` est posé."""

from __future__ import annotations

import importlib
import json

import pytest
from conftest import JWT
from fastapi.testclient import TestClient

from boondmanager_mock import persistance
from boondmanager_mock.settings import settings

#: Le paquet exporte l'OBJET `state`, qui masque le module du même nom.
module_state = importlib.import_module("boondmanager_mock.state")


@pytest.fixture()
def fichier(tmp_path, monkeypatch):
    chemin = tmp_path / "donnees" / "etat.json"
    monkeypatch.setattr(settings, "data_file", str(chemin))
    yield chemin
    module_state.state.reset()


def _redemarrer() -> TestClient:
    """Reconstruit l'état partagé comme au démarrage du processus : les modules qui
    le référencent voient le même objet, relu depuis le fichier."""
    module_state.state.__init__()
    return TestClient(importlib.import_module("boondmanager_mock.app").app)


def test_sans_fichier_rien_n_est_ecrit(client, tmp_path) -> None:
    client.post(
        "/api/candidates",
        json={"data": {"type": "candidate", "attributes": {"firstName": "A", "lastName": "B"}}},
        headers=JWT,
    )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.usefixtures("fichier")
def test_une_creation_survit_au_redemarrage() -> None:
    client = _redemarrer()
    cree = client.post(
        "/api/candidates",
        json={
            "data": {"type": "candidate", "attributes": {"firstName": "Awa", "lastName": "Diop"}}
        },
        headers=JWT,
    ).json()["data"]

    relu = _redemarrer().get(f"/api/candidates/{cree['id']}", headers=JWT)

    assert relu.status_code == 200
    assert relu.json()["data"]["attributes"]["lastName"] == "Diop"


def test_le_premier_demarrage_ecrit_le_monde_de_la_graine(fichier) -> None:
    _redemarrer()

    contenu = json.loads(fichier.read_text(encoding="utf-8"))
    assert contenu["format"] == persistance.VERSION_FORMAT
    assert contenu["dataset"]["opportunities"]


@pytest.mark.usefixtures("fichier")
def test_le_redemarrage_ne_rejoue_pas_la_vie_de_l_entreprise() -> None:
    premier = module_state.MockState()
    premier.evolution.appliques = 7
    premier.invalider_caches()

    second = module_state.MockState()

    assert second.evolution.appliques == 7
    assert second.evolution.demarrage == premier.evolution.demarrage


def test_un_fichier_illisible_ou_d_un_autre_format_repart_de_la_graine(fichier) -> None:
    fichier.parent.mkdir(parents=True)
    fichier.write_text("{pas du json", encoding="utf-8")
    assert persistance.charger(str(fichier)) is None

    fichier.write_text(json.dumps({"format": 999}), encoding="utf-8")
    assert persistance.charger(str(fichier)) is None

    assert module_state.MockState().dataset["opportunities"]


def test_une_sauvegarde_interrompue_laisse_l_ancien_etat(fichier, monkeypatch) -> None:
    persistance.sauvegarder(str(fichier), {"dataset": {"ancien": True}})

    def echec(*_args, **_kwargs):
        raise OSError("disque plein")

    with monkeypatch.context() as patch, pytest.raises(OSError):
        patch.setattr(persistance.json, "dump", echec)
        persistance.sauvegarder(str(fichier), {"dataset": {"nouveau": True}})

    assert persistance.charger(str(fichier))["dataset"] == {"ancien": True}
    assert [f.name for f in fichier.parent.iterdir()] == ["etat.json"]
