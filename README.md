# 🛶 Arca: respaldo de repositorios de GitHub

```
 ______________________________________________
< El conocimiento que no se copia, se pierde. >
 ----------------------------------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
```

Arca guarda **el código y también el conocimiento** de los repositorios de GitHub, por si un día desaparecen:

- 📦 **Código completo:** todas las ramas, tags, el código de los pull requests y la wiki.
- 💬 **Conocimiento:** issues, pull requests, comentarios, revisiones de código, discusiones, releases, etiquetas e hitos.
- 📖 **Legible por humanos:** todo se convierte a Markdown con un índice; se puede leer sin GitHub y sin herramientas.
- 🗜️ **Comprimido y verificable:** un `.zip` por repo, con su huella SHA-256 e instrucciones para restaurarlo.
- ☁️ **Guardado donde quieras:** una carpeta local, un USB, un NAS, **MEGA**, Google Drive, Internet Archive y más de 70 servicios.
- 🚨 **Detecta bajas:** te avisa si un repo fue borrado, se volvió privado o lo bloquearon por DMCA (HTTP 451).

---

## ⬇️ Descargar

- **Sin git:** en esta página pulsa **Code → Download ZIP** y descomprímelo.
- **Con git:**
  ```bash
  git clone https://github.com/JafetBrito/arca.git
  ```

---

## ¿Cómo quieres usarlo? Elige un camino

| | **Camino A: solo código** 🖥️ | **Camino B: programa con ventana** 🪟 |
|---|---|---|
| Para quién | Quien se maneja con la terminal o quiere automatizar | Cualquiera: botones, listas y casillas |
| Qué ejecutas | `arca respaldar ...` en la consola | `Arca.exe` con doble clic |
| Extras | 🐮🌈 vaca que habla y arcoíris (cowsay + lolcat) | Pestañas de Buscar, Estado y Ajustes |
| Necesita compilar | No | Una vez, con `construir_exe.bat` |

Los dos caminos usan el mismo motor y los mismos respaldos, así que puedes combinarlos.

### Requisitos (ambos caminos)

| Programa | Para qué | Cómo instalarlo |
|---|---|---|
| **Python 3.10+** | Ejecutar o compilar Arca | https://www.python.org/downloads/ (marca *"Add python.exe to PATH"*) |
| **Git** | Copiar el código de los repos | https://git-scm.com/download/win o `winget install Git.Git` |
| **rclone** *(opcional)* | Subir a MEGA u otras nubes | `winget install Rclone.Rclone` |
| **GitHub CLI** *(opcional)* | Aportar el token de GitHub de forma automática | `winget install GitHub.cli` y luego `gh auth login` |

> **Token de GitHub (muy recomendado):** sin token, GitHub solo permite 60 consultas por hora y no se pueden guardar las discusiones; con token son 5000. Puedes obtenerlo de tres formas:
> - con `gh auth login`;
> - creando uno en https://github.com/settings/tokens/new (sin marcar ningún permiso) y guardándolo en la variable `GITHUB_TOKEN`;
> - pegándolo en *Ajustes* dentro del programa con ventana.

---

## 🅰️ Camino A: solo código (consola)

1. Descarga y descomprime el proyecto, y abre una terminal dentro de su carpeta.
2. Comprueba que todo funciona:
   ```bash
   arca dice "Hola, mundo"
   ```
   Si ves una vaca de colores, ya está.
   - En **PowerShell** escribe `.\arca` en lugar de `arca`.
   - En **Linux o macOS** usa `python3 -m arca`.

### Uso básico

**Respaldar repos sueltos.** Si no indicas destino, se guardan en `respaldos/`:
```bash
arca respaldar torvalds/linux https://github.com/python/cpython
```

**Encontrar repos y añadirlos a `repos.txt`:**
```bash
arca buscar --tema digital-preservation --estrellas-min 100
```
```bash
arca buscar --consulta "privacy language:python" --estrellas-min 500 --limite 200
```
```bash
arca buscar --org mozilla
```
```bash
arca buscar --estrellas-de TU_USUARIO
```

**Respaldar toda la lista.** Para ir a MEGA, configúralo antes (ver más abajo). Si no está configurado, se usa la carpeta local:
```bash
arca respaldar --destino mega:arca
```

**Guardar en un disco externo:**
```bash
arca respaldar --destino E:\respaldos-github
```

**Ver qué está respaldado y qué desapareció de GitHub:**
```bash
arca estado
```

**Subir a MEGA lo que ya tenías guardado en local:**
```bash
arca subir --destino mega:arca
```

**Comprobar que ningún paquete se dañó:**
```bash
arca verificar
```

**Pedir también una copia permanente a Software Heritage** (el archivo mundial de código, apoyado por la UNESCO):
```bash
arca heritage
```

**La vaca del arca habla.** Las figuras disponibles son `vaca`, `arca` y `pinguino`:
```bash
arca dice "Respaldemos el mundo" --figura arca
```

### Opciones de `respaldar`

| Opción | Qué hace |
|---|---|
| `--destino X` | Carpeta local o remoto de rclone (`mega:arca`). Se puede repetir para guardar en varios sitios a la vez |
| `--paralelo 4` | Respalda 4 repos a la vez (por defecto 2) |
| `--sin-metadatos` | Guarda solo el código, sin issues ni comentarios; es más rápido |
| `--revisiones` | Incluye las revisiones de cada PR (aprobado o cambios pedidos); hace una consulta por PR |
| `--assets-max-mb 200` | Baja también los binarios de las releases, hasta 200 MB cada uno |
| `--lfs` | Baja los archivos grandes de Git LFS (requiere `git-lfs`) |
| `--limpiar` | Borra la carpeta de trabajo cuando todo quedó a salvo en los destinos |
| `--heritage` | Pide además una copia a Software Heritage |
| `--forzar` | Repite aunque se haya respaldado hace menos de 20 h |

Opciones generales, que van **antes** del comando:

| Opción | Qué hace |
|---|---|
| `--dir D:\arca` | Carpeta de trabajo (por defecto `datos`) |
| `--carpeta-local E:\respaldos` | Carpeta de respaldo local (por defecto `respaldos`) |
| `--serio` | Sin vaca ni colores. También se desactivan con la variable `NO_COLOR` |

**Para automatizarlo** (por ejemplo, cada noche con el Programador de tareas de Windows):
```bash
arca --serio respaldar --destino mega:arca --limpiar
```

---

## 🅱️ Camino B: compilar el `.exe` y usar la ventana

1. Descarga y descomprime el proyecto.
2. Haz doble clic en **`construir_exe.bat`**. Instala PyInstaller por su cuenta y tarda 1 o 2 minutos.
3. Abre **`dist\Arca.exe`**. Puedes copiarlo a donde quieras o compartirlo; funciona sin Python.

> 💡 **¿Quieres la ventana sin compilar?** Haz doble clic en `arca.bat`: abre la misma ventana usando Python.

> ⚠️ Windows puede mostrar *"Windows protegió tu PC"* porque el `.exe` no lleva firma digital. Pulsa **Más información → Ejecutar de todas formas**.

### Las pestañas

| Pestaña | Qué haces ahí |
|---|---|
| **Respaldar** | Pegas URLs o `dueño/repo` (también varias a la vez), eliges dónde guardar y qué incluir, y pulsas **▶ Iniciar respaldo** |
| **Buscar repos** | Buscas por texto, tema, usuario, organización o estrellas, y agregas los resultados a la lista |
| **Estado** | Ves qué está respaldado y qué **desapareció de GitHub**. Desde aquí envías paquetes a la nube y verificas su integridad; con doble clic en una fila abres su paquete |
| **Ajustes** | Token de GitHub (se guarda cifrado con tu usuario de Windows), carpeta de trabajo y comprobación de Git y rclone |

**¿Dónde quedan los respaldos?** En `Documentos\Arca\respaldos`. Si marcas MEGA pero todavía no está configurado, se usa esa carpeta local automáticamente.

---

## ☁️ Configurar MEGA (u otra nube)

**Desde la ventana:** pestaña *Respaldar* → **Configurar MEGA…** → escribe tu correo y contraseña → **Conectar**. Después, en *Estado*, pulsa **Enviar paquetes a los destinos marcados** para subir lo que ya tenías guardado en local.

**Desde la consola:**
```bash
rclone config
```
Elige `n` (nuevo), ponle de nombre `mega`, de tipo `mega`, e introduce tu correo y contraseña. Luego:
```bash
arca subir --destino mega:arca
```

Con `rclone config` puedes crear más remotos y usarlos como destino: `gdrive` (Google Drive), `ia` (Internet Archive, tipo `internetarchive`), `b2`, `s3`, `onedrive`, `dropbox`, `sftp`...

🔐 Tus contraseñas las guarda rclone en su propia configuración, ofuscadas. Arca nunca las almacena.

---

## 📦 Qué hay dentro de cada respaldo

`respaldos/<dueño>/<dueño>__<repo>__AAAAMMDD.zip`:
```text
LEEME.txt                      instrucciones de restauración
<repo>/repo.bundle             código completo (ramas, tags, PRs)
<repo>/wiki.bundle             wiki del proyecto
<repo>/conocimiento/INDICE.md  issues, PRs y discusiones en Markdown legible
<repo>/meta/*.jsonl            datos crudos de la API (para migrar a Gitea/Forgejo/GitLab)
<repo>/releases/               binarios publicados (si se pidió)
<repo>/MANIFIESTO.json         SHA-256 de cada archivo
```

**Para restaurar el código:**
```bash
git clone repo.bundle mi-repo
```

**Para volver a publicarlo en otro sitio:**
```bash
git clone --mirror repo.bundle mi-repo.git
```
```bash
git -C mi-repo.git push --mirror https://codeberg.org/TU_USUARIO/mi-repo.git
```

Cada día que respaldas se genera un `.zip` nuevo con fecha, así que vas acumulando versiones.

---

## ⚠️ Límites conocidos

- La búsqueda de GitHub devuelve **como máximo 1000 resultados por consulta**. Para cubrir más, divídela por rangos (`stars:500..1000`, `stars:1000..5000`, ...).
- Con token tienes 5000 consultas por hora. Un repo con 10 000 issues y PRs gasta unas 300. Cuando se agota, Arca espera solo.
- **MEGA gratis** ofrece 20 GB y tiene un límite de transferencia. Para colecciones grandes, combina varios destinos.
- Si tu cuenta de MEGA usa **verificación en dos pasos**, configúrala con `rclone config`.
- **No se guardan:** los logs de GitHub Actions, los Projects y los avatares.
- Respeta la licencia de cada proyecto: preservar está bien, pero redistribuir depende de la licencia.

---

## 🗂️ Estructura del código

```text
arca.bat              atajo de consola (sin argumentos abre la ventana)
construir_exe.bat     compila dist\Arca.exe
arca_app.py           punto de entrada (ventana o consola)
repos.txt             lista de ejemplo
arca/
  cli.py              comandos de consola
  gui.py              interfaz gráfica (tkinter)
  proceso.py          flujo: comprobar → clonar → metadatos → empaquetar → guardar
  github.py           API de GitHub (REST + GraphQL, límites, reintentos)
  git_repo.py         espejo git y bundles
  metadatos.py        issues, PRs, comentarios, discusiones, releases
  conocimiento.py     conversión a Markdown
  empaquetar.py       .zip + manifiesto SHA-256
  subir.py            carpeta local / rclone (MEGA y otras nubes)
  estado.py           registro de avance y de repos caídos
  heritage.py         Software Heritage
  config.py           ajustes de la ventana (token cifrado con DPAPI)
  diversion.py        🐮🌈 cowsay + lolcat en Python puro
```

Sin dependencias externas: solo la biblioteca estándar de Python, más Git y rclone.

---

## 🤝 Contribuir y licencia

Las mejoras son bienvenidas: abre un *issue* o un *pull request*.

Arca se distribuye bajo la **licencia MIT** (ver [LICENSE](LICENSE)). Puedes usarlo, copiarlo, modificarlo y redistribuirlo libremente, siempre que conserves el aviso de copyright.

---

*En nombre de la humanidad: el conocimiento pertenece a quien lo necesita. Cuídalo y compártelo.* 🛶
