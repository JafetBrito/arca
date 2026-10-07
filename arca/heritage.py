"""Pide a Software Heritage (archivo universal de código fuente, respaldado por la UNESCO)
que guarde una copia permanente de cada repo. Gratuito; no sustituye tu copia propia."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://archive.softwareheritage.org/api/1/origin/save/git/url/{}/"


def solicitar_guardado(nombre):
    url_origen = f"https://github.com/{nombre}"
    url = API.format(urllib.parse.quote(url_origen, safe=":/"))
    cabeceras = {"User-Agent": "arca-respaldo", "Accept": "application/json"}
    if os.environ.get("SWH_TOKEN"):
        cabeceras["Authorization"] = f"Bearer {os.environ['SWH_TOKEN']}"
    for intento in range(6):
        req = urllib.request.Request(url, data=b"", method="POST", headers=cabeceras)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
                return d.get("save_request_status", "?"), d.get("save_task_status", "?")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                espera = int(e.headers.get("Retry-After") or 0) or 60 * (intento + 1)
                time.sleep(espera)
                continue
            return "error", f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (intento + 1))
    return "error", "demasiados reintentos"
