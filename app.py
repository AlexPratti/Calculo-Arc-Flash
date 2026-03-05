import streamlit as st
import pandas as pd

# 1. Configuração da Página (Deve ser a primeira linha de comando Streamlit)
st.set_page_config(page_title="Gestão de Arco Elétrico", layout="wide")

# 2. Inicialização do Estado
if 'logado' not in st.session_state:
    st.session_state['logado'] = False
if 'tela_registro' not in st.session_state:
    st.session_state['tela_registro'] = False

# --- FUNÇÃO DE LOGIN SIMPLIFICADA (Ajuste para sua lógica de DB/CSV) ---
def verificar_login(u, p):
    return u == "admin" and p == "123" # Exemplo: Usuário admin, Senha 123

# --- INTERFACE DE AUTENTICAÇÃO ---
if not st.session_state['logado']:
    if st.session_state['tela_registro']:
        st.sidebar.title("📝 Solicitar Acesso")
        novo_user = st.sidebar.text_input("Usuário")
        nova_senha = st.sidebar.text_input("Senha", type='password')
        if st.sidebar.button("Cadastrar"):
            st.sidebar.success("Solicitação enviada!")
            st.session_state['tela_registro'] = False
            st.rerun()
        if st.sidebar.button("Voltar ao Login"):
            st.session_state['tela_registro'] = False
            st.rerun()
    else:
        st.sidebar.title("🔐 Login")
        user = st.sidebar.text_input("Usuário")
        pw = st.sidebar.text_input("Senha", type='password')
        if st.sidebar.button("Entrar"):
            if verificar_login(user, pw):
                st.session_state['logado'] = True
                st.rerun()
            else:
                st.sidebar.error("Usuário ou senha incorretos")
        
        st.sidebar.markdown("---")
        if st.sidebar.button("Solicitar Acesso"):
            st.session_state['tela_registro'] = True
            st.rerun()

# --- CONTEÚDO PRINCIPAL (SÓ APARECE SE LOGADO) ---
if st.session_state['logado']:
    # Barra lateral logada
    st.sidebar.success(f"Conectado")
    if st.sidebar.button("Sair"):
        st.session_state['logado'] = False
        st.rerun()

    # TUDO O QUE VOCÊ TINHA NO "PAINEL DE CONTROLE" DEVE VIR AQUI:
    st.title("Painel de Controle")
    
    col1, col2 = st.columns(2)
    with col1:
        distancia = st.number_input("Distância (mm)", value=455)
    
    # Exemplo de gráfico (onde dava o erro anterior)
    dados = pd.DataFrame({'Distância': [10, 20, 30], 'Energia': [1.2, 2.5, 3.8]})
    st.area_chart(dados.set_index('Distância'))

    if st.button("Gerar Relatório PDF"):
        st.write("Gerando PDF...") 
        # Chame sua função gerar_pdf_profissional(dados) aqui
