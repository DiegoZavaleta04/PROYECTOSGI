import os
import streamlit as st
from config.conexion import obtener_conexion

NOMBRE_LOGO = "Logo prueba.jpeg"

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
    # El logo está en la raíz del proyecto (una carpeta arriba de modulos)
    carpeta_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta_logo = os.path.join(carpeta_raiz, NOMBRE_LOGO)

    if os.path.exists(ruta_logo):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image(ruta_logo, use_container_width=True)
    else:
        st.warning(f"No se encontró la imagen en: {ruta_logo}")
        st.write("Archivos en la raíz:", os.listdir(carpeta_raiz))

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
