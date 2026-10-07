"""Utilidades comunes: archivos atómicos, JSONL, hashes y ejecución de comandos."""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

NOMBRE_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*)/[A-Za-z0-9._-]+$")


class ErrorComando(Exception):
    def __init__(self, programa, codigo, salida):
        super().__init__(f"{programa} terminó con código {codigo}: {salida}")
        self.codigo = codigo
        self.salida = salida


def ahora_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalizar_repo(texto):
    """Acepta 'dueño/repo', URLs https o ssh de GitHub. Devuelve 'dueño/repo' o None."""
    t = texto.strip()
    if not t or t.startswith("#"):
        return None
    t = re.sub(r"^(https?://)?(www\.)?github\.com[/:]", "", t)
    t = re.sub(r"^git@github\.com:", "", t)
    t = t.split("?")[0].split("#")[0].strip().strip("/")
    if t.endswith(".git"):
        t = t[:-4]
    partes = t.split("/")
    if len(partes) < 2:
        return None
    t = f"{partes[0]}/{partes[1]}"
    return t if NOMBRE_REPO.match(t) else None


def leer_lista(ruta):
    vistos, salida = set(), []
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        nombre = normalizar_repo(linea)
        if nombre and nombre.lower() not in vistos:
            vistos.add(nombre.lower())
            salida.append(nombre)
    return salida


def escribir_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ruta)


def leer_jsonl(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                yield json.loads(linea)


def guardar_jsonl(iterable, ruta):
    """Escribe un iterable a JSONL de forma atómica. Devuelve el número de registros."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    n = 0
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for obj in iterable:
                f.write(json.dumps(obj, ensure_ascii=False))
                f.write("\n")
                n += 1
        os.replace(tmp, ruta)
    finally:
        if tmp.exists():
            tmp.unlink()
    return n


def sha256_archivo(ruta, bloque=1 << 20):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while chunk := f.read(bloque):
            h.update(chunk)
    return h.hexdigest()


# Evita que cada llamada a git/rclone abra una ventana de consola cuando corre como .exe gráfico.
SIN_VENTANA = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def ejecutar(cmd, cwd=None, timeout=None):
    """Ejecuta un comando sin interacción. En error, no expone los argumentos (pueden llevar tokens)."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    r = subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        encoding="utf-8", errors="replace", timeout=timeout, **SIN_VENTANA,
    )
    if r.returncode != 0:
        salida = (r.stderr or r.stdout or "").strip()
        raise ErrorComando(Path(cmd[0]).name, r.returncode, salida[-800:])
    return r.stdout


def borrar_arbol(ruta):
    """rmtree que también borra archivos de solo lectura (objetos de git en Windows)."""
    def _forzar(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if Path(ruta).exists():
        if sys.version_info >= (3, 12):
            shutil.rmtree(ruta, onexc=_forzar)
        else:
            shutil.rmtree(ruta, onerror=_forzar)


def nombre_seguro(texto, maximo=120):
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(texto)).strip(" .")
    return (limpio or "_")[:maximo]


def tamano_legible(n):
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unidad == "TB":
            return f"{n:.1f} {unidad}" if unidad != "B" else f"{n} B"
        n /= 1024
