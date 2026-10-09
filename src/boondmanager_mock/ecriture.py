"""Écriture — créer et modifier des opportunités et des candidats.

Les routes du fournisseur (RAML officiel) :

  POST /api/opportunities                     crée une opportunité
  PUT  /api/opportunities/{id}/information    modifie son onglet « information »
  POST /api/candidates                        crée un candidat
  PUT  /api/candidates/{id}/information       modifie son onglet « information »

Les deux répondent **200** avec la fiche, pas 201 : c'est ce que déclare le
RAML (`resourceTypes/search.raml`, `resourceTypes/base.raml`).

Le corps est validé contre les **schémas JSON officiels** du fournisseur,
recopiés tels quels dans `schemas/` : plutôt que de réécrire à la main les
champs obligatoires et les types, le mock refuse exactement ce que le schéma
refuse. Ces schémas déclarent `additionalProperties: false` sur les attributs :
un attribut inconnu est refusé, pas ignoré — c'est ce qui fait qu'une faute de
frappe côté client se voit en test au lieu de disparaître en silence.

NON VÉRIFIÉ en réel (cf. docs/UNVERIFIED-FIELDS.md) : le `code` métier et le
libellé des 422 de validation. Le mock répond `code: "422"` avec le chemin du
champ fautif dans `source.parameter`.

Une nouvelle fiche prend la FORME des fiches du jeu de données : mêmes clés
d'attributs et de relations, remises à zéro, puis les valeurs fournies. Un
consommateur qui relit sa création retrouve donc exactement la structure qu'il
lit ailleurs.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft7Validator

from .admin import _horodate_apres_tous

#: Le compte au nom duquel le jeton utilisateur du mock agit (cf. /application/current-user).
RESPONSABLE_PAR_DEFAUT = "1"


class RequeteInvalide(Exception):
    """Le corps ne respecte pas le schéma, ou désigne une entité inconnue."""

    def __init__(self, detail: str, parametre: str) -> None:
        super().__init__(detail)
        self.detail = detail
        self.parametre = parametre


@dataclass(frozen=True)
class SpecEcriture:
    """Ce qu'il faut savoir d'une collection pour y écrire."""

    chemin: str
    cle_dataset: str
    type_jsonapi: str
    schema_creation: str
    schema_modification: str
    #: Valeurs par défaut d'une création, au-delà de la remise à zéro générique.
    defauts: dict[str, Any] = field(default_factory=dict)
    #: Attributs du schéma qui sont des OPTIONS de la requête, pas des données
    #: de la fiche : acceptés, puis jamais stockés.
    options: frozenset[str] = frozenset()


ECRITURES: tuple[SpecEcriture, ...] = (
    SpecEcriture(
        "opportunities",
        "opportunities",
        "opportunity",
        "opportunities-post.json",
        "opportunities-information-put.json",
        defauts={
            "isVisible": True,
            "mode": 1,
            "exchangeRate": 1.0,
            "exchangeRateAgency": 1.0,
            "canShowContact": True,
            "canShowCompany": True,
        },
    ),
    SpecEcriture(
        "companies",
        "companies",
        "company",
        "companies-post.json",
        "companies-information-put.json",
    ),
    SpecEcriture(
        "contacts",
        "contacts",
        "contact",
        "contacts-post.json",
        "contacts-information-put.json",
    ),
    SpecEcriture(
        "candidates",
        "candidates",
        "candidate",
        "candidates-post.json",
        "candidates-information-put.json",
        defauts={"isVisible": True, "availability": -1},
        options=frozenset(
            {
                "importResumes",
                "importFiles",
                "importContractFiles",
                "importContract",
                "importFields",
            }
        ),
    ),
)


@cache
def _validateur(nom: str) -> Draft7Validator:
    texte = resources.files("boondmanager_mock.schemas").joinpath(nom).read_text(encoding="utf-8")
    return Draft7Validator(json.loads(texte))


def _valider(nom_schema: str, corps: Any) -> None:
    erreur = next(iter(sorted(_validateur(nom_schema).iter_errors(corps), key=str)), None)
    if erreur is not None:
        chemin = "/".join(str(p) for p in erreur.absolute_path) or "data"
        raise RequeteInvalide(f"422 - Invalid value: {erreur.message}", chemin)


_ZEROS: dict[type, Any] = {bool: False, int: 0, float: 0.0, str: ""}


def _a_zero(valeur: Any) -> Any:
    if isinstance(valeur, list):
        return []
    if isinstance(valeur, dict):
        return {cle: _a_zero(v) for cle, v in valeur.items()}
    return _ZEROS.get(type(valeur))


def _gabarit(items: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Les clés d'attributs et de relations d'une fiche existante, remises à zéro."""
    if not items:
        return {}, {}
    modele = items[0]
    attributs = {cle: _a_zero(v) for cle, v in modele.get("attributes", {}).items()}
    relations = {cle: {"data": None} for cle in (modele.get("relationships") or {})}
    return attributs, relations


def _verifier_relations(relations: dict[str, Any], index: dict[tuple[str, str], Any]) -> None:
    for nom, valeur in relations.items():
        cible = valeur.get("data") if isinstance(valeur, dict) else None
        if cible is not None and (cible["type"], str(cible["id"])) not in index:
            raise RequeteInvalide(
                f"422 - Unknown {cible['type']} {cible['id']}",
                f"data/relationships/{nom}",
            )


def _relations_par_defaut(
    relations: dict[str, Any], index: dict[tuple[str, str], Any]
) -> dict[str, Any]:
    """Le responsable et l'agence de l'utilisateur du jeton, comme le ferait Boond."""
    responsable = index.get(("resource", RESPONSABLE_PAR_DEFAUT))
    if "mainManager" in relations and responsable is not None:
        relations["mainManager"] = {"data": {"id": RESPONSABLE_PAR_DEFAUT, "type": "resource"}}
        agence = (responsable.get("relationships") or {}).get("agency")
        if "agency" in relations and agence is not None:
            relations["agency"] = copy.deepcopy(agence)
    return relations


def creer(
    spec: SpecEcriture,
    dataset: dict[str, Any],
    index: dict[tuple[str, str], Any],
    corps: Any,
) -> dict[str, Any]:
    """Valide, construit et AJOUTE la fiche au jeu de données ; la rend."""
    _valider(spec.schema_creation, corps)
    donnees = corps["data"]
    if donnees["type"] != spec.type_jsonapi:
        raise RequeteInvalide(f"422 - Expected type {spec.type_jsonapi}", "data/type")
    fournies = donnees.get("relationships") or {}
    _verifier_relations(fournies, index)

    items: list[dict[str, Any]] = dataset[spec.cle_dataset]
    attributs, relations = _gabarit(items)
    attributs.update(spec.defauts)
    attributs.update(donnees["attributes"])
    relations = _relations_par_defaut(relations, index)
    relations.update(copy.deepcopy(fournies))

    item: dict[str, Any] = {
        "id": str(max((int(i["id"]) for i in items), default=0) + 1),
        "type": spec.type_jsonapi,
        "attributes": attributs,
        "relationships": relations,
    }
    horodatage = _horodate_apres_tous(items, item)
    if not attributs.get("creationDate"):
        attributs["creationDate"] = horodatage
    attributs["updateDate"] = horodatage
    items.append(item)
    return item


def modifier(
    spec: SpecEcriture,
    dataset: dict[str, Any],
    index: dict[tuple[str, str], Any],
    item_id: str,
    corps: Any,
) -> dict[str, Any] | None:
    """Valide et applique la modification ; `None` si la fiche n'existe pas."""
    _valider(spec.schema_modification, corps)
    donnees = corps["data"]
    if str(donnees["id"]) != item_id:
        raise RequeteInvalide("422 - Identifier does not match the route", "data/id")
    if donnees["type"] != spec.type_jsonapi:
        raise RequeteInvalide(f"422 - Expected type {spec.type_jsonapi}", "data/type")

    items: list[dict[str, Any]] = dataset[spec.cle_dataset]
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        return None
    fournies = donnees.get("relationships") or {}
    _verifier_relations(fournies, index)

    attributs = {
        cle: v for cle, v in (donnees.get("attributes") or {}).items() if cle not in spec.options
    }
    item.setdefault("attributes", {}).update(attributs)
    item.setdefault("relationships", {}).update(copy.deepcopy(fournies))
    item["attributes"]["updateDate"] = _horodate_apres_tous(items, item)
    return item
