"""Flujo completo para un repo: comprobar → clonar → metadatos → Markdown → empaquetar → guardar/subir → limpiar.
Lo usan tanto la línea de comandos como la interfaz gráfica."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import conocimiento, git_repo, heritage
from .empaquetar import empaquetar
from .github import ErrorGitHub, NoDisponible
from .metadatos import respaldar_metadatos
from .subir import es_local, subir_archivo
from .util import ErrorComando, ahora_iso, borrar_arbol, tamano_legible

log = logging.getLogger("arca")

CODIGOS = {404: "no existe o se volvió privado", 410: "eliminado", 451: "bloqueado por motivos legales (DMCA)"}


class Cancelado(Exception):
    pass


@dataclass
class Opciones:
    dir: Path
    destinos: list = field(default_factory=list)
    sin_metadatos: bool = False
    revisiones: bool = False
    assets_max_mb: int = 0
    lfs: bool = False
    limpiar: bool = False
    omitir_horas: float = 20
    forzar: bool = False
    heritage: bool = False
    paralelo: int = 2
    cancelar: object = None  # threading.Event opcional


def _revisar(op):
    if op.cancelar is not None and op.cancelar.is_set():
        raise Cancelado()


def _reciente(registro, horas):
    if registro.get("estado") != "ok" or not registro.get("ultimo"):
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(registro["ultimo"]) < timedelta(hours=horas)


def transferir(nombre, archivo, destinos, estado, dir_temporal):
    """Copia el paquete a cada destino. Si quedó en todos y está en la carpeta temporal,
    borra el temporal y deja registrada la copia local como la de referencia."""
    archivo = Path(archivo)
    dueno = nombre.split("/")[0]
    hechos = set(estado.obtener(nombre).get("subido") or [])
    copia_local = None
    for destino in destinos:
        if destino in hechos:
            continue
        try:
            ruta = subir_archivo(archivo, destino, dueno)
            estado.marcar_subido(nombre, destino)
            hechos.add(destino)
            if es_local(destino):
                copia_local = ruta
            log.info("[%s] guardado en %s", nombre, ruta)
        except (ErrorComando, OSError) as e:
            log.error("[%s] fallo al guardar en %s: %s", nombre, destino, e)
    completo = all(d in hechos for d in destinos)
    temporal = archivo.resolve().is_relative_to(Path(dir_temporal).resolve())
    if completo and copia_local and temporal:
        archivo.unlink(missing_ok=True)
        archivo.with_name(archivo.name + ".sha256").unlink(missing_ok=True)
        estado.actualizar(nombre, archivo=copia_local)
    return completo


def respaldar_repo(gh, nombre, op, estado):
    previo = estado.obtener(nombre)
    if not op.forzar and _reciente(previo, op.omitir_horas):
        log.info("[%s] respaldado hace poco, se omite (usa 'forzar' para repetir)", nombre)
        return "omitido"
    _revisar(op)

    # 1. ¿Sigue vivo?
    try:
        info = gh.get(f"/repos/{nombre}")
    except NoDisponible as e:
        motivo = CODIGOS.get(e.codigo, str(e))
        nota = " ¡Tenías copia previa!" if previo.get("sha256") else ""
        log.warning("[%s] NO DISPONIBLE: %s.%s", nombre, motivo, nota)
        estado.actualizar(nombre, estado="caido", codigo=e.codigo, motivo=motivo,
                          detectado=previo.get("detectado") or ahora_iso())
        return "caido"
    if info["full_name"].lower() != nombre.lower():
        log.info("[%s] ahora se llama %s", nombre, info["full_name"])

    dueno, repo = nombre.split("/")
    carpeta = op.dir / "repos" / dueno / repo
    carpeta.mkdir(parents=True, exist_ok=True)
    token_git = gh.token if info.get("private") else None

    # 2. Código: espejo completo + bundle
    log.info("[%s] git: %s", nombre, "actualizando espejo" if (carpeta / "repo.git" / "HEAD").exists() else "clonando espejo")
    git_repo.clonar_o_actualizar(f"https://github.com/{info['full_name']}.git", carpeta / "repo.git", token_git)
    _revisar(op)
    if not git_repo.crear_bundle(carpeta / "repo.git", carpeta / "repo.bundle"):
        log.info("[%s] repositorio vacío (sin commits)", nombre)
    if op.lfs:
        try:
            git_repo.descargar_lfs(carpeta / "repo.git", token_git)
        except ErrorComando as e:
            log.warning("[%s] LFS: %s", nombre, e)
    if info.get("has_wiki"):
        try:
            git_repo.clonar_o_actualizar(f"https://github.com/{info['full_name']}.wiki.git", carpeta / "wiki.git", token_git)
            git_repo.crear_bundle(carpeta / "wiki.git", carpeta / "wiki.bundle")
        except ErrorComando:
            pass  # wiki habilitada pero sin páginas
    _revisar(op)

    # 3. Conocimiento: issues, PRs, comentarios, discusiones, releases...
    resumen = {}
    if not op.sin_metadatos:
        log.info("[%s] descargando issues, PRs, comentarios, discusiones y releases", nombre)
        resumen = respaldar_metadatos(gh, nombre, carpeta, info, op.revisiones, op.assets_max_mb)
        conocimiento.generar(carpeta)
        for seccion, error in resumen["errores"].items():
            log.info("[%s]   %s no disponible: %s", nombre, seccion, error)
    _revisar(op)

    # 4. Empaquetar
    archivo, suma = empaquetar(carpeta, nombre, op.dir / "archivos")
    tamano = archivo.stat().st_size
    secciones = resumen.get("secciones", {})
    log.info("[%s] paquete %s (%s) · issues+PRs: %s · comentarios: %s",
             nombre, archivo.name, tamano_legible(tamano), secciones.get("issues", "-"),
             secciones.get("issue_comments", "-"))
    estado.actualizar(nombre, estado="ok", ultimo=ahora_iso(), archivo=str(archivo), sha256=suma,
                      bytes=tamano, estrellas=info.get("stargazers_count"), subido=[],
                      codigo=None, motivo=None, error=None)

    # 5. Guardar en carpeta local y/o subir a la nube
    completo = transferir(nombre, archivo, op.destinos, estado, op.dir / "archivos")

    # 6. Liberar espacio de trabajo solo si quedó a salvo en todos los destinos
    if op.limpiar and completo:
        borrar_arbol(carpeta)
        log.info("[%s] carpeta de trabajo eliminada", nombre)

    if op.heritage:
        pedido, tarea = heritage.solicitar_guardado(nombre)
        log.info("[%s] Software Heritage: %s / %s", nombre, pedido, tarea)
    return "ok"


def ejecutar_lote(gh, repos, op, estado, al_avanzar=None):
    """Respalda varios repos en paralelo. `al_avanzar(hechos, total, nombre, resultado)` es opcional."""
    conteo = {}
    log.info("Respaldando %d repos con %d hilo(s). Destinos: %s", len(repos), op.paralelo, ", ".join(op.destinos))

    def tarea(nombre):
        try:
            return respaldar_repo(gh, nombre, op, estado)
        except Cancelado:
            return "cancelado"
        except (ErrorComando, ErrorGitHub, OSError) as e:
            log.error("[%s] ERROR: %s", nombre, e)
            estado.actualizar(nombre, estado="error", error=str(e)[:500])
            return "error"

    with ThreadPoolExecutor(max_workers=max(1, op.paralelo), thread_name_prefix="arca") as pool:
        futuros = {pool.submit(tarea, r): r for r in repos}
        try:
            for i, f in enumerate(as_completed(futuros), 1):
                res = f.result()
                conteo[res] = conteo.get(res, 0) + 1
                log.info("Progreso %d/%d", i, len(repos))
                if al_avanzar:
                    al_avanzar(i, len(repos), futuros[f], res)
        except KeyboardInterrupt:
            if op.cancelar is not None:
                op.cancelar.set()
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    log.info("Terminado: %s", ", ".join(f"{k}={v}" for k, v in sorted(conteo.items())) or "nada que hacer")
    return conteo


def subir_pendientes(estado, destinos, dir_trabajo, forzar=False, cancelar=None):
    """Lleva a `destinos` los paquetes que ya existen en disco y aún no están allí."""
    fallos = enviados = 0
    for nombre, reg in estado.todos().items():
        if cancelar is not None and cancelar.is_set():
            break
        archivo = Path(reg["archivo"]) if reg.get("archivo") else None
        if not archivo or not archivo.exists():
            continue
        if forzar:
            estado.actualizar(nombre, subido=[d for d in reg.get("subido", []) if d not in destinos])
        faltan = [d for d in destinos if forzar or d not in (reg.get("subido") or [])]
        if not faltan:
            continue
        enviados += 1
        if not transferir(nombre, archivo, faltan, estado, Path(dir_trabajo) / "archivos"):
            fallos += 1
    log.info("Paquetes procesados: %d, con fallos: %d", enviados, fallos)
    return fallos
