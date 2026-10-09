"""Point d'entrée conteneur : `python -m boondmanager_mock`.

Volontairement minimal — pas de CLI, pas d'options. Tout se configure par
variables d'environnement (cf. settings.py), parce que c'est le seul mécanisme
qui marche identiquement en docker compose, en Deployment Kubernetes et en
sidecar Tekton.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    # `h11` et non `httptools` (le défaut d'uvicorn[standard]) : un client qui
    # propose HTTP/2 en clair (`Upgrade: h2c`, ce que fait le HttpClient du JDK)
    # voit sinon le corps de son POST perdu, et un 422 « corps invalide » que le
    # vrai Boond, en HTTPS, ne renverrait jamais.
    uvicorn.run(
        "boondmanager_mock:app",
        host=os.environ.get("BOOND_MOCK_HOST", "0.0.0.0"),
        port=int(os.environ.get("BOOND_MOCK_PORT", "8000")),
        http="h11",
        log_config=None,
    )


if __name__ == "__main__":
    main()
