#!/usr/bin/env python3
"""
Scraper JSON Trismegistos (GeoResponder)
----------------------------------------

Objectif
    Télécharger en masse des fichiers JSON depuis:
      1) Vue directe ("view"):  
         https://www.trismegistos.org/dataservices/georesponder/georesponder.php?id=1628
      2) Téléchargement ("download"):  
         https://www.trismegistos.org/dataservices/georesponder/georesponder.php?id=1628&dl=1

Fonctionnement
    - Parcourt une plage d'identifiants (ex: 1500 à 2000)
    - Tente d'abord l'URL avec `dl=1` (téléchargement direct), puis retombe sur la vue simple
      si besoin.
    - Gère les erreurs HTTP, les réponses non‑JSON, les éléments manquants.
    - Sauvegarde chaque JSON valide dans un dossier de sortie, sous le nom `id_<ID>.json`.
    - Reprise possible (les fichiers déjà présents sont ignorés avec `--resume`).
    - Délai configurable entre requêtes pour rester poli avec le site.
    - Option de vérification facultative du robots.txt.

Dépendances
    - Python >= 3.8
    - Aucun paquet externe requis.

Exemples
    # Plage 1500..2000 incluse, sortie dans ./out, délai 0.5s, reprise si fichiers déjà présents
    python scrape_trismegistos_geojson.py --start 1500 --end 2000 --out out --delay 0.5 --resume

    # Forcer uniquement la méthode "view"
    python scrape_trismegistos_geojson.py --method view

    # Désactiver la vérification du robots.txt
    python scrape_trismegistos_geojson.py --no-check-robots

Note
    Veillez à respecter les conditions d'utilisation du site, ainsi que son robots.txt.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import requests
from urllib import robotparser

BASE_URL = "https://www.trismegistos.org/dataservices/georesponder/georesponder.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 "
        "(contact: your-email@example.com)"
    )
}


def check_robots(ua: str = HEADERS["User-Agent"]) -> bool:
    """Retourne True si l'agent est autorisé à crawler l'endpoint /dataservices/.

    Cette vérification est best‑effort: en cas d'échec réseau on renvoie True.
    """
    robots_url = "https://www.trismegistos.org/robots.txt"
    try:
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        # Autorisation générique sur le chemin des dataservices
        return rp.can_fetch(ua, "/dataservices/georesponder/")
    except Exception:
        # En cas d'erreur, on ne bloque pas, mais on journalise.
        logging.warning("Impossible de lire robots.txt — poursuite quand même.")
        return True


def is_json_response(resp: requests.Response) -> bool:
    ct = resp.headers.get("Content-Type", "").lower()
    return "application/json" in ct or resp.text.strip().startswith("{")


def fetch_one(session: requests.Session, tm_id: int, method: str = "auto", timeout: int = 20) -> Optional[dict]:
    """Récupère un enregistrement JSON pour un id donné.

    method:
        - "auto"  : essaie d'abord ?dl=1 puis sans dl
        - "download": n'essaie que ?dl=1
        - "view"  : n'essaie que sans dl
    Retourne le dict JSON si trouvé/valide, sinon None.
    """
    params_base = {"id": tm_id}

    def try_url(with_dl: bool) -> Optional[dict]:
        params = dict(params_base)
        if with_dl:
            params["dl"] = 1
        resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            logging.debug("ID %s → HTTP %s", tm_id, resp.status_code)
            return None
        if not is_json_response(resp):
            logging.debug("ID %s → réponse non JSON (Content-Type=%s)", tm_id, resp.headers.get("Content-Type"))
            return None
        try:
            data = resp.json()
        except json.JSONDecodeError:
            logging.debug("ID %s → JSON invalide", tm_id)
            return None
        # Certaines API renvoient un champ d'erreur au lieu d'un 404
        if isinstance(data, dict) and any(k in data for k in ("error", "message")) and not data:
            logging.debug("ID %s → JSON de type erreur/vide", tm_id)
            return None
        return data

    if method == "download":
        return try_url(with_dl=True)
    if method == "view":
        return try_url(with_dl=False)

    # auto
    data = try_url(with_dl=True)
    if data is not None:
        return data
    return try_url(with_dl=False)


def save_json(data: dict, outdir: Path, tm_id: int) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"id_{tm_id}.json"
    # Écriture atomique simple
    tmp = outdir / f".id_{tm_id}.json.part"
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return path


def iter_ids(start: int, end: int):
    step = 1 if end >= start else -1
    for i in range(start, end + step, step):
        yield i


def main():
    parser = argparse.ArgumentParser(description="Télécharger des JSON GeoResponder de Trismegistos")
    parser.add_argument("--start", type=int, default=1500, help="Premier id (inclus)")
    parser.add_argument("--end", type=int, default=2000, help="Dernier id (inclus)")
    parser.add_argument("--out", type=Path, default=Path("out"), help="Dossier de sortie")
    parser.add_argument("--delay", type=float, default=0.5, help="Délai en secondes entre requêtes")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout HTTP en secondes")
    parser.add_argument("--method", choices=["auto", "download", "view"], default="auto", help="Méthode d'accès")
    parser.add_argument("--resume", action="store_true", help="Ignorer les ids déjà téléchargés")
    parser.add_argument("--no-check-robots", dest="check_robots", action="store_false", help="Ne pas lire robots.txt")
    parser.set_defaults(check_robots=True)
    parser.add_argument("--verbose", action="store_true", help="Logs détaillés")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if args.check_robots and not check_robots():
        logging.error("Le robots.txt n'autorise pas le crawl de /dataservices/georesponder/ pour cet User-Agent.")
        sys.exit(2)

    ok = 0
    missing = 0
    skipped = 0
    failed = 0

    with requests.Session() as session:
        for tm_id in iter_ids(args.start, args.end):
            outpath = args.out / f"id_{tm_id}.json"
            if args.resume and outpath.exists():
                logging.info("%s déjà présent — passage.", outpath.name)
                skipped += 1
                continue

            try:
                data = fetch_one(session, tm_id, method=args.method, timeout=args.timeout)
            except requests.RequestException as e:
                logging.warning("ID %s → erreur réseau: %s", tm_id, e)
                failed += 1
                time.sleep(args.delay)
                continue

            if data is None:
                logging.info("ID %s → introuvable ou non JSON.", tm_id)
                missing += 1
            else:
                path = save_json(data, args.out, tm_id)
                logging.info("ID %s → sauvegardé: %s", tm_id, path)
                ok += 1

            time.sleep(args.delay)

    logging.info("Terminé. %s ok, %s manquants, %s ignorés, %s erreurs.", ok, missing, skipped, failed)


if __name__ == "__main__":
    main()
