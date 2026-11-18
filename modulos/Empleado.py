import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion

# Valores con los que se guarda el Estado en la tabla USUARIO.
# Si en tu tabla usas otros (por ejemplo 1 y 0), cámbialos aquí.
ESTADO_ACTIVO = "Activo"
ESTADO_INACTIVO = "Inactivo"

# Solo el administrador (rol 5) puede registrar y editar empleados,
# y es el único que ve a los empleados de todas las sedes.
# Los encargados solo ven a los empleados de su propia sede.
# Quién ve el módulo en el menú se define en app.py (PERMISOS_MODULOS).
ROLES_ADMINISTRAR = (5,)

OPCIONES_ESTADO = ["Todos", "Activos", "Inactivos"]

# Roles que se pueden asignar según el tipo de sede (Sede.tipo).
# Se comparan por NOMBRE (en minúsculas), tal como están en la tabla Rol.
# !! REVISA que coincidan con tu tabla Rol (SELECT * FROM Rol;) !!
ROLES_POR_TIPO = {
    "CD": (
        "encargado cd",
        "vendedor cd",
        "administrador",
    ),
    "TIENDA": (
        "encargado tienda",
        "vendedor tienda",
    ),
}


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


def obtener_roles():
    return consultar(
        "SELECT id_rol, nombre FROM Rol ORDER BY id_rol"
    )


def obtener_sedes():
    """Devuelve (id_sede, nombre, tipo) de cada sede."""
    return consultar(
        "SELECT id_sede, nombre, tipo FROM Sede ORDER BY nombre"
    )


def obtener_empleados(busqueda="", id_rol=None, id_sede=None):
    consulta = """
    SELECT
        u.Id_usuario,
        u.Nombre,
        u.Apellido,
        u.Correo,
        u.Id_rol,
        r.nombre,
        u.Estado,
        u.Id_sede,
        s.nombre
    FROM USUARIO u
    INNER JOIN Rol r
        ON u.Id_rol = r.id_rol
    INNER JOIN Sede s
        ON u.Id_sede = s.id_sede
    WHERE
        (%s = '' OR u.Nombre LIKE %s
         OR u.Apellido LIKE %s
         OR u.Correo LIKE %s
         OR CAST(u.Id_usuario AS CHAR) LIKE %s)
        AND (%s IS NULL OR u.Id_rol = %s)
        AND (%s IS NULL OR u.Id_sede = %s)
    ORDER BY u.Nombre, u.Apellido
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
            id_rol,
            id_rol,
            id_sede,
            id_sede
        )
    )


def correo_existe(correo, id_excluir=None):
    filas = consultar(
        "SELECT Id_usuario FROM USUARIO WHERE Correo = %s",
        (correo.strip(),)
    )

    for fila in filas:
        if id_excluir is None or fila[0] != id_excluir:
            return True

    return False


def es_activo(estado):
    return str(estado).strip().lower() in ("1", "activo", "true")


def valor_estado(activo):
    if activo:
        return ESTADO_ACTIVO

    return ESTADO_INACTIVO


# ==============================
# ROLES SEGUN LA SEDE
# ==============================
def nombres_roles_permitidos(tipo_sede):
    """Nombres de rol (minúsculas) que admite ese tipo de sede."""
    return ROLES_POR_TIPO.get(str(tipo_sede).strip().upper(), ())


def roles_de_sede(roles, tipo_sede):
    """Solo los roles que corresponden al tipo de la sede."""
    permitidos = nombres_roles_permitidos(tipo_sede)

    return [
        r for r in roles
        if r[1].strip().lower() in permitidos
    ]


def rol_corresponde_a_sede(rol, sede):
    """True si el rol (id, nombre) puede asignarse a la sede (id, nombre, tipo)."""
    if rol is None or sede is None:
        return False

    return rol[1].strip().lower() in nombres_roles_permitidos(sede[2])


def validar_datos(nombre, apellido, correo, contrasena, exigir_contrasena):
    """Devuelve un mensaje de error, o None si todo está bien."""
    if (
        nombre.strip() == ""
        or apellido.strip() == ""
        or correo.strip() == ""
    ):
        return "Debe ingresar nombre, apellido y correo."

    if len(nombre.strip()) > 50 or len(apellido.strip()) > 50:
        return "El nombre y el apellido admiten máximo 50 caracteres."

    correo_limpio = correo.strip()

    if (
        "@" not in correo_limpio
        or "." not in correo_limpio.split("@")[-1]
        or " " in correo_limpio
    ):
        return "Ingrese un correo válido."

    if len(correo_limpio) > 100:
        return "El correo admite máximo 100 caracteres."

    if exigir_contrasena and contrasena.strip() == "":
        return "Debe ingresar una contraseña."

    if contrasena.strip() != "" and len(contrasena.strip()) < 6:
        return "La contraseña debe tener al menos 6 caracteres."

    return None


def etiqueta_sede(sede):
    return f"{sede[1]} ({sede[2]})"


# ==============================
# PANTALLA DEL MÓDULO
# ==============================
def mostrar_empleado():
    st.header("Gestión de empleados")

    # Rol y sede del usuario con la sesión iniciada
    id_rol_usuario = st.session_state.get("id_rol")
    id_sede_usuario = st.session_state.get("id_sede")
    es_administrador = id_rol_usuario in ROLES_ADMINISTRAR

    # Mensaje que se guarda antes de recargar la página
    mensaje = st.session_state.pop("mensaje_empleado", None)
    if mensaje:
        st.success(mensaje)

    roles = obtener_roles()
    sedes = obtener_sedes()

    if not roles:
        st.warning(
            "Primero debe registrar los roles."
        )
        return

    if not sedes:
        st.warning(
            "Primero debe registrar una sede."
        )
        return

    # Los encargados necesitan una sede para ver su listado
    if not es_administrador and id_sede_usuario is None:
        st.warning(
            "No se pudo identificar su sede. "
            "Cierre sesión y vuelva a iniciar sesión."
        )
        return

    # -----------------------------------
    # LISTADO
    # -----------------------------------
    st.subheader("Listado de empleados")

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar empleado",
            placeholder="Nombre, apellido, correo o ID"
        )

    with col2:
        opciones_rol = {"Todos los roles": None}

        for rol in roles:
            opciones_rol[rol[1]] = rol[0]

        rol_filtro = st.selectbox(
            "Filtrar por rol",
            list(opciones_rol.keys())
        )

    with col3:
        if es_administrador:
            # El administrador puede ver todas las sedes
            opciones_sede = {"Todas las sedes": None}

            for sede in sedes:
                opciones_sede[sede[1]] = sede[0]

            sede_filtro = st.selectbox(
                "Filtrar por sede",
                list(opciones_sede.keys())
            )

            id_sede_filtro = opciones_sede[sede_filtro]
        else:
            # Los encargados solo ven su propia sede (bloqueada)
            nombre_sede_usuario = next(
                (s[1] for s in sedes if s[0] == id_sede_usuario),
                "Mi sede"
            )

            st.selectbox(
                "Sede",
                [nombre_sede_usuario],
                disabled=True
            )

            id_sede_filtro = id_sede_usuario

    with col4:
        estado_filtro = st.selectbox(
            "Filtrar por estado",
            OPCIONES_ESTADO
        )

    empleados = obtener_empleados(
        busqueda,
        opciones_rol[rol_filtro],
        id_sede_filtro
    )

    # Filtro por estado (activos / inactivos)
    if estado_filtro == "Activos":
        empleados = [e for e in empleados if es_activo(e[6])]
    elif estado_filtro == "Inactivos":
        empleados = [e for e in empleados if not es_activo(e[6])]

    if empleados:
        tabla = pd.DataFrame(
            [
                (
                    e[0],
                    e[1],
                    e[2],
                    e[3],
                    e[5],
                    e[8],
                    valor_estado(es_activo(e[6]))
                )
                for e in empleados
            ],
            columns=[
                "ID",
                "Nombre",
                "Apellido",
                "Correo",
                "Rol",
                "Sede",
                "Estado"
            ]
        )

        st.dataframe(
            tabla,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            f"Total de empleados encontrados: {len(empleados)}"
        )
    else:
        st.info(
            "No se encontraron empleados."
        )

    # Solo el administrador puede registrar y editar empleados.
    # Los demás roles solo ven el listado, sin formularios.
    if not es_administrador:
        return

    st.divider()

    # -----------------------------------
    # REGISTRAR EMPLEADO
    # -----------------------------------
    st.subheader("Registrar nuevo empleado")

    # La sede va FUERA del formulario: así, al cambiarla, la lista de
    # roles se actualiza al instante (dentro de un formulario no se puede).
    sede = st.selectbox(
        "Sede",
        sedes,
        format_func=etiqueta_sede,
        key="empleado_nueva_sede"
    )

    roles_sede = roles_de_sede(roles, sede[2])

    st.caption(
        "Roles disponibles en esta sede: "
        + (", ".join(r[1] for r in roles_sede) or "ninguno")
    )

    with st.form("form_empleado"):
        nombre = st.text_input(
            "Nombre",
            max_chars=50
        )

        apellido = st.text_input(
            "Apellido",
            max_chars=50
        )

        correo = st.text_input(
            "Correo",
            max_chars=100
        )

        contrasena = st.text_input(
            "Contraseña",
            type="password"
        )

        rol = st.selectbox(
            "Rol",
            roles_sede,
            format_func=lambda r: r[1],
            key=f"empleado_nuevo_rol_{sede[0]}"
        )

        activo = st.checkbox(
            "Usuario activo",
            value=True
        )

        guardar = st.form_submit_button(
            "Guardar empleado"
        )

    if guardar:
        error_validacion = validar_datos(
            nombre,
            apellido,
            correo,
            contrasena,
            True
        )

        if error_validacion:
            st.warning(error_validacion)
        elif not rol_corresponde_a_sede(rol, sede):
            # Validación de seguridad: el rol debe ser de esa sede
            st.warning(
                "El rol seleccionado no corresponde al tipo de sede."
            )
        elif correo_existe(correo):
            st.warning(
                "Ya existe un empleado con ese correo."
            )
        else:
            consulta = """
            INSERT INTO USUARIO
            (Nombre, Apellido, Correo, Id_rol,
             Contrasena, Estado, Id_sede)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """

            if ejecutar(
                consulta,
                (
                    nombre.strip(),
                    apellido.strip(),
                    correo.strip(),
                    rol[0],
                    contrasena.strip(),
                    valor_estado(activo),
                    sede[0]
                )
            ):
                st.session_state["mensaje_empleado"] = (
                    "Empleado registrado correctamente."
                )
                st.rerun()

    st.divider()

    # -----------------------------------
    # EDITAR EMPLEADO
    # -----------------------------------
    st.subheader("Editar empleado")

    todos = obtener_empleados()

    if not todos:
        st.info(
            "No hay empleados registrados para editar."
        )
        return

    empleado = st.selectbox(
        "Selecciona el empleado que deseas editar",
        todos,
        format_func=lambda e: f"{e[0]} - {e[1]} {e[2]}",
        key="empleado_editar"
    )

    indice_sede = next(
        (i for i, s in enumerate(sedes) if s[0] == empleado[7]),
        0
    )

    # Igual que al registrar: la sede va fuera del formulario para que
    # los roles disponibles cambien según la sede elegida.
    nueva_sede = st.selectbox(
        "Sede",
        sedes,
        index=indice_sede,
        format_func=etiqueta_sede,
        key=f"editar_sede_{empleado[0]}"
    )

    roles_edicion = roles_de_sede(roles, nueva_sede[2])

    indice_rol = next(
        (i for i, r in enumerate(roles_edicion) if r[0] == empleado[4]),
        0
    )

    st.caption(
        "Roles disponibles en esta sede: "
        + (", ".join(r[1] for r in roles_edicion) or "ninguno")
    )

    # Aviso para empleados que ya estaban con un rol que no corresponde
    if empleado[4] not in [r[0] for r in roles_edicion]:
        st.warning(
            f"El rol actual ({empleado[5]}) no corresponde a esta sede. "
            "Seleccione el rol correcto antes de guardar."
        )

    # La clave incluye el ID para que el formulario se actualice
    # al cambiar de empleado
    with st.form(f"form_editar_empleado_{empleado[0]}"):
        nuevo_nombre = st.text_input(
            "Nombre",
            value=empleado[1],
            max_chars=50
        )

        nuevo_apellido = st.text_input(
            "Apellido",
            value=empleado[2],
            max_chars=50
        )

        nuevo_correo = st.text_input(
            "Correo",
            value=empleado[3],
            max_chars=100
        )

        nueva_contrasena = st.text_input(
            "Nueva contraseña (dejar vacío para no cambiarla)",
            type="password"
        )

        nuevo_rol = st.selectbox(
            "Rol",
            roles_edicion,
            index=indice_rol if roles_edicion else None,
            format_func=lambda r: r[1],
            key=f"editar_rol_{empleado[0]}_{nueva_sede[0]}"
        )

        nuevo_activo = st.checkbox(
            "Usuario activo",
            value=es_activo(empleado[6])
        )

        actualizar = st.form_submit_button(
            "Guardar cambios"
        )

    if actualizar:
        error_validacion = validar_datos(
            nuevo_nombre,
            nuevo_apellido,
            nuevo_correo,
            nueva_contrasena,
            False
        )

        es_mismo_usuario = (
            nuevo_correo.strip() == st.session_state.get("usuario", "")
            or empleado[3] == st.session_state.get("usuario", "")
        )

        if error_validacion:
            st.warning(error_validacion)
        elif not rol_corresponde_a_sede(nuevo_rol, nueva_sede):
            # Validación de seguridad: el rol debe ser de esa sede
            st.warning(
                "El rol seleccionado no corresponde al tipo de sede."
            )
        elif correo_existe(nuevo_correo, empleado[0]):
            st.warning(
                "Ya existe otro empleado con ese correo."
            )
        elif es_mismo_usuario and not nuevo_activo:
            st.warning(
                "No puede desactivar el usuario con el que inició sesión."
            )
        else:
            if nueva_contrasena.strip() == "":
                consulta = """
                UPDATE USUARIO
                SET Nombre = %s,
                    Apellido = %s,
                    Correo = %s,
                    Id_rol = %s,
                    Estado = %s,
                    Id_sede = %s
                WHERE Id_usuario = %s
                """

                parametros = (
                    nuevo_nombre.strip(),
                    nuevo_apellido.strip(),
                    nuevo_correo.strip(),
                    nuevo_rol[0],
                    valor_estado(nuevo_activo),
                    nueva_sede[0],
                    empleado[0]
                )
            else:
                consulta = """
                UPDATE USUARIO
                SET Nombre = %s,
                    Apellido = %s,
                    Correo = %s,
                    Id_rol = %s,
                    Contrasena = %s,
                    Estado = %s,
                    Id_sede = %s
                WHERE Id_usuario = %s
                """

                parametros = (
                    nuevo_nombre.strip(),
                    nuevo_apellido.strip(),
                    nuevo_correo.strip(),
                    nuevo_rol[0],
                    nueva_contrasena.strip(),
                    valor_estado(nuevo_activo),
                    nueva_sede[0],
                    empleado[0]
                )

            if ejecutar(consulta, parametros):
                st.session_state["mensaje_empleado"] = (
                    "Empleado actualizado correctamente."
                )
                st.rerun()
