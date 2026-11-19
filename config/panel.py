"""
Panel de control con tarjetas (icono grande + boton) en lugar de la barra
lateral, con fondo rosado y el logo de la cooperativa.
Guardar este archivo como config/panel.py

Este archivo SOLO dibuja el panel. Los modulos y los permisos por rol
siguen en app.py (MODULOS y PERMISOS_MODULOS): app.py le pasa a
mostrar_panel() la lista de modulos que el usuario puede ver.

ICONOS: se buscan en assets/iconos/<nombre>.png, .jpg o .svg. Si ponen su
propio dibujo en PNG con el mismo nombre, ese tiene prioridad sobre el SVG.
La carpeta assets va junto a app.py.
"""

import base64
import html
import os
from pathlib import Path

import streamlit as st


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
# NAVEGACION
# ==============================
def pagina_actual():
    """Devuelve 'inicio' o el nombre del modulo abierto."""
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
        .panel-usuario {{
            text-align: center;
            color: {COLOR_TITULO};
            font-size: 0.9rem;
            margin: 0.3rem 0 0 0;
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
    """Devuelve el HTML del icono, o un marcador si no se encuentra."""
    tipos = (
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".svg", "image/svg+xml"),
    )

    if nombre:
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


def mostrar_encabezado(ruta_logo=None, usuario=""):
    col_logo, col_titulo, _ = st.columns([1, 4, 1])

    with col_logo:
        # Primero el logo que indique app.py; si no, assets/logo.*
        if ruta_logo and os.path.exists(ruta_logo):
            st.image(ruta_logo, width=120)
        else:
            for nombre in NOMBRES_LOGO:
                ruta = CARPETA_ASSETS / nombre

                if ruta.exists():
                    st.image(str(ruta), width=120)
                    break

    with col_titulo:
        texto_usuario = (
            f'<p class="panel-usuario">Usuario: {html.escape(usuario)}</p>'
            if usuario else ""
        )

        st.markdown(
            f'<p class="panel-titulo">{NOMBRE_SISTEMA}</p>'
            f'<p class="panel-subtitulo">{NOMBRE_COOPERATIVA}</p>'
            f"{texto_usuario}",
            unsafe_allow_html=True
        )


def mostrar_panel(opciones, iconos, ruta_logo=None, usuario=""):
    """
    Dibuja el panel con una tarjeta por cada modulo de 'opciones'.

    - opciones: nombres de los modulos que el usuario puede ver (los
      mismos nombres de MODULOS en app.py).
    - iconos: diccionario {nombre del modulo: nombre del icono}.
    - Al pulsar una tarjeta guarda el modulo en st.session_state y recarga.
    - Devuelve "cerrar" si pulsan "Cerrar sistema"; si no, devuelve None.
    """
    mostrar_encabezado(ruta_logo, usuario)
    st.write("")

    if not opciones:
        st.warning("Su rol no tiene módulos disponibles.")

    for inicio in range(0, len(opciones), COLUMNAS):
        fila = opciones[inicio:inicio + COLUMNAS]
        columnas = st.columns(COLUMNAS)

        for columna, nombre in zip(columnas, fila):
            with columna:
                st.markdown(
                    _html_icono(iconos.get(nombre)),
                    unsafe_allow_html=True
                )

                if st.button(
                    nombre,
                    key=f"panel_{nombre}",
                    use_container_width=True
                ):
                    st.session_state[CLAVE_PAGINA] = nombre
                    st.rerun()

        st.write("")

    st.write("")
    _, _, col_cerrar = st.columns([4, 4, 1])

    with col_cerrar:
        if st.button("Cerrar sistema", key="cerrar_sistema"):
            return "cerrar"

    return None
