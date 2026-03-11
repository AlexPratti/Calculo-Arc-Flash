import streamlit as st
import numpy as np
import io
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.pdfgen import canvas

# --- 1. CONFIGURAÇÃO DE PÁGINA (WIDE LAYOUT) ---
st.set_page_config(page_title="Gestão de Energia Incidente", layout="wide", initial_sidebar_state="expanded")

# --- 2. CONEXÃO ÚNICA COM SUPABASE ---
URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co" 
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe" 

if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(URL_SUPABASE, KEY_SUPABASE)

supabase = st.session_state.supabase

# --- 3. BUSCA DE DADOS E BARRA LATERAL ---
icc_sugerida = 0.0
v_sugerida = 380.0

with st.sidebar:
    st.header("📥 Importar Curto-Circuito")
    try:
        res_db = supabase.table("calculos_curto").select("*").order("created_at", desc=True).limit(10).execute()
        lista_db = res_db.data
        if lista_db:
            opcoes = {f"{c['tag_painel']} ({c['icc_ka']} kA)": c for c in lista_db}
            selecao = st.selectbox("Selecione um CCM calculado:", ["-- Entrada Manual --"] + list(opcoes.keys()), key="select_import_ccm_final")
            if selecao != "-- Entrada Manual --":
                icc_sugerida = float(opcoes[selecao]['icc_ka'])
                v_sugerida = float(opcoes[selecao]['v_sec'])
                st.success(f"✅ Dados de {selecao} carregados!")
    except Exception as e:
        st.error(f"Erro ao conectar ao banco: {e}")

# --- 4. FUNÇÕES TÉCNICAS (NBR 17227:2025) ---
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
    return (12.552 / 50.0) * t * (10**exp)

def calc_dla_step(ia, ibf, g, t, k, cf):
    k1, k2, k3, k4, k5, k6, k7, k8, k9, k10, k11, k12, k13 = k
    poli_den = (k4*ibf**7 + k5*ibf**6 + k6*ibf**5 + k7*ibf**4 + k8*ibf**3 + k9*ibf**2 + k10*ibf)
    termo_ia = (k3 * ia) / poli_den if poli_den != 0 else 0
    log_fixo = (k1 + k2*np.log10(g) + termo_ia + k11*np.log10(ibf) + k13*np.log10(ia) + np.log10(1.0/cf))
    return 10**((np.log10(5.0 / ((12.552 / 50.0) * t)) - log_fixo) / k12)

def interpolar(v, f600, f2700, f14300):
    if v <= 0.6: return f600
    if v <= 2.7: return f600 + (f2700 - f600) * (v - 0.6) / 2.1
    return f2700 + (f14300 - f2700) * (v - 2.7) / 11.6

def definir_vestimenta(caloria):
    if caloria < 1.2: return "SEGURO"
    if caloria <= 4: return "CAT 1"
    if caloria <= 8: return "CAT 2"
    if caloria <= 25: return "CAT 3"
    return "CAT 4"

# --- 5. LOGIN ---
if 'auth' not in st.session_state: st.session_state['auth'] = None
if st.session_state['auth'] is None:
    st.title("🔐 Acesso ao Sistema NBR 17227")
    u, p = st.text_input("E-mail"), st.text_input("Senha", type="password")
    if st.button("Acessar"):
        if u == "admin" and p == "101049app":
            st.session_state['auth'] = {"role": "admin", "user": "Administrador"}
            st.rerun()
        else:
            try:
                res = supabase.table("usuarios").select("*").eq("email", u).eq("senha", p).execute()
                if res.data and res.data[0]['status'] == 'ativo':
                    st.session_state['auth'] = {"role": "user", "user": u}; st.rerun()
                else: st.error("Acesso negado.")
            except: st.error("Erro de conexão.")
    st.stop()

# --- 6. INTERFACE AMPLIADA ---
equip_data = {
    "CCM 15 kV": {"gap": 152.0, "dist": 914.4, "dims": {"914,4 x 914,4 x 914,4": [914.4, 914.4, 914.4, ""]}},
    "Conjunto de manobra 15 kV": {"gap": 152.0, "dist": 914.4, "dims": {"1143 x 762 x 762": [1143.0, 762.0, 762.0, ""]}},
    "CCM 5 kV": {"gap": 104.0, "dist": 914.4, "dims": {"660,4 x 660,4 x 660,4": [660.4, 660.4, 660.4, ""]}},
    "Conjunto de manobra 5 kV": {"gap": 104.0, "dist": 914.4, "dims": {"914,4 x 914,4 x 914,4": [914.4, 914.4, 914.4, ""], "1143 x 762 x 762": [1143.0, 762.0, 762.0, ""]}},
    "CCM e painel BT": {"gap": 25.0, "dist": 457.2, "dims": {"355,6 x 304,8 x > 203,2": [355.6, 304.8, 203.2, ">"]}},
    "Conjunto de manobra BT": {"gap": 32.0, "dist": 609.6, "dims": {"508 x 508 x 508": [508.0, 508.0, 508.0, ""]}}
}

tab1, tab2, tab3 = st.tabs(["Equipamento/Dimensões", "Cálculos e Resultados", "Relatório Final"])

with tab1:
    st.subheader("Configuração do Equipamento")
    equip_sel = st.selectbox("Selecione o Equipamento:", list(equip_data.keys()))
    info = equip_data[equip_sel]
    sel_dim = st.selectbox("Selecione o Invólucro:", list(info["dims"].keys()))
    v_a, v_l, v_p, v_s = info["dims"][sel_dim]
    
    # Layout em colunas expandidas
    c1, c2, c3, c4 = st.columns(4)
    alt, larg = c1.number_input("Altura [A] (mm)", value=float(v_a)), c2.number_input("Largura [L] (mm)", value=float(v_l))
    sinal_op = ["", "≤", ">"]
    sinal_f = c3.selectbox("Sinal P", sinal_op, index=sinal_op.index(v_s) if v_s in sinal_op else 0)
    prof = c4.number_input("Profundidade [P] (mm)", value=float(v_p))
    
    ce1, ce2 = st.columns(2)
    gap_f = ce1.number_input("GAP (mm)", value=float(info["gap"]))
    dist_f = ce2.number_input("Distância Trabalho (mm)", value=float(info["dist"]))

with tab2:
    st.subheader("Resultados e Sensibilidade")
    # Colunas mais largas para os inputs principais
    col1, col2, col3 = st.columns([1.2, 1.2, 1.2])
    v_oc = col1.number_input("Tensão Voc (kV)", 0.0, 15.0, value=v_sugerida / 1000)
    i_bf = col2.number_input("Corrente Ibf (kA)", 0.0, 106.0, value=icc_sugerida)
    t_arc = col3.number_input("Tempo T (ms)", 10.0, 5000.0, 488.0)

    if st.button("Calcular", use_container_width=True):
        k_v = [0.6, 2.7, 14.3]
        k_ia = {0.6: [-0.04287, 1.035, -0.083, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092], 2.7: [0.0065, 1.001, -0.024, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729], 14.3: [0.005795, 1.015, -0.011, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729]}
        k_en = {0.6: [0.753364, 0.566, 1.752636, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092, 0, -1.598, 0.957], 2.7: [2.40021, 0.165, 0.354202, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.569, 0.9778], 14.3: [3.825917, 0.11, -0.999749, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.568, 0.99]}
        
        ees = (alt/25.4 + larg/25.4) / 2.0
        cf = -0.0003*ees**2 + 0.03441*ees + 0.4325
        ia_sts = [calc_ia_step(i_bf, gap_f, k_ia[v]) for v in k_v]
        i_arc = interpolar(v_oc, *ia_sts)
        dla_sts = [calc_dla_step(ia, i_bf, gap_f, t_arc, k_en[v], cf) for ia, v in zip(ia_sts, k_v)]
        dla = interpolar(v_oc, *dla_sts)

        sens_list = []
        for d in np.linspace(dist_f, dla, 5):
            e_sts_temp = [calc_en_step(ia, i_bf, gap_f, d, t_arc, k_en[v], cf) for ia, v in zip(ia_sts, k_v)]
            e_v = interpolar(v_oc, *e_sts_temp) / 4.184
            sens_list.append([str(round(d, 1)), str(round(e_v, 4)), definir_vestimenta(e_v)])
        
        e_trab_cal = float(sens_list[0][1])
        st.session_state['res'] = {"I": i_arc, "D": dla, "E_cal": e_trab_cal, "E_joule": e_trab_cal*4.184, "V_norma": definir_vestimenta(e_trab_cal), "V_seguranca": "CAT 2" if (1.2 < e_trab_cal <= 4) else definir_vestimenta(e_trab_cal), "Sens": sens_list, "Equip": equip_sel, "Gap": gap_f, "Dist": dist_f}
        
        st.divider()
        r1, r2 = st.columns(2)
        r1.metric("Iarc Final", f"{i_arc:.3f} kA")
        r2.metric("Fronteira (DLA)", f"{dla:.1f} mm")
        
        st.write("#### Tabela de Sensibilidade")
        st.table(pd.DataFrame(sens_list, columns=["Distância (mm)", "Energia (cal/cm²)", "Vestimenta"]))
        st.metric("Energia Incidente", f"{e_trab_cal:.4f} cal/cm²")
        st.success(f"💡 Recomendação: {st.session_state['res']['V_seguranca']}")

with tab3:
    if 'res' in st.session_state:
        r = st.session_state['res']
        c1, c2, c3, c4 = st.columns(4)
        cliente, local_eq, uf_c, num_c = c1.text_input("Cliente:"), c2.text_input("Local:"), c3.text_input("UF:"), c4.text_input("Número CREA:")

        def gerar_pdf():
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            elements = [Paragraph("Relatório Técnico", getSampleStyleSheet()['Title']), Spacer(1, 2*cm)]
            elements.append(Paragraph(f"Iarc: {r['I']:.3f} kA", getSampleStyleSheet()['Normal']))
            elements.append(Paragraph(f"Energia: {r['E_cal']:.4f} cal/cm²", getSampleStyleSheet()['Normal']))
            doc.build(elements); return buffer.getvalue()

        st.download_button("📩 Baixar PDF", gerar_pdf(), f"Laudo_{cliente}.pdf", use_container_width=True)
