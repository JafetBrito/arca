"""Empaqueta un repo respaldado en un único .zip autodescriptivo con manifiesto de hashes."""

import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .util import sha256_archivo

# Ya vienen comprimidos: guardarlos sin recomprimir ahorra mucho tiempo.
SIN_COMPRIMIR = {".bundle", ".pack", ".zip", ".gz", ".tgz", ".xz", ".bz2", ".7z", ".zst",
                 ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".exe", ".msi", ".dmg", ".deb", ".rpm", ".jar"}
EXCLUIR = {"repo.git", "wiki.git"}

LEEME = """\
RESPALDO DE github.com/{nombre}
Creado por Arca el {fecha} (UTC).

CONTENIDO
  repo.bundle      Repositorio git completo: todas las ramas, tags y refs de pull requests.
                   Restaurar:   git clone repo.bundle {repo}
                   Ver refs:    git bundle list-heads repo.bundle
  wiki.bundle      Wiki del proyecto (si tenía).   git clone wiki.bundle {repo}-wiki
  lfs/             Objetos Git LFS (si se pidió).  Copiar a <clon>/.git/lfs/objects
  conocimiento/    Issues, pull requests y discusiones en Markdown legible.
                   Empieza por conocimiento/INDICE.md
  meta/*.jsonl     Datos crudos de la API de GitHub (un objeto JSON por línea):
                   repo, issues, comentarios, PRs, revisiones de código, releases,
                   etiquetas, hitos, colaboradores y discusiones.
  releases/        Binarios publicados en las releases (si se pidió).
  MANIFIESTO.json  SHA-256 de cada archivo para comprobar integridad.

El conocimiento pertenece a quien lo necesita. Cuídalo y compártelo.
"""


def empaquetar(carpeta, nombre, dir_salida):
    carpeta, dir_salida = Path(carpeta), Path(dir_salida)
    dueno, repo = nombre.split("/")
    fecha = datetime.now(timezone.utc)
    destino = dir_salida / dueno / f"{dueno}__{repo}__{fecha:%Y%m%d}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)

    archivos = []
    for raiz, dirs, nombres in os.walk(carpeta):
        rel_raiz = Path(raiz).relative_to(carpeta)
        if rel_raiz == Path("."):
            dirs[:] = [d for d in dirs if d not in EXCLUIR]
        for n in nombres:
            if n.endswith((".tmp", ".parcial")):
                continue
            archivos.append((Path(raiz) / n, (rel_raiz / n).as_posix()))
    lfs = carpeta / "repo.git" / "lfs" / "objects"
    if lfs.exists():
        for ruta in lfs.rglob("*"):
            if ruta.is_file():
                archivos.append((ruta, "lfs/" + ruta.relative_to(lfs).as_posix()))
    archivos.sort(key=lambda x: x[1])

    manifiesto = {"repo": nombre, "creado": fecha.isoformat(timespec="seconds"), "archivos": {}}
    tmp = destino.with_name(destino.name + ".parcial")
    with zipfile.ZipFile(tmp, "w", allowZip64=True) as z:
        z.writestr("LEEME.txt", LEEME.format(nombre=nombre, repo=repo, fecha=f"{fecha:%Y-%m-%d %H:%M}"))
        for ruta, arc in archivos:
            sin = ruta.suffix.lower() in SIN_COMPRIMIR or arc.startswith("lfs/")
            z.write(ruta, f"{repo}/{arc}", compress_type=zipfile.ZIP_STORED if sin else zipfile.ZIP_DEFLATED,
                    compresslevel=None if sin else 9)
            manifiesto["archivos"][arc] = {"sha256": sha256_archivo(ruta), "bytes": ruta.stat().st_size}
        z.writestr(f"{repo}/MANIFIESTO.json", json.dumps(manifiesto, ensure_ascii=False, indent=2))
    tmp.replace(destino)

    suma = sha256_archivo(destino)
    destino.with_name(destino.name + ".sha256").write_text(f"{suma}  {destino.name}\n", encoding="utf-8")
    return destino, suma
