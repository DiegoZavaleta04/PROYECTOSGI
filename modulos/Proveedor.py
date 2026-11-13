import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# FUNCIONES DE BASE DE DATOS
# ==============================
def consultar(consulta, parametros=()):
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return []

        cursor = conexion.cursor()
        cursor.execute(consulta, parametros)

        return cursor.fetchall()

    except Exception as error:
        st.error(
            f"Error al consultar los datos: {error}"
        )
        return []

    finally:
        if cursor is not None:
            cursor.close()

        if (
            conexion is not None
            and conexion.is_connected()
        ):
            conexion.close()


def ejecutar(consulta, parametros=()):
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return False

        cursor = conexion.cursor()
        cursor.execute(consulta, parametros)
        conexion.commit()

        return True

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        st.error(
            f"Error al guardar los datos: {error}"
        )
        return False

    finally:
        if cursor is not None:
            cursor.close()

        if (
            conexion is not None
            and conexion.is_connected()
        ):
            conexion.close()


def obtener_sedes():
    return consultar(
        "SELECT id_sede, nombre FROM Sede ORDER BY nombre"
    )


def obtener_proveedores(busqueda="", id_sede=None):
    consulta = """
    SELECT
        p.Id_proveedor,
        p.Nombre,
        p.DUI_NIT,
        p.Telefono,
        p.Id_sede,
        s.nombre
    FROM PROVEEDORES p
    INNER JOIN Sede s
        ON p.Id_sede = s.id_sede
    WHERE
        (%s = '' OR p.Nombre LIKE %s
         OR p.DUI_NIT LIKE %s
         OR p.Telefono LIKE %s
         OR CAST(p.Id_proveedor AS CHAR) LIKE %s)
        AND (%s IS NULL OR p.Id_sede = %s)
    ORDER BY p.Nombre
    """

    termino = f"%{busqueda.strip()}%"

    return consultar(
        consulta,
        (
            busqueda.strip(),
            termino,
            termino,
            termino,
            termino,
            id_sede,
            id_sede
        )
    )


def validar_datos(nombre, documento, telefono):
    """Devuelve un mensaje de error, o None si todo está bien."""
    if nombre.strip() == "" or documento.strip() == "":
        return "Debe ingresar el nombre y el DUI/NIT."

    if len(nombre.strip()) > 100:
        return "El nombre admite máximo 100 caracteres."

    if len(documento.strip()) > 20:
        return "El DUI/NIT admite máximo 20 caracteres."

    if telefono.strip() != "":
        if len(telefono.strip()) > 20:
            return "El teléfono admite máximo 20 caracteres."

        if not all(c.isdigit() or c in " +-()" for c in telefono.strip()):
            return "El teléfono solo puede tener números, espacios, + - ( )."

    return None


# ==============================
# PANTALLA DEL MÓDULO
# ==============================
def mostrar_proveedor():
    st.header("Gestión de proveedores")

    # Mensaje que se guarda antes de recargar la página
    mensaje = st.session_state.pop("mensaje_proveedor", None)
    if mensaje:
        st.success(mensaje)

    sedes = obtener_sedes()

    if not sedes:
        st.warning(
            "Primero debe registrar una sede."
        )
        return

    # -----------------------------------
    # LISTADO
    # -----------------------------------
    st.subheader("Listado de proveedores")

    col1, col2 = st.columns([2, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar proveedor",
            placeholder="Nombre, DUI/NIT, teléfono o ID"
        )

    with col2:
        opciones_filtro = {"Todas las sedes": None}

        for sede in sedes:
            opciones_filtro[sede[1]] = sede[0]

        sede_filtro = st.selectbox(
            "Filtrar por
