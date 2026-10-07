"""Clonado espejo (todas las ramas, tags y refs de PRs) y creación de bundles de git."""

import base64
import shutil
from pathlib import Path

from .util import ejecutar


def _auth(token):
    if not token:
        return []
    cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {cred}"]


def clonar_o_actualizar(url, destino, token=None, timeout=6 * 3600):
    """Mantiene un espejo bare en `destino`. Si ya existe, solo descarga lo nuevo."""
    destino = Path(destino)
    if (destino / "HEAD").exists():
        ejecutar(["git", *_auth(token), "-C", str(destino), "remote", "update", "--prune"], timeout=timeout)
        return "actualizado"
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".parcial")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    ejecutar(["git", *_auth(token), "clone", "--mirror", url, str(tmp)], timeout=timeout)
    tmp.rename(destino)
    return "clonado"


def tiene_refs(repo):
    return bool(ejecutar(["git", "-C", str(repo), "for-each-ref", "--count=1"]).strip())


def crear_bundle(repo, bundle):
    """Un .bundle es un único archivo con toda la historia; se restaura con `git clone x.bundle`."""
    bundle = Path(bundle)
    if not tiene_refs(repo):
        return False
    tmp = bundle.with_name(bundle.name + ".tmp")
    ejecutar(["git", "-C", str(repo), "bundle", "create", str(tmp.resolve()), "--all"], timeout=6 * 3600)
    ejecutar(["git", "bundle", "verify", "--quiet", str(tmp.resolve())], cwd=str(repo), timeout=6 * 3600)
    tmp.replace(bundle)
    return True


def descargar_lfs(repo, token=None):
    if not shutil.which("git-lfs"):
        return False
    ejecutar(["git", *_auth(token), "-C", str(repo), "lfs", "fetch", "--all"], timeout=12 * 3600)
    return (Path(repo) / "lfs" / "objects").exists()
