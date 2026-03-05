import streamlit as st

# --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
if 'tela_registro' not in st.session_state:
    st.session_state['tela_registro'] = False

# --- FUNÇÃO PARA SALVAR NOVO USUÁRIO (Exemplo simples em CSV) ---
def adicionar_usuario(user, pwd):
    import pandas as pd
    import os
    file = 'usuarios.csv'
    # Cria o arquivo se não existir
    if not os.path.exists(file):
        df = pd.DataFrame(columns=['usuario', 'senha'])
        df.to_csv(file, index=False)
    
    df = pd.read_csv(file)
    if user in df['usuario'].values:
        return False
    
    novo_df = pd.concat([df, pd.DataFrame({'usuario': [user], 'senha': [pwd]})], ignore_index=False)
    novo_df.to_csv(file, index=False)
    return True

# --- LÓGICA DA BARRA LATERAL (SIDEBAR) ---
if not st.session_state['logado']:
    # VERIFICA SE O USUÁRIO CLICOU EM "SOLICITAR ACESSO"
    if st.session_state['tela_registro']:
        st.sidebar.title("📝 Solicitar Acesso")
        novo_usuario = st.sidebar.text_input("Defina seu Nome de Usuário", key="reg_user")
        nova_senha = st.sidebar.text_input("Defina sua Senha", type='password', key="reg_pwd")
        confirmar_senha = st.sidebar.text_input("Confirme sua Senha", type='password', key="reg_pwd_conf")
        
        if st.sidebar.button("Enviar Solicitação / Cadastrar"):
            if nova_senha == confirmar_senha and novo_usuario:
                if adicionar_usuario(novo_usuario, nova_senha):
                    st.sidebar.success("Conta criada com sucesso! Faça o login agora.")
                    st.session_state['tela_registro'] = False
                    st.rerun()
                else:
                    st.sidebar.error("Este usuário já existe.")
            else:
                st.sidebar.error("As senhas não coincidem ou campos estão vazios.")
        
        if st.sidebar.button("Voltar para o Login"):
            st.session_state['tela_registro'] = False
            st.rerun()
            
    else:
        # TELA DE LOGIN PADRÃO
        st.sidebar.title("🔐 Login do Sistema")
        usuario = st.sidebar.text_input("Usuário", key="login_user")
        senha = st.sidebar.text_input("Senha", type='password', key="login_pwd")
        
        if st.sidebar.button("Entrar"):
            # Aqui você mantém sua lógica de verificação atual
            # Ex: if verificar_login(usuario, senha): ...
            st.session_state['logado'] = True # Exemplo simplificado
            st.rerun()
            
        # O BOTÃO QUE ESTAVA FALTANDO
        st.sidebar.markdown("---")
        st.sidebar.write("Ainda não tem conta?")
        if st.sidebar.button("Solicitar Acesso"):
            st.session_state['tela_registro'] = True
            st.rerun()

else:
    # SE ESTIVER LOGADO, MOSTRA O BOTÃO DE SAIR E O RESTO DO APP
    st.sidebar.success(f"Logado como: Usuário")
    if st.sidebar.button("Sair"):
        st.session_state['logado'] = False
        st.rerun()
    
    # --- O RESTANTE DO SEU CÓDIGO (Gráficos, Tabelas, PDF) SEGUE ABAIXO ---
    st.title("Painel de Controle")
    # ... colar o código de st.area_chart, gerar_pdf, etc.
