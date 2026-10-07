"""Configuración persistente de la interfaz gráfica. El token de GitHub se guarda cifrado con
DPAPI de Windows (solo tu usuario de Windows puede descifrarlo)."""

import base64
import json
import os
from pathlib import Path

from .util import escribir_json


def carpeta_base():
    docs = Path.home() / "Documents"
    return (docs if docs.exists() else Path.home()) / "Arca"


RUTA = carpeta_base() / "config.json"

PREDETERMINADA = {
    "dir_trabajo": str(carpeta_base() / "trabajo"),
    "carpeta_local": str(carpeta_base() / "respaldos"),
    "usar_local": True,
    "usar_mega": True,
    "destino_mega": "mega:arca",
    "lista": str(carpeta_base() / "repos.txt"),
    "paralelo": 2,
    "revisiones": False,
    "assets_max_mb": 0,
    "lfs": False,
    "sin_metadatos": False,
    "limpiar": False,
    "heritage": False,
    "token_cifrado": "",
}


# --- DPAPI ------------------------------------------------------------------

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _dpapi(datos, cifrar):
        entrada = _Blob(len(datos), ctypes.cast(ctypes.create_string_buffer(datos, len(datos)), ctypes.POINTER(ctypes.c_char)))
        salida = _Blob()
        fn = ctypes.windll.crypt32.CryptProtectData if cifrar else ctypes.windll.crypt32.CryptUnprotectData
        if not fn(ctypes.byref(entrada), None, None, None, None, 0x01, ctypes.byref(salida)):
            raise OSError("DPAPI falló")
        try:
            return ctypes.string_at(salida.pbData, salida.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(salida.pbData)
else:
    def _dpapi(datos, cifrar):
        return datos


def cifrar_token(token):
    return base64.b64encode(_dpapi(token.encode(), True)).decode() if token else ""


def descifrar_token(texto):
    if not texto:
        return ""
    try:
        return _dpapi(base64.b64decode(texto), False).decode()
    except (OSError, ValueError):
        return ""


# --- lectura/escritura --------------------------------------------------------

def cargar():
    datos = dict(PREDETERMINADA)
    if RUTA.exists():
        try:
            datos.update(json.loads(RUTA.read_text("utf-8")))
        except ValueError:
            pass
    return datos


def guardar(datos):
    escribir_json(RUTA, datos)
