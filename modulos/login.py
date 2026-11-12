def login():
    st.title("Inicio de sesión")

    correo = st.text_input("Correo")
    contrasena = st.text_input("Contraseña", type="password")

    if st.button("Iniciar sesión"):
        if correo.strip() == "" or contrasena.strip() == "":
            st.warning("Ingrese su correo y contraseña.")
            return

        usuario = verificar_usuario(correo.strip(), contrasena)

        if not usuario:
            st.error("Correo o contraseña incorrectos.")
            return

        # Solo se muestra alerta si el usuario está desactivado
        if not usuario_activo(usuario["Estado"]):
            st.error("Usuario desactivado")
            st.toast("Usuario desactivado", icon="🚫")
            return

        # Usuario activo: inicia sesión sin mostrar ninguna alerta
        st.session_state["sesion_iniciada"] = True
        st.session_state["id_usuario"] = usuario["Id_usuario"]
        st.session_state["nombre"] = f"{usuario['Nombre']} {usuario['Apellido']}"
        st.session_state["correo"] = usuario["Correo"]
        st.session_state["id_rol"] = usuario["Id_rol"]
        st.session_state["id_sede"] = usuario["Id_sede"]
        st.rerun()
