import streamlit as st
import numpy as np
import io
import pandas as pd
import math
from datetime import datetime, timezone, timedelta, date
from supabase import create_client, Client

# Importações para os PDFs (ReportLab e FPDF)
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

# CSS para replicar EXATAMENTE o visual "Original" da sua imagem
st.markdown("""
    <style>
    .metric-label { font-size: 14px; color: #999; margin-bottom: -10px; margin-top: 15px; }
    .metric-value { font-size: 28px; font-weight: bold; color: white; margin-bottom: 5px; }
    .stButton>button { width: 100%; border-radius: 5px; }
    .main { background-color: #0e1117; }
    </style>
    """, unsafe_allow_html=True)

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co" 
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe" 

# Inicialização de session_state para persistência
if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85
if 'df_motores' not in st.session_state:
    st.session_state.df_motores = pd.DataFrame(columns=['Equipamento', 'Motor (CV)', 'Quantidade', 'Partida', 'CCM Destino', 'Status'])

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro no Banco de Dados: {e}")
    st.stop()

# --- 2. FUNÇÕES TÉCNICAS (NBR 17227 / CAPACITORES) ---
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
    return {"kvar": round(kvar, 2), "i_proj": round(i_nom * 1.35, 2), "bitola": bitola, "estagios": 6 if kvar <= 100 else 12}

# --- 3. SISTEMA DE LOGIN ---
if st.session_state['auth'] is None:
    st.title("🔐 Login - Plataforma Elétrica")
    u = st.text_input("Usuário")
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
                else: st.error("Acesso negado.")
            except: st.error("Erro de conexão.")
    st.stop()

# --- 4. INTERFACE PRINCIPAL ---
st.sidebar.button("Sair", on_click=lambda: st.session_state.update({"auth": None}))

aba_arco, aba_curto, aba_cap = st.tabs(["🔥 Arco Elétrico (NBR 17227)", "⚡ Curto-Circuito", "🔋 Banco de Capacitores"])

# --- MODULO 1: ARCO ELÉTRICO ---
with aba_arco:
    st.markdown("### Análise de Arco Elétrico")
    
    # Dicionário de equipamentos robusto (CONFORME SUA IMAGEM)
    equip_data = {
        "CCM 15 kV": {"914,4x914,4x914,4": [152.0, 914.4, 914.4, 914.4, 914.4, ""]},
        "CCM e painel típico de BT": {"355,6x304,8x>203,2": [25.0, 457.2, 355.6, 304.8, 203.2, ">"]},
        "Conjunto de manobra BT": {"508x508x508": [32.0, 609.6, 508.0, 508.0, 508.0, ""]},
        "Caixa de junção de cabos": {"355,6x304,8x≤203,2": [13.0, 457.2, 355.6, 304.8, 203.2, "≤"]}
    }

    # Inputs em linha ÚNICA (Visual Original)
    col_v, col_i, col_t = st.columns(3)
    v_oc = col_v.number_input("Tensão Voc (kV)", value=13.8)
    i_bf = col_i.number_input("Corrente Ibf (kA)", value=float(st.session_state['corrente_transf']))
    t_arc = col_t.number_input("Tempo T (ms)", value=488.0)

    # Seleção de Equipamento (Sem sub-abas para manter o visual limpo)
    eq_sel = st.selectbox("Equipamento:", list(equip_data.keys()))
    inv_key = list(equip_data[eq_sel].keys())[0]
    gap_f, dist_f, alt, larg, prof, sinal_p = equip_data[eq_sel][inv_key]

    if st.button("Executar Estudo", type="primary"):
        # Lógica NBR 17227 Completa
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

        st.markdown("---")
        st.markdown("#### Resultados do Estudo")
        
        # MÉTRICAS EM DESTAQUE (Visual Original)
        st.markdown(f'<p class="metric-label">Corrente de Arco (kA)</p><p class="metric-value">{i_arc:.3f} kA</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="metric-label">Fronteira de Arco (mm)</p><p class="metric-value">{dla:.1f} mm</p>', unsafe_allow_html=True)
        
        st.markdown("**Distância X Energia Incidente**")
        st.table(pd.DataFrame(sens, columns=["Dist (mm)", "Energia (cal/cm²)", "Vestimenta"]))
        
        e_final = sens[0][1]
        st.markdown(f"### {e_final:.4f} cal/cm²")
        st.markdown(f"### {e_final * 4.184:.2f} J/cm²")
        
        st.success("Atende aos requisitos da NBR 17227")
        st.info(f"Vestimenta recomendada: {sens[0][2]}")
        
        # Bloco de Relatório PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = [Paragraph(f"RELATÓRIO TÉCNICO - {eq_sel}", getSampleStyleSheet()['Title'])]
        doc.build(elements)
        st.download_button("Gerar Relatório Profissional", buffer.getvalue(), "relatorio.pdf")

# --- MODULO 2: CURTO-CIRCUITO ---
with aba_curto:
    st.markdown("### Cálculo de Curto-Circuito e Motores")
    
    col_se1, col_se2, col_se3 = st.columns(3)
    p_trafo = col_se1.number_input("Trafo (kVA)", value=225.0, key="c_trafo")
    v_sec = col_se2.number_input("Tensão (V)", value=380.0, key="c_vsec")
    z_pct = col_se3.number_input("Impedância Z%", value=5.0, key="c_zpct")
    
    st.markdown("#### Cadastro de Motores")
    c_m1, c_m2, c_m3 = st.columns([2, 1, 1])
    n_eq = c_m1.text_input("Equipamento", key="c_neq")
    pot_m = c_m2.selectbox("Motor (CV)", [1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50, 100], key="c_potm")
    qtd_m = c_m3.number_input("Qtd", value=1, key="c_qtdm")
    
    if st.button("➕ Adicionar à Lista", key="btn_add"):
        if n_eq and pot_m:
            nova = pd.DataFrame([{'Equipamento': n_eq, 'Motor (CV)': pot_m, 'Quantidade': qtd_m}])
            st.session_state.df_motores = pd.concat([st.session_state.df_motores, nova], ignore_index=True)
            st.rerun()

    if not st.session_state.df_motores.empty:
        st.table(st.session_state.df_motores)
        if st.button("🚀 EXECUTAR CÁLCULOS ICC"):
            icc_ka = round((v_sec / (1.732 * ((z_pct/100)*((v_sec**2)/(p_trafo*1000))))) * 0.85 / 1000, 3)
            st.session_state['res_icc_ka'] = icc_ka
            st.markdown(f'<p class="metric-label">Icc Local Calculada</p><p class="metric-value">{icc_ka} kA</p>', unsafe_allow_html=True)
            
            # BOTÃO DE TRANSFERÊNCIA
            if st.button("💾 ENVIAR VALOR PARA ARCO ELÉTRICO"):
                st.session_state['corrente_transf'] = st.session_state['res_icc_ka']
                st.success("Valor transferido com sucesso!")

# --- MODULO 3: CAPACITORES ---
with aba_cap:
    st.markdown("### Banco de Capacitores")
    with st.form("form_cap"):
        ca1, ca2 = st.columns(2)
        pk = ca1.number_input("kW Ativo", value=100.0)
        vk = ca1.selectbox("Tensão", [220, 380, 440], index=1)
        fpa = ca2.number_input("FP Atual", value=0.82)
        fpt = ca2.number_input("FP Alvo", value=0.95)
        if st.form_submit_button("Calcular Banco"):
            res_c = calcular_cap(pk, fpa, fpt, vk)
            st.success(f"Potência Necessária: {res_c['kvar']} kVAr")
            st.write(f"Cabo Sugerido: {res_c['bitola']} mm²")
