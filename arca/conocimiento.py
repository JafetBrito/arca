"""Convierte los datos crudos de la API en Markdown legible por humanos, sin herramientas especiales."""

import json
from collections import defaultdict
from pathlib import Path

from .util import borrar_arbol, leer_jsonl


def _numero(url):
    return int(url.rstrip("/").rsplit("/", 1)[1])


def _login(obj):
    return (obj or {}).get("login") or "fantasma"


def _bloque_comentario(autor, fecha, cuerpo, extra=""):
    return f"### @{autor} · {fecha}{extra}\n\n{(cuerpo or '').strip() or '_(sin texto)_'}\n"


def _celda(texto):
    return (texto or "").replace("|", "\\|").replace("\n", " ")


def generar(carpeta):
    carpeta = Path(carpeta)
    meta, salida = carpeta / "meta", carpeta / "conocimiento"
    borrar_arbol(salida)

    hilos = defaultdict(list)  # número -> [(fecha, markdown)]
    for c in leer_jsonl(meta / "issue_comments.jsonl"):
        hilos[_numero(c["issue_url"])].append(
            (c["created_at"], _bloque_comentario(_login(c.get("user")), c["created_at"], c.get("body"))))
    for c in leer_jsonl(meta / "pull_review_comments.jsonl"):
        lugar = f" · revisión en `{c.get('path')}`" + (f" línea {c['line']}" if c.get("line") else "")
        cuerpo = f"```diff\n{c.get('diff_hunk', '')}\n```\n\n{c.get('body') or ''}"
        hilos[_numero(c["pull_request_url"])].append(
            (c["created_at"], _bloque_comentario(_login(c.get("user")), c["created_at"], cuerpo, lugar)))
    for r in leer_jsonl(meta / "pull_reviews.jsonl"):
        if r.get("body") or r.get("state") not in ("COMMENTED", None):
            fecha = r.get("submitted_at") or ""
            hilos[r["pull_number"]].append(
                (fecha, _bloque_comentario(_login(r.get("user")), fecha, r.get("body"), f" · revisión: **{r.get('state')}**")))

    pulls = {p["number"]: (p.get("merged_at"), (p.get("head") or {}).get("label"), (p.get("base") or {}).get("ref"))
             for p in leer_jsonl(meta / "pulls.jsonl")}

    indice = {"issues": [], "pulls": [], "discusiones": []}
    for it in leer_jsonl(meta / "issues.jsonl"):
        n = it["number"]
        es_pr = "pull_request" in it
        tipo = "pulls" if es_pr else "issues"
        estado = it.get("state", "")
        lineas = [f"# #{n} {it.get('title', '')}", ""]
        lineas.append(f"- **Tipo:** {'Pull request' if es_pr else 'Issue'}")
        if es_pr and n in pulls:
            fusion, cabeza, base = pulls[n]
            if fusion:
                estado = f"fusionado ({fusion})"
            lineas.append(f"- **Ramas:** `{cabeza}` → `{base}`")
        lineas += [
            f"- **Estado:** {estado}",
            f"- **Autor:** @{_login(it.get('user'))}",
            f"- **Creado:** {it.get('created_at')}" + (f" · **Cerrado:** {it['closed_at']}" if it.get("closed_at") else ""),
        ]
        etiquetas = ", ".join(e["name"] for e in it.get("labels", []) if isinstance(e, dict))
        if etiquetas:
            lineas.append(f"- **Etiquetas:** {etiquetas}")
        if it.get("milestone"):
            lineas.append(f"- **Hito:** {it['milestone'].get('title')}")
        lineas += [f"- **Original:** {it.get('html_url')}", "", "---", "", (it.get("body") or "_(sin descripción)_").strip(), ""]
        comentarios = sorted(hilos.pop(n, []), key=lambda x: x[0] or "")
        if comentarios:
            lineas += ["---", "", f"## Conversación ({len(comentarios)})", ""]
            lineas += [md for _, md in comentarios]
        archivo = salida / tipo / f"{n:06d}.md"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text("\n".join(lineas), encoding="utf-8")
        indice[tipo].append((n, it.get("title", ""), estado, len(comentarios)))

    for d in leer_jsonl(meta / "discussions.jsonl"):
        lineas = [f"# Discusión #{d['number']} {d['title']}", "",
                  f"- **Categoría:** {(d.get('category') or {}).get('name')}",
                  f"- **Autor:** @{_login(d.get('author'))}",
                  f"- **Creada:** {d.get('createdAt')}",
                  f"- **Original:** {d.get('url')}", "", "---", "", (d.get("body") or "").strip(), ""]
        comentarios = d["comments"]["nodes"]
        if comentarios:
            lineas += ["---", "", f"## Conversación ({len(comentarios)})", ""]
        for c in comentarios:
            marca = " · ✅ **respuesta aceptada**" if c.get("isAnswer") else ""
            lineas.append(_bloque_comentario(_login(c.get("author")), c["createdAt"], c.get("body"), marca))
            for r in c["replies"]["nodes"]:
                cita = "\n".join("> " + l for l in _bloque_comentario(_login(r.get("author")), r["createdAt"], r.get("body")).splitlines())
                lineas.append(cita + "\n")
        archivo = salida / "discusiones" / f"{d['number']:06d}.md"
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text("\n".join(lineas), encoding="utf-8")
        indice["discusiones"].append((d["number"], d["title"], "respondida" if d.get("answerChosenAt") else "", len(comentarios)))

    info = json.loads((meta / "repo.json").read_text("utf-8")) if (meta / "repo.json").exists() else {}
    partes = [f"# {info.get('full_name', carpeta.name)}", "", info.get("description") or "", "",
              f"- Estrellas: {info.get('stargazers_count')} · Forks: {info.get('forks_count')}",
              f"- Licencia: {(info.get('license') or {}).get('spdx_id', 'desconocida')}",
              f"- Temas: {', '.join(info.get('topics') or [])}", ""]
    titulos = {"issues": "Issues", "pulls": "Pull requests", "discusiones": "Discusiones"}
    for tipo, filas in indice.items():
        if not filas:
            continue
        partes += [f"## {titulos[tipo]} ({len(filas)})", "", "| # | Título | Estado | Comentarios |", "|---|---|---|---|"]
        partes += [f"| [{n}]({tipo}/{n:06d}.md) | {_celda(t)} | {_celda(e)} | {c} |" for n, t, e, c in filas]
        partes.append("")
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "INDICE.md").write_text("\n".join(partes), encoding="utf-8")
    return {k: len(v) for k, v in indice.items()}
