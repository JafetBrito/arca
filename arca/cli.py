"""Interfaz de línea de comandos de Arca."""

import argparse
import logging
import sys
from pathlib import Path

from . import __version__, diversion, heritage
from .descubrir import agregar_a_lista, buscar
from .estado import Estado
from .github import GitHub, obtener_token
from .proceso import Opciones, ejecutar_lote, subir_pendientes
from .subir import resolver_destinos
from .util import leer_lista, normalizar_repo, sha256_archivo, tamano_legible

log = logging.getLogger("arca")


def configurar_log(directorio, detallado, consola=True):
    directorio.mkdir(parents=True, exist_ok=True)
    if consola and sys.stdout:
        manejador = logging.StreamHandler(sys.stdout)
        manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
        log.addHandler(manejador)
    archivo = logging.FileHandler(directorio / "arca.log", encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)s %(message)s"))
    log.addHandler(archivo)
    log.setLevel(logging.DEBUG if detallado else logging.INFO)


def cliente_github(token=None):
    token = token or obtener_token()
    if not token:
        log.warning("Sin token de GitHub: límite de 60 peticiones/hora y sin discusiones. "
                    "Ejecuta 'gh auth login' o define GITHUB_TOKEN.")
    return GitHub(token)


def repos_de_args(args):
    repos = [n for n in (normalizar_repo(r) for r in args.repos) if n]
    for r in args.repos:
        if not normalizar_repo(r):
            log.warning("Ignorado (no parece dueño/repo): %s", r)
    if args.lista and Path(args.lista).exists():
        repos += leer_lista(args.lista)
    elif not repos:
        log.error("No hay repos. Indica dueño/repo o crea la lista %s con 'arca buscar'.", args.lista)
    vistos = set()
    return [r for r in repos if not (r.lower() in vistos or vistos.add(r.lower()))]


def carpeta_local(args):
    """Por defecto, 'respaldos' junto a la carpeta de trabajo."""
    return args.carpeta_local or args.dir.resolve().parent / "respaldos"


# --- comandos ---------------------------------------------------------------

def cmd_buscar(args):
    if not any([args.consulta, args.tema, args.usuario, args.org, args.estrellas_de, args.estrellas_min]):
        log.error("Indica al menos un criterio: --consulta, --tema, --usuario, --org, --estrellas-de o --estrellas-min")
        return 2
    gh = cliente_github()
    resultados = []
    for r in buscar(gh, args.consulta, args.usuario, args.org, args.estrellas_de, args.tema,
                    args.estrellas_min, args.limite, args.incluir_forks, not args.sin_archivados):
        resultados.append(r)
        print(f"  {r['full_name']:<55} {r.get('stargazers_count', 0):>8}★  {(r.get('description') or '')[:60]}")
    if args.solo_mostrar:
        log.info("%d repos encontrados (no se guardaron)", len(resultados))
    else:
        nuevos = agregar_a_lista(args.lista, resultados)
        log.info("%d repos encontrados, %d nuevos añadidos a %s", len(resultados), nuevos, args.lista)
    return 0


def cmd_respaldar(args):
    repos = repos_de_args(args)
    if not repos:
        return 2
    destinos = resolver_destinos(args.destino, carpeta_local(args))
    op = Opciones(dir=args.dir, destinos=destinos, sin_metadatos=args.sin_metadatos,
                  revisiones=args.revisiones, assets_max_mb=args.assets_max_mb, lfs=args.lfs,
                  limpiar=args.limpiar, omitir_horas=args.omitir_horas, forzar=args.forzar,
                  heritage=args.heritage, paralelo=args.paralelo)
    conteo = ejecutar_lote(cliente_github(), repos, op, Estado(args.dir / "estado.json"))
    diversion.despedida(conteo)
    return 1 if conteo.get("error") else 0


def cmd_subir(args):
    destinos = resolver_destinos(args.destino, carpeta_local(args))
    return 1 if subir_pendientes(Estado(args.dir / "estado.json"), destinos, args.dir, args.forzar) else 0


def cmd_estado(args):
    datos = Estado(args.dir / "estado.json").todos()
    if not datos:
        print("Aún no hay respaldos. Empieza con:  python -m arca respaldar dueño/repo")
        return 0
    por_estado = {}
    for nombre, reg in datos.items():
        por_estado.setdefault(reg.get("estado", "?"), []).append((nombre, reg))
    total_bytes = sum(r.get("bytes") or 0 for r in datos.values() if r.get("estado") == "ok")
    print(f"Repos registrados: {len(datos)}   Tamaño de los paquetes: {tamano_legible(total_bytes)}")
    for est, filas in sorted(por_estado.items()):
        print(f"  {est:<8} {len(filas)}")
    if por_estado.get("caido"):
        print("\nRepos que ya NO están disponibles en GitHub:")
        for nombre, reg in por_estado["caido"]:
            copia = "con copia" if reg.get("sha256") else "SIN copia"
            print(f"  {nombre:<50} HTTP {reg.get('codigo')} {reg.get('motivo')} · desde {reg.get('detectado')} · {copia}")
    if por_estado.get("error"):
        print("\nErrores (se reintentarán en el próximo 'respaldar'):")
        for nombre, reg in por_estado["error"]:
            print(f"  {nombre:<50} {(reg.get('error') or '')[:100]}")
    return 0


def verificar_carpetas(carpetas):
    malos = buenos = 0
    for carpeta in carpetas:
        for suma in sorted(Path(carpeta).rglob("*.zip.sha256")):
            esperado, nombre = suma.read_text("utf-8").split(maxsplit=1)
            zip_ = suma.with_name(nombre.strip())
            if not zip_.exists():
                continue
            if sha256_archivo(zip_) == esperado:
                buenos += 1
            else:
                malos += 1
                log.error("CORRUPTO: %s", zip_)
    log.info("Verificados: %d correctos, %d corruptos", buenos, malos)
    return buenos, malos


def cmd_verificar(args):
    carpetas = [c for c in (args.dir / "archivos", carpeta_local(args)) if Path(c).exists()]
    return 1 if verificar_carpetas(carpetas)[1] else 0


def cmd_dice(args):
    texto = " ".join(args.texto) or diversion.FRASES[0]
    if diversion.activo():
        diversion.decir(texto, args.figura)
    else:
        print(diversion.cowsay(texto, args.figura or "vaca"))
    return 0


def cmd_heritage(args):
    for nombre in repos_de_args(args):
        pedido, tarea = heritage.solicitar_guardado(nombre)
        log.info("[%s] Software Heritage: %s / %s", nombre, pedido, tarea)
    return 0


# --- argumentos -------------------------------------------------------------

def construir_parser():
    p = argparse.ArgumentParser(prog="arca", description="Arca: respalda repos de GitHub con todo su conocimiento.")
    p.add_argument("--version", action="version", version=f"arca {__version__}")
    p.add_argument("--dir", type=Path, default=Path("datos"), help="carpeta de trabajo (por defecto: datos)")
    p.add_argument("--carpeta-local", type=Path,
                   help="carpeta donde quedan los respaldos terminados (por defecto: respaldos). "
                        "Se usa si no das --destino o si el remoto (p. ej. MEGA) no está configurado")
    p.add_argument("-v", "--detallado", action="store_true", help="mostrar más detalle")
    p.add_argument("--serio", action="store_true", help="sin vaca ni arcoíris (también: variable NO_COLOR)")
    sub = p.add_subparsers(dest="comando", required=True)

    b = sub.add_parser("buscar", help="encontrar repos y añadirlos a la lista")
    b.add_argument("--consulta", help='búsqueda de GitHub, p. ej. "machine learning language:python"')
    b.add_argument("--tema", help="topic de GitHub, p. ej. privacy")
    b.add_argument("--usuario", help="todos los repos de un usuario")
    b.add_argument("--org", help="todos los repos de una organización")
    b.add_argument("--estrellas-de", help="los repos que un usuario marcó con estrella")
    b.add_argument("--estrellas-min", type=int, default=0)
    b.add_argument("--limite", type=int, default=1000, help="máximo de resultados (la búsqueda de GitHub topa en 1000)")
    b.add_argument("--incluir-forks", action="store_true")
    b.add_argument("--sin-archivados", action="store_true", help="excluir repos archivados")
    b.add_argument("--lista", default="repos.txt")
    b.add_argument("--solo-mostrar", action="store_true", help="no guardar en la lista")
    b.set_defaults(func=cmd_buscar)

    r = sub.add_parser("respaldar", help="clonar, descargar conocimiento, empaquetar y guardar/subir")
    r.add_argument("repos", nargs="*", help="dueño/repo o URLs (además de la lista)")
    r.add_argument("--lista", default="repos.txt")
    r.add_argument("--destino", action="append", default=[],
                   help="carpeta local o remoto rclone (p. ej. mega:arca). Repetible. Sin él: carpeta local")
    r.add_argument("--paralelo", type=int, default=2, help="repos simultáneos (por defecto 2)")
    r.add_argument("--sin-metadatos", action="store_true", help="solo código git")
    r.add_argument("--revisiones", action="store_true", help="incluir revisiones de cada PR (1 petición por PR)")
    r.add_argument("--assets-max-mb", type=int, default=0, help="bajar binarios de releases hasta N MB cada uno")
    r.add_argument("--lfs", action="store_true", help="bajar objetos Git LFS (requiere git-lfs)")
    r.add_argument("--limpiar", action="store_true", help="borrar la carpeta de trabajo tras guardar con éxito en todos los destinos")
    r.add_argument("--omitir-horas", type=float, default=20, help="no repetir repos respaldados hace menos de N horas")
    r.add_argument("--forzar", action="store_true", help="respaldar aunque sea reciente")
    r.add_argument("--heritage", action="store_true", help="pedir también a Software Heritage que lo archive")
    r.set_defaults(func=cmd_respaldar)

    s = sub.add_parser("subir", help="llevar los paquetes existentes a destinos nuevos (p. ej. MEGA)")
    s.add_argument("--destino", action="append", required=True, help="carpeta local o remoto rclone (repetible)")
    s.add_argument("--forzar", action="store_true", help="volver a subir aunque ya conste como subido")
    s.set_defaults(func=cmd_subir)

    sub.add_parser("estado", help="resumen: respaldados, caídos, errores").set_defaults(func=cmd_estado)
    sub.add_parser("verificar", help="comprobar la integridad SHA-256 de los paquetes").set_defaults(func=cmd_verificar)

    h = sub.add_parser("heritage", help="pedir a Software Heritage que archive los repos")
    h.add_argument("repos", nargs="*")
    h.add_argument("--lista", default="repos.txt")
    h.set_defaults(func=cmd_heritage)

    d = sub.add_parser("dice", help="la vaca del arca dice algo (cowsay + lolcat)")
    d.add_argument("texto", nargs="*")
    d.add_argument("--figura", choices=sorted(diversion.FIGURAS), help="vaca, arca o pinguino")
    d.set_defaults(func=cmd_dice)
    return p


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = construir_parser().parse_args(argv)
    if args.serio:
        diversion.desactivar()
    if args.comando == "dice":
        return cmd_dice(args)
    configurar_log(args.dir, args.detallado)
    diversion.saludo()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        log.warning("Interrumpido. El avance quedó guardado; vuelve a ejecutar para continuar.")
        return 130
