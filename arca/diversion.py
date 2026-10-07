"""cowsay + lolcat en Python puro (sin dependencias) para darle vida a la consola.
Se desactiva solo cuando la salida no es una terminal, con --serio o con la variable NO_COLOR."""

import math
import os
import random
import sys
import textwrap

FRASES = [
    "El conocimiento que no se copia, se pierde.",
    "Un repo respaldado es un repo que sobrevive.",
    "Git no olvida... si alguien guardó la copia.",
    "Los issues también son historia. Guárdalos.",
    "Hoy respaldamos, mañana restauramos.",
    "Ningún 404 borra lo que ya está en el arca.",
    "Dos de cada especie: una en local, otra en la nube.",
    "El código es de quien lo preserva y lo comparte.",
    "Mientras haya un .bundle, hay esperanza.",
]

VACA = r"""
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||"""

ARCA = r"""
        \
         \          |>
          \         |
                ____|____
           ____/ [] [] []\____
           \   A  R  C  A    /
      ~~~~~~\_______________/~~~~~~
        ~~~~     ~~~~     ~~~~"""

PINGUINO = r"""
        \
         \    .--.
             |o_o |
             |:_/ |
            //   \ \
           (|     | )
          /'\_   _/`\
          \___)=(___/"""

FIGURAS = {"vaca": VACA, "arca": ARCA, "pinguino": PINGUINO}

_activo = None


def _activar_ansi_windows():
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        modo = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(modo)):
            return False
        return bool(k.SetConsoleMode(h, modo.value | 0x0004))  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except (AttributeError, OSError):
        return False


def activo():
    """True si la salida es una terminal interactiva y no se pidió modo serio."""
    global _activo
    if _activo is None:
        salida = sys.stdout
        _activo = bool(salida and hasattr(salida, "isatty") and salida.isatty()
                       and not os.environ.get("NO_COLOR") and not os.environ.get("ARCA_SERIO"))
        if _activo and os.name == "nt":
            _activo = _activar_ansi_windows()
    return _activo


def desactivar():
    global _activo
    _activo = False


def lolcat(texto, frecuencia=0.13, dispersion=3.0, inicio=None):
    """Colorea el texto con un arcoíris en diagonal (colores ANSI de 24 bits)."""
    base = random.uniform(0, 60) if inicio is None else inicio
    lineas = []
    for i, linea in enumerate(texto.splitlines()):
        trozos = []
        for j, caracter in enumerate(linea):
            x = frecuencia * (base + i + j / dispersion)
            r, g, b = (int(math.sin(x + k * 2 * math.pi / 3) * 127 + 128) for k in range(3))
            trozos.append(f"\033[38;2;{r};{g};{b}m{caracter}")
        lineas.append("".join(trozos) + "\033[0m")
    return "\n".join(lineas)


def cowsay(texto, figura="vaca", ancho=46):
    lineas = []
    for parrafo in str(texto).splitlines() or [""]:
        lineas += textwrap.wrap(parrafo, ancho) or [""]
    w = max(len(l) for l in lineas)
    globo = [" " + "_" * (w + 2)]
    if len(lineas) == 1:
        globo.append(f"< {lineas[0]} >")
    else:
        for k, l in enumerate(lineas):
            izq, der = ("/", "\\") if k == 0 else ("\\", "/") if k == len(lineas) - 1 else ("|", "|")
            globo.append(f"{izq} {l.ljust(w)} {der}")
    globo.append(" " + "-" * (w + 2))
    return "\n".join(globo) + FIGURAS.get(figura, VACA)


def decir(texto, figura=None):
    """Imprime el cowsay arcoíris (solo en terminal interactiva)."""
    if not activo():
        return
    figura = figura or random.choice(["vaca", "vaca", "arca", "pinguino"])
    print(lolcat(cowsay(texto, figura)), flush=True)
    print(flush=True)


def saludo():
    decir(random.choice(FRASES))


def despedida(conteo):
    if not conteo:
        return
    partes = []
    if conteo.get("ok"):
        partes.append(f"{conteo['ok']} repo(s) a salvo en el arca.")
    if conteo.get("omitido"):
        partes.append(f"{conteo['omitido']} ya estaban al día.")
    if conteo.get("caido"):
        partes.append(f"{conteo['caido']} ya NO existen en GitHub. Revisa 'arca estado'.")
    if conteo.get("error"):
        partes.append(f"{conteo['error']} con error; se reintentarán la próxima vez.")
    decir("\n".join(partes) or "Nada que hacer.", "arca" if not conteo.get("caido") else "vaca")
