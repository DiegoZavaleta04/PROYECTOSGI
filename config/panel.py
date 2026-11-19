"""
Panel de control con tarjetas (icono grande + boton) en lugar de la barra
lateral, con fondo rosado y el logo de la cooperativa.
Guardar este archivo como config/panel.py

CARPETAS (la carpeta assets va junto a app.py):

    proyecto/
    |-- app.py
    |-- assets/
    |   |-- logo.png              <-- el logo de la cooperativa
    |   `-- iconos/
    |       |-- inventario.svg    (compras.svg, ventas.svg, ...)
    |-- config/
    |   |-- conexion.py
    |   `-- panel.py
    `-- modulos/

USO EN app.py (despues de iniciar sesion):

    from config.panel import (
        aplicar_estilo, mostrar_panel, boton_volver,
        pagina_actual, modulo_permitido, obtener_nombre_rol,
    )

    aplicar_estilo()
    pagina = pagina_actual()

    if pagina == "inicio":
        if mostrar_panel() == "cerrar":
            st.session_state.clear()
            st.rerun()
    else:
        if not modulo_permitido(pagina):
            st.error("No tiene permisos para este módulo.")
        else:
            boton_volver()
            ...   # aqui va el codigo que ya tienen para abrir el modulo
                  # "pagina" ("compras", "inventario", ...)
"""

import base64
from pathlib import Path

import streamlit as st

from config.conexion import obtener_conexion


# ==============================
# TEXTOS, COLORES Y CARPETAS
# ==============================
NOMBRE_SISTEMA = "SISTEMA DE INVENTARIO"
NOMBRE_COOPERATIVA = "Cooperativa de Mujeres de Occidente"

COLOR_FONDO = "#F9D6E4"          # fondo rosado
COLOR_TITULO = "#7A1F4B"         # titulo (vino)
COLOR_BOTON = "#A3205B"          # botones
COLOR_BOTON_HOVER = "#7A1F4B"    # botones al pasar el mouse
COLOR_CERRAR = "#2E9E44"         # boton "Cerrar sistema"

# La carpeta assets esta junto a app.py (un nivel arriba de config)
CARPETA_ASSETS = Path(__file__).resolve().parent.parent / "assets"
CARPETA_ICONOS = CARPETA_ASSETS / "iconos"
NOMBRES_LOGO = ("logo.png", "logo.jpg", "logo.jpeg", "logo.svg")

COLUMNAS = 3                      # tarjetas por fila
CLAVE_PAGINA = "pagina"           # clave en st.session_state


# ==============================
# MODULOS DEL PANEL
# ==============================
# clave: (texto del boton, nombre del icono, roles que lo pueden ver)
# La clave es la que usa app.py para saber que modulo abrir.
# Los roles son los nombres de la tabla Rol, en minusculas.
# !! AJUSTA esta lista a los modulos que tengan !!
TODOS_MENOS_ADMIN = {
    "encargado cd",
    "encargado tienda",
    "vendedor cd",
    "vendedor tienda",
}

MODULOS = {
    "sedes":       ("Gestión de sedes",    "sedes",       {"administrador"}),
    "usuarios":    ("Gestión de usuarios", "usuarios",    {"administrador"}),
    "productos":   ("Productos",           "productos",   {"encargado tienda"}),
    "proveedores": ("Proveedores",         "proveedores", TODOS_MENOS_ADMIN),
    "compras":     ("Compras",             "compras",     TODOS_MENOS_ADMIN),
    "ventas":      ("Ventas",              "ventas",      TODOS_MENOS_ADMIN),
    "inventario":  ("Inventario",          "inventario",  TODOS_MENOS_ADMIN),
}


# ==============================
# ROL DEL USUARIO
# ==============================
def obtener_nombre_rol():
    """Devuelve el nombre del rol del usuario (en minusculas), o None."""
    id_rol = st.session_state.get("id_rol")

    if id_rol is None:
        return None

    # Misma clave que usan los demas modulos: se consulta una sola vez
    clave = f"_nombre_rol_{id_rol}"

    if clave not in st.session_state:
        nombre = None
        conexion = obtener_conexion()

        if conexion is not None:
            try:
                cursor = conexion.cursor()
                cursor.execute(
                    "SELECT Nombre FROM Rol WHERE Id_rol = %s",
                    (id_rol,)
                )
                fila = cursor.fetchone()
                cursor.close()

                if fila:
                    nombre = fila[0].strip().lower()

            except Exception:
                nombre = None

            finally:
                conexion.close()

        st.session_state[clave] = nombre

    return st.session_state[clave]


def modulo_permitido(clave, rol=None):
    """True si el rol del usuario puede entrar al modulo indicado."""
    rol = rol or obtener_nombre_rol()

    if clave not in MODULOS or rol is None:
        return False

    return rol in MODULOS[clave][2]


# ==============================
# NAVEGACION
# ==============================
def pagina_actual():
    return st.session_state.get(CLAVE_PAGINA, "inicio")


def ir_al_panel():
    st.session_state[CLAVE_PAGINA] = "inicio"


def boton_volver():
    """Boton para regresar al panel desde cualquier modulo."""
    if st.button("← Volver al panel", key="volver_panel"):
        ir_al_panel()
        st.rerun()


# ==============================
# ESTILO
# ==============================
def aplicar_estilo():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {COLOR_FONDO};
        }}
        header[data-testid="stHeader"] {{
            background: transparent;
        }}
        section[data-testid="stSidebar"],
        div[data-testid="collapsedControl"],
        div[data-testid="stSidebarCollapsedControl"] {{
            display: none;
        }}
        .panel-titulo {{
            text-align: center;
            color: {COLOR_TITULO};
            font-size: 2.4rem;
            font-weight: 800;
            line-height: 1.1;
            letter-spacing: 1px;
            margin: 0.4rem 0 0 0;
        }}
        .panel-subtitulo {{
            text-align: center;
            color: {COLOR_TITULO};
            font-size: 1.2rem;
            font-weight: 600;
            margin: 0.2rem 0 0 0;
        }}
        .panel-icono {{
            text-align: center;
            margin: 1.2rem 0 0.6rem 0;
        }}
        .panel-icono img {{
            width: 150px;
            height: 150px;
            object-fit: contain;
        }}
        div.stButton > button,
        div[data-testid="stFormSubmitButton"] > button {{
            background-color: {COLOR_BOTON};
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            padding: 0.65rem 1rem;
            box-shadow: 0 3px 6px rgba(0, 0, 0, 0.25);
        }}
        div.stButton > button p,
        div[data-testid="stFormSubmitButton"] > button p {{
            color: white;
            font-weight: 700;
        }}
        div.stButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {{
            background-color: {COLOR_BOTON_HOVER};
            color: white;
            border: none;
        }}
        .st-key-cerrar_sistema button {{
            background-color: {COLOR_CERRAR};
        }}
        .st-key-cerrar_sistema button:hover {{
            background-color: #23782F;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


# ==============================
# PANEL
# ==============================
def _html_icono(nombre):
    """
    Busca assets/iconos/<nombre>.png, .jpg o .svg. Si ponen su propio
    dibujo en PNG con el mismo nombre, ese tiene prioridad sobre el SVG.
    """
    tipos = (
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".svg", "image/svg+xml"),
    )

    for extension, tipo in tipos:
        ruta = CARPETA_ICONOS / f"{nombre}{extension}"

        if ruta.exists():
            datos = base64.b64encode(ruta.read_bytes()).decode()

            return (
                '<div class="panel-icono">'
                f'<img src="data:{tipo};base64,{datos}" alt="{nombre}">'
                "</div>"
            )

    # Si falta el dibujo, se muestra un marcador
    return '<div class="panel-icono" style="font-size:90px">📦</div>'


def mostrar_encabezado():
    col_logo, col_titulo, _ = st.columns([1, 4, 1])

    with col_logo:
        for nombre in NOMBRES_LOGO:
            ruta = CARPETA_ASSETS / nombre

            if ruta.exists():
                st.image(str(ruta), width=120)
                break

    with col_titulo:
        st.markdown(
            f'<p class="panel-titulo">{NOMBRE_SISTEMA}</p>'
            f'<p class="panel-subtitulo">{NOMBRE_COOPERATIVA}</p>',
            unsafe_allow_html=True
        )


def mostrar_panel(rol=None):
    """
    Dibuja el panel con las tarjetas que le corresponden al rol.

    - Al pulsar una tarjeta guarda la pagina en st.session_state y recarga.
    - Devuelve "cerrar" si pulsan "Cerrar sistema"; si no, devuelve None.
    """
    rol = rol or obtener_nombre_rol()

    mostrar_encabezado()
    st.write("")

    visibles = [
        (clave, datos)
        for clave, datos in MODULOS.items()
        if rol in datos[2]
    ]

    if not visibles:
        st.warning("Su rol no tiene módulos disponibles.")

    for inicio in range(0, len(visibles), COLUMNAS):
        fila = visibles[inicio:inicio + COLUMNAS]
        columnas = st.columns(COLUMNAS)

        for columna, (clave, (texto, icono, _roles)) in zip(columnas, fila):
            with columna:
                st.markdown(_html_icono(icono), unsafe_allow_html=True)

                if st.button(
                    texto,
                    key=f"panel_{clave}",
                    use_container_width=True
                ):
                    st.session_state[CLAVE_PAGINA] = clave
                    st.rerun()

        st.write("")

    st.write("")
    _, _, col_cerrar = st.columns([4, 4, 1])

    with col_cerrar:
        if st.button("Cerrar sistema", key="cerrar_sistema"):
            return "cerrar"

    return None
