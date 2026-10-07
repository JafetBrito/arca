"""Cliente mínimo de la API de GitHub (REST + GraphQL) con paginación y manejo de límites."""

import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .util import SIN_VENTANA

API = "https://api.github.com"
log = logging.getLogger("arca")


class ErrorGitHub(Exception):
    def __init__(self, codigo, mensaje):
        super().__init__(f"HTTP {codigo}: {mensaje}")
        self.codigo = codigo


class NoDisponible(ErrorGitHub):
    """404 (no existe / privado), 410 (deshabilitado) o 451 (bloqueado por motivos legales, p. ej. DMCA)."""


def obtener_token():
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=20,
                           stdin=subprocess.DEVNULL, **SIN_VENTANA)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _mensaje(cuerpo):
    try:
        return json.loads(cuerpo).get("message", cuerpo)[:300]
    except (ValueError, AttributeError):
        return cuerpo[:300]


class GitHub:
    def __init__(self, token=None):
        self.token = token
        self._pausa_hasta = 0.0
        self._lock = threading.Lock()

    # --- bajo nivel -------------------------------------------------------

    def _esperar_pausa_global(self):
        with self._lock:
            espera = self._pausa_hasta - time.time()
        if espera > 0:
            time.sleep(espera)

    def _pausar(self, segundos, motivo):
        with self._lock:
            hasta = time.time() + segundos
            if hasta > self._pausa_hasta:
                self._pausa_hasta = hasta
                log.warning("Límite de la API (%s). Esperando %d s...", motivo, int(segundos))

    def solicitud(self, metodo, url, cuerpo=None):
        if not url.startswith("http"):
            url = API + url
        cabeceras = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "arca-respaldo",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            cabeceras["Authorization"] = f"Bearer {self.token}"
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        intentos = 0
        while True:
            self._esperar_pausa_global()
            req = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras)
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    contenido = r.read()
                    restantes = r.headers.get("X-RateLimit-Remaining")
                    if restantes is not None and int(restantes) < 5:
                        reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                        self._pausar(max(reset - time.time(), 1) + 2, "cuota casi agotada")
                    return (json.loads(contenido) if contenido else None), r.headers
            except urllib.error.HTTPError as e:
                texto = e.read().decode("utf-8", errors="replace")
                if e.code in (403, 429):
                    if e.headers.get("Retry-After"):
                        self._pausar(int(e.headers["Retry-After"]) + 1, "secundario")
                        continue
                    if e.headers.get("X-RateLimit-Remaining") == "0":
                        reset = int(e.headers.get("X-RateLimit-Reset", time.time() + 60))
                        self._pausar(max(reset - time.time(), 1) + 2, "cuota agotada")
                        continue
                    if "rate limit" in texto.lower():
                        self._pausar(60 * (intentos + 1), "secundario")
                        intentos += 1
                        continue
                if e.code in (404, 410, 451):
                    raise NoDisponible(e.code, _mensaje(texto)) from None
                if e.code >= 500 and intentos < 6:
                    intentos += 1
                    time.sleep(min(2 ** intentos, 60))
                    continue
                raise ErrorGitHub(e.code, _mensaje(texto)) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if intentos < 6:
                    intentos += 1
                    log.debug("Error de red (%s), reintento %d", e, intentos)
                    time.sleep(min(2 ** intentos, 60))
                    continue
                raise

    # --- alto nivel -------------------------------------------------------

    def get(self, ruta, params=None):
        if params:
            ruta += "?" + urllib.parse.urlencode(params)
        return self.solicitud("GET", ruta)[0]

    def paginar(self, ruta, params=None, limite=None):
        url = ruta + "?" + urllib.parse.urlencode({"per_page": 100, **(params or {})})
        n = 0
        while url:
            datos, cab = self.solicitud("GET", url)
            elementos = datos.get("items", []) if isinstance(datos, dict) else (datos or [])
            for el in elementos:
                yield el
                n += 1
                if limite and n >= limite:
                    return
            url = None
            m = re.search(r'<([^>]+)>;\s*rel="next"', cab.get("Link") or "")
            if m:
                url = m.group(1)

    def graphql(self, consulta, variables):
        if not self.token:
            raise ErrorGitHub(401, "GraphQL requiere token")
        intentos = 0
        while True:
            datos, _ = self.solicitud("POST", "/graphql", {"query": consulta, "variables": variables})
            errores = (datos or {}).get("errors")
            if not errores:
                return datos["data"]
            tipos = {e.get("type") for e in errores}
            if "RATE_LIMITED" in tipos and intentos < 5:
                intentos += 1
                self._pausar(60 * intentos, "GraphQL")
                continue
            if "NOT_FOUND" in tipos:
                raise NoDisponible(404, errores[0].get("message", ""))
            raise ErrorGitHub(200, "; ".join(e.get("message", "") for e in errores)[:300])
