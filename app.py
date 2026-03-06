import streamlit as st
import pandas as pd
import numpy as np
import io
import math
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Engenharia Elétrica Pro", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co"
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe"

# Inicialização de Estados (Persistência)
if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro de Conexão Supabase: {e}")
    st.stop()

# --- 2. SISTEMA DE LOGIN (VERSÃO CORRIGIDA) ---
if st.session_state['auth'] is None:
    st.title("🔐 Login do Sistema")
    u_login = st.text_input("E-mail")
    p_login = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        try:
            # Consulta exata
            res = supabase.table("usuarios").select("*").eq("email", u_login).eq("senha", p_login).execute()
            
            # Verifica se retornou algum dado
            if res.data and len(res.data) > 0:
                user_data = res.data[0] # ACESSO AO PRIMEIRO ITEM DA LISTA
                
                # Tratamento de Data para Bloqueio de 1 Ano
                # Remove o 'Z' e frações de segundo para o Python entender
                raw_date = user_data['created_at'].split('.')[0].replace('Z', '')
                data_criacao = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
                hoje = datetime.now(timezone.utc)

                if (hoje - data_criacao) > timedelta(days=365):
                    st.error("❌ Seu acesso de 1 ano expirou. Contate o administrador.")
                elif user_data.get('status', '').lower() == 'ativo':
                    st.session_state['auth'] = {"user": u_login, "role": user_data.get('role', 'user')}
                    st.success("Acesso autorizado!")
                    st.rerun()
                else:
                    st.warning("⏳ Seu usuário ainda não foi ativado no banco de dados.")
            else:
                st.error("❌ E-mail ou senha incorretos.")
        except Exception as e:
            st.error(f"Erro técnico no login: {e}")
    st.stop()

# --- 3. INTERFACE PRINCIPAL ---
st.sidebar.write(f"Usuário: **{st.session_state['auth']['user']}**")
if st.sidebar.button("Sair"):
    st.session_state['auth'] = None
    st.rerun()

aba_arco, aba_curto, aba_cap, aba_hist = st.tabs(["🔥 Arco Elétrico", "⚡ Curto-Circuito", "🔋 Capacitores", "📜 Histórico"])

# --- ABA ARCO ELÉTRICO ---
with aba_arco:
    st.header("Estudo de Arco (NBR 17227)")
    i_bf = st.number_input("Ibf (kA)", value=float(st.session_state['corrente_transf']), help="Valor atualizado pela aba de Curto-Circuito")
    st.info("Utilize a aba 'Curto-Circuito' para calcular e enviar este valor automaticamente.")

# --- ABA CURTO-CIRCUITO ---
with aba_curto:
    st.header("Cálculo de Curto-Circuito")
    pot_t = st.number_input("Trafo (kVA)", value=225.0)
    tens_t = st.number_input("Tensão (V)", value=380.0)
    z_t = st.number_input("Z% Trafo", value=5.0)
    
    if st.button("🚀 Calcular Icc"):
        icc_ka = round((tens_t / (1.732 * ((z_t/100)*((tens_t**2)/(pot_t*1000)))) * 0.85) / 1000, 3)
        st.session_state['res_temp_icc'] = icc_ka
        st.success(f"Icc Local: {icc_ka} kA")
    
    if 'res_temp_icc' in st.session_state:
        if st.button("💾 ENVIAR PARA ARCO ELÉTRICO"):
            st.session_state['corrente_transf'] = st.session_state['res_temp_icc']
            st.success("Valor transferido com sucesso!")

# --- ABA CAPACITORES ---
with aba_cap:
    st.header("Banco de Capacitores")
    p_kw = st.number_input("Potência Ativa (kW)", value=100.0)
    v_cap = st.selectbox("Tensão da Rede (V)", [220, 380, 440], index=1)

# --- ABA HISTÓRICO COM EXCLUSÃO ---
with aba_hist:
    st.header("Gerenciar Registros")
    try:
        # Busca histórico de curto-circuito
        hist = supabase.table("calculos_curto").select("*").order("created_at", desc=True).execute()
        if hist.data:
            for r in hist.data:
                col_info, col_btn = st.columns([4, 1])
                col_info.write(f"📅 {r['created_at'][:10]} | Tag: {r.get('tag_painel', '---')} | **{r.get('icc_ka')} kA**")
                if col_btn.button("🗑️", key=f"del_{r['id']}"):
                    supabase.table("calculos_curto").delete().eq("id", r['id']).execute()
                    st.rerun()
        else:
            st.info("Nenhum registro no banco.")
    except:
        st.error("Erro ao carregar histórico.")
