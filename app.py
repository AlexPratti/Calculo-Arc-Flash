import streamlit as st
import pandas as pd
import numpy as np
import io
import math
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO, CONEXÃO E ESTADO ---
st.set_page_config(page_title="Streamlit - NBR 17227", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co"
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe"

# Inicializa a memória para transferência entre abas
if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85 # Valor padrão original
if 'df_motores' not in st.session_state: 
    st.session_state.df_motores = pd.DataFrame(columns=['Equipamento', 'Motor (CV)', 'Quantidade', 'Partida', 'CCM Destino', 'Status'])

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. SISTEMA DE LOGIN (REGRAS DE ACESSO) ---
if st.session_state['auth'] is None:
    st.title("🔐 Acesso Restrito")
    u_login = st.text_input("Usuário")
    p_login = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        # Login mestre para evitar erro de banco
        if u_login == "admin" and p_login == "101049app":
            st.session_state['auth'] = {"user": "Administrador", "role": "admin"}
            st.rerun()
        else:
            try:
                res = supabase.table("usuarios").select("*").eq("email", u_login).eq("senha", p_login).execute()
                if res.data and len(res.data) > 0:
                    u_data = res.data[0]
                    # Trava de 1 ano
                    dt_c = datetime.fromisoformat(u_data['created_at'].split('.')[0].replace('Z',''))
                    if (datetime.now() - dt_c) > timedelta(days=365):
                        st.error("Acesso expirado (365 dias).")
                    elif u_data.get('status','').lower() == 'ativo':
                        st.session_state['auth'] = {"user": u_login, "role": "user"}
                        st.rerun()
                    else: st.warning("Aguarde ativação do cadastro.")
                else: st.error("Dados incorretos.")
            except: st.error("Erro ao validar login.")
    st.stop()

# --- 3. NAVEGAÇÃO POR ABAS PRINCIPAIS ---
st.sidebar.button("Sair", on_click=lambda: st.session_state.update({"auth": None}))

tab_arco, tab_curto, tab_cap, tab_hist = st.tabs([
    "🔥 Arco Elétrico (NBR 17227)", 
    "⚡ Curto-Circuito", 
    "🔋 Banco de Capacitores",
    "📜 Histórico de Cálculos"
])

# --- ABA 1: SEU CÓDIGO ORIGINAL (NBR 17227) ---
with tab_arco:
    # AQUI VOCÊ COLA O SEU CÓDIGO ORIGINAL DE ARCO ELÉTRICO
    # Importante: No campo 'st.number_input' da Corrente Ibf, use o session_state:
    # Exemplo: i_bf = st.number_input("Corrente Ibf (kA)", value=st.session_state['corrente_transf'])
    
    st.header("Análise de Arco Elétrico")
    st.info("Interface original preservada. O valor de Ibf abaixo pode ser preenchido pela aba de Curto-Circuito.")
    
    # Exemplo da sua interface original (mantenha exatamente a sua)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.number_input("Tensão Voc (kV)", value=13.8)
    with col2:
        # AQUI O VALOR É ATUALIZADO PELA OUTRA ABA
        st.number_input("Corrente Ibf (kA)", value=float(st.session_state['corrente_transf']), key="ibf_input_original")
    with col3:
        st.number_input("Tempo T (ms)", value=488.0)
    
    st.button("Executar Estudo", type="primary")
    # ... continue com todo o seu código original de tabelas e resultados ...

# --- ABA 2: CURTO-CIRCUITO (COM GESTÃO DE MOTORES) ---
with tab_curto:
    st.header("⚡ Cálculo de Curto-Circuito e Motores")
    
    # Seu código que você me passou de CCMs e Motores
    n_ccm = st.number_input("Quantidade de CCMs", min_value=1, value=1)
    
    st.subheader("📋 Cadastro de Motores")
    c1, c2, c3 = st.columns(3)
    nome_eq = c1.text_input("Equipamento")
    pot_m = c2.selectbox("Motor (CV)", [1, 2, 3, 5, 10, 20, 50, 100])
    qtd_m = c3.number_input("Qtd", min_value=1, value=1)
    
    if st.button("➕ Adicionar à Lista"):
        novo_m = pd.DataFrame([{'Equipamento': nome_eq, 'Motor (CV)': pot_m, 'Quantidade': qtd_m}])
        st.session_state.df_motores = pd.concat([st.session_state.df_motores, novo_m], ignore_index=True)
        st.rerun()

    if not st.session_state.df_motores.empty:
        st.table(st.session_state.df_motores)
        if st.button("🚀 EXECUTAR CÁLCULO DE ICC"):
            # Lógica de cálculo que gera o valor
            icc_calculada = 10.50 # Valor fictício para o exemplo
            st.session_state['icc_val_temp'] = icc_calculada
            st.success(f"Curto-Circuito Local: {icc_calculada} kA")
            
            # O BOTÃO QUE VOCÊ PEDIU:
            if st.button("💾 ENVIAR VALOR PARA ABA DE CÁLCULOS"):
                st.session_state['corrente_transf'] = st.session_state['icc_val_temp']
                st.success("Valor enviado! Verifique a aba de Arco Elétrico.")

# --- ABA 3: BANCO DE CAPACITORES ---
with tab_cap:
    st.header("🔋 Dimensionamento de Banco de Capacitores")
    # Insira aqui o seu código de capacitores (Potência, FP atual, FP alvo, etc.)
    st.write("Interface de cálculo de capacitores.")

# --- ABA 4: HISTÓRICO ---
with tab_hist:
    st.header("📜 Histórico do Banco de Dados")
    if st.button("🔄 Sincronizar Histórico"):
        res = supabase.table("calculos_curto").select("*").execute()
        st.dataframe(pd.DataFrame(res.data), use_container_width=True)
