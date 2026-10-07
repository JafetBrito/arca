"""Punto de entrada del ejecutable: sin argumentos abre la ventana; con argumentos funciona como la CLI."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from arca.cli import main
    else:
        from arca.gui import main
    sys.exit(main())
