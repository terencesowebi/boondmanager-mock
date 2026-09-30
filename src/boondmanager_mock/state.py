"""État mutable du serveur.

L'API publique — `state.dataset`, `state.fail_collections`, `state.reset(seed=…)`
— est conservée. S'y ajoutent deux caches invalidés ensemble à chaque mutation
du monde (reset, événement d'évolution, /__admin/mutate) :

  • `index_entites()` — (type, id) → entité, pour `included` et les détails ;
  • `blobs(cle)`      — le texte de recherche `keywords` par item, précalculé.

Sans eux, chaque requête resérialisait tout le jeu de données (recherche) et
reparcourait toutes les collections (included).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from . import persistance
from .evolution import Evolution
from .included import TYPE_VERS_CLE
from .injection import engine
from .settings import settings


def build_dataset(seed: int = 42) -> dict[str, Any]:
    """Construit le jeu de données « Boréal Conseil »."""
    from .dataset.realiste import build_realiste_dataset

    return build_realiste_dataset(seed)


class MockState:
    """État serveur mutable, pour simuler des changements distants et des pannes."""

    def __init__(self) -> None:
        self.dataset: dict[str, Any] = {}
        # Conservé pour compatibilité : le levier d'injection historique,
        # mutable en process. Les nouvelles pannes passent par
        # `injection.engine`, pilotable par HTTP.
        self.fail_collections: set[str] = set()
        self.seed: int = settings.seed
        self.evolution: Evolution = Evolution(self.seed, time.time())
        self._index: dict[tuple[str, str], dict[str, Any]] | None = None
        self._blobs: dict[str, list[str]] = {}
        #: Sérialise les écritures et leur sauvegarde : les handlers FastAPI
        #: tournent dans un pool de threads, et deux créations simultanées
        #: calculeraient le même identifiant.
        self.verrou = threading.RLock()
        if not self._restaurer():
            self.reset()

    def _restaurer(self) -> bool:
        """Reprend l'instantané du fichier d'état, s'il y en a un d'exploitable."""
        if not settings.data_file:
            return False
        contenu = persistance.charger(settings.data_file)
        if contenu is None:
            return False
        self.seed = contenu["seed"]
        self.dataset = contenu["dataset"]
        evolution = contenu["evolution"]
        self.evolution = Evolution(self.seed, evolution["demarrage"])
        self.evolution.appliques = evolution["appliques"]
        self.evolution.journal = evolution["journal"]
        self.fail_collections = set()
        engine.clear()
        engine.reset_counters()
        self._index = None
        self._blobs = {}
        _apply_baseline_injections()
        return True

    def _persister(self) -> None:
        if not settings.data_file:
            return
        with self.verrou:
            persistance.sauvegarder(
                settings.data_file,
                {
                    "seed": self.seed,
                    "dataset": self.dataset,
                    "evolution": {
                        "demarrage": self.evolution.demarrage,
                        "appliques": self.evolution.appliques,
                        "journal": self.evolution.journal,
                    },
                },
            )

    def reset(self, seed: int | None = None) -> None:
        """Reconstruit le jeu de données et remet les compteurs à zéro.

        ⚠️ Les règles d'injection sont remises À LA LIGNE DE BASE DÉCLARÉE PAR
        L'ENVIRONNEMENT, et non à vide : si un `reset` vidait les règles, la
        première requête d'une suite de tests effacerait silencieusement une
        limite de débit configurée au niveau du compose.

        L'évolution temporelle est RÉARMÉE : la chronologie repart de zéro.
        """
        self.seed = settings.seed if seed is None else seed
        self.dataset = build_dataset(self.seed)
        self.fail_collections = set()
        engine.clear()
        engine.reset_counters()
        self.evolution = Evolution(self.seed, time.time())
        self.invalider_caches()
        _apply_baseline_injections()

    # ── Caches dérivés du dataset ────────────────────────────────────────────

    def invalider_caches(self) -> None:
        """À appeler après TOUTE mutation du dataset (admin, évolution, écriture).

        C'est aussi le point de sauvegarde : toute mutation passe par ici, donc
        aucune ne peut échapper au fichier d'état.
        """
        self._index = None
        self._blobs = {}
        self._persister()

    def avancer_evolution(self, maintenant: float) -> None:
        """Fait avancer la vie de l'entreprise ; invalide les caches si elle a bougé."""
        if self.evolution.avancer(self.dataset, maintenant):
            self.invalider_caches()

    def index_entites(self) -> dict[tuple[str, str], dict[str, Any]]:
        """(type, id) → entité, sur toutes les collections servies."""
        if self._index is None:
            index: dict[tuple[str, str], dict[str, Any]] = {}
            for cle in TYPE_VERS_CLE.values():
                elements = self.dataset.get(cle)
                if isinstance(elements, list):
                    for element in elements:
                        index[(element["type"], element["id"])] = element
            self._index = index
        return self._index

    def blobs(self, cle_dataset: str) -> list[str]:
        """Le texte de recherche par item, aligné sur la liste de la collection."""
        if cle_dataset not in self._blobs:
            items = self.dataset.get(cle_dataset, [])
            self._blobs[cle_dataset] = [
                json.dumps(item, ensure_ascii=False).lower() for item in items
            ]
        return self._blobs[cle_dataset]

    def totals(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.dataset.items() if isinstance(v, list)}


def _apply_baseline_injections() -> None:
    """Règles d'injection déclarées par l'environnement, réappliquées à chaque reset.

    Permet à un docker-compose ou à un sidecar de faire tourner le mock en
    permanence dégradé (limite de débit basse, par exemple) sans qu'un test ne
    l'annule par inadvertance.
    """
    import os

    if (seuil := os.environ.get("BOOND_MOCK_RATE_LIMIT_AFTER")) is not None:
        engine.add(
            kind="rate_limit",
            scope="/api/*",
            after_requests=int(seuil),
            retry_after_seconds=int(os.environ.get("BOOND_MOCK_RETRY_AFTER", "1")),
        )


state = MockState()
