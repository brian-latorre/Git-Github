# Taller Colaborativo de Git y GitHub

Un espacio abierto, práctico y 100% gratuito diseñado para aprender a colaborar en equipo utilizando Git y GitHub, sin importar tu nivel de experiencia técnica previo.

---

## ¿De qué trata este curso y cuál es su propósito?

La forma tradicional de aprender Git suele ser frustrante: clases teóricas donde se escucha pasivamente a un instructor, presentaciones con diagramas abstractos y listas interminables de comandos en la terminal que se olvidan al primer error.

Este taller propone una dinámica diferente: **aprender haciendo en conjunto**.

* **Pensado para todos los perfiles:** No necesitas conocimientos previos de programación. Está diseñado tanto para personas de áreas no técnicas (diseño, redacción, análisis, gestión de proyectos) que necesitan colaborar en entornos digitales, como para quienes están dando sus primeros pasos en el desarrollo de software.
* **Aprendizaje activo y colectivo:** En lugar de ser un espectador, trabajas directamente en tu computadora desde el primer minuto. Cada participante aporta su parte y la progresión se realiza paso a paso, asegurando que todo el grupo avance al mismo ritmo y nadie se quede atrás.
* **Apoyo con Inteligencia Artificial:** Incorporamos herramientas de IA como asistentes de aprendizaje para explicar conceptos con analogías cotidianas, resolver dudas en tiempo real y perderle el miedo a la consola.
* **Ecosistema Google y coordinación grupal:** Las sesiones en vivo se llevan a cabo mediante **Google Meet**, complementadas con recursos y notas compartidas para garantizar un punto de encuentro ágil y accesible para todos.
* **Plataforma web y tracker de integración:** Contamos con una aplicación web propia y un sistema de seguimiento ligero en tiempo real. Esto permite ver cómo se va construyendo el árbol de trabajo colaborativo, verificar la participación y celebrar los aportes del equipo en directo.

---

## ¿Cómo funciona la dinámica de clase?

1. **Punto de Encuentro:** Nos conectamos a la sesión grupal en Google Meet a la hora indicada.
2. **Entorno Local Listo:** Cada integrante abre su editor de código y su terminal en su máquina.
3. **Asistente de Integración:** Se inicia un pequeño programa local (`iniciar_alumno.bat` en Windows o `python client/let_track.py`) que conecta tu terminal con la pizarra en vivo de la clase.
4. **Construcción en Equipo:** Realizamos dinámicas guiadas —crear archivos, registrar cambios, abrir ramas individuales y resolver cruces de información— experimentando el trabajo real de un equipo colaborativo.

---

## Puesta en marcha rápida (Para Alumnos)

### 1. Requisitos Iniciales
Solo necesitas tener instalado en tu computadora:
* **Git** (control de versiones)
* **Python** (versión 3.10 o superior)
* **Visual Studio Code** (o tu editor de texto preferido)

> Si usas Windows y tienes el sistema limpio, puedes instalar todo de una sola vez abriendo una **Terminal** (`Win + X`) y ejecutando:
> ```powershell
> winget install Git.Git Python.Python.3.12 Microsoft.VisualStudioCode --accept-package-agreements --accept-source-agreements
> ```

### 2. Obtener el Proyecto
Clona este repositorio en tu equipo e ingresa a la carpeta:
```bash
git clone https://github.com/brian-latorre/Git-Github.git
cd Git-Github
```

### 3. Registrar tu Identidad
Configura tu firma de autor en Git desde tu terminal:
```bash
git config --global user.name "Tu Nombre y Apellido"
git config --global user.email "tu-correo@ejemplo.com"
```
El sistema de seguimiento identificará tu autoría automáticamente a partir de esta configuración.

### 4. Conectarte a la Sesión
* **En Windows (Recomendado):** Haz doble clic sobre el archivo `iniciar_alumno.bat` en la raíz del proyecto. Este archivo comprobará tus dependencias y abrirá la conexión con la clase de inmediato.
* **Desde la terminal (Cualquier sistema operativo):**
  ```bash
  pip install -r client/requirements.txt
  python client/let_track.py
  ```

Una vez conectado, abre una segunda pestaña de terminal en tu editor para ejecutar tus comandos de Git durante las dinámicas.

### Personalizar los enlaces sin subirlos al repositorio

El lanzador abre cada URL que encuentre en `enlaces.md`, una por línea. Para usar
enlaces propios, copia ese archivo con el nombre `enlaces.local.md` y edita la
copia:

```powershell
Copy-Item enlaces.md enlaces.local.md
```

Al iniciar, `iniciar_alumno.bat` usará `enlaces.local.md` si existe; si no,
usará el archivo compartido `enlaces.md`. El archivo local está incluido en
`.gitignore`, por lo que Git no lo mostrará como un archivo sin seguimiento ni
lo incluirá en un commit. Se pueden añadir comentarios comenzando la línea con
`#` y dejar líneas vacías; las líneas que comiencen con `http://` o `https://`
se abrirán en el navegador predeterminado.

El `.gitignore` sí debe estar en el repositorio: no cancela las subidas ni
impide hacer `git push`. Solo indica a Git qué archivos locales debe ignorar.
Por eso la regla `enlaces.local.md` protege a todos los alumnos, mientras que
cada alumno mantiene su archivo personalizado únicamente en su computadora.

---

## Enlaces de la Sesión

* **Videollamada en Google Meet:** [Unirse a la sesión](https://meet.google.com/xhb-dfgw-fbc)
* **Plataforma y Tablero en Vivo:** [git-course-tracker-prod.fly.dev](https://git-course-tracker-prod.fly.dev)
* **Visualizador del Árbol de Git:** [git-course-tracker-prod.fly.dev/grafo](https://git-course-tracker-prod.fly.dev/grafo)
* **Notas y Cuaderno de Trabajo:** [Notebook del Curso](https://notebook.google.com/notebook/24bca4a3-ab5b-410a-b979-309f91525823)

---

## Principios de Convivencia y Aprendizaje

1. **El error es una herramienta de trabajo:** En Git casi ninguna acción es definitiva; todo se puede inspeccionar, deshacer y corregir. Equivocarse es la forma más rápida y natural de aprender.
2. **Acompañamiento mutuo:** Nadie avanza dejando a otros atrás. Si alguien encuentra una traba con un comando o una configuración, nos apoyamos entre compañeros.
3. **Claridad y respeto:** Fomentamos comentarios constructivos en cada revisión y mensajes descriptivos que faciliten la comprensión del trabajo colectivo.

---

## Estructura del Repositorio

```text
Git-Github/
├── client/                     # Asistente de telemetría y configuración del alumno
│   ├── config/                 # Configuración de conexión automática a Fly.io
│   ├── core/                   # Analizadores de teclado, identidad y git local
│   ├── let_track.py            # Programa de telemetría del alumno
│   └── requirements.txt        # Dependencias ligeras de Python
├── historias/                  # Archivos de práctica colaborativa
│   ├── parque_central.md       # Relato comunitario base
│   ├── diario_ana.md           # Bitácora de perspectiva (quiosco de nieve)
│   └── diario_carlos.md        # Bitácora de perspectiva (club de ajedrez)
├── iniciar_alumno.bat          # Lanzador automático de 1 clic para Windows
├── enlaces.md                  # Accesos compartidos (una URL por línea)
├── enlaces.local.md            # Opcional: enlaces personales, ignorado por Git
└── README.md                   # Esta guía
```
