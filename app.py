import os
import importlib
import mysql.connector
import streamlit as st

NOMBRE_LOGO = "Logo prueba.jpeg"


# ==============================
# CONEXIÓN Y LOGIN
# ==============================
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
        SELECT Id_usuario, Estado, Id_rol, Id_sede
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


def obtener_ruta_logo():
    carpeta = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(carpeta, NOMBRE_LOGO)


def mostrar_logo():
    ruta_logo = obtener_ruta_logo()
    if os.path.exists(ruta_logo):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image(ruta_logo, use_container_width=True)
    else:
        st.warning(f"No se encontró la imagen en: {ruta_logo}")


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
                    st.session_state["id_rol"] = resultado[2]
                    st.session_state["id_sede"] = resultado[3]
                    st.rerun()
                else:
                    st.error(
                        "Usuario desactivado"
                    )
            else:
                st.error(
                    "Correo o contraseña incorrectos."
                )


# ==============================
# CARGA SEGURA DE MÓDULOS
# ==============================
def cargar_modulo(nombre_archivo, nombre_funcion):
    """
    Importa modulos/<nombre_archivo>.py y devuelve la función indicada.
    Si el archivo o la función no existen (o tienen un error), devuelve
    una función que muestra un aviso en pantalla, así la app NO se cae.
    """
    try:
        modulo = importlib.import_module(f"modulos.{nombre_archivo}")
        return getattr(modulo, nombre_funcion)
    except Exception as error:
        mensaje = (
            f"No se pudo cargar modulos/{nombre_archivo}.py "
            f"(función {nombre_funcion}): {error}"
        )

        def aviso():
            st.warning(mensaje)

        return aviso


def mostrar_informacion():
    st.header("Información del sistema")


# ==============================================================
# >>>>>>>>>>  AQUÍ SE AGREGAN LOS NUEVOS MÓDULOS  <<<<<<<<<<
#
# Formato:
#   "Nombre que se ve en el menú": cargar_modulo("archivo", "funcion")
#
# "archivo" es el nombre del .py dentro de modulos/ (sin el .py),
# escrito igual que en GitHub (mayúsculas incluidas).
# "funcion" es la función que dibuja la pantalla en ese archivo.
#
# Ejemplo: si creas modulos/Compras.py con la función
# mostrar_compra(), agrega esta línea:
#   "Compras": cargar_modulo("Compras", "mostrar_compra"),
# ==============================================================
MODULOS = {
    "Ventas": cargar_modulo("ventas", "mostrar_venta"),
    "Productos": cargar_modulo("Producto", "render"),
    "Proveedores": cargar_modulo("Proveedor", "mostrar_proveedor"),
    "Empleados": cargar_modulo("Empleado", "mostrar_empleado"),
    "Inventario": cargar_modulo("Inventario", "mostrar_inventario"),
    "Compras": cargar_modulo("Compras", "mostrar_compra"),
    # "Clientes": cargar_modulo("Clientes", "mostrar_cliente"),
    "Información": mostrar_informacion,
}


# ==============================
# FLUJO PRINCIPAL
# ==============================
# Inicializar variables de sesión
if "sesion_iniciada" not in st.session_state:
    st.session_state["sesion_iniciada"] = False

if "usuario" not in st.session_state:
    st.session_state["usuario"] = ""

if "id_rol" not in st.session_state:
    st.session_state["id_rol"] = None

if "id_sede" not in st.session_state:
    st.session_state["id_sede"] = None

# Comprobar si el usuario inició sesión
if st.session_state["sesion_iniciada"]:

    # Logo en el menú lateral
    ruta_logo = obtener_ruta_logo()
    if os.path.exists(ruta_logo):
        st.sidebar.image(ruta_logo, use_container_width=True)

    st.sidebar.title("Menú")

    st.sidebar.write(
        f"Usuario: {st.session_state['usuario']}"
    )

    # Las opciones salen automáticamente del diccionario MODULOS
    seleccion = st.sidebar.selectbox(
        "Seleccione una opción",
        list(MODULOS.keys())
    )

    # Mostrar el módulo elegido
    MODULOS[seleccion]()

    # Cerrar sesión
    if st.sidebar.button("Cerrar sesión"):
        st.session_state["sesion_iniciada"] = False
        st.session_state["usuario"] = ""
        st.session_state["id_rol"] = None
        st.session_state["id_sede"] = None
        st.rerun()

else:
    # Si no hay sesión iniciada, mostrar login
    login()
