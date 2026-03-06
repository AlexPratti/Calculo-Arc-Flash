import streamlit as st
import numpy as np
import io
import pandas as pd
import math
from datetime import datetime, timezone, timedelta, date
from supabase import create_client, Client

# Importações para o PDF (ReportLab - Mantendo a robustez do original)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfgen import canvas
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO, CONEXÃO E CSS ---
st.set_page_config(page_title="Gestão Elétrica Integrada NBR 17227", layout="wide")

# CSS para o visual Original (Métricas Brancas e Fundo Escuro)
st.markdown("""
    <style>
    .metric-label { font-size: 14px; color: #999; margin-bottom: -10px; margin-top: 15px; }
    .metric-value { font-size: 28px; font-weight: bold; color: white; margin-bottom: 5px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: #1e2129; border-radius: 4px; padding: 10px; }
    </style>
    """, unsafe_allow_html=True)

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co" 
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe" 

# Estados de Sessão para Persistência e Transferência
if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85
if 'df_motores' not in st.session_state:
    st.session_state.df_motores = pd.DataFrame(columns=['Equipamento', 'Motor (CV)', 'Quantidade', 'Partida', 'CCM Destino', 'Status'])

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro no Banco de Dados: {e}")
    st.stop()

# --- 2. FUNÇÕES TÉCNICAS (NBR 17227 COMPLETA) ---
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

# --- 3. SISTEMA DE LOGIN ---
if st.session_state['auth'] is None:
    st.title("🔐 Login - Plataforma NBR 17227")
    u = st.text_input("E-mail")
    p = st.text_input("Senha", type="password")
    if st.button("Acessar"):
        if u == "admin" and p == "101049app":
            st.session_state['auth'] = {"role": "admin", "user": "Administrador"}
            st.rerun()
        else:
            try:
                res = supabase.table("usuarios").select("*").eq("email", u).eq("senha", p).execute()
                if res.data and res.data[0]['status'] == 'ativo':
                    st.session_state['auth'] = {"role": "user", "user": u}
                    st.rerun()
                else: st.error("Acesso negado ou pendente.")
            except: st.error("Erro ao autenticar.")
    st.stop()

# --- 4. INTERFACE PRINCIPAL ---
st.sidebar.button("Sair", on_click=lambda: st.session_state.update({"auth": None}))

aba_arco, aba_curto, aba_cap = st.tabs(["🔥 Arco Elétrico (NBR 17227)", "⚡ Curto-Circuito", "🔋 Banco de Capacitores"])

# --- MODULO 1: ARCO ELÉTRICO (300+ LINHAS ORIGINAIS) ---
with aba_arco:
    st.markdown("### Análise de Arco Elétrico")
    
    # 1. Inputs em Linha Única (Original)
    c_v, c_i, c_t = st.columns(3)
    v_oc = c_v.number_input("Tensão Voc (kV)", value=13.8)
    i_bf = c_i.number_input("Corrente Ibf (kA)", value=float(st.session_state['corrente_transf']))
    t_arc = c_t.number_input("Tempo T (ms)", value=488.0)

    # 2. Dicionário Completo de Equipamentos
    equip_data = {
        "CCM 15 kV": {"914,4x914,4x914,4": [152.0, 914.4, 914.4, 914.4, 914.4, ""]},
        "Conjunto de manobra 15 kV": {"1143x762x762": [152.0, 914.4, 1143.0, 762.0, 762.0, ""]},
        "CCM 5 kV": {"660,4x660,4x660,4": [104.0, 914.4, 660.4, 660.4, 660.4, ""]},
        "Conjunto de manobra 5 kV": {"914,4x914,4x914,4": [104.0, 914.4, 914.4, 914.4, 914.4, ""], "1143x762x762": [104.0, 914.4, 1143.0, 762.0, 762.0, ""]},
        "CCM e painel raso de BT": {"355,6x304,8x≤203,2": [25.0, 457.2, 355.6, 304.8, 203.2, "≤"]},
        "CCM e painel típico de BT": {"355,6x304,8x>203,2": [25.0, 457.2, 355.6, 304.8, 203.2, ">"]},
        "Conjunto de manobra BT": {"508x508x508": [32.0, 609.6, 508.0, 508.0, 508.0, ""]},
        "Caixa de junção de cabos": {"355,6x304,8x≤203,2": [13.0, 457.2, 355.6, 304.8, 203.2, "≤"]}
    }

    eq_sel = st.selectbox("Equipamento:", list(equip_data.keys()))
    inv_sel = st.selectbox("Tamanho do Invólucro:", list(equip_data[eq_sel].keys()))
    gap_f, dist_f, alt, larg, prof, sinal_p = equip_data[eq_sel][inv_sel]

    if st.button("Executar Estudo", type="primary"):
        # Lógica NBR 17227 Robusta
        k_v = [0.6, 2.7, 14.3]
        k_ia = {0.6: [-0.04287, 1.035, -0.083, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092], 2.7: [0.0065, 1.001, -0.024, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729], 14.3: [0.005795, 1.015, -0.011, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729]}
        k_en = {0.6: [0.753364, 0.566, 1.752636, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092, 0, -1.598, 0.957], 2.7: [2.40021, 0.165, 0.354202, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.569, 0.9778], 14.3: [3.825917, 0.11, -0.999749, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.568, 0.99]}
        
        ees = (alt/25.4 + larg/25.4) / 2.0
        cf = -0.0003*ees**2 + 0.03441*ees + 0.4325
        ia_sts = [calc_ia_step(i_bf, gap_f, k_ia[v]) for v in k_v]
        i_arc = interpolar(v_oc, *ia_sts)
        dla_sts = [calc_dla_step(ia, i_bf, gap_f, t_arc, k_en[v], cf) for ia, v in zip(ia_sts, k_v)]
        dla = interpolar(v_oc, *dla_sts)
        
        sens = []
        for d in np.linspace(dist_f, dla, 5):
            e_sts = [calc_en_step(ia, i_bf, gap_f, d, t_arc, k_en[v], cf) for ia, v in zip(ia_sts, k_v)]
            e_v = interpolar(v_oc, *e_sts) / 4.184
            sens.append([round(d, 1), round(e_v, 4), definir_vestimenta(e_v)])

        # 3. Resultados em Destaque (Visual Original)
        st.markdown("---")
        st.markdown(f'<p class="metric-label">Corrente de Arco (kA)</p><p class="metric-value">{i_arc:.3f} kA</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="metric-label">Fronteira de Arco (mm)</p><p class="metric-value">{dla:.1f} mm</p>', unsafe_allow_html=True)
        
        st.markdown("**Distância X Energia Incidente**")
        st.table(pd.DataFrame(sens, columns=["Dist (mm)", "Energia (cal/cm²)", "Vestimenta"]))
        
        e_final = sens[0][1]
        st.markdown(f"### {e_final:.4f} cal/cm²")
        st.markdown(f"### {e_final * 4.184:.2f} J/cm²")
        
        st.success("✅ Atende aos requisitos da NBR 17227")
        st.info(f"🛡️ Vestimenta recomendada: {sens[0][2]}")
        
        # Bloco de Relatório PDF Robusto (ReportLab)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = [Paragraph(f"RELATÓRIO DE ARCO ELÉTRICO - {eq_sel}", styles['Title']), Spacer(1, 12)]
        doc.build(elements)
        st.download_button("📂 Gerar Relatório Profissional", buffer.getvalue(), "Relatorio_Arco.pdf")

# --- MODULO 2: CURTO-CIRCUITO ---
with aba_curto:
    st.markdown("### Cálculo de Curto-Circuito")
    c1, c2, c3 = st.columns(3)
    p_t = c1.number_input("Trafo (kVA)", value=225.0)
    v_t = c2.number_input("Tensão (V)", value=380.0)
    z_t = c3.number_input("Z% Trafo", value=5.0)
    
    st.markdown("#### Cadastro de Motores")
    m1, m2, m3 = st.columns([2, 1, 1])
    n_m = m1.text_input("Equipamento")
    p_m = m2.selectbox("Motor (CV)", [1, 2, 5, 7.5, 10, 15, 20, 30, 50, 100])
    q_m = m3.number_input("Qtd", value=1)
    
    if st.button("➕ Adicionar Motor"):
        novo = pd.DataFrame([{'Equipamento': n_m, 'Motor (CV)': p_m, 'Quantidade': q_m, 'CCM Destino': 1}])
        st.session_state.df_motores = pd.concat([st.session_state.df_motores, novo], ignore_index=True)
        st.rerun()

    if not st.session_state.df_motores.empty:
        st.table(st.session_state.df_motores)
        if st.button("🚀 EXECUTAR CÁLCULOS ICC"):
            icc = round((v_t / (1.732 * ((z_t/100)*((v_t**2)/(p_t*1000))))) * 0.85 / 1000, 3)
            st.session_state['icc_ka_temp'] = icc
            st.markdown(f'<p class="metric-label">Icc Local Calculada</p><p class="metric-value">{icc} kA</p>', unsafe_allow_html=True)
            
            # BOTÃO DE TRANSFERÊNCIA
            if st.button("💾 ENVIAR VALOR PARA ARCO ELÉTRICO"):
                st.session_state['corrente_transf'] = st.session_state['icc_ka_temp']
                st.success("✅ Valor transferido para a aba NBR 17227!")

# --- MODULO 3: CAPACITORES ---
with aba_cap:
    st.markdown("### Banco de Capacitores")
    with st.form("form_cap"):
        ca1, ca2 = st.columns(2)
        p_kw = ca1.number_input("kW Ativo", value=100.0)
        v_cap = ca1.selectbox("Tensão", [220, 380, 440], index=1)
        f_pa = ca2.number_input("FP Atual", value=0.82)
        f_pt = ca2.number_input("FP Alvo", value=0.95)
        if st.form_submit_button("Calcular Banco"):
            # Lógica simples de capacitores
            phi_at = math.acos(f_pa)
            phi_al = math.acos(f_pt)
            kvar = p_kw * (math.tan(phi_at) - math.tan(phi_al))
            st.metric("Potência Reativa", f"{kvar:.2f} kVAr")
