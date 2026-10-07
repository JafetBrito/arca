"""Encontrar repositorios: búsqueda de GitHub, usuarios, organizaciones, estrellas, temas."""

import logging
from pathlib import Path

from .util import leer_lista

log = logging.getLogger("arca")


def buscar(gh, consulta=None, usuario=None, org=None, estrellas_de=None, tema=None,
           estrellas_min=0, limite=1000, incluir_forks=False, incluir_archivados=True):
    fuentes = []
    if consulta or tema or estrellas_min:
        q = " ".join(filter(None, [consulta, f"topic:{tema}" if tema else None,
                                   f"stars:>={estrellas_min}" if estrellas_min else None]))
        fuentes.append(gh.paginar("/search/repositories", {"q": q, "sort": "stars", "order": "desc"}, limite))
    if usuario:
        fuentes.append(gh.paginar(f"/users/{usuario}/repos", {"type": "owner", "sort": "updated"}))
    if org:
        fuentes.append(gh.paginar(f"/orgs/{org}/repos", {"type": "all", "sort": "updated"}))
    if estrellas_de:
        fuentes.append(gh.paginar(f"/users/{estrellas_de}/starred"))

    encontrados = 0
    for fuente in fuentes:
        for r in fuente:
            if r.get("fork") and not incluir_forks:
                continue
            if r.get("archived") and not incluir_archivados:
                continue
            if r.get("stargazers_count", 0) < estrellas_min:
                continue
            yield r
            encontrados += 1
            if encontrados >= limite:
                return


def agregar_a_lista(ruta, repos):
    """Añade repos a la lista (un dueño/repo por línea) sin duplicar. Devuelve cuántos son nuevos."""
    ruta = Path(ruta)
    existentes = {r.lower() for r in leer_lista(ruta)} if ruta.exists() else set()
    nuevos = []
    for r in repos:
        nombre = r["full_name"]
        if nombre.lower() not in existentes:
            existentes.add(nombre.lower())
            nuevos.append(f"{nombre}  # {r.get('stargazers_count', 0)}★ {(r.get('description') or '')[:80]}")
    if nuevos:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("a", encoding="utf-8") as f:
            f.write("\n".join(nuevos) + "\n")
    return len(nuevos)
