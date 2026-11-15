import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# PERMISOS
# ==============================
# Clave de st.session_state donde guardas el rol al iniciar sesion.
# Cambiala si en tu login se llama distinto.
CLAVE_ROL = "id_rol"

# Nombre del rol tal como esta en la tabla Rol (se compara sin importar
# mayusculas o minusculas).
# !! REVISA que coincida con tu tabla Rol (SELECT * FROM Rol;) !!
ROL_ADMINISTRADOR = "administrador"

# Estos roles pueden VER las sedes, pero no agregar ni modificar.
ROLES_SOLO_LECTURA = (
    "encargado cd",
    "vendedor cd",
    "encargado tienda",
    "vendedor tienda",
)


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
        st.error(f"Error al consultar los datos: {error}")
        return []

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


def ejecutar(consulta, parametros=()):
    """Ejecuta un INSERT o UPDATE. Devuelve True si salio bien."""
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

        st.error(f"Error al guardar los datos: {error}")
        return False

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


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


def es_administrador():
    return obtener_nombre_rol() == ROL_ADMINISTRADOR


def puede_ver_sedes():
    """El administrador y los roles de solo lectura pueden ver las sedes."""
    rol = obtener_nombre_rol()
    return rol == ROL_ADMINISTRADOR or rol in ROLES_SOLO_LECTURA


# ==============================
# FUNCIONES DE BASE DE DATOS
# ==============================
def obtener_sedes(busqueda=""):
    return consultar(
        """
        SELECT id_sede, nombre
        FROM Sede
        WHERE nombre LIKE %s
        ORDER BY nombre
        """,
        (f"%{busqueda.strip()}%",)
    )


def nombre_repetido(nombre, id_sede=None):
    """True si ya existe otra sede con ese nombre."""
    filas = consultar(
        """
        SELECT 1
        FROM Sede
        WHERE LOWER(nombre) = LOWER(%s)
          AND (%s IS NULL OR id_sede <> %s)
        LIMIT 1
        """,
        (nombre, id_sede, id_sede)
    )

    return len(filas) > 0


def agregar_sede(nombre):
    # Seguridad: aunque otra parte del codigo llame a esta funcion,
    # solo el administrador puede agregar sedes.
    if not es_administrador():
        st.error("No tiene permiso para agregar sedes.")
        return False

    return ejecutar(
        "INSERT INTO Sede (nombre) VALUES (%s)",
        (nombre,)
    )


def modificar_sede(id_sede, nombre):
    # Seguridad: solo el administrador puede modificar sedes.
    if not es_administrador():
        st.error("No tiene permiso para modificar sedes.")
        return False

    return ejecutar(
        "UPDATE Sede SET nombre = %s WHERE id_sede = %s",
        (nombre, id_sede)
    )


# ==============================
# PANTALLA DEL MODULO
# ==============================
def mostrar_listado():
    """Listado de sedes con busqueda. Lo ven todos los roles con acceso."""
    busqueda = st.text_input(
        "Buscar sede",
        placeholder="Nombre de la sede",
        key="sede_busqueda"
    )

    sedes = obtener_sedes(busqueda)

    if sedes:
        tabla = pd.DataFrame(
            [(s[0], s[1]) for s in sedes],
            columns=["ID", "Nombre"]
        )

        st.dataframe(
            tabla,
            use_container_width=True,
            hide_index=True
        )

        st.caption(f"Sedes encontradas: {len(sedes)}")
    else:
        st.info("No se encontraron sedes.")


def mostrar_sedes():
    st.header("Gestión de sedes")

    # Solo el administrador y los encargados/vendedores entran al modulo
    if not puede_ver_sedes():
        st.error("No tiene permisos para acceder a las sedes.")
        return

    # Encargados y vendedores: solo consulta, aqui termina su pantalla
    if not es_administrador():
        mostrar_listado()
        return

    # Mensaje que se guarda antes de recargar la pagina
    mensaje = st.session_state.pop("mensaje_sede", None)
    if mensaje:
        st.success(mensaje)

    tab_listado, tab_agregar, tab_modificar = st.tabs(
        ["Listado", "Agregar sede", "Modificar sede"]
    )

    # -----------------------------------
    # LISTADO
    # -----------------------------------
    with tab_listado:
        mostrar_listado()

    # -----------------------------------
    # AGREGAR
    # -----------------------------------
    with tab_agregar:
        with st.form("form_agregar_sede", clear_on_submit=True):
            nombre_nuevo = st.text_input("Nombre de la sede")

            guardar = st.form_submit_button("Guardar sede")

        if guardar:
            nombre_nuevo = nombre_nuevo.strip()

            if not nombre_nuevo:
                st.warning("El nombre de la sede es obligatorio.")
            elif nombre_repetido(nombre_nuevo):
                st.warning("Ya existe una sede con ese nombre.")
            elif agregar_sede(nombre_nuevo):
                st.session_state["mensaje_sede"] = (
                    f"Sede '{nombre_nuevo}' registrada correctamente."
                )
                st.rerun()

    # -----------------------------------
    # MODIFICAR
    # -----------------------------------
    with tab_modificar:
        todas = obtener_sedes()

        if not todas:
            st.info("Aún no hay sedes para modificar.")
            return

        sede = st.selectbox(
            "Sede a modificar",
            todas,
            format_func=lambda s: f"{s[0]} - {s[1]}",
            key="sede_a_modificar"
        )

        # La clave depende del id para que el campo se actualice
        # al cambiar de sede en el selector.
        nombre_editado = st.text_input(
            "Nuevo nombre",
            value=sede[1],
            key=f"sede_nombre_{sede[0]}"
        )

        if st.button("Guardar cambios", key="guardar_cambios_sede"):
            nombre_editado = nombre_editado.strip()

            if not nombre_editado:
                st.warning("El nombre de la sede es obligatorio.")
            elif nombre_editado == sede[1]:
                st.info("No hay cambios que guardar.")
            elif nombre_repetido(nombre_editado, sede[0]):
                st.warning("Ya existe otra sede con ese nombre.")
            elif modificar_sede(sede[0], nombre_editado):
                st.session_state["mensaje_sede"] = (
                    "Sede actualizada correctamente."
                )
                st.rerun()
