import streamlit as st
import pandas as pd
import numpy as np
import io
import math
from datetime import datetime, date, timezone, timedelta
from supabase import create_client, Client
from fpdf import FPDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Engenharia Elétrica Pro", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co"
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe"

# Inicialização de Estados Globais (Persistência entre abas)
if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85
if 'df_motores' not in st.session_state: 
    st.session_state.df_motores = pd.DataFrame(columns=['Equipamento', 'Motor (CV)', 'Quantidade', 'Partida', 'CCM Destino'])

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro de Conexão Supabase: {e}")
    st.stop()

# --- 2. FUNÇÕES TÉCNICAS (CÁLCULOS) ---

def calc_ia_step(ibf, g, k):
    k1, k2, k3, k4, k5, k6, k7, k8, k9, k10 = k
    log_base = k1 + k2 * np.log10(ibf) + k3 * np.log10(g)
    poli = (k4*ibf**6 + k5*ibf**5 + k6*ibf**4 + k7*ibf**3 + k8*ibf**2 + k9*ibf + k10)
    return 10**(log_base * poli)

def calc_en_step(ia, ibf, g, d, t, k, cf):
    k1, k2, k3, k4, k5, k6, k7, k8, k9, k10, k11, k12, k13 = k
    poli_den = (k4*ibf**7 + k5*ibf**6 + k6*ibf**5 + k7*ibf**4 + k8*ibf**3 + k9*ibf**2 + k10*ibf)
    termo_ia = (k3 * ia) / poli_den if poli_den != 0 else 0
    exp = (k1 + k2*np.log10(g) + termo_ia + k11*np.log10(ibf) + k12*np.log10(d) + k13*np.log10(ia) + np.log10(1.0/cf))
    return (12.552 / 50.0) * (t/1000.0) * (10**exp)

def calc_dla_step(ia, ibf, g, t, k, cf):
    k1, k2, k3, k4, k5, k6, k7, k8, k9, k10, k11, k12, k13 = k
    poli_den = (k4*ibf**7 + k5*ibf**6 + k6*ibf**5 + k7*ibf**4 + k8*ibf**3 + k9*ibf**2 + k10*ibf)
    termo_ia = (k3 * ia) / poli_den if poli_den != 0 else 0
    log_fixo = (k1 + k2*np.log10(g) + termo_ia + k11*np.log10(ibf) + k13*np.log10(ia) + np.log10(1.0/cf))
    return 10**((np.log10(5.0 / ((12.552 / 50.0) * (t/1000.0))) - log_fixo) / k12)

def interpolar(v, f600, f2700, f14300):
    if v <= 0.6: return f600
    if v <= 2.7: return f600 + (f2700 - f600) * (v - 0.6) / 2.1
    return f2700 + (f14300 - f2700) * (v - 2.7) / 11.6

def definir_vestimenta(cal):
    if cal <= 1.2: return "Nível 0 (Não FR)"
    if cal <= 8: return "CAT 2"
    if cal <= 25: return "CAT 3"
    if cal <= 40: return "CAT 4"
    return "PERIGO (>40 cal/cm²)"

def calcular_cap(p_kw, fp_at, fp_al, v):
    phi_at = math.acos(min(fp_at, 0.9999))
    phi_al = math.acos(min(fp_al, 0.9999))
    kvar = p_kw * (math.tan(phi_at) - math.tan(phi_al))
    i_nom = (kvar * 1000) / (math.sqrt(3) * v) if kvar > 0 else 0
    tabela = [(1.5, 15.5), (2.5, 21), (4, 28), (6, 36), (10, 50), (16, 68), (25, 89), (35, 110), (50, 134), (70, 171)]
    bitola = 1.5
    for b, amp in tabela:
        if amp >= (i_nom * 1.35):
            bitola = b
            break
    return {"kvar": round(kvar, 2), "i_proj": round(i_nom * 1.35, 2), "bitola": bitola}

# --- 3. SISTEMA DE LOGIN COM VALIDAÇÃO DE 1 ANO ---
if st.session_state['auth'] is None:
    st.title("🔐 Login do Sistema")
    u_login = st.text_input("E-mail")
    p_login = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        try:
            res = supabase.table("usuarios").select("*").eq("email", u_login).eq("senha", p_login).execute()
            if res.data and len(res.data) > 0:
                user_data = res.data[0] # Acessa o primeiro item da lista
                
                # Conversão de data ISO para comparação
                raw_date = user_data['created_at'].replace('Z', '').split('+')[0]
                data_criacao = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
                hoje = datetime.now(timezone.utc)

                if (hoje - data_criacao) > timedelta(days=365):
                    st.error("❌ Acesso expirado (Limite de 365 dias).")
                elif user_data['status'].lower() == 'ativo':
                    st.session_state['auth'] = {"user": u_login, "role": user_data.get('role', 'user')}
                    st.rerun()
                else:
                    st.warning("⏳ Usuário pendente de aprovação.")
            else:
                st.error("❌ E-mail ou senha incorretos.")
        except Exception as e:
            st.error(f"Erro de Autenticação: {e}")
    st.stop()

# --- 4. INTERFACE PRINCIPAL ---
st.sidebar.write(f"Logado como: **{st.session_state['auth']['user']}**")
if st.sidebar.button("Sair"):
    st.session_state['auth'] = None
    st.rerun()

aba_arco, aba_curto, aba_cap, aba_hist = st.tabs(["🔥 Arco Elétrico", "⚡ Curto-Circuito", "🔋 Capacitores", "📜 Histórico"])

# --- ABA ARCO ELÉTRICO ---
with aba_arco:
    st.header("Cálculo de Energia Incidente (NBR 17227)")
    col_e, col_c = st.columns(2)
    with col_e:
        eq_sel = st.selectbox("Tipo de Equipamento:", ["CCM e painel típico de BT", "Conjunto de manobra BT"])
        gap = st.number_input("GAP (mm)", value=25.0)
        dist = st.number_input("Distância de Trabalho (mm)", value=457.2)
    with col_c:
        v_oc = st.number_input("Tensão (kV)", value=0.38)
        # USA VALOR QUE PODE TER SIDO ENVIADO DA ABA DE CURTO-CIRCUITO
        i_bf = st.number_input("Ibf (kA)", value=float(st.session_state['corrente_transf']))
        t_ms = st.number_input("Tempo (ms)", value=100.0)

    if st.button("Calcular Arco"):
        # Lógica simplificada de interpolação para o exemplo
        k_v = [0.6, 2.7, 14.3]
        k_ia = {0.6: [-0.04287, 1.035, -0.083, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092], 2.7: [0.0065, 1.001, -0.024, 0,0,0,0,0, -0.003191, 0.9729], 14.3: [0.005795, 1.015, -0.011, 0,0,0,0,0, -0.003191, 0.9729]}
        k_en = {0.6: [0.753364, 0.566, 1.752636, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092, 0, -1.598, 0.957], 2.7: [2.40021, 0.165, 0.354202, 0,0,0,0,0, -0.003191, 0.9729, 0, -1.569, 0.9778], 14.3: [3.825917, 0.11, -0.999749, 0,0,0,0,0, -0.003191, 0.9729, 0, -1.568, 0.99]}
        
        ia_sts = [calc_ia_step(i_bf, gap, k_ia[v]) for v in k_v]
        e_sts = [calc_en_step(ia, i_bf, gap, dist, t_ms, k_en[v], 0.5) for ia, v in zip(ia_sts, k_v)]
        energia = interpolar(v_oc, *e_sts) / 4.184
        st.metric("Energia Calculada", f"{energia:.2f} cal/cm²")
        st.warning(f"Vestimenta: {definir_vestimenta(energia)}")

# --- ABA CURTO-CIRCUITO ---
with aba_curto:
    st.header("⚡ Dimensionamento de CCM e Curto-Circuito")
    with st.expander("Dados da Subestação", expanded=True):
        c1, c2, c3 = st.columns(3)
        pot_t = c1.number_input("Trafo (kVA)", value=225.0)
        tens_t = c2.number_input("Tensão (V)", value=380.0)
        z_t = c3.number_input("Z% do Trafo", value=5.0)
    
    st.subheader("Cadastro de Motores")
    with st.container(border=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        m_tag = col1.text_input("Nome/Tag")
        m_cv = col2.selectbox("CV", [1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50])
        m_qtd = col3.number_input("Qtd", 1)
        if st.button("➕ Adicionar Motor"):
            novo = pd.DataFrame([{'Equipamento': m_tag, 'Motor (CV)': m_cv, 'Quantidade': m_qtd, 'CCM Destino': 1}])
            st.session_state.df_motores = pd.concat([st.session_state.df_motores, novo], ignore_index=True)
            st.rerun()

    if not st.session_state.df_motores.empty:
        st.data_editor(st.session_state.df_motores, use_container_width=True)
        if st.button("🚀 Calcular Icc"):
            icc_base = tens_t / (1.732 * ((z_t/100)*((tens_t**2)/(pot_t*1000))))
            icc_ka = round((icc_base * 0.85) / 1000, 3)
            st.session_state.res_cc_final = icc_ka
            st.success(f"Corrente de Curto Calculada: {icc_ka} kA")
            
            if st.button("💾 ENVIAR VALOR PARA ARCO ELÉTRICO"):
                st.session_state['corrente_transf'] = st.session_state.res_cc_final
                st.success("Valor transferido!")

# --- ABA CAPACITORES ---
with aba_cap:
    st.header("🔋 Banco de Capacitores")
    c1, c2 = st.columns(2)
    p_ativa = c1.number_input("Potência Ativa (kW)", value=100.0)
    v_rede = c1.selectbox("Tensão da Rede",, index=1)
    fp_a = c2.number_input("FP Atual", 0.5, 0.99, 0.80)
    fp_o = c2.number_input("FP Objetivo", 0.92, 1.0, 0.95)
    
    if st.button("Calcular Banco"):
        res = calcular_cap(p_ativa, fp_a, fp_o, v_rede)
        st.write(f"Potência Reativa: **{res['kvar']} kVAr**")
        st.write(f"Cabo de Cobre sugerido: **{res['bitola']} mm²**")

# --- ABA HISTÓRICO ---
with aba_hist:
    st.header("📜 Histórico de Registros")
    if st.button("🔄 Sincronizar com Banco de Dados"):
        try:
            h_cc = supabase.table("calculos_curto").select("*").execute()
            h_ar = supabase.table("arc_flash_history").select("*").execute()
            
            st.subheader("Curto-Circuito")
            st.dataframe(pd.DataFrame(h_cc.data), use_container_width=True)
            
            st.subheader("Arco Elétrico")
            st.dataframe(pd.DataFrame(h_ar.data), use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao carregar histórico: {e}")
