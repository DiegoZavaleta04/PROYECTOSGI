import re

import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# PERMISOS
# ==============================
# Claves de st.session_state donde guardas los datos del usuario
# al iniciar sesion. Cambialas si en tu login se llaman distinto.
CLAVE_ROL = "id_rol"
CLAVE_SEDE = "id_sede"

# Nombres de los roles tal como estan en la tabla Rol (se comparan sin
# importar mayusculas o minusculas). Se usan NOMBRES y no numeros de id
# para que el modulo no dependa del orden en que se crearon los roles.
# !! REVISA que coincidan con tu tabla Rol (SELECT * FROM Rol;) !!
ROL_ENCARGADO_CD = "encargado cd"
ROL_VENDEDOR_CD = "vendedor cd"
ROL_ENCARGADO_TIENDA = "encargado tienda"
ROL_VENDEDOR_TIENDA = "vendedor tienda"

# El rol Administrador NO aparece: no tiene acceso a los proveedores.

# True si el encargado del CD tambien debe poder agregar y modificar
# proveedores del CD. Con False solo puede verlos.
ENCARGADO_CD_PUEDE_EDITAR = False


def obtener_nombre_rol():
    """Devuelve el nombre del rol del usuario (en minusculas), o None."""
    id_rol = st.session_state.get(CLAVE_ROL)

    if id_rol is None:
        return None

    # Se guarda en la sesion para no consultar la base en cada recarga
    clave = f"_nombre_rol_{id_rol}"

    if clave not in st.session_state:
        filas = consultar(
            "SELECT Nombre FROM Rol WHERE Id_rol = %s",
            (id_rol,)
        )
        st.session_state[clave] = (
            filas[0][0].strip().lower() if filas else None
        )

    return st.session_state[clave]


def obtener_permisos():
    """
    Devuelve (id_sede, puede_ver_todas, puede_editar).

    - Administrador: sin acceso a los proveedores.
    - Encargado del CD: ve los proveedores del CD (su sede). Solo los
      modifica si ENCARGADO_CD_PUEDE_EDITAR es True.
    - Vendedor del CD: solo ve los proveedores del CD (su sede).
    - Encargado de tienda: ve, agrega y modifica los proveedores de SU
      tienda.
    - Vendedor de tienda: solo ve los proveedores de SU tienda.

    Ningun rol ve todas las sedes, por eso puede_ver_todas siempre es False.
    """
    id_sede = st.session_state.get(CLAVE_SEDE)
    rol = obtener_nombre_rol()

    if rol is None or id_sede is None:
        return None, False, False

    if rol == ROL_ENCARGADO_TIENDA:
        return id_sede, False, True

    if rol == ROL_ENCARGADO_CD:
        return id_sede, False, ENCARGADO_CD_PUEDE_EDITAR

    if rol in (ROL_VENDEDOR_CD, ROL_VENDEDOR_TIENDA):
        return id_sede, False, False

    # Administrador, rol desconocido o sin sede asignada: sin acceso
    return None, False, False


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
    """Devuelve (exito, filas_afectadas)."""
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return False, 0

        cursor = conexion.cursor()
        cursor.execute(consulta, parametros)
        filas = cursor.rowcount
        conexion.commit()

        return True, filas

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        st.error(
            f"Error al guardar los datos: {error}"
        )
        return False, 0

    finally:
        if cursor is not None:
            cursor.close()

        if (
            conexion is not None
            and conexion.is_connected()
        ):
            conexion.close()


def obtener_sedes(id_sede=None):
    return consultar(
        """
        SELECT id_sede, nombre
        FROM Sede
        WHERE (%s IS NULL OR id_sede = %s)
        ORDER BY nombre
        """,
        (id_sede, id_sede)
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


# Formatos que tambien exige la base de datos (CHECK):
#   DUI: 00000000-0        NIT: 0000-000000-000-0
#   Telefono: 7777-7777
PATRON_DUI = re.compile(r"^\d{8}-\d$")
PATRON_NIT = re.compile(r"^\d{4}-\d{6}-\d{3}-\d$")
PATRON_TELEFONO = re.compile(r"^\d{4}-\d{4}$")


def validar_datos(nombre, documento, telefono):
    """Devuelve un mensaje de error, o None si todo está bien."""
    nombre = nombre.strip()
    documento = documento.strip()
    telefono = telefono.strip()

    if nombre == "":
        return "Debe ingresar el nombre del proveedor."

    if len(nombre) > 100:
        return "El nombre admite máximo 100 caracteres."

    # El DUI/NIT es opcional, pero si se escribe debe tener formato valido
    if documento != "":
        if not (
            PATRON_DUI.match(documento)
            or PATRON_NIT.match(documento)
        ):
            return (
                "El DUI/NIT no tiene un formato válido. "
                "Use 00000000-0 (DUI) o 0000-000000-000-0 (NIT)."
            )

    # El telefono es obligatorio
    if telefono == "":
        return "Debe ingresar el teléfono."

    if not PATRON_TELEFONO.match(telefono):
        return "El teléfono debe tener el formato 7777-7777."

    return None


# ==============================
# PANTALLA DEL MÓDULO
# ==============================
def mostrar_proveedor():
    st.header("Gestión de proveedores")

    # ---- Permisos del usuario actual ----
    sede_usuario, ve_todas, puede_editar = obtener_permisos()

    if not ve_todas and sede_usuario is None:
        st.error(
            "No tiene permisos para ver los proveedores."
        )
        return

    # Mensaje que se guarda antes de recargar la página
    mensaje = st.session_state.pop("mensaje_proveedor", None)
    if mensaje:
        st.success(mensaje)

    # Si no ve todas las sedes, solo se carga la suya
    sedes = obtener_sedes(None if ve_todas else sede_usuario)

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
        if ve_todas:
            opciones_filtro = {"Todas las sedes": None}

            for sede in sedes:
                opciones_filtro[sede[1]] = sede[0]

            sede_filtro = st.selectbox(
                "Filtrar por sede",
                list(opciones_filtro.keys())
            )
            id_sede_filtro = opciones_filtro[sede_filtro]
        else:
            # Usuario de una sola sede: filtro fijo
            st.text_input(
                "Sede",
                value=sedes[0][1],
                disabled=True
            )
            id_sede_filtro = sede_usuario

    proveedores = obtener_proveedores(
        busqueda,
        id_sede_filtro
    )

    if proveedores:
        tabla = pd.DataFrame(
            [(p[0], p[1], p[2] or "", p[3], p[5]) for p in proveedores],
            columns=[
                "ID",
                "Proveedor",
                "DUI/NIT",
                "Teléfono",
                "Sede"
            ]
        )

        st.dataframe(
            tabla,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            f"Total de proveedores encontrados: {len(proveedores)}"
        )
    else:
        st.info(
            "No se encontraron proveedores."
        )

    # Los roles de solo consulta terminan aqui su pantalla
    if not puede_editar:
        return

    st.divider()

    # -----------------------------------
    # REGISTRAR PROVEEDOR
    # -----------------------------------
    st.subheader("Registrar nuevo proveedor")

    with st.form("form_proveedor"):
        nombre = st.text_input(
            "Nombre del proveedor",
            max_chars=100
        )

        documento = st.text_input(
            "DUI/NIT (opcional)",
            max_chars=17,
            placeholder="00000000-0 o 0000-000000-000-0"
        )

        telefono = st.text_input(
            "Teléfono",
            max_chars=9,
            placeholder="7777-7777"
        )

        sede = st.selectbox(
            "Sede",
            sedes,
            format_func=lambda s: s[1]
        )

        guardar = st.form_submit_button(
            "Guardar proveedor"
        )

    if guardar:
        error_validacion = validar_datos(
            nombre,
            documento,
            telefono
        )

        if error_validacion:
            st.warning(error_validacion)
        else:
            # Seguridad: siempre se guarda en la sede del usuario
            id_sede_guardar = sede[0] if ve_todas else sede_usuario

            consulta = """
            INSERT INTO PROVEEDORES
            (Nombre, DUI_NIT, Telefono, Id_sede)
            VALUES (%s, %s, %s, %s)
            """

            exito, _ = ejecutar(
                consulta,
                (
                    nombre.strip(),
                    documento.strip() or None,
                    telefono.strip(),
                    id_sede_guardar
                )
            )

            if exito:
                st.session_state["mensaje_proveedor"] = (
                    "Proveedor registrado correctamente."
                )
                st.rerun()

    st.divider()

    # -----------------------------------
    # EDITAR PROVEEDOR
    # -----------------------------------
    st.subheader("Editar proveedor")

    todos = obtener_proveedores(
        "",
        None if ve_todas else sede_usuario
    )

    if not todos:
        st.info(
            "No hay proveedores registrados para editar."
        )
        return

    proveedor = st.selectbox(
        "Selecciona el proveedor que deseas editar",
        todos,
        format_func=lambda p: f"{p[0]} - {p[1]}",
        key="proveedor_editar"
    )

    # Posición de la sede actual dentro de la lista de sedes
    indice_sede = next(
        (i for i, s in enumerate(sedes) if s[0] == proveedor[4]),
        0
    )

    # La clave incluye el ID para que el formulario se actualice
    # al cambiar de proveedor
    with st.form(f"form_editar_proveedor_{proveedor[0]}"):
        nuevo_nombre = st.text_input(
            "Nombre",
            value=proveedor[1],
            max_chars=100
        )

        nuevo_documento = st.text_input(
            "DUI/NIT (opcional)",
            value=proveedor[2] or "",
            max_chars=17,
            placeholder="00000000-0 o 0000-000000-000-0"
        )

        nuevo_telefono = st.text_input(
            "Teléfono",
            value=proveedor[3] or "",
            max_chars=9,
            placeholder="7777-7777"
        )

        nueva_sede = st.selectbox(
            "Sede",
            sedes,
            index=indice_sede,
            format_func=lambda s: s[1],
            disabled=not ve_todas
        )

        actualizar = st.form_submit_button(
            "Guardar cambios"
        )

    if actualizar:
        error_validacion = validar_datos(
            nuevo_nombre,
            nuevo_documento,
            nuevo_telefono
        )

        if error_validacion:
            st.warning(error_validacion)
        else:
            # Seguridad: nadie mueve proveedores a otra sede
            id_sede_guardar = nueva_sede[0] if ve_todas else sede_usuario

            # Seguridad extra: el WHERE tambien limita por sede
            consulta = """
            UPDATE PROVEEDORES
            SET Nombre = %s,
                DUI_NIT = %s,
                Telefono = %s,
                Id_sede = %s
            WHERE Id_proveedor = %s
              AND (%s IS NULL OR Id_sede = %s)
            """

            sede_restriccion = None if ve_todas else sede_usuario

            exito, filas = ejecutar(
                consulta,
                (
                    nuevo_nombre.strip(),
                    nuevo_documento.strip() or None,
                    nuevo_telefono.strip(),
                    id_sede_guardar,
                    proveedor[0],
                    sede_restriccion,
                    sede_restriccion
                )
            )

            if exito and filas > 0:
                st.session_state["mensaje_proveedor"] = (
                    "Proveedor actualizado correctamente."
                )
                st.rerun()
            elif exito:
                st.warning(
                    "No se modificó ningún registro "
                    "(sin cambios o sin permiso)."
                )
