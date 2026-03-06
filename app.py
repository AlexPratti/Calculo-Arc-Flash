import streamlit as st
import pandas as pd
import numpy as np
import io
import math
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Engenharia Elétrica Pro", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co"
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe"

if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro de Conexão: {e}")
    st.stop()

# --- 2. SISTEMA DE LOGIN (VERSÃO BLINDADA) ---
if st.session_state['auth'] is None:
    st.title("🔐 Login do Sistema")
    u_login = st.text_input("E-mail ou Usuário")
    p_login = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        # REGRA DE OURO: LOGIN MESTRE (Ignora o banco de dados)
        if u_login == "admin" and p_login == "101049app":
            st.session_state['auth'] = {"user": "Administrador", "role": "admin"}
            st.success("Login Mestre realizado!")
            st.rerun()
        
        # BUSCA NO BANCO DE DADOS (Para outros usuários)
        else:
            try:
                res = supabase.table("usuarios").select("*").eq("email", u_login).eq("senha", p_login).execute()
                
                if res.data and len(res.data) > 0:
                    user_data = res.data[0] # Pega o primeiro usuário da lista
                    
                    # Validação de data (1 ano)
                    raw_date = user_data['created_at'].split('.')[0].replace('Z', '')
                    data_criacao = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - data_criacao) > timedelta(days=365):
                        st.error("❌ Acesso expirado (Limite de 365 dias).")
                    elif user_data.get('status', '').lower() == 'ativo':
                        st.session_state['auth'] = {"user": u_login, "role": user_data.get('role', 'user')}
                        st.rerun()
                    else:
                        st.warning("⏳ Usuário pendente de ativação.")
                else:
                    st.error("❌ E-mail ou senha incorretos.")
            except Exception as e:
                st.error(f"Erro técnico: {e}")
    st.stop()

# --- 3. INTERFACE PRINCIPAL ---
st.sidebar.write(f"Conectado: **{st.session_state['auth']['user']}**")
if st.sidebar.button("Sair"):
    st.session_state['auth'] = None
    st.rerun()

aba_arco, aba_curto, aba_cap, aba_hist = st.tabs(["🔥 Arco Elétrico", "⚡ Curto-Circuito", "🔋 Capacitores", "📜 Histórico"])

# --- ABA ARCO ELÉTRICO ---
with aba_arco:
    st.header("Estudo de Arco (NBR 17227)")
    i_bf = st.number_input("Corrente Ibf (kA)", value=float(st.session_state['corrente_transf']))
    st.info("O valor acima pode ser atualizado automaticamente pela aba 'Curto-Circuito'.")

# --- ABA CURTO-CIRCUITO ---
with aba_curto:
    st.header("Cálculo de Icc")
    c1, c2 = st.columns(2)
    v_tensao = c1.number_input("Tensão (V)", value=380.0)
    z_trafo = c2.number_input("Z% Trafo", value=5.0)
    
    if st.button("🚀 Calcular Curto-Circuito"):
        icc_result = round((v_tensao / (1.732 * (z_trafo/100))) / 1000, 3) # Exemplo simplificado
        st.session_state['tmp_icc'] = icc_result
        st.success(f"Icc Calculada: {icc_result} kA")
    
    if 'tmp_icc' in st.session_state:
        if st.button("➡️ ENVIAR PARA ARCO ELÉTRICO"):
            st.session_state['corrente_transf'] = st.session_state['tmp_icc']
            st.success("Valor transferido!")

# --- ABA CAPACITORES ---
with aba_cap:
    st.header("Banco de Capacitores")
    v_sel = st.selectbox("Tensão da Rede (V)", [220, 380, 440], index=1)

# --- ABA HISTÓRICO ---
with aba_hist:
    st.header("Gestão de Registros")
    try:
        hist = supabase.table("calculos_curto").select("*").order("created_at", desc=True).execute()
        if hist.data:
            for r in hist.data:
                col_i, col_d = st.columns([4, 1])
                col_i.write(f"📅 {r['created_at'][:10]} | **{r.get('icc_ka')} kA** | {r.get('tag_painel', '---')}")
                if col_d.button("🗑️", key=f"del_{r['id']}"):
                    supabase.table("calculos_curto").delete().eq("id", r['id']).execute()
                    st.rerun()
    except:
        st.info("Nenhum registro encontrado no histórico.")
