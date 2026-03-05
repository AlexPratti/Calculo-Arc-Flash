import streamlit as st
import numpy as np
import io
import pandas as pd
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

# Importações para o PDF (ReportLab)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfgen import canvas

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Gestão de Arco Elétrico NBR 17227", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co" 
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe" 

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro no Banco de Dados: {e}")
    st.stop()

# --- 2. FUNÇÕES TÉCNICAS (NBR 17227) ---
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

# --- 3. SISTEMA DE LOGIN E SOLICITAÇÃO ---
if 'auth' not in st.session_state:
    st.session_state['auth'] = None

if st.session_state['auth'] is None:
    st.title("🔐 Acesso ao Sistema NBR 17227")
    t1, t2 = st.tabs(["Entrar", "Solicitar Acesso"])
    
    with t1:
        u = st.text_input("Usuário (E-mail)")
        p = st.text_input("Senha", type="password")
        if st.button("Acessar"):
            if u == "admin" and p == "101049app":
                st.session_state['auth'] = {"role": "admin", "user": "Administrador"}
                st.rerun()
            else:
                try:
                    res = supabase.table("usuarios").select("*").eq("email", u).eq("senha", p).execute()
                    if res.data:
                        user_found = res.data[0]
                        if user_found['status'] == 'ativo':
                            st.session_state['auth'] = {"role": "user", "user": u}
                            st.rerun()
                        else:
                            st.warning("Seu acesso está pendente de aprovação.")
                    else:
                        st.error("Credenciais incorretas.")
                except:
                    st.error("Erro de conexão.")

    with t2:
        ne = st.text_input("Seu E-mail para cadastro", key="reg_email")
        np_ = st.text_input("Crie uma Senha", type="password", key="reg_pass")
        if st.button("Enviar Solicitação"):
            try:
                supabase.table("usuarios").insert({"email": ne, "senha": np_, "status": "pendente"}).execute()
                st.success("Solicitação enviada com sucesso!")
            except:
                st.error("E-mail já cadastrado.")
    st.stop()

# --- 4. INTERFACE PRINCIPAL ---
st.sidebar.write(f"Conectado: **{st.session_state['auth']['user']}**")
if st.sidebar.button("Sair"):
    st.session_state['auth'] = None
    st.rerun()

# --- 5. PAINEL ADMIN ---
if st.session_state['auth']['role'] == "admin":
    with st.expander("⚙️ Gerenciar Usuários"):
        res = supabase.table("usuarios").select("*").execute()
        for user in res.data:
            c1, c2 = st.columns([3, 1])
            c1.write(f"{user['email']} [{user['status']}]")
            if user['status'] == 'pendente' and c2.button("Aprovar", key=user['email']):
                supabase.table("usuarios").update({"status": "ativo"}).eq("email", user['email']).execute()
                st.rerun()

# --- 6. CALCULADORA ---
equip_data = {
    "CCM 15 kV": {"gap": 152.0, "dist": 914.4, "dims": {"914,4 x 914,4 x 914,4": [914.4, 914.4, 914.4, ""]}},
    "CCM e painel típico de BT": {"gap": 25.0, "dist": 457.2, "dims": {"355,6 x 304,8 x > 203,2": [355.6, 304.8, 203.2, ">"]}},
    "Conjunto de manobra BT": {"gap": 32.0, "dist": 609.6, "dims": {"508 x 508 x 508": [508.0, 508.0, 508.0, ""]}}
}

tab_eq, tab_calc, tab_pdf = st.tabs(["Equipamento", "Cálculos", "Relatório"])

with tab_eq:
    eq_sel = st.selectbox("Equipamento:", list(equip_data.keys()))
    info = equip_data[eq_sel]
    sel_dim = st.selectbox("Invólucro:", list(info["dims"].keys()))
    v_a, v_l, v_p, v_s = info["dims"][sel_dim]
    
    alt = st.number_input("Altura (mm)", value=float(v_a))
    larg = st.number_input("Largura (mm)", value=float(v_l))
    gap_f = st.number_input("GAP (mm)", value=float(info["gap"]))
    dist_f = st.number_input("Distância (mm)", value=float(info["dist"]))

with tab_calc:
    v_oc = st.number_input("Tensão Voc (kV)", 0.2, 15.0, 13.8)
    i_bf = st.number_input("Corrente Ibf (kA)", 0.5, 106.0, 4.85)
    t_arc = st.number_input("Tempo T (ms)", 10.0, 5000.0, 488.0)

    if st.button("Executar Estudo"):
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
        
        st.session_state['res'] = {"I": i_arc, "D": dla, "E": sens[0][1], "Sens": sens, "Eq": eq_sel}
        st.success(f"Energia: {sens[0][1]} cal/cm²")
        st.table(pd.DataFrame(sens, columns=["Dist (mm)", "Energia", "Vestimenta"]))

with tab_pdf:
    if 'res' in st.session_state:
        if st.button("Gerar Relatório Profissional"):
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            elements = []
            styles = getSampleStyleSheet()
            
            elements.append(Paragraph(f"RELATÓRIO TÉCNICO - {st.session_state['res']['Eq']}", styles['Title']))
            elements.append(Spacer(1, 1*cm))
            elements.append(Paragraph(f"Corrente de Arco: {st.session_state['res']['I']:.2f} kA", styles['Normal']))
            elements.append(Paragraph(f"Energia Incidente: {st.session_state['res']['E']} cal/cm²", styles['Normal']))
            
            doc.build(elements)
            st.download_button("Baixar PDF", buffer.getvalue(), "relatorio.pdf", "application/pdf")
