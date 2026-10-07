"""Destinos de los respaldos: una carpeta local (disco, USB, NAS) o cualquier remoto de rclone
(MEGA, Google Drive, S3, Internet Archive, Dropbox, OneDrive, SFTP...)."""

import json
import logging
import os
import re
import shutil
from pathlib import Path

from .util import ErrorComando, ejecutar, sha256_archivo

log = logging.getLogger("arca")

# "mega:arca" es remoto; "C:\respaldos", "\\nas\x" o "respaldos" son carpetas locales.
_REMOTO = re.compile(r"^[\w.\-+@ ]{2,}:")


class SinRclone(Exception):
    pass


def es_local(destino):
    return not _REMOTO.match(str(destino))


def rclone():
    ruta = shutil.which("rclone")
    if not ruta and os.name == "nt":
        # Recién instalado con winget: el PATH de este proceso aún no lo conoce.
        winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
        candidatos = [winget / "Links" / "rclone.exe", *sorted((winget / "Packages").glob("Rclone.Rclone*/*/rclone.exe"))]
        ruta = next((str(c) for c in candidatos if c.exists()), None)
    if not ruta:
        raise SinRclone("No se encontró rclone. Instálalo con:  winget install Rclone.Rclone")
    return ruta


def remotos_configurados():
    try:
        return [r.rstrip(":") for r in ejecutar([rclone(), "listremotes"]).split()]
    except (SinRclone, ErrorComando, OSError):
        return []


def comprobar_destino(destino):
    remoto = destino.split(":", 1)[0]
    rclone()
    if remoto not in remotos_configurados():
        raise SinRclone(f"El remoto '{remoto}' no está configurado en rclone")


def resolver_destinos(destinos, carpeta_local):
    """Valida los destinos. Un remoto no configurado se sustituye por la carpeta local."""
    finales = []
    for d in destinos or [str(carpeta_local)]:
        if not es_local(d):
            try:
                comprobar_destino(d)
            except SinRclone as e:
                log.warning("%s. Los respaldos se guardarán en la carpeta local: %s", e, carpeta_local)
                d = str(carpeta_local)
        if es_local(d):
            d = str(Path(d).expanduser().resolve())
        if d not in finales:
            finales.append(d)
    return finales


def configurar_mega(correo, contrasena, nombre="mega"):
    """Crea (o reemplaza) el remoto de MEGA en rclone. La contraseña queda ofuscada en rclone.conf."""
    ejecutar([rclone(), "config", "create", nombre, "mega", f"user={correo}", f"pass={contrasena}",
              "--obscure", "--non-interactive"], timeout=60)
    ejecutar([rclone(), "lsd", f"{nombre}:"], timeout=120)  # comprueba que el acceso funciona


def _copiar_local(archivo, carpeta):
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / archivo.name
    tmp = destino.with_name(destino.name + ".parcial")
    shutil.copyfile(archivo, tmp)
    if sha256_archivo(tmp) != sha256_archivo(archivo):
        tmp.unlink(missing_ok=True)
        raise ErrorComando("copia", 0, f"la copia en {carpeta} no coincide con el original")
    os.replace(tmp, destino)
    suma = archivo.with_name(archivo.name + ".sha256")
    if suma.exists():
        shutil.copyfile(suma, carpeta / suma.name)
    return destino


def subir_archivo(archivo, destino, subcarpeta=""):
    """Copia `archivo` (y su .sha256) a destino/subcarpeta, verificando. Devuelve la ruta final."""
    archivo = Path(archivo)
    if es_local(destino):
        try:
            return str(_copiar_local(archivo, Path(destino) / subcarpeta))
        except OSError as e:
            raise ErrorComando("copia", 0, str(e)) from None
    base = destino.rstrip("/")
    if subcarpeta:
        base += "/" + subcarpeta
    opciones = ["--retries", "5", "--low-level-retries", "20", "--stats", "0"]
    for f in (archivo, archivo.with_name(archivo.name + ".sha256")):
        if f.exists():
            ejecutar([rclone(), "copyto", str(f), f"{base}/{f.name}", *opciones], timeout=24 * 3600)
    lista = json.loads(ejecutar([rclone(), "lsjson", f"{base}/{archivo.name}"]) or "[]")
    remoto = lista[0]["Size"] if lista else -1
    if remoto != archivo.stat().st_size:
        raise ErrorComando("rclone", 0, f"verificación fallida: local {archivo.stat().st_size} B, remoto {remoto} B")
    return f"{base}/{archivo.name}"
