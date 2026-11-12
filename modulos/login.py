def login():
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.image("logo.png", use_container_width=True)

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
