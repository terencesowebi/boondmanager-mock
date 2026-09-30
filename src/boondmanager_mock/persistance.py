"""Persistance — l'état du mock survit au redémarrage, sur option.

Sans `BOOND_MOCK_DATA_FILE`, rien ne change : le monde se reconstruit de la
graine à chaque démarrage, ce que veulent les suites de tests et la CI.

Avec, le mock devient une base de développement : ce qu'un consommateur a créé
ou modifié (écritures, `/__admin/mutate`, vie de l'entreprise) est encore là au
démarrage suivant. `/__admin/reset` repart de la graine ET écrase le fichier.

Le fichier est un instantané JSON, réécrit en entier après chaque mutation :
écrit à côté puis RENOMMÉ, si bien qu'un arrêt brutal laisse l'ancien état ou le
nouveau, jamais un fichier tronqué. Le jeu de données tient en quelques
centaines de kilo-octets ; une base relationnelle n'apporterait rien ici.

L'état de l'évolution est sauvegardé avec les données : sans son compteur, un
redémarrage REJOUERAIT les événements déjà appliqués sur un jeu qui les contient
déjà (actions en double, factures réglées deux fois).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

#: Relever ce numéro à tout changement de forme du fichier : un fichier d'une
#: autre version est ignoré, et le monde repart de la graine.
VERSION_FORMAT = 1


def charger(chemin: str) -> dict[str, Any] | None:
    """L'instantané, ou `None` s'il est absent, illisible ou d'un autre format."""
    fichier = Path(chemin)
    if not fichier.is_file():
        return None
    try:
        contenu: dict[str, Any] = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if contenu.get("format") != VERSION_FORMAT:
        return None
    return contenu


def sauvegarder(chemin: str, contenu: dict[str, Any]) -> None:
    fichier = Path(chemin)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(dir=fichier.parent, prefix=f".{fichier.name}.")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as sortie:
            json.dump({"format": VERSION_FORMAT, **contenu}, sortie, ensure_ascii=False)
            sortie.flush()
            os.fsync(sortie.fileno())
        os.replace(temporaire, fichier)
    except BaseException:
        Path(temporaire).unlink(missing_ok=True)
        raise
