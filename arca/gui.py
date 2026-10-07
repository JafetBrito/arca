"""Interfaz gráfica de Arca (tkinter, incluida en Python: no requiere nada extra)."""

import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

from . import __version__, config
from .descubrir import buscar
from .estado import Estado
from .github import ErrorGitHub, GitHub, obtener_token
from .proceso import Opciones, ejecutar_lote, subir_pendientes
from .subir import SinRclone, configurar_mega, es_local, rclone, remotos_configurados, resolver_destinos
from .util import ErrorComando, SIN_VENTANA, leer_lista, normalizar_repo, tamano_legible

log = logging.getLogger("arca")

AZUL = "#1f3a5f"
VERDE, AMBAR, ROJO = "#7ee2a8", "#ffd27a", "#ff9b9b"
ETIQUETAS_ESTADO = {"ok": "✔ respaldado", "caido": "✖ caído", "error": "⚠ error", "cancelado": "■ cancelado"}


def recurso(nombre):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "recursos" / nombre


def abrir(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        if ruta.suffix:
            messagebox.showinfo("Arca", f"Todavía no existe:\n{ruta}")
            return
        ruta.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(ruta)  # noqa: S606 - abre el explorador de archivos
    else:
        subprocess.Popen(["xdg-open", str(ruta)])


class ManejadorCola(logging.Handler):
    def __init__(self, cola):
        super().__init__()
        self.cola = cola
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, registro):
        self.cola.put(("log", registro.levelno, self.format(registro)))


class App:
    def __init__(self, raiz):
        self.raiz = raiz
        self.cfg = config.cargar()
        self.cola = queue.Queue()
        self.cancelar = threading.Event()
        self.ocupado = False
        self.token = None
        self.resultados = []
        self._archivo_log = None

        raiz.title(f"Arca · Respaldo de GitHub  v{__version__}")
        ancho = min(1180, raiz.winfo_screenwidth() - 60)
        alto = min(860, raiz.winfo_screenheight() - 90)
        raiz.geometry(f"{ancho}x{alto}+{max(0, (raiz.winfo_screenwidth() - ancho) // 2)}+20")
        raiz.minsize(900, 640)
        try:
            raiz.iconbitmap(str(recurso("arca.ico")))
        except tk.TclError:
            pass

        log.setLevel(logging.INFO)
        log.addHandler(ManejadorCola(self.cola))
        self._log_a_archivo()
        self._estilos()
        self._construir()
        self._cargar_lista()
        self.refrescar_estado()
        raiz.protocol("WM_DELETE_WINDOW", self.cerrar)
        raiz.after(100, self._procesar_cola)
        self.comprobar_entorno()

    # --- infraestructura ------------------------------------------------------

    def en_ui(self, funcion, *args):
        """Ejecuta `funcion` en el hilo de la interfaz (tkinter no es seguro entre hilos)."""
        self.cola.put(("ui", funcion, args))

    def _procesar_cola(self):
        try:
            while True:
                tipo, a, b = self.cola.get_nowait()
                if tipo == "log":
                    self._escribir_log(a, b)
                else:
                    a(*b)
        except queue.Empty:
            pass
        self.raiz.after(120, self._procesar_cola)

    def _log_a_archivo(self):
        if self._archivo_log:
            log.removeHandler(self._archivo_log)
            self._archivo_log.close()
        carpeta = Path(self.cfg["dir_trabajo"])
        carpeta.mkdir(parents=True, exist_ok=True)
        self._archivo_log = logging.FileHandler(carpeta / "arca.log", encoding="utf-8")
        self._archivo_log.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)s %(message)s"))
        log.addHandler(self._archivo_log)

    def _lanzar(self, trabajo, descripcion, indeterminado=False):
        if self.ocupado:
            messagebox.showinfo("Arca", "Ya hay una tarea en curso. Espera a que termine o pulsa Detener.")
            return
        self.ocupado = True
        self.cancelar.clear()
        self._botones_ocupado(True)
        self.v_progreso_txt.set(descripcion)
        if indeterminado:
            self.barra.configure(mode="indeterminate")
            self.barra.start(12)

        def envoltura():
            try:
                trabajo()
            except Exception as e:  # cualquier fallo inesperado debe verse en la ventana, no perderse
                log.exception("Error inesperado: %s", e)
            finally:
                self.en_ui(self._tarea_terminada)

        threading.Thread(target=envoltura, daemon=True, name="arca-gui").start()

    def _tarea_terminada(self):
        self.ocupado = False
        self._botones_ocupado(False)
        if str(self.barra.cget("mode")) == "indeterminate":
            self.barra.stop()
            self.barra.configure(mode="determinate", value=0)
            if self.v_progreso_txt.get().endswith("…"):
                self.v_progreso_txt.set("Listo.")
        self.refrescar_estado()

    def _botones_ocupado(self, ocupado):
        for b in self.botones_tarea:
            b.configure(state="disabled" if ocupado else "normal")
        self.b_detener.configure(state="normal" if ocupado else "disabled")

    # --- estilo y estructura ----------------------------------------------------

    def _estilos(self):
        estilo = ttk.Style()
        if "vista" in estilo.theme_names():
            estilo.theme_use("vista")
        self.raiz.option_add("*Font", ("Segoe UI", 10))
        estilo.configure(".", font=("Segoe UI", 10))
        estilo.configure("Primario.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 8))
        estilo.configure("TNotebook.Tab", padding=(16, 6))
        estilo.configure("Treeview", rowheight=26)
        estilo.configure("Nota.TLabel", foreground="#5f6b7a")

    def _construir(self):
        cab = tk.Frame(self.raiz, bg=AZUL, padx=18, pady=12)
        cab.pack(fill="x")
        tk.Label(cab, text="Arca", bg=AZUL, fg="white", font=("Segoe UI Semibold", 20)).pack(side="left")
        tk.Label(cab, text="  Guarda el código y el conocimiento de GitHub", bg=AZUL, fg="#c9d6e8",
                 font=("Segoe UI", 11)).pack(side="left", pady=(8, 0))
        self.chips = {}
        for clave in ("mega", "git", "github"):
            etiqueta = tk.Label(cab, text="", bg=AZUL, fg=AMBAR, font=("Segoe UI", 10), padx=8)
            etiqueta.pack(side="right")
            self.chips[clave] = etiqueta

        pie = ttk.Frame(self.raiz, padding=(10, 0, 10, 8))
        pie.pack(side="bottom", fill="x")
        self.v_progreso_txt = tk.StringVar(value="Listo.")
        ttk.Label(pie, textvariable=self.v_progreso_txt, style="Nota.TLabel").pack(side="left")
        self.barra = ttk.Progressbar(pie, mode="determinate", length=320)
        self.barra.pack(side="right")

        panel = ttk.PanedWindow(self.raiz, orient="vertical")
        panel.pack(fill="both", expand=True, padx=10, pady=(8, 6))
        self.cuaderno = ttk.Notebook(panel)
        panel.add(self.cuaderno, weight=4)

        self.botones_tarea = []
        self._pestana_respaldar()
        self._pestana_buscar()
        self._pestana_estado()
        self._pestana_ajustes()

        marco_log = ttk.LabelFrame(panel, text="Registro de actividad", padding=4)
        panel.add(marco_log, weight=1)
        self.txt_log = tk.Text(marco_log, height=6, wrap="word", font=("Consolas", 9), state="disabled",
                               relief="flat", background="#fbfcfd")
        barra = ttk.Scrollbar(marco_log, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.tag_configure("WARNING", foreground="#a55f00")
        self.txt_log.tag_configure("ERROR", foreground="#c62828")

    def _escribir_log(self, nivel, texto):
        etiqueta = "ERROR" if nivel >= logging.ERROR else "WARNING" if nivel >= logging.WARNING else ""
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", texto + "\n", etiqueta)
        if int(self.txt_log.index("end").split(".")[0]) > 5000:
            self.txt_log.delete("1.0", "1000.0")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    # --- pestaña Respaldar --------------------------------------------------------

    def _pestana_respaldar(self):
        p = ttk.Frame(self.cuaderno, padding=12)
        self.cuaderno.add(p, text="  Respaldar  ")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)

        # Lista de repos
        izq = ttk.LabelFrame(p, text="Repositorios a respaldar", padding=8)
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        izq.columnconfigure(0, weight=1)
        izq.rowconfigure(1, weight=1)
        fila = ttk.Frame(izq)
        fila.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        fila.columnconfigure(0, weight=1)
        self.e_repo = ttk.Entry(fila)
        self.e_repo.grid(row=0, column=0, sticky="ew")
        self.e_repo.bind("<Return>", lambda _e: self.agregar_repos())
        ttk.Button(fila, text="Agregar", command=self.agregar_repos).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(izq, text="Escribe dueño/repo o pega una o varias URLs de GitHub.", style="Nota.TLabel").grid(
            row=3, column=0, sticky="w", pady=(4, 0))
        self.lb_repos = tk.Listbox(izq, selectmode="extended", activestyle="none", relief="flat",
                                   highlightthickness=1, highlightcolor="#9fb3c8", font=("Segoe UI", 10))
        self.lb_repos.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(izq, command=self.lb_repos.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.lb_repos.configure(yscrollcommand=sb.set)
        self.lb_repos.bind("<Delete>", lambda _e: self.quitar_repos())
        acciones = ttk.Frame(izq)
        acciones.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(acciones, text="Quitar seleccionados", command=self.quitar_repos).pack(side="left")
        ttk.Button(acciones, text="Importar lista…", command=self.importar_lista).pack(side="left", padx=6)
        ttk.Button(acciones, text="Exportar…", command=self.exportar_lista).pack(side="left")
        self.l_cuenta = ttk.Label(acciones, text="", style="Nota.TLabel")
        self.l_cuenta.pack(side="right")

        # Destinos y opciones
        der = ttk.Frame(p)
        der.grid(row=0, column=1, sticky="nsew")

        # Se empaqueta primero (abajo) para que el botón nunca quede aplastado en pantallas pequeñas.
        botones = ttk.Frame(der)
        botones.pack(side="bottom", fill="x")
        b = ttk.Button(botones, text="▶  Iniciar respaldo", style="Primario.TButton", command=self.iniciar_respaldo)
        b.pack(side="left", fill="x", expand=True)
        self.botones_tarea.append(b)
        self.b_detener = ttk.Button(botones, text="■  Detener", command=self.detener, state="disabled")
        self.b_detener.pack(side="left", padx=(8, 0), ipady=4)

        dest = ttk.LabelFrame(der, text="¿Dónde guardar?", padding=10)
        dest.pack(fill="x")
        dest.columnconfigure(1, weight=1)
        self.v_local = tk.BooleanVar(value=self.cfg["usar_local"])
        self.v_carpeta = tk.StringVar(value=self.cfg["carpeta_local"])
        ttk.Checkbutton(dest, text="Carpeta local", variable=self.v_local).grid(row=0, column=0, sticky="w")
        ttk.Entry(dest, textvariable=self.v_carpeta, width=34).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(dest, text="…", width=3, command=self.elegir_carpeta_local).grid(row=0, column=2)
        ttk.Button(dest, text="Abrir", command=lambda: abrir(self.v_carpeta.get())).grid(row=0, column=3, padx=(4, 0))

        self.v_mega = tk.BooleanVar(value=self.cfg["usar_mega"])
        self.v_destino_mega = tk.StringVar(value=self.cfg["destino_mega"])
        ttk.Checkbutton(dest, text="MEGA / nube", variable=self.v_mega).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(dest, textvariable=self.v_destino_mega, width=34).grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(dest, text="Configurar MEGA…", command=self.dialogo_mega).grid(row=1, column=2, columnspan=2, pady=(8, 0), sticky="ew")
        self.l_mega = ttk.Label(dest, text="", style="Nota.TLabel", wraplength=420)
        self.l_mega.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        opc = ttk.LabelFrame(der, text="Qué guardar", padding=10)
        opc.pack(fill="x", pady=10)
        self.v_opc = {}
        textos = [
            ("sin_metadatos", "Solo el código (sin issues, PRs ni comentarios)"),
            ("revisiones", "Incluir revisiones de cada pull request (más lento)"),
            ("lfs", "Descargar archivos grandes Git LFS"),
            ("heritage", "Pedir copia permanente a Software Heritage"),
            ("limpiar", "Borrar la carpeta de trabajo al terminar (ahorra disco)"),
        ]
        for clave, texto in textos:
            self.v_opc[clave] = tk.BooleanVar(value=self.cfg[clave])
            ttk.Checkbutton(opc, text=texto, variable=self.v_opc[clave]).pack(anchor="w", pady=1)
        self.v_forzar = tk.BooleanVar(value=False)
        ttk.Checkbutton(opc, text="Repetir aunque se haya respaldado hace poco", variable=self.v_forzar).pack(anchor="w", pady=1)
        fila = ttk.Frame(opc)
        fila.pack(fill="x", pady=(6, 0))
        ttk.Label(fila, text="Binarios de releases hasta").pack(side="left")
        self.v_assets = tk.IntVar(value=self.cfg["assets_max_mb"])
        ttk.Spinbox(fila, from_=0, to=10000, increment=50, width=6, textvariable=self.v_assets).pack(side="left", padx=4)
        ttk.Label(fila, text="MB (0 = no)").pack(side="left")
        ttk.Label(fila, text="Repos a la vez").pack(side="left", padx=(18, 0))
        self.v_paralelo = tk.IntVar(value=self.cfg["paralelo"])
        ttk.Spinbox(fila, from_=1, to=8, width=4, textvariable=self.v_paralelo).pack(side="left", padx=4)

    def _cargar_lista(self):
        ruta = Path(self.cfg["lista"])
        self.lb_repos.delete(0, "end")
        if ruta.exists():
            for r in leer_lista(ruta):
                self.lb_repos.insert("end", r)
        self._actualizar_cuenta()

    def _guardar_lista(self):
        ruta = Path(self.cfg["lista"])
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("\n".join(self.repos()) + "\n", encoding="utf-8")
        self._actualizar_cuenta()

    def _actualizar_cuenta(self):
        self.l_cuenta.configure(text=f"{self.lb_repos.size()} repos")

    def repos(self):
        return list(self.lb_repos.get(0, "end"))

    def anadir(self, nombres):
        existentes = {r.lower() for r in self.repos()}
        n = 0
        for nombre in nombres:
            if nombre and nombre.lower() not in existentes:
                existentes.add(nombre.lower())
                self.lb_repos.insert("end", nombre)
                n += 1
        self._guardar_lista()
        return n

    def agregar_repos(self):
        texto = self.e_repo.get()
        trozos = [t for t in re.split(r"[\s,;]+", texto) if t]
        validos = [normalizar_repo(t) for t in trozos]
        malos = [t for t, v in zip(trozos, validos) if not v]
        n = self.anadir([v for v in validos if v])
        self.e_repo.delete(0, "end")
        if malos:
            messagebox.showwarning("Arca", "No parecen repos de GitHub:\n" + "\n".join(malos[:10]))
        elif n == 0 and trozos:
            log.info("Ese repo ya estaba en la lista")

    def quitar_repos(self):
        for i in reversed(self.lb_repos.curselection()):
            self.lb_repos.delete(i)
        self._guardar_lista()

    def importar_lista(self):
        ruta = filedialog.askopenfilename(title="Importar lista de repos", filetypes=[("Texto", "*.txt"), ("Todos", "*.*")])
        if ruta:
            n = self.anadir(leer_lista(ruta))
            log.info("Importados %d repos nuevos desde %s", n, ruta)

    def exportar_lista(self):
        ruta = filedialog.asksaveasfilename(title="Exportar lista", defaultextension=".txt",
                                            initialfile="repos.txt", filetypes=[("Texto", "*.txt")])
        if ruta:
            Path(ruta).write_text("\n".join(self.repos()) + "\n", encoding="utf-8")

    def elegir_carpeta_local(self):
        ruta = filedialog.askdirectory(title="Carpeta donde guardar los respaldos", initialdir=self.v_carpeta.get())
        if ruta:
            self.v_carpeta.set(str(Path(ruta)))

    def _guardar_cfg(self):
        self.cfg.update(
            usar_local=self.v_local.get(), carpeta_local=self.v_carpeta.get().strip(),
            usar_mega=self.v_mega.get(), destino_mega=self.v_destino_mega.get().strip() or "mega:arca",
            paralelo=max(1, int(self.v_paralelo.get() or 1)), assets_max_mb=max(0, int(self.v_assets.get() or 0)),
            dir_trabajo=self.v_dir.get().strip() or self.cfg["dir_trabajo"],
            **{k: v.get() for k, v in self.v_opc.items()},
        )
        config.guardar(self.cfg)

    def _destinos_pedidos(self):
        pedidos = []
        if self.v_local.get():
            pedidos.append(self.cfg["carpeta_local"])
        if self.v_mega.get():
            pedidos.append(self.cfg["destino_mega"])
        return pedidos

    def iniciar_respaldo(self):
        try:
            self._guardar_cfg()
        except (tk.TclError, ValueError):
            messagebox.showerror("Arca", "Revisa los números de las opciones.")
            return
        repos = self.repos()
        if not repos:
            messagebox.showinfo("Arca", "Agrega al menos un repositorio a la lista (o búscalos en la pestaña Buscar).")
            return
        if not shutil.which("git"):
            if messagebox.askyesno("Falta Git", "Arca necesita Git para copiar el código.\n¿Abrir la página de descarga?"):
                webbrowser.open("https://git-scm.com/download/win")
            return
        pedidos = self._destinos_pedidos()
        if not pedidos:
            messagebox.showinfo("Arca", "Marca al menos un destino: carpeta local o MEGA.")
            return
        cfg = dict(self.cfg)
        op = Opciones(dir=Path(cfg["dir_trabajo"]), sin_metadatos=cfg["sin_metadatos"], revisiones=cfg["revisiones"],
                      assets_max_mb=cfg["assets_max_mb"], lfs=cfg["lfs"], limpiar=cfg["limpiar"],
                      forzar=self.v_forzar.get(), heritage=cfg["heritage"], paralelo=cfg["paralelo"],
                      cancelar=self.cancelar)
        self.barra.configure(maximum=len(repos), value=0)

        def trabajo():
            op.destinos = resolver_destinos(pedidos, cfg["carpeta_local"])
            if not self.token:
                log.warning("Sin token de GitHub: solo 60 peticiones por hora. Agrégalo en la pestaña Ajustes.")
            conteo = ejecutar_lote(GitHub(self.token), repos, op, Estado(op.dir / "estado.json"),
                                   al_avanzar=lambda i, n, nombre, res: self.en_ui(self._avance, i, n, nombre, res))
            self.en_ui(self._fin_respaldo, conteo)

        self._lanzar(trabajo, f"Respaldando {len(repos)} repos…")

    def _avance(self, i, n, nombre, resultado):
        self.barra.configure(value=i)
        self.v_progreso_txt.set(f"{i} de {n} · {nombre}: {ETIQUETAS_ESTADO.get(resultado, resultado)}")
        self.refrescar_estado()

    def _fin_respaldo(self, conteo):
        resumen = ", ".join(f"{ETIQUETAS_ESTADO.get(k, k)}: {v}" for k, v in sorted(conteo.items())) or "nada que hacer"
        self.v_progreso_txt.set("Terminado · " + resumen)
        if conteo.get("caido"):
            messagebox.showwarning("Arca", f"{conteo['caido']} repo(s) ya no están disponibles en GitHub.\n"
                                           "Míralos en la pestaña Estado.")

    def detener(self):
        self.cancelar.set()
        self.b_detener.configure(state="disabled")
        self.v_progreso_txt.set("Deteniendo… (se para al terminar el paso actual)")
        log.warning("Deteniendo: se termina el paso en curso y no se empiezan repos nuevos.")

    # --- pestaña Buscar -----------------------------------------------------------

    def _pestana_buscar(self):
        p = ttk.Frame(self.cuaderno, padding=12)
        self.cuaderno.add(p, text="  Buscar repos  ")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)

        form = ttk.LabelFrame(p, text="Criterios (llena uno o varios)", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        self.v_busq = {}
        campos = [
            ("consulta", "Búsqueda libre", 'p. ej.  privacy language:python'),
            ("tema", "Tema (topic)", "p. ej.  digital-preservation"),
            ("usuario", "Todos los de un usuario", "p. ej.  torvalds"),
            ("org", "Todos los de una organización", "p. ej.  mozilla"),
            ("estrellas_de", "Los que un usuario marcó con ★", "tu usuario de GitHub"),
        ]
        for i, (clave, texto, ayuda) in enumerate(campos):
            fila, col = divmod(i, 2)
            ttk.Label(form, text=texto).grid(row=fila * 2, column=col * 2, sticky="w", padx=(0 if col == 0 else 16, 6))
            self.v_busq[clave] = tk.StringVar()
            ttk.Entry(form, textvariable=self.v_busq[clave], width=34).grid(row=fila * 2, column=col * 2 + 1, sticky="ew")
            ttk.Label(form, text=ayuda, style="Nota.TLabel").grid(row=fila * 2 + 1, column=col * 2 + 1, sticky="w", pady=(0, 6))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        extra = ttk.Frame(form)
        extra.grid(row=4, column=2, columnspan=2, sticky="w", padx=(16, 0))
        ttk.Label(extra, text="Mín. ★").pack(side="left")
        self.v_min = tk.IntVar(value=0)
        ttk.Spinbox(extra, from_=0, to=1000000, increment=100, width=8, textvariable=self.v_min).pack(side="left", padx=(4, 12))
        ttk.Label(extra, text="Máximo").pack(side="left")
        self.v_limite = tk.IntVar(value=100)
        ttk.Spinbox(extra, from_=1, to=1000, increment=50, width=6, textvariable=self.v_limite).pack(side="left", padx=4)
        self.v_forks = tk.BooleanVar(value=False)
        ttk.Checkbutton(extra, text="Incluir forks", variable=self.v_forks).pack(side="left", padx=(12, 0))
        b = ttk.Button(form, text="🔍  Buscar", style="Primario.TButton", command=self.buscar)
        b.grid(row=5, column=0, columnspan=4, sticky="e", pady=(6, 0))
        self.botones_tarea.append(b)

        res = ttk.Frame(p)
        res.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        res.columnconfigure(0, weight=1)
        res.rowconfigure(0, weight=1)
        self.arbol_busq = ttk.Treeview(res, columns=("repo", "estrellas", "desc"), show="headings", selectmode="extended")
        for col, texto, ancho, est in (("repo", "Repositorio", 280, False), ("estrellas", "★", 80, False), ("desc", "Descripción", 520, True)):
            self.arbol_busq.heading(col, text=texto)
            self.arbol_busq.column(col, width=ancho, stretch=est, anchor="e" if col == "estrellas" else "w")
        self.arbol_busq.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(res, command=self.arbol_busq.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.arbol_busq.configure(yscrollcommand=sb.set)
        self.arbol_busq.bind("<Double-1>", lambda _e: self._abrir_seleccion_busq())
        acc = ttk.Frame(res)
        acc.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(acc, text="Agregar seleccionados a la lista", command=lambda: self._agregar_busq(False)).pack(side="left")
        ttk.Button(acc, text="Agregar todos", command=lambda: self._agregar_busq(True)).pack(side="left", padx=6)
        ttk.Button(acc, text="Ver en GitHub", command=self._abrir_seleccion_busq).pack(side="left")
        self.l_busq = ttk.Label(acc, text="", style="Nota.TLabel")
        self.l_busq.pack(side="right")

    def buscar(self):
        criterios = {k: v.get().strip() or None for k, v in self.v_busq.items()}
        try:
            minimo, limite = int(self.v_min.get() or 0), int(self.v_limite.get() or 100)
        except (tk.TclError, ValueError):
            messagebox.showerror("Arca", "Revisa los números de estrellas y máximo.")
            return
        if not any(criterios.values()) and not minimo:
            messagebox.showinfo("Arca", "Escribe al menos un criterio de búsqueda.")
            return
        forks = self.v_forks.get()

        def trabajo():
            encontrados = []
            try:
                for r in buscar(GitHub(self.token), criterios["consulta"], criterios["usuario"], criterios["org"],
                                criterios["estrellas_de"], criterios["tema"], minimo, limite, forks):
                    encontrados.append(r)
            except ErrorGitHub as e:
                log.error("Búsqueda: %s", e)
            log.info("Búsqueda: %d repos encontrados", len(encontrados))
            self.en_ui(self._mostrar_busq, encontrados)

        self._lanzar(trabajo, "Buscando…", indeterminado=True)

    def _mostrar_busq(self, encontrados):
        self.resultados = encontrados
        self.arbol_busq.delete(*self.arbol_busq.get_children())
        for i, r in enumerate(encontrados):
            self.arbol_busq.insert("", "end", iid=str(i), values=(
                r["full_name"], f"{r.get('stargazers_count', 0):,}", (r.get("description") or "")[:200]))
        self.l_busq.configure(text=f"{len(encontrados)} resultados")
        self.v_progreso_txt.set("Listo.")

    def _agregar_busq(self, todos):
        ids = self.arbol_busq.get_children() if todos else self.arbol_busq.selection()
        n = self.anadir([self.resultados[int(i)]["full_name"] for i in ids])
        self.l_busq.configure(text=f"{n} agregados a la lista de respaldo")

    def _abrir_seleccion_busq(self):
        for i in self.arbol_busq.selection()[:5]:
            webbrowser.open(self.resultados[int(i)]["html_url"])

    # --- pestaña Estado -------------------------------------------------------------

    def _pestana_estado(self):
        p = ttk.Frame(self.cuaderno, padding=12)
        self.cuaderno.add(p, text="  Estado  ")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)
        self.l_resumen = ttk.Label(p, text="", font=("Segoe UI", 11))
        self.l_resumen.grid(row=0, column=0, sticky="w", pady=(0, 8))
        cols = (("repo", "Repositorio", 230), ("estado", "Estado", 110), ("ultimo", "Último respaldo", 150),
                ("tam", "Tamaño", 80), ("donde", "Guardado en", 260), ("nota", "Detalle", 260))
        self.arbol_estado = ttk.Treeview(p, columns=[c[0] for c in cols], show="headings")
        for col, texto, ancho in cols:
            self.arbol_estado.heading(col, text=texto)
            self.arbol_estado.column(col, width=ancho, stretch=col in ("donde", "nota"))
        self.arbol_estado.tag_configure("caido", foreground="#c62828")
        self.arbol_estado.tag_configure("error", foreground="#a55f00")
        self.arbol_estado.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(p, command=self.arbol_estado.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.arbol_estado.configure(yscrollcommand=sb.set)
        self.arbol_estado.bind("<Double-1>", lambda _e: self._abrir_paquete())

        acc = ttk.Frame(p)
        acc.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(acc, text="Actualizar", command=self.refrescar_estado).pack(side="left")
        b = ttk.Button(acc, text="Enviar paquetes a los destinos marcados", command=self.enviar_pendientes)
        b.pack(side="left", padx=6)
        self.botones_tarea.append(b)
        b = ttk.Button(acc, text="Verificar integridad", command=self.verificar)
        b.pack(side="left")
        self.botones_tarea.append(b)
        ttk.Button(acc, text="Abrir paquete", command=self._abrir_paquete).pack(side="left", padx=6)
        ttk.Label(acc, text="Doble clic en una fila para ver su paquete.", style="Nota.TLabel").pack(side="right")

    def refrescar_estado(self):
        ruta = Path(self.cfg["dir_trabajo"]) / "estado.json"
        try:
            datos = Estado(ruta).todos() if ruta.exists() else {}
        except ValueError:
            return
        self.arbol_estado.delete(*self.arbol_estado.get_children())
        self._estado = datos
        totales = {}
        bytes_ok = 0
        orden = {"caido": 0, "error": 1}
        for nombre, r in sorted(datos.items(), key=lambda x: (orden.get(x[1].get("estado"), 2), x[0].lower())):
            est = r.get("estado", "?")
            totales[est] = totales.get(est, 0) + 1
            bytes_ok += r.get("bytes") or 0 if est == "ok" else 0
            if est == "caido":
                nota = f"HTTP {r.get('codigo')}: {r.get('motivo')} · {'tienes copia' if r.get('sha256') else 'sin copia'}"
            elif est == "error":
                nota = (r.get("error") or "")[:160]
            else:
                nota = f"{r.get('estrellas') or 0:,} ★"
            donde = ", ".join(Path(d).name if es_local(d) else d for d in r.get("subido") or []) or "—"
            self.arbol_estado.insert("", "end", iid=nombre, tags=(est,), values=(
                nombre, ETIQUETAS_ESTADO.get(est, est), (r.get("ultimo") or "")[:16].replace("T", " "),
                tamano_legible(r["bytes"]) if r.get("bytes") else "", donde, nota))
        partes = [f"{len(datos)} repos", f"{totales.get('ok', 0)} respaldados ({tamano_legible(bytes_ok)})"]
        if totales.get("caido"):
            partes.append(f"{totales['caido']} caídos")
        if totales.get("error"):
            partes.append(f"{totales['error']} con error")
        self.l_resumen.configure(text="   ·   ".join(partes) if datos else "Aún no hay respaldos.")

    def _abrir_paquete(self):
        sel = self.arbol_estado.selection()
        if not sel:
            return
        archivo = (self._estado.get(sel[0]) or {}).get("archivo")
        if archivo and Path(archivo).exists():
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(Path(archivo))], **SIN_VENTANA)
            else:
                abrir(Path(archivo).parent)
        else:
            messagebox.showinfo("Arca", "No hay paquete local de ese repo (puede estar solo en la nube).")

    def enviar_pendientes(self):
        self._guardar_cfg()
        pedidos = self._destinos_pedidos()
        if not pedidos:
            messagebox.showinfo("Arca", "Marca al menos un destino en la pestaña Respaldar.")
            return
        cfg = dict(self.cfg)

        def trabajo():
            destinos = resolver_destinos(pedidos, cfg["carpeta_local"])
            subir_pendientes(Estado(Path(cfg["dir_trabajo"]) / "estado.json"), destinos, cfg["dir_trabajo"],
                             cancelar=self.cancelar)

        self._lanzar(trabajo, "Enviando paquetes…", indeterminado=True)

    def verificar(self):
        from .cli import verificar_carpetas
        carpetas = [c for c in (Path(self.cfg["dir_trabajo"]) / "archivos", Path(self.cfg["carpeta_local"])) if c.exists()]

        def trabajo():
            buenos, malos = verificar_carpetas(carpetas)
            self.en_ui(messagebox.showinfo if not malos else messagebox.showerror, "Verificación",
                       f"Paquetes correctos: {buenos}\nPaquetes dañados: {malos}")

        self._lanzar(trabajo, "Verificando…", indeterminado=True)

    # --- pestaña Ajustes --------------------------------------------------------------

    def _pestana_ajustes(self):
        p = ttk.Frame(self.cuaderno, padding=12)
        self.cuaderno.add(p, text="  Ajustes  ")
        p.columnconfigure(0, weight=1)

        gh = ttk.LabelFrame(p, text="Acceso a GitHub", padding=10)
        gh.grid(row=0, column=0, sticky="ew")
        gh.columnconfigure(1, weight=1)
        self.l_token = ttk.Label(gh, text="Comprobando…")
        self.l_token.grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(gh, text="Token personal").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.e_token = ttk.Entry(gh, show="•")
        self.e_token.grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(gh, text="Guardar", command=self.guardar_token).grid(row=1, column=2, pady=(8, 0))
        ttk.Button(gh, text="Olvidar", command=self.olvidar_token).grid(row=1, column=3, padx=(6, 0), pady=(8, 0))
        ttk.Label(gh, style="Nota.TLabel", wraplength=900, justify="left", text=(
            "Con un token GitHub permite 5000 consultas por hora en lugar de 60 y se pueden guardar las discusiones. "
            "No necesita ningún permiso para repos públicos. Se guarda cifrado con tu usuario de Windows.")).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(gh, text="Crear un token en GitHub…", command=lambda: webbrowser.open(
            "https://github.com/settings/tokens/new?description=Arca%20respaldo")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        car = ttk.LabelFrame(p, text="Carpeta de trabajo", padding=10)
        car.grid(row=1, column=0, sticky="ew", pady=10)
        car.columnconfigure(0, weight=1)
        self.v_dir = tk.StringVar(value=self.cfg["dir_trabajo"])
        ttk.Entry(car, textvariable=self.v_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(car, text="…", width=3, command=self.elegir_dir).grid(row=0, column=1, padx=6)
        ttk.Button(car, text="Abrir", command=lambda: abrir(self.v_dir.get())).grid(row=0, column=2)
        ttk.Label(car, style="Nota.TLabel", wraplength=900, justify="left", text=(
            "Aquí se descargan los repos antes de empaquetarlos y aquí se guarda el registro de estado. "
            "Conservarla hace que las siguientes copias solo bajen lo nuevo.")).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        her = ttk.LabelFrame(p, text="Herramientas necesarias", padding=10)
        her.grid(row=2, column=0, sticky="ew")
        her.columnconfigure(1, weight=1)
        self.l_git = ttk.Label(her, text="Git: comprobando…")
        self.l_git.grid(row=0, column=0, sticky="w")
        ttk.Button(her, text="Descargar Git", command=lambda: webbrowser.open("https://git-scm.com/download/win")).grid(row=0, column=2, sticky="e")
        self.l_rclone = ttk.Label(her, text="rclone: comprobando…")
        self.l_rclone.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(her, text="Instalar rclone", command=self.instalar_rclone).grid(row=1, column=2, sticky="e", pady=(6, 0))
        ttk.Button(her, text="Volver a comprobar", command=self.comprobar_entorno).grid(row=2, column=2, sticky="e", pady=(10, 0))

        otros = ttk.Frame(p)
        otros.grid(row=3, column=0, sticky="ew", pady=10)
        ttk.Button(otros, text="Abrir registro detallado (arca.log)",
                   command=lambda: abrir(Path(self.cfg["dir_trabajo"]) / "arca.log")).pack(side="left")
        ttk.Label(otros, text=f"Arca {__version__} · el conocimiento pertenece a quien lo necesita",
                  style="Nota.TLabel").pack(side="right")

    def elegir_dir(self):
        ruta = filedialog.askdirectory(title="Carpeta de trabajo", initialdir=self.v_dir.get())
        if ruta:
            self.v_dir.set(str(Path(ruta)))
            self._guardar_cfg()
            self._log_a_archivo()
            self.refrescar_estado()

    def guardar_token(self):
        token = self.e_token.get().strip()
        if not token:
            return
        self.cfg["token_cifrado"] = config.cifrar_token(token)
        config.guardar(self.cfg)
        self.e_token.delete(0, "end")
        self.comprobar_entorno()

    def olvidar_token(self):
        self.cfg["token_cifrado"] = ""
        config.guardar(self.cfg)
        self.comprobar_entorno()

    def instalar_rclone(self):
        if os.name == "nt" and shutil.which("winget"):
            subprocess.Popen(["cmd", "/c", "start", "Instalar rclone", "cmd", "/k",
                              "winget install --id Rclone.Rclone -e && echo. && echo Listo. Cierra esta ventana y pulsa 'Volver a comprobar' en Arca."])
        else:
            webbrowser.open("https://rclone.org/downloads/")

    # --- MEGA -----------------------------------------------------------------------

    def dialogo_mega(self):
        try:
            rclone()
        except SinRclone:
            if messagebox.askyesno("Falta rclone", "Para subir a MEGA, Arca usa el programa gratuito rclone.\n"
                                                   "¿Instalarlo ahora?"):
                self.instalar_rclone()
            return
        d = tk.Toplevel(self.raiz)
        d.title("Configurar MEGA")
        d.transient(self.raiz)
        d.resizable(False, False)
        marco = ttk.Frame(d, padding=16)
        marco.pack(fill="both")
        ttk.Label(marco, text="Conectar tu cuenta de MEGA", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(marco, style="Nota.TLabel", wraplength=380, justify="left", text=(
            "Los datos se entregan a rclone, que guarda la contraseña ofuscada en su propia configuración. "
            "Arca no los almacena. Si tu cuenta usa verificación en dos pasos, configúrala con 'rclone config'.")).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
        ttk.Label(marco, text="Correo").grid(row=2, column=0, sticky="w")
        e_correo = ttk.Entry(marco, width=36)
        e_correo.grid(row=2, column=1, pady=3)
        ttk.Label(marco, text="Contraseña").grid(row=3, column=0, sticky="w")
        e_pass = ttk.Entry(marco, width=36, show="•")
        e_pass.grid(row=3, column=1, pady=3)
        v_msg = tk.StringVar()
        ttk.Label(marco, textvariable=v_msg, wraplength=380).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        botones = ttk.Frame(marco)
        botones.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        remoto = (self.v_destino_mega.get().split(":", 1)[0] or "mega").strip()

        def conectar():
            correo, clave = e_correo.get().strip(), e_pass.get()
            if not correo or not clave:
                v_msg.set("Escribe correo y contraseña.")
                return
            b_ok.configure(state="disabled")
            v_msg.set("Conectando con MEGA…")

            def trabajo():
                try:
                    configurar_mega(correo, clave, remoto)
                    self.en_ui(listo, True, f"MEGA conectado. Los respaldos irán a {remoto}:")
                except (ErrorComando, SinRclone, OSError) as e:
                    self.en_ui(listo, False, f"No se pudo conectar: {str(e)[-200:]}")

            threading.Thread(target=trabajo, daemon=True).start()

        def listo(ok, mensaje):
            v_msg.set(mensaje)
            b_ok.configure(state="normal")
            if ok:
                self.v_mega.set(True)
                self._guardar_cfg()
                self.comprobar_entorno()
                d.after(1200, d.destroy)

        b_ok = ttk.Button(botones, text="Conectar", command=conectar)
        b_ok.pack(side="right")
        ttk.Button(botones, text="Cancelar", command=d.destroy).pack(side="right", padx=6)
        e_correo.focus_set()
        d.bind("<Return>", lambda _e: conectar())
        d.grab_set()

    # --- entorno ---------------------------------------------------------------------

    def comprobar_entorno(self):
        def trabajo():
            token = config.descifrar_token(self.cfg.get("token_cifrado"))
            origen = "guardado en Arca"
            if not token:
                token = obtener_token()
                origen = "de GitHub CLI" if token else "no encontrado"
            usuario = None
            if token:
                try:
                    usuario = GitHub(token).get("/user").get("login")
                except ErrorGitHub:
                    token, origen = None, "el token es inválido o caducó"
                except OSError:
                    usuario = "? (sin conexión)"
            git = shutil.which("git")
            try:
                tiene_rclone = bool(rclone())
            except SinRclone:
                tiene_rclone = False
            remotos = remotos_configurados() if tiene_rclone else []
            self.en_ui(self._mostrar_entorno, token, origen, usuario, git, tiene_rclone, remotos)

        threading.Thread(target=trabajo, daemon=True).start()

    def _mostrar_entorno(self, token, origen, usuario, git, tiene_rclone, remotos):
        self.token = token
        if token:
            self.chips["github"].configure(text=f"● GitHub: @{usuario}", fg=VERDE)
            self.l_token.configure(text=f"✔ Conectado como @{usuario} (token {origen}).")
        else:
            self.chips["github"].configure(text="● GitHub: sin token", fg=AMBAR)
            self.l_token.configure(text=f"Sin token ({origen}). Funciona, pero muy lento: pega un token abajo.")
        self.chips["git"].configure(text="● Git" if git else "● Falta Git", fg=VERDE if git else ROJO)
        self.l_git.configure(text=f"✔ Git: {git}" if git else "✖ Git no está instalado (es necesario).")
        self.l_rclone.configure(text="✔ rclone instalado (para MEGA y otras nubes)" if tiene_rclone
                                else "rclone no instalado: solo necesario para MEGA / nube.")
        remoto = (self.cfg.get("destino_mega") or "mega:arca").split(":", 1)[0]
        if remoto in remotos:
            self.chips["mega"].configure(text="● MEGA conectado", fg=VERDE)
            self.l_mega.configure(text=f"✔ '{remoto}' configurado en rclone.")
        else:
            self.chips["mega"].configure(text="● MEGA sin configurar → carpeta local", fg=AMBAR)
            self.l_mega.configure(text="MEGA aún no está configurado: mientras tanto todo se guarda en la carpeta local. "
                                       "Cuando lo conectes, usa «Enviar paquetes» en la pestaña Estado para subir lo ya guardado.")

    def cerrar(self):
        if self.ocupado and not messagebox.askyesno("Arca", "Hay una tarea en curso. ¿Salir de todos modos?\n"
                                                            "Lo ya terminado queda guardado."):
            return
        self.cancelar.set()
        try:
            self._guardar_cfg()
        except (tk.TclError, ValueError):
            pass
        self.raiz.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Arca.Respaldo")
        except (AttributeError, OSError):
            pass
    raiz = tk.Tk()
    App(raiz)
    raiz.mainloop()
    return 0
