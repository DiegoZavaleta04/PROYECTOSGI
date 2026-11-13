import os
import mysql.connector
import streamlit as st
from productos import mostrar_productos

NOMBRE_LOGO = "Logo prueba.jpeg"


def obtener_conexion():
    try:
        conexion = mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            port=st.secrets["mysql"]["port"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"]
        )
        if conexion.is_connected():
            return conexion
        return None
    except mysql.connector.Error as err:
        st.error(f"Error al conectar con la base de datos: {err}")
        return None


def verificar_usuario(correo, contrasena):
    conexion = obtener_conexion()
    if conexion is None:
        return None
    cursor = None
    try:
        cursor = conexion.cursor()
        consulta = """
        SELECT Id_usuario, Estado
        FROM USUARIO
        WHERE Correo = %s AND Contrasena = %s
        LIMIT 1
        """
        cursor.execute(
            consulta,
            (correo, contrasena)
        )
        resultado = cursor.fetchone()
        return resultado
    except Exception as error:
        st.error(f"Error al verificar el usuario: {error}")
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if conexion.is_connected():
            conexion.close()


def mostrar_logo():
    # El logo está en la misma carpeta que app.py
    carpeta = os.path.dirname(os.path.abspath(__file__))
    ruta_logo = os.path.join(carpeta, NOMBRE_LOGO)

    if os.path.exists(ruta_logo):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image(ruta_logo, use_container_width=True)
    else:
        st.warning(f"No se encontró la imagen en: {ruta_logo}")
        st.write("Archivos en la carpeta:", os.listdir(carpeta))


def login():
    mostrar_logo()

    st.title("Inicio de sesión")
    correo = st.text_input("Correo")
    contrasena = st.text_input(
        "Contraseña",
        type="password"
    )
    if st.button("Iniciar sesión"):
        if correo.strip() == "" or contrasena.strip() == "":
            st.warning(
                "Ingrese su correo y contraseña."
            )
        else:
            resultado = verificar_usuario(
                correo,
                contrasena
            )
            if resultado:
                estado = str(resultado[1]).strip().lower()
                if estado in ("1", "activo", "true"):
                    st.session_state["sesion_iniciada"] = True
                    st.session_state["usuario"] = correo
                    st.rerun()
                else:
                    st.error(
                        "Usuario desactivado"
                    )
            else:
                st.error(
                    "Correo o contraseña incorrectos."
                )


# ---- Flujo principal ----
if not st.session_state.get("sesion_iniciada"):
    login()
else:
    st.title("Bienvenido")
    st.write(f"Sesión iniciada con: {st.session_state['usuario']}")

    # Menú principal
    st.sidebar.title("Menú principal")

    opcion = st.sidebar.radio(
        "Seleccione un módulo:",
        ["Inicio", "Productos"]
    )

    if opcion == "Inicio":
        st.subheader("Inicio")
        st.write("Bienvenido al Sistema de Gestión de Información.")

    elif opcion == "Productos":
        mostrar_productos()

    # Cerrar sesión
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()
