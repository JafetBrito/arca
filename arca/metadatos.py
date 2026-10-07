"""Descarga todo lo que vive en GitHub fuera de git: issues, PRs, comentarios, revisiones,
discusiones, releases, etiquetas, hitos, colaboradores."""

import logging
import urllib.error
import urllib.request
from pathlib import Path

from .github import ErrorGitHub, NoDisponible
from .util import escribir_json, guardar_jsonl, leer_jsonl, nombre_seguro

log = logging.getLogger("arca")

# (archivo, endpoint relativo a /repos/{dueño}/{repo}, parámetros)
SECCIONES = [
    ("labels", "labels", {}),
    ("milestones", "milestones", {"state": "all"}),
    ("releases", "releases", {}),
    ("issues", "issues", {"state": "all", "sort": "created", "direction": "asc"}),
    ("issue_comments", "issues/comments", {"sort": "created", "direction": "asc"}),
    ("pulls", "pulls", {"state": "all", "sort": "created", "direction": "asc"}),
    ("pull_review_comments", "pulls/comments", {"sort": "created", "direction": "asc"}),
    ("contributors", "contributors", {"anon": "true"}),
]

CONSULTA_DISCUSIONES = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    discussions(first: 25, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id number title body url createdAt updatedAt closed answerChosenAt
        author { login } category { name } labels(first: 20) { nodes { name } }
        comments(first: 50) {
          pageInfo { hasNextPage endCursor }
          nodes { ...Comentario }
        }
      }
    }
  }
}
fragment Comentario on DiscussionComment {
  id body createdAt isAnswer author { login }
  replies(first: 50) { pageInfo { hasNextPage endCursor } nodes { body createdAt author { login } } }
}
"""

CONSULTA_MAS_COMENTARIOS = """
query($id: ID!, $cursor: String) {
  node(id: $id) { ... on Discussion {
    comments(first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id body createdAt isAnswer author { login }
        replies(first: 50) { pageInfo { hasNextPage endCursor } nodes { body createdAt author { login } } } }
    } } }
}
"""

CONSULTA_MAS_RESPUESTAS = """
query($id: ID!, $cursor: String) {
  node(id: $id) { ... on DiscussionComment {
    replies(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor } nodes { body createdAt author { login } }
    } } }
}
"""


def _completar_respuestas(gh, comentario):
    rep = comentario["replies"]
    while rep["pageInfo"]["hasNextPage"]:
        d = gh.graphql(CONSULTA_MAS_RESPUESTAS, {"id": comentario["id"], "cursor": rep["pageInfo"]["endCursor"]})
        nuevo = d["node"]["replies"]
        rep["nodes"].extend(nuevo["nodes"])
        rep["pageInfo"] = nuevo["pageInfo"]


def _discusiones(gh, nombre):
    dueno, repo = nombre.split("/")
    cursor = None
    while True:
        d = gh.graphql(CONSULTA_DISCUSIONES, {"owner": dueno, "name": repo, "cursor": cursor})
        pagina = d["repository"]["discussions"]
        for disc in pagina["nodes"]:
            com = disc["comments"]
            while com["pageInfo"]["hasNextPage"]:
                m = gh.graphql(CONSULTA_MAS_COMENTARIOS, {"id": disc["id"], "cursor": com["pageInfo"]["endCursor"]})
                nuevo = m["node"]["comments"]
                com["nodes"].extend(nuevo["nodes"])
                com["pageInfo"] = nuevo["pageInfo"]
            for c in com["nodes"]:
                _completar_respuestas(gh, c)
            yield disc
        if not pagina["pageInfo"]["hasNextPage"]:
            return
        cursor = pagina["pageInfo"]["endCursor"]


def _revisiones(gh, nombre, archivo_pulls):
    for pr in leer_jsonl(archivo_pulls):
        for rev in gh.paginar(f"/repos/{nombre}/pulls/{pr['number']}/reviews"):
            rev["pull_number"] = pr["number"]
            yield rev


def _descargar_assets(carpeta, archivo_releases, max_bytes):
    n = 0
    for rel in leer_jsonl(archivo_releases):
        for asset in rel.get("assets", []):
            if asset.get("size", 0) > max_bytes:
                log.info("  asset omitido por tamaño: %s (%d MB)", asset["name"], asset["size"] >> 20)
                continue
            destino = carpeta / "releases" / nombre_seguro(rel.get("tag_name") or rel["id"]) / nombre_seguro(asset["name"])
            if destino.exists() and destino.stat().st_size == asset["size"]:
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            tmp = destino.with_name(destino.name + ".parcial")
            req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "arca-respaldo"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r, tmp.open("wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                tmp.replace(destino)
                n += 1
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                log.warning("  no se pudo bajar el asset %s: %s", asset["name"], e)
                tmp.unlink(missing_ok=True)
    return n


def respaldar_metadatos(gh, nombre, carpeta, info, revisiones=False, assets_max_mb=0):
    carpeta = Path(carpeta)
    meta = carpeta / "meta"
    escribir_json(meta / "repo.json", info)
    resumen = {"secciones": {}, "errores": {}}

    def seccion(clave, generador):
        try:
            resumen["secciones"][clave] = guardar_jsonl(generador, meta / f"{clave}.jsonl")
        except (NoDisponible, ErrorGitHub) as e:
            resumen["errores"][clave] = str(e)
            log.debug("  %s: %s", clave, e)

    for clave, sub, params in SECCIONES:
        seccion(clave, gh.paginar(f"/repos/{nombre}/{sub}", params))

    if revisiones and (meta / "pulls.jsonl").exists():
        seccion("pull_reviews", _revisiones(gh, nombre, meta / "pulls.jsonl"))

    if info.get("has_discussions"):
        if gh.token:
            seccion("discussions", _discusiones(gh, nombre))
        else:
            resumen["errores"]["discussions"] = "se necesita token para GraphQL"

    if assets_max_mb > 0 and (meta / "releases.jsonl").exists():
        resumen["secciones"]["release_assets"] = _descargar_assets(carpeta, meta / "releases.jsonl", assets_max_mb << 20)

    escribir_json(meta / "resumen.json", resumen)
    return resumen
