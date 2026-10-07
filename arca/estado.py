"""Registro persistente del avance, para poder reanudar y saber qué repos desaparecieron."""

import json
import threading
from pathlib import Path

from .util import escribir_json


class Estado:
    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self._lock = threading.Lock()
        self.datos = json.loads(self.ruta.read_text("utf-8")) if self.ruta.exists() else {}

    def obtener(self, repo):
        with self._lock:
            return dict(self.datos.get(repo, {}))

    def actualizar(self, repo, **campos):
        with self._lock:
            self.datos.setdefault(repo, {}).update(campos)
            escribir_json(self.ruta, self.datos)

    def marcar_subido(self, repo, destino):
        with self._lock:
            subidos = self.datos.setdefault(repo, {}).setdefault("subido", [])
            if destino not in subidos:
                subidos.append(destino)
            escribir_json(self.ruta, self.datos)

    def todos(self):
        with self._lock:
            return {k: dict(v) for k, v in self.datos.items()}
