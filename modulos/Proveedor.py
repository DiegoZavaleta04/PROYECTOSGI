import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# PERMISOS (AJUSTAR A TU PROYECTO)
# ==============================
# Claves de st.session_state donde guardas los datos del usuario
# al iniciar sesion. Cambialas si en tu login se llaman distinto.
CLAVE_ROL = "rol"
CLAVE_SEDE = "id_sede"

# Nombres de rol (se comparan en minusculas, sin espacios al inicio/fin)
ROL_VENDEDOR = "vendedor tienda"
ROL_ENCARGADO = "encargado tienda"
ROL_VENDEDOR = "vendedor CD"
ROL_ENCARGADO = "encargado CD"
# Roles que ven todas las sedes (opcional). Deja la lista vacia
# si no existe un rol administrador.
ROLES_TODAS_LAS_SEDES = ["administrador"]


def obtener_permisos():
    """
    Devuelve (id_sede, puede_ver_todas, puede_editar).

    - Vendedor: solo ve los proveedores de su sede (CD o tienda).
    - Encargado: ve y modifica solo los proveedores de su sede.
    - Administrador (si existe): ve y modifica todo.
    """
    rol = str(st.session_state.get(CLAVE_ROL, "")).strip().lower()
    id_sede = st.session_state.get(CLAVE_SEDE)

    if rol in ROLES_TODAS_LAS_SEDES:
        return None, True, True

    if rol == ROL_ENCARGADO and id_sede is not None:
        return id_sede, False, True

    if rol == ROL_VENDEDOR and id_sede is not None:
        return id_sede, False, False

    # Rol desconocido o sin sede asignada: sin acceso
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
            [(p[0], p[1], p[2], p[3], p[5]) for p in proveedores],
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

    # El vendedor solo puede consultar, aqui termina su pantalla
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
            "DUI/NIT",
            max_chars=20
        )

        telefono = st.text_input(
            "Teléfono",
            max_chars=20
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
            # Seguridad: el encargado siempre guarda en su propia sede
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
                    documento.strip(),
                    telefono.strip() or None,
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
            "DUI/NIT",
            value=proveedor[2] or "",
            max_chars=20
        )

        nuevo_telefono = st.text_input(
            "Teléfono",
            value=proveedor[3] or "",
            max_chars=20
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
            # Seguridad: el encargado no puede mover proveedores a otra sede
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
                    nuevo_documento.strip(),
                    nuevo_telefono.strip() or None,
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
