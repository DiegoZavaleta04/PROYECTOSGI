import re

import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# PERMISOS
# ==============================
# Clave de st.session_state donde guardas el rol al iniciar sesion.
CLAVE_ROL = "id_rol"

# Nombre del rol tal como esta en la tabla Rol (se compara sin importar
# mayusculas o minusculas).
ROL_ADMINISTRADOR = "administrador"

# Estos roles pueden VER las sedes, pero no agregar ni modificar.
ROLES_SOLO_LECTURA = (
    "encargado cd",
    "vendedor cd",
    "encargado tienda",
    "vendedor tienda",
)

# Valores de la columna Sede.tipo (enum de la base de datos)
TIPOS_SEDE = ["CD", "TIENDA"]

NOMBRES_TIPO = {
    "CD": "Centro de distribución (CD)",
    "TIENDA": "Tienda",
}

# Encabezados legibles para el listado
ENCABEZADOS = {
    "id_sede": "ID",
    "nombre": "Nombre",
    "direccion": "Dirección",
    "telefono": "Teléfono",
    "tipo": "Tipo",
}

# El telefono se guarda con 9 caracteres: 4 digitos, guion y 4 digitos
PATRON_TELEFONO = re.compile(r"^\d{4}-\d{4}$")


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
def obtener_sedes():
    """Sedes con todos sus datos: (id, nombre, direccion, telefono, tipo)."""
    return consultar(
        """
        SELECT id_sede, nombre, direccion, telefono, tipo
        FROM Sede
        ORDER BY nombre
        """
    )


def obtener_sedes_completas(busqueda=""):
    """
    Devuelve (columnas, filas) con TODAS las columnas de la tabla Sede,
    sean cuales sean, para mostrarlas en el listado.
    """
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return [], []

        cursor = conexion.cursor()
        cursor.execute(
            """
            SELECT *
            FROM Sede
            WHERE nombre LIKE %s
            ORDER BY nombre
            """,
            (f"%{busqueda.strip()}%",)
        )

        columnas = [c[0] for c in cursor.description]

        return columnas, cursor.fetchall()

    except Exception as error:
        st.error(f"Error al consultar los datos: {error}")
        return [], []

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


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


def cantidad_empleados(id_sede):
    """Cuantos empleados tiene asignados la sede."""
    filas = consultar(
        "SELECT COUNT(*) FROM USUARIO WHERE Id_sede = %s",
        (id_sede,)
    )

    return int(filas[0][0]) if filas else 0


def validar_sede(nombre, direccion, telefono, tipo):
    """Devuelve un mensaje de error, o None si todo esta bien."""
    if nombre == "":
        return "El nombre de la sede es obligatorio."

    if len(nombre) > 100:
        return "El nombre admite máximo 100 caracteres."

    if tipo not in TIPOS_SEDE:
        return "Seleccione si la sede es un CD o una tienda."

    if direccion == "":
        return "La ubicación (dirección) de la sede es obligatoria."

    if len(direccion) > 200:
        return "La ubicación admite máximo 200 caracteres."

    if telefono == "":
        return "El teléfono de la sede es obligatorio."

    if not PATRON_TELEFONO.match(telefono):
        return "El teléfono debe tener el formato 0000-0000."

    return None


def agregar_sede(nombre, direccion, telefono, tipo):
    # Seguridad: aunque otra parte del codigo llame a esta funcion,
    # solo el administrador puede agregar sedes.
    if not es_administrador():
        st.error("No tiene permiso para agregar sedes.")
        return False

    return ejecutar(
        """
        INSERT INTO Sede (nombre, direccion, telefono, tipo)
        VALUES (%s, %s, %s, %s)
        """,
        (nombre, direccion, telefono, tipo)
    )


def modificar_sede(id_sede, nombre, direccion, telefono, tipo):
    # Seguridad: solo el administrador puede modificar sedes.
    if not es_administrador():
        st.error("No tiene permiso para modificar sedes.")
        return False

    return ejecutar(
        """
        UPDATE Sede
        SET nombre = %s,
            direccion = %s,
            telefono = %s,
            tipo = %s
        WHERE id_sede = %s
        """,
        (nombre, direccion, telefono, tipo, id_sede)
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

    columnas, sedes = obtener_sedes_completas(busqueda)

    if sedes:
        encabezados = [
            ENCABEZADOS.get(c.lower(), c.replace("_", " ").capitalize())
            for c in columnas
        ]

        tabla = pd.DataFrame(sedes, columns=encabezados)

        st.dataframe(
            tabla,
            use_container_width=True,
            hide_index=True
        )

        st.caption(f"Sedes encontradas: {len(sedes)}")
    else:
        st.info("No se encontraron sedes.")


def mostrar_agregar():
    # El numero cambia al guardar, para que el formulario quede vacio
    n = st.session_state.get("sede_form_n", 0)

    with st.form(f"form_agregar_sede_{n}"):
        nombre = st.text_input(
            "Nombre de la sede",
            max_chars=100,
            key=f"sede_nueva_nombre_{n}"
        )

        tipo = st.selectbox(
            "Tipo de sede",
            TIPOS_SEDE,
            format_func=lambda t: NOMBRES_TIPO[t],
            key=f"sede_nueva_tipo_{n}"
        )

        direccion = st.text_input(
            "Ubicación (dirección)",
            max_chars=200,
            key=f"sede_nueva_direccion_{n}"
        )

        telefono = st.text_input(
            "Teléfono",
            max_chars=9,
            placeholder="0000-0000",
            key=f"sede_nueva_telefono_{n}"
        )

        guardar = st.form_submit_button("Guardar sede")

    if guardar:
        nombre = nombre.strip()
        direccion = direccion.strip()
        telefono = telefono.strip()

        error = validar_sede(nombre, direccion, telefono, tipo)

        if error:
            st.warning(error)
        elif nombre_repetido(nombre):
            st.warning("Ya existe una sede con ese nombre.")
        elif agregar_sede(nombre, direccion, telefono, tipo):
            st.session_state["sede_form_n"] = n + 1
            st.session_state["mensaje_sede"] = (
                f"Sede '{nombre}' registrada correctamente."
            )
            st.rerun()


def mostrar_modificar():
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

    id_sede = sede[0]

    # Las claves dependen del id para que los campos se actualicen
    # al cambiar de sede en el selector.
    nombre = st.text_input(
        "Nombre",
        value=sede[1],
        max_chars=100,
        key=f"sede_nombre_{id_sede}"
    )

    tipo = st.selectbox(
        "Tipo de sede",
        TIPOS_SEDE,
        index=TIPOS_SEDE.index(sede[4]) if sede[4] in TIPOS_SEDE else 0,
        format_func=lambda t: NOMBRES_TIPO[t],
        key=f"sede_tipo_{id_sede}"
    )

    direccion = st.text_input(
        "Ubicación (dirección)",
        value=sede[2],
        max_chars=200,
        key=f"sede_direccion_{id_sede}"
    )

    telefono = st.text_input(
        "Teléfono",
        value=sede[3],
        max_chars=9,
        placeholder="0000-0000",
        key=f"sede_telefono_{id_sede}"
    )

    if st.button("Guardar cambios", key="guardar_cambios_sede"):
        nombre = nombre.strip()
        direccion = direccion.strip()
        telefono = telefono.strip()

        error = validar_sede(nombre, direccion, telefono, tipo)

        if error:
            st.warning(error)
        elif (
            nombre == sede[1]
            and direccion == sede[2]
            and telefono == sede[3]
            and tipo == sede[4]
        ):
            st.info("No hay cambios que guardar.")
        elif nombre_repetido(nombre, id_sede):
            st.warning("Ya existe otra sede con ese nombre.")
        elif tipo != sede[4] and cantidad_empleados(id_sede) > 0:
            # Los roles de los empleados dependen del tipo de sede
            st.warning(
                "No se puede cambiar el tipo de una sede que tiene "
                "empleados asignados. Primero pase a esos empleados a "
                "otra sede."
            )
        elif modificar_sede(id_sede, nombre, direccion, telefono, tipo):
            st.session_state["mensaje_sede"] = (
                "Sede actualizada correctamente."
            )
            st.rerun()


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

    with tab_listado:
        mostrar_listado()

    with tab_agregar:
        mostrar_agregar()

    with tab_modificar:
        mostrar_modificar()
