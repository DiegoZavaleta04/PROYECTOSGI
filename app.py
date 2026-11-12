import mysql.connector 

import streamlit as st 

st.title("Conexión con base de datos MySQL") 

# Obtener las credenciales almacenadas en Streamlit Secrets 

host = st.secrets["mysql"]["host"] 

port = st.secrets["mysql"]["port"] 

user = st.secrets["mysql"]["user"] 

password = st.secrets["mysql"]["password"] 

database = st.secrets["mysql"]["database"] 

# Intentar establecer la conexión 

try: 

    conn = mysql.connector.connect( 

        host=host, 

        port=port, 

        user=user, 

        password=password, 

        database=database 

    ) 

    # Verificar si la conexión fue exitosa 

    if conn.is_connected(): 

        st.success("Conexión exitosa a la base de datos MySQL.") 

    else: 

        st.error("No se pudo conectar a la base de datos.") 

except mysql.connector.Error as err: 

    # Mostrar el error si la conexión falla 

    st.error(f"Error al conectar con la base de datos: {err}") 

finally: 

    if "conn" in locals() and conn.is_connected(): 

        conn.close() 


from login import login

if not st.session_state.get("sesion_iniciada"):
    login()
    st.stop()

st.title("Bienvenido")
st.write(f"Sesión iniciada con: {st.session_state['usuario']}")

if st.button("Cerrar sesión"):
    st.session_state.clear()
    st.rerun()
