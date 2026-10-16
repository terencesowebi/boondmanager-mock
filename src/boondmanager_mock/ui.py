"""Une vitrine en lecture seule du jeu de données, pour voir ce que le mock contient.

Hors `/api` et hors contrat OpenAPI : ce n'est pas l'API de Boond. Les chemins
reprennent ceux de l'interface web de Boond (`/opportunities/{id}/information`),
si bien qu'un lien vers une fiche, forgé pour le vrai Boond, s'ouvre aussi ici.
"""

from __future__ import annotations

import json
import re
from html import escape
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .state import state

router = APIRouter(include_in_schema=False)

_STYLE = """
:root{--fond:#f6f7f9;--carte:#fff;--trait:#e3e6eb;--texte:#1f2328;--doux:#667085;--lien:#1d4ed8}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:var(--fond);
  color:var(--texte);line-height:1.5}
.bandeau{background:#b42318;color:#fff;padding:12px 16px;font-weight:600}
.bandeau small{display:block;font-weight:400;opacity:.9;margin-top:4px}
main{padding:24px 16px;max-width:1100px;margin:auto}
h1{font-size:1.6rem;margin:.2rem 0 .3rem}
h2{font-size:1rem;margin:2rem 0 .6rem;color:var(--doux);font-weight:600}
.meta{color:var(--doux);font-size:.9rem;margin:0}
table{border-collapse:collapse;width:100%;background:var(--carte);border:1px solid var(--trait);
  border-radius:8px;overflow:hidden}
th,td{border-bottom:1px solid var(--trait);padding:8px 12px;text-align:left;vertical-align:top;
  font-size:14px}
tr:last-child th,tr:last-child td{border-bottom:0}
th{background:#f9fafb;font-weight:600;width:14rem;color:var(--doux)}
a{color:var(--lien);overflow-wrap:anywhere}
.texte{background:var(--carte);border:1px solid var(--trait);border-radius:8px;padding:14px 16px;
  white-space:pre-wrap;overflow-wrap:anywhere;font-size:15px;max-width:75ch}
.valeur{white-space:pre-wrap;overflow-wrap:anywhere}
.vide{color:#98a2b3}
.puce{display:inline-block;background:#eef2f6;border-radius:999px;padding:1px 10px;
  margin:1px 4px 1px 0;font-size:13px}
pre{white-space:pre-wrap;margin:0;font-size:13px}
details{margin-top:1.5rem}
summary{cursor:pointer;color:var(--doux)}
form{margin:12px 0}
@media (max-width:640px){th{width:auto}}
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
    tous = element.get("attributes") or {}
    textes = {nom: v for nom, v in tous.items() if _est_texte_long(v)}
    remplis = {nom: v for nom, v in tous.items() if nom not in textes and not _est_vide(v)}
    vides = [nom for nom, v in tous.items() if nom not in textes and _est_vide(v)]
    blocs_texte = "".join(
        f"<h2>{escape(nom)}</h2><div class='texte'>{_texte(valeur)}</div>"
        for nom, valeur in textes.items()
    )
    attributs = "".join(
        f"<tr><th>{escape(nom)}</th><td>{_valeur(valeur)}</td></tr>"
        for nom, valeur in remplis.items()
    )
    champs_vides = (
        f"<details><summary>Champs vides ({len(vides)})</summary>"
        f"<p class='meta'>{escape(', '.join(vides))}</p></details>"
        if vides
        else ""
    )
    relations = "".join(
        f"<tr><th>{escape(nom)}</th><td>{_relation(valeur)}</td></tr>"
        for nom, valeur in (element.get("relationships") or {}).items()
    )
    return _page(
        f"{chemin} #{item_id}",
        f"<p><a href='/{chemin}'>← {escape(chemin)}</a></p><h1>{escape(_libelle(element))}</h1>"
        f"<p class='meta'>{escape(str(element.get('type', chemin)))} #{escape(item_id)}</p>"
        f"{blocs_texte}<h2>Attributs</h2><table>{attributs}</table>{champs_vides}"
        f"<h2>Relations</h2><table>{relations or '<tr><td class=vide>—</td></tr>'}</table>",
    )


_URL = re.compile(r"https?://[^\s<]*[^\s<.,;:)\]]")


def _est_vide(valeur: Any) -> bool:
    return valeur is None or valeur in ("", [], {})


def _est_texte_long(valeur: Any) -> bool:
    """Une description, des compétences : un texte qu'on lit, pas une valeur qu'on repère."""
    return isinstance(valeur, str) and ("\n" in valeur or len(valeur) > 120)


def _texte(valeur: str) -> str:
    """Le texte tel qu'il a été saisi, retours à la ligne compris, avec ses liens cliquables."""
    return _URL.sub(lambda m: f"<a href='{m.group(0)}'>{m.group(0)}</a>", escape(valeur))


def _valeur(valeur: Any) -> str:
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if isinstance(valeur, (int, float)):
        return escape(str(valeur))
    if isinstance(valeur, str):
        return f"<span class='valeur'>{_texte(valeur)}</span>"
    if isinstance(valeur, list) and all(isinstance(v, (str, int, float)) for v in valeur):
        return "".join(f"<span class='puce'>{escape(str(v))}</span>" for v in valeur)
    if isinstance(valeur, dict) and all(not isinstance(v, (dict, list)) for v in valeur.values()):
        return "<br>".join(
            f"<span class='meta'>{escape(str(cle))} :</span> {'—' if _est_vide(v) else _valeur(v)}"
            for cle, v in valeur.items()
        )
    return f"<pre>{escape(_json(valeur))}</pre>"


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
