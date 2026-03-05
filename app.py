# --- 3. SISTEMA DE LOGIN --- 
from datetime import timezone, timedelta # Garanta que estes estão no topo do seu código

if 'auth' not in st.session_state: st.session_state['auth'] = None 

if st.session_state['auth'] is None: 
    st.title("ༀ༁༂ Acesso ao Sistema NBR 17227") 
    t1, t2 = st.tabs(["Entrar", "Solicitar Acesso"]) 
    
    with t1: 
        u = st.text_input("E-mail") 
        p = st.text_input("Senha", type="password") 
        if st.button("Acessar"): 
            if u == "admin" and p == "101049app": 
                st.session_state['auth'] = {"role": "admin", "user": "Administrador"} 
                st.rerun() 
            else: 
                try: 
                    res = supabase.table("usuarios").select("*").eq("email", u).eq("senha", p).execute() 
                    if res.data: 
                        user_found = res.data[0] 
                        if user_found['status'] == 'ativo': 
                            # LÓGICA DE EXPIRAÇÃO DE 1 ANO
                            data_str = user_found['data_aprovacao'].replace('Z', '+00:00') 
                            data_ap = datetime.fromisoformat(data_str).astimezone(timezone.utc) 
                            agora_utc = datetime.now(timezone.utc) 
                            
                            if agora_utc > data_ap + timedelta(days=365): 
                                st.error("Seu acesso expirou (validade de 1 ano atingida).") 
                            else: 
                                st.session_state['auth'] = {"role": "user", "user": u} 
                                st.rerun() 
                        else: 
                            st.warning(f"Seu acesso está: {user_found['status'].upper()}. Aguarde aprovação.") 
                    else: 
                        st.error("E-mail ou senha incorretos.") 
                except Exception as e: 
                    st.error(f"Erro de conexão: {e}") 
    
    with t2: 
        ne = st.text_input("Seu E-mail para cadastro", key="reg_email") 
        np_ = st.text_input("Crie uma Senha", type="password", key="reg_pass") 
        if st.button("Enviar Solicitação"): 
            try: 
                supabase.table("usuarios").insert({"email": ne, "senha": np_, "status": "pendente"}).execute() 
                st.success("Solicitação enviada!") 
            except: 
                st.error("Erro ao enviar solicitação.") 
    st.stop()
