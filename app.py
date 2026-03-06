import streamlit as st
import pandas as pd
import numpy as np
import io
import math
from datetime import datetime, date, timezone, timedelta
from supabase import create_client, Client
from fpdf import FPDF

# --- IMPORTAÇÕES REPORTLAB (PARA ABA ARCO ELÉTRICO) ---
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Engenharia Elétrica Pro", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co"
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe"

# Inicialização de Estados Globais
if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85
if 'df_motores' not in st.session_state: 
    st.session_state.df_motores = pd.DataFrame(columns=['Selecionar', 'Equipamento', 'Motor (CV)', 'Quantidade', 'Partida', 'CCM Destino', 'Status'])

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro no Banco de Dados: {e}")
    st.stop()

# --- 2. FUNÇÕES TÉCNICAS ---

# Arco Elétrico (NBR 17227)
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

# Banco de Capacitores
def calcular_dimensionamento_cap(p_kw, fp_atual, fp_alvo, tensao):
    phi_atual = math.acos(min(fp_atual, 0.9999))
    phi_alvo = math.acos(min(fp_alvo, 0.9999))
    kvar_total = p_kw * (math.tan(phi_atual) - math.tan(phi_alvo))
    kvar_total = max(0.0, float(kvar_total))
    corrente_nominal = (kvar_total * 1000) / (math.sqrt(3) * tensao) if kvar_total > 0 else 0
    corrente_projeto = corrente_nominal * 1.35
    tabela_cabos = [(1.5, 15.5), (2.5, 21), (4, 28), (6, 36), (10, 50), (16, 68), (25, 89), (35, 110), (50, 134), (70, 171), (95, 207), (120, 239)]
    bitola_sugerida = 1.5
    for b, amp in tabela_cabos:
        if amp >= corrente_projeto:
            bitola_sugerida = b
            break
    return {"kvar_total": round(kvar_total, 2), "i_nom": round(corrente_nominal, 2), "i_proj": round(corrente_projeto, 2), "bitola": bitola_sugerida, "estagios": 6 if kvar_total <= 100 else 12, "pot_estagio": round(kvar_total / 5, 2) if kvar_total <= 100 else round(kvar_total / 11, 2)}

class RelatorioPDFCap(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'RELATORIO TECNICO - BANCO DE CAPACITORES', 0, 1, 'C')
        self.ln(5)

# --- 3. SISTEMA DE LOGIN COM TRAVA DE 1 ANO ---
if st.session_state['auth'] is None:
    st.title("🔐 Login - Plataforma de Engenharia")
    u = st.text_input("Usuário (E-mail)")
    p = st.text_input("Senha", type="password")
    if st.button("Acessar"):
        try:
            res = supabase.table("usuarios").select("*").eq("email", u).eq("senha", p).execute()
            if res.data:
                user = res.data[0]
                # Validação de Tempo de Acesso (created_at da tabela usuarios)
                data_criacao = datetime.fromisoformat(user['created_at'].replace('Z', '+00:00'))
                if (datetime.now(timezone.utc) - data_criacao) > timedelta(days=365):
                    st.error("❌ Acesso expirado (Limite de 1 ano atingido).")
                elif user['status'] == 'ativo':
                    st.session_state['auth'] = {"role": user.get('role', 'user'), "user": u}
                    st.rerun()
                else:
                    st.warning("⏳ Aguarde aprovação do administrador.")
            else: st.error("Usuário ou senha incorretos.")
        except Exception as e: st.error(f"Erro: {e}")
    st.stop()

# --- 4. INTERFACE PRINCIPAL ---
st.sidebar.title("Menu")
st.sidebar.write(f"Usuário: **{st.session_state['auth']['user']}**")
if st.sidebar.button("Sair"):
    st.session_state['auth'] = None
    st.rerun()

aba_arco, aba_curto, aba_cap, aba_hist = st.tabs(["🔥 Arco Elétrico", "⚡ Curto-Circuito", "🔋 Capacitores", "📜 Histórico"])

# --- ABA: ARCO ELÉTRICO ---
with aba_arco:
    equip_data = {
        "CCM e painel típico de BT": {"gap": 25.0, "dist": 457.2, "dims": {"355,6 x 304,8 x > 203,2": [355.6, 304.8, 203.2, ""]}},
        "Conjunto de manobra BT": {"gap": 32.0, "dist": 609.6, "dims": {"508 x 508 x 508": [508.0, 508.0, 508.0, ""]}}
    }
    col_e, col_c = st.columns(2)
    with col_e:
        eq_sel = st.selectbox("Equipamento:", list(equip_data.keys()))
        gap_f = st.number_input("GAP (mm)", value=float(equip_data[eq_sel]["gap"]))
        dist_f = st.number_input("Distância de Trabalho (mm)", value=float(equip_data[eq_sel]["dist"]))
    with col_c:
        v_oc = st.number_input("Tensão Voc (kV)", 0.2, 1.0, 0.38)
        # RECEBE VALOR DA ABA DE CURTO-CIRCUITO
        i_bf = st.number_input("Corrente de Curto Ibf (kA)", 0.5, 100.0, value=float(st.session_state['corrente_transf']))
        t_arc = st.number_input("Tempo de Atuação (ms)", value=100.0)

    if st.button("Calcular Energia Incidente"):
        k_v = [0.6, 2.7, 14.3]
        k_ia = {0.6: [-0.04287, 1.035, -0.083, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092], 2.7: [0.0065, 1.001, -0.024, 0,0,0,0,0, -0.003191, 0.9729], 14.3: [0.005795, 1.015, -0.011, 0,0,0,0,0, -0.003191, 0.9729]}
        k_en = {0.6: [0.753364, 0.566, 1.752636, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092, 0, -1.598, 0.957], 2.7: [2.40021, 0.165, 0.354202, 0,0,0,0,0, -0.003191, 0.9729, 0, -1.569, 0.9778], 14.3: [3.825917, 0.11, -0.999749, 0,0,0,0,0, -0.003191, 0.9729, 0, -1.568, 0.99]}
        cf = 0.5 # Simplificado para exemplo
        ia_sts = [calc_ia_step(i_bf, gap_f, k_ia[v]) for v in k_v]
        dla_sts = [calc_dla_step(ia, i_bf, gap_f, t_arc, k_en[v], cf) for ia, v in zip(ia_sts, k_v)]
        dla = interpolar(v_oc, *dla_sts)
        e_sts = [calc_en_step(ia, i_bf, gap_f, dist_f, t_arc, k_en[v], cf) for ia, v in zip(ia_sts, k_v)]
        energia = interpolar(v_oc, *e_sts) / 4.184
        st.metric("Energia Incidente", f"{energia:.2f} cal/cm²")
        st.info(f"Vestimenta Recomendada: {definir_vestimenta(energia)}")

# --- ABA: CURTO-CIRCUITO ---
with aba_curto:
    st.header("⚡ Dimensionamento de CCM e Curto-Circuito")
    AMPACIDADE = [24, 32, 41, 57, 76, 101, 125, 151, 192, 232, 269, 309, 353, 415, 473]
    
    with st.expander("Configurações da Subestação", expanded=True):
        c1, c2, c3 = st.columns(3)
        p_trafo = c1.number_input("Trafo (kVA)", value=225.0)
        v_sec = c2.number_input("Tensão Secundária (V)", value=380.0)
        z_pct = c3.number_input("Z% Trafo", value=5.0)
        n_ccm = st.number_input("Qtd CCMs", min_value=1, value=1)
    
    st.subheader("Motores")
    with st.container(border=True):
        col1, col2, col3, col4 = st.columns([2,1,1,1])
        n_m = col1.text_input("Tag Motor")
        p_m = col2.selectbox("CV", [1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50])
        q_m = col3.number_input("Qtd", 1)
        d_m = col4.selectbox("Destino", list(range(1, n_ccm + 1)))
        if st.button("Adicionar Motor"):
            nova_linha = pd.DataFrame([{'Equipamento': n_m, 'Motor (CV)': p_m, 'Quantidade': q_m, 'CCM Destino': d_m}])
            st.session_state.df_motores = pd.concat([st.session_state.df_motores, nova_linha], ignore_index=True)
            st.rerun()

    if not st.session_state.df_motores.empty:
        st.data_editor(st.session_state.df_motores, use_container_width=True)
        if st.button("🚀 Calcular Curto-Circuito"):
            icc_qgbt = v_sec / (1.732 * ((z_pct/100)*((v_sec**2)/(p_trafo*1000))))
            res = []
            for i in range(1, n_ccm + 1):
                icc_local = round((icc_qgbt * 0.85)/1000, 4)
                res.append({"Painel": f"CCM {i}", "Icc Local (kA)": icc_local})
            st.session_state.res_cc = res
            st.table(pd.DataFrame(res))

    if 'res_cc' in st.session_state:
        p_sel = st.selectbox("Escolha o Painel para Transferir:", [r["Painel"] for r in st.session_state.res_cc])
        if st.button("💾 Enviar Corrente para Arco Elétrico"):
            valor = next(x["Icc Local (kA)"] for x in st.session_state.res_cc if x["Painel"] == p_sel)
            st.session_state['corrente_transf'] = valor
            st.success(f"Valor {valor} kA enviado para aba Arco Elétrico!")

# --- ABA: CAPACITORES ---
with aba_cap:
    st.header("🔋 Banco de Capacitores")
    with st.form("cap_form"):
        c1, c2 = st.columns(2)
        p_kw = c1.number_input("kW Ativo", value=100.0)
        v_cap = c1.selectbox("Voltagem", [220, 380, 440], index=1)
        fpa = c2.number_input("FP Atual", value=0.80)
        fpt = c2.number_input("FP Alvo", value=0.95)
        if st.form_submit_button("Calcular Banco"):
            res = calcular_dimensionamento_cap(p_kw, fpa, fpt, v_cap)
            st.metric("Potência Necessária", f"{res['kvar_total']} kVAr")
            st.write(f"Cabo Sugerido: {res['bitola']} mm²")

# --- ABA: HISTÓRICO ---
with aba_hist:
    st.header("📜 Histórico do Supabase")
    h_tab1, h_tab2 = st.tabs(["Curto-Circuito", "Arco Elétrico"])
    
    with h_tab1:
        if st.button("Carregar Dados de Curto"):
            dados = supabase.table("calculos_curto").select("*").execute()
            st.dataframe(pd.DataFrame(dados.data), use_container_width=True)
            
    with h_tab2:
        if st.button("Carregar Dados de Arco"):
            dados = supabase.table("arc_flash_history").select("*").execute()
            st.dataframe(pd.DataFrame(dados.data), use_container_width=True)
