"""Le serveur du conteneur : ce qu'il fait d'une requête avant FastAPI."""

from __future__ import annotations

from typing import Any

import uvicorn

from boondmanager_mock.__main__ import main


def test_le_serveur_ignore_une_proposition_http2_en_clair(monkeypatch) -> None:
    lance: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda _app, **options: lance.update(options))

    main()

    assert lance["http"] == "h11"
