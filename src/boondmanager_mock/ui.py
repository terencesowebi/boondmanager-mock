"""Une vitrine en lecture seule du jeu de données, pour voir ce que le mock contient.

Hors `/api` et hors contrat OpenAPI : ce n'est pas l'API de Boond. Les chemins
reprennent ceux de l'interface web de Boond (`/opportunities/{id}/information`),
si bien qu'un lien vers une fiche, forgé pour le vrai Boond, s'ouvre aussi ici.
"""

from __future__ import annotations

import json
from html import escape
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .state import state

router = APIRouter(include_in_schema=False)

_STYLE = """
body{font-family:system-ui,sans-serif;margin:0;background:#fafafa;color:#222}
.bandeau{background:#b42318;color:#fff;padding:12px 16px;font-weight:600}
.bandeau small{display:block;font-weight:400;opacity:.9;margin-top:4px}
main{padding:16px;max-width:1200px;margin:auto}
table{border-collapse:collapse;width:100%;background:#fff}
th,td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top;font-size:14px}
th{background:#f0f0f0}
a{color:#1d4ed8}
pre{white-space:pre-wrap;margin:0;font-size:13px}
form{margin:12px 0}
"""

_BANDEAU = (
    '<div class="bandeau">⚠️ MOCK BoondManager — ceci n\'est PAS Boond.'
    "<small>Données fictives servies par boondmanager-mock pour le développement."
    " Rien de ce qui est affiché ici n'existe dans un vrai Boond.</small></div>"
)

_TYPE_VERS_CHEMIN = {
    "company": "companies",
    "contact": "contacts",
    "opportunity": "opportunities",
    "candidate": "candidates",
    "resource": "resources",
    "project": "projects",
    "agency": "agencies",
    "pole": "poles",
}


@router.get("/", response_class=HTMLResponse)
def accueil() -> HTMLResponse:
    lignes = "".join(
        f"<tr><td><a href='/{chemin}'>{escape(chemin)}</a></td><td>{len(_elements(cle))}</td></tr>"
        for chemin, cle in sorted(_collections().items())
    )
    return _page(
        "Accueil",
        "<h1>Contenu du mock</h1><table><tr><th>Collection</th><th>Fiches</th></tr>"
        f"{lignes}</table><p><a href='/docs'>API (OpenAPI)</a></p>",
    )


@router.get("/{chemin}", response_class=HTMLResponse)
def liste(chemin: str, q: str = "") -> HTMLResponse:
    cle = _collections().get(chemin)
    if cle is None:
        return _page("Introuvable", f"<p>Collection inconnue : {escape(chemin)}</p>")
    cherche = q.strip().lower()
    elements = [e for e in _elements(cle) if not cherche or cherche in _json(e).lower()]
    lignes = "".join(
        f"<tr><td>{_lien(chemin, str(e['id']), escape(str(e['id'])))}</td>"
        f"<td>{escape(_libelle(e))}</td></tr>"
        for e in reversed(elements)
    )
    return _page(
        chemin,
        f"<p><a href='/'>← Accueil</a></p><h1>{escape(chemin)} ({len(elements)})</h1>"
        f"<form><input name='q' value='{escape(q)}' placeholder='Rechercher'>"
        " <button>OK</button></form>"
        f"<table><tr><th>Id</th><th>Libellé</th></tr>{lignes}</table>",
    )


@router.get("/{chemin}/{item_id}/information", response_class=HTMLResponse)
def fiche(chemin: str, item_id: str) -> HTMLResponse:
    cle = _collections().get(chemin)
    elements = _elements(cle) if cle else []
    element = next((e for e in elements if str(e.get("id")) == item_id), None)
    if element is None:
        return _page(
            "Introuvable", f"<p>Fiche introuvable : {escape(chemin)} #{escape(item_id)}</p>"
        )
    attributs = "".join(
        f"<tr><th>{escape(nom)}</th><td><pre>{escape(_json(valeur))}</pre></td></tr>"
        for nom, valeur in (element.get("attributes") or {}).items()
    )
    relations = "".join(
        f"<tr><th>{escape(nom)}</th><td>{_relation(valeur)}</td></tr>"
        for nom, valeur in (element.get("relationships") or {}).items()
    )
    return _page(
        f"{chemin} #{item_id}",
        f"<p><a href='/{chemin}'>← {escape(chemin)}</a></p><h1>{escape(_libelle(element))}</h1>"
        f"<h2>Attributs</h2><table>{attributs}</table>"
        f"<h2>Relations</h2><table>{relations}</table>",
    )


def _page(titre: str, corps: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Mock Boond — {escape(titre)}</title><style>{_STYLE}</style></head>"
        f"<body>{_BANDEAU}<main>{corps}</main></body></html>"
    )


def _collections() -> dict[str, str]:
    """Segment d'URL → clé du jeu de données, pour toutes les collections servies."""
    from .app import COLLECTIONS

    return {spec.chemin: spec.cle_dataset for spec in COLLECTIONS}


def _elements(cle: str) -> list[dict[str, Any]]:
    elements = state.dataset.get(cle, [])
    return elements if isinstance(elements, list) else []


def _libelle(element: dict[str, Any]) -> str:
    attributs = element.get("attributes") or {}
    for champ in ("title", "name", "reference", "number"):
        if attributs.get(champ):
            return str(attributs[champ])
    personne = f"{attributs.get('firstName', '')} {attributs.get('lastName', '')}".strip()
    return personne or f"#{element.get('id')}"


def _relation(valeur: Any) -> str:
    data = valeur.get("data") if isinstance(valeur, dict) else None
    cibles = data if isinstance(data, list) else [data] if data else []
    if not cibles:
        return "—"
    liens = []
    for cible in cibles:
        chemin = _TYPE_VERS_CHEMIN.get(cible.get("type", ""))
        texte = escape(f"{cible.get('type')} #{cible.get('id')}")
        liens.append(_lien(chemin, str(cible.get("id")), texte) if chemin else texte)
    return ", ".join(liens)


def _lien(chemin: str, item_id: str, texte_echappe: str) -> str:
    return f"<a href='/{chemin}/{escape(item_id)}/information'>{texte_echappe}</a>"


def _json(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, indent=1)
