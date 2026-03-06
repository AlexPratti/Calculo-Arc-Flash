import streamlit as st
import numpy as np
import io
import pandas as pd
import math
from datetime import datetime, timezone, timedelta, date
from supabase import create_client, Client

# Importações para o PDF (ReportLab - NBR 17227)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfgen import canvas
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Gestão Elétrica Integrada", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co" 
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe" 

# Inicialização de Estados (Memória Global)
if 'auth' not in st.session_state: st.session_state['auth'] = None
if 'corrente_transf' not in st.session_state: st.session_state['corrente_transf'] = 4.85
if 'df_motores' not in st.session_state:
    st.session_state.df_motores = pd.DataFrame(columns=['Selecionar', 'Equipamento', 'Motor (CV)', 'Quantidade', 'Partida', 'CCM Destino', 'Status'])

try:
    supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)
except Exception as e:
    st.error(f"Erro no Banco de Dados: {e}")
    st.stop()

# --- 2. FUNÇÕES TÉCNICAS (ARCO ELÉTRICO NBR 17227) ---
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

# --- 3. FUNÇÕES TÉCNICAS (CAPACITORES) ---
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

# --- 4. SISTEMA DE LOGIN ---
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
                        else: st.warning("Seu acesso está pendente de aprovação.")
                    else: st.error("Credenciais incorretas.")
                except: st.error("Erro de conexão.")
    with t2:
        ne = st.text_input("E-mail para cadastro", key="reg_email")
        np_ = st.text_input("Senha", type="password", key="reg_pass")
        if st.button("Enviar Solicitação"):
            try:
                supabase.table("usuarios").insert({"email": ne, "senha": np_, "status": "pendente"}).execute()
                st.success("Solicitação enviada!")
            except: st.error("E-mail já cadastrado.")
    st.stop()

# --- 5. INTERFACE PRINCIPAL ---
st.sidebar.write(f"Conectado: **{st.session_state['auth']['user']}**")
if st.sidebar.button("Sair"):
    st.session_state['auth'] = None
    st.rerun()

# Painel Admin
if st.session_state['auth']['role'] == "admin":
    with st.expander("⚙️ Gerenciar Usuários"):
        res = supabase.table("usuarios").select("*").execute()
        for user in res.data:
            c1, c2 = st.columns([3, 1])
            c1.write(f"{user['email']} [{user['status']}]")
            if user['status'] == 'pendente' and c2.button("Aprovar", key=user['email']):
                supabase.table("usuarios").update({"status": "ativo"}).eq("email", user['email']).execute()
                st.rerun()

# --- ABAS DO APP ---
aba_arco, aba_curto, aba_cap = st.tabs(["🔥 Arco Elétrico (NBR 17227)", "⚡ Curto-Circuito", "🔋 Banco de Capacitores"])

# --- MODULO 1: ARCO ELÉTRICO ---
with aba_arco:
    # DICIONÁRIO COMPLETO COM TODAS AS OPÇÕES E SINAIS P
    equip_data = {
        "CCM 15 kV": {"914,4 x 914,4 x 914,4": [152.0, 914.4, 914.4, 914.4, 914.4, ""]},
        "Conjunto de manobra 15 kV": {"1143 x 762 x 762": [152.0, 914.4, 1143.0, 762.0, 762.0, ""]},
        "CCM 5 kV": {"660,4 x 660,4 x 660,4": [104.0, 914.4, 660.4, 660.4, 660.4, ""]},
        "Conjunto de manobra 5 kV": {
            "914,4 x 914,4 x 914,4": [104.0, 914.4, 914.4, 914.4, 914.4, ""],
            "1143 x 762 x 762": [104.0, 914.4, 1143.0, 762.0, 762.0, ""]
        },
        "CCM e painel raso de BT": {"355,6 x 304,8 x ≤ 203,2": [25.0, 457.2, 355.6, 304.8, 203.2, "≤"]},
        "CCM e painel típico de BT": {"355,6 x 304,8 x > 203,2": [25.0, 457.2, 355.6, 304.8, 203.2, ">"]},
        "Conjunto de manobra BT": {"508 x 508 x 508": [32.0, 609.6, 508.0, 508.0, 508.0, ""]},
        "Caixa de junção de cabos": {
            "355,6 x 304,8 x ≤ 203,2": [13.0, 457.2, 355.6, 304.8, 203.2, "≤"],
            "355,6 x 304,8 x > 203,2": [13.0, 457.2, 355.6, 304.8, 203.2, ">"]
        }
    }

    t_eq, t_calc, t_pdf = st.tabs(["Configuração do Equipamento", "Cálculos e Resultados", "Gerar Relatório"])

    with t_eq:
        st.write("### Parâmetros Físicos")
        eq_sel = st.selectbox("Selecione o Equipamento:", list(equip_data.keys()))
        opcoes_inv = list(equip_data[eq_sel].keys())
        inv_sel = st.selectbox("Tamanho do Invólucro:", opcoes_inv)
        
        # Extração automática
        g_pad, d_pad, a_pad, l_pad, p_pad, s_pad = equip_data[eq_sel][inv_sel]
        
        c1, c2, c3 = st.columns(3)
        alt = c1.number_input("Altura (A) mm", value=a_pad)
        larg = c2.number_input("Largura (L) mm", value=l_pad)
        prof = c3.number_input("Profundidade (P) mm", value=p_pad)
        
        c4, c5, c6 = st.columns(3)
        gap_f = c4.number_input("GAP mm", value=g_pad)
        dist_f = c5.number_input("Distância mm", value=d_pad)
        sinal_p = c6.text_input("Sinal P", value=s_pad if s_pad else "N/A", disabled=True)

    with t_calc:
        st.write("### Variáveis Elétricas")
        v_oc = st.number_input("Tensão Voc (kV)", 0.2, 15.0, 13.8)
        # CONEXÃO: Recebe valor vindo do cálculo de curto-circuito (session_state)
        i_bf = st.number_input("Corrente Ibf (kA)", 0.5, 106.0, value=float(st.session_state['corrente_transf']))
        t_arc = st.number_input("Tempo T (ms)", 10.0, 5000.0, 488.0)

        if st.button("Executar Estudo de Arco"):
            # Lógica NBR 17227
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
            st.success(f"Energia Incidente: {sens[0][1]} cal/cm²")
            st.table(pd.DataFrame(sens, columns=["Dist (mm)", "Energia", "Vestimenta"]))

    with t_pdf:
        if 'res' in st.session_state:
            if st.button("Download Relatório PDF (NBR 17227)"):
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=A4)
                elements = []
                styles = getSampleStyleSheet()
                elements.append(Paragraph(f"RELATÓRIO TÉCNICO - {st.session_state['res']['Eq']}", styles['Title']))
                elements.append(Spacer(1, 1*cm))
                elements.append(Paragraph(f"Corrente de Arco: {st.session_state['res']['I']:.2f} kA", styles['Normal']))
                elements.append(Paragraph(f"Energia Incidente: {st.session_state['res']['E']} cal/cm²", styles['Normal']))
                doc.build(elements)
                st.download_button("Baixar Relatório PDF", buffer.getvalue(), f"Arco_{st.session_state['res']['Eq']}.pdf", "application/pdf")

# --- MODULO 2: CURTO-CIRCUITO ---
with aba_curto:
    st.header("⚡ Dimensionamento de Curto-Circuito e Cargas")
    CABOS_COMERCIAIS = [2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300]
    AMPACIDADE = [24, 32, 41, 57, 76, 101, 125, 151, 192, 232, 269, 309, 353, 415, 473]

    def sugerir_cabo(corrente, secao_queda):
        secao_final = max(secao_queda, 2.5)
        for i, cap in enumerate(AMPACIDADE):
            if cap >= corrente and CABOS_COMERCIAIS[i] >= secao_final: return CABOS_COMERCIAIS[i], cap
        return 300, 473

    with st.sidebar:
        st.header("🔌 Parâmetros da Subestação")
        p_trafo = st.number_input("Trafo (kVA)", value=225.0, key="c_trafo")
        v_sec = st.number_input("Tensão (V)", value=380.0, key="c_vsec")
        z_pct = st.number_input("Impedância Z%", value=5.0, key="c_zpct")
        dist_se = st.number_input("Dist. SE ao QGBT (m)", value=15.0, key="c_distse")

    n_ccm = st.number_input("Qtd CCMs", min_value=1, value=2, key="c_nccm")
    dist_ccms = {i+1: st.number_input(f"Dist. CCM {i+1} (m)", value=20.0, key=f"c_d_{i}") for i in range(int(n_ccm))}

    st.subheader("📋 Cadastro de Motores")
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1.5, 1])
        n_eq = c1.text_input("Equipamento", key="c_neq")
        pot_m = c2.selectbox("Motor (CV)", [0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50, 100], index=None, key="c_potm")
        qtd_m = c3.number_input("Qtd", min_value=1, value=1, key="c_qtdm")
        part_m = c4.selectbox("Partida", ["Direta", "Estrela-Triângulo", "Inversor", "Soft-Starter"], key="c_partm")
        dest_m = c5.selectbox("CCM", list(range(1, int(n_ccm) + 1)), key="c_destm")
        if st.button("➕ Adicionar à Lista"):
            if pot_m and n_eq:
                nova_m = pd.DataFrame([{'Equipamento': n_eq, 'Motor (CV)': float(pot_m), 'Quantidade': int(qtd_m), 'Partida': part_m, 'CCM Destino': int(dest_m)}])
                st.session_state.df_motores = pd.concat([st.session_state.df_motores, nova_m], ignore_index=True)
                st.rerun()

    if not st.session_state.df_motores.empty:
        st.session_state.df_motores = st.data_editor(st.session_state.df_motores, use_container_width=True)
        if st.button("🚀 EXECUTAR CÁLCULOS"):
            icc_qgbt = v_sec / (1.732 * ((z_pct/100)*((v_sec**2)/(p_trafo*1000))))
            res_c = []
            for i in range(1, int(n_ccm) + 1):
                m_ccm = st.session_state.df_motores[st.session_state.df_motores['CCM Destino'] == i]
                cv_ccm = (m_ccm['Motor (CV)'] * m_ccm['Quantidade']).sum()
                if cv_ccm == 0: continue
                in_ccm = (cv_ccm * 736) / (v_sec * 1.732 * 0.85 * 0.9)
                s_queda = (1.732 * dist_ccms[i] * in_ccm * 0.85) / (56 * (v_sec * 0.03))
                cabo, _ = sugerir_cabo(in_ccm, s_queda)
                res_c.append({"Painel": f"CCM {i}", "Icc Local (kA)": round((icc_qgbt * 0.85)/1000, 4)})
            st.session_state.res_curto = res_c

    if 'res_curto' in st.session_state:
        st.table(pd.DataFrame(st.session_state.res_curto))
        col_s, col_b = st.columns([3, 2])
        escolha = col_s.selectbox("Selecione Painel para Exportar:", [r["Painel"] for r in st.session_state.res_curto])
        if col_b.button("🚀 ENVIAR PARA ABA DE ARCO ELÉTRICO"):
            dados = next(item for item in st.session_state.res_curto if item["Painel"] == escolha)
            st.session_state['corrente_transf'] = dados["Icc Local (kA)"]
            st.success(f"Valor {dados['Icc Local (kA)']} kA enviado!")

# --- MODULO 3: CAPACITORES ---
with aba_cap:
    st.header("🔋 Banco de Capacitores")
    with st.form("f_cap"):
        ca, cb = st.columns(2)
        cliente_c = ca.text_input("Cliente", "EMPRESA TESTE")
        p_kw = ca.number_input("Potência Ativa (kW)", value=150.0)
        tens_c = ca.selectbox("Tensão (V)", [220, 380, 440], index=1)
        fp_at = cb.number_input("FP Atual", 0.50, 0.99, 0.82)
        fp_al = cb.number_input("FP Alvo", 0.92, 1.00, 0.95)
        btn_cap = st.form_submit_button("Calcular e Gerar PDF")

    if btn_cap:
        res_cap = calcular_dimensionamento_cap(p_kw, fp_at, fp_al, tens_c)
        st.metric("Total kVAr", f"{res_cap['kvar_total']} kVAr")
        pdf_c = RelatorioPDFCap()
        pdf_c.add_page()
        pdf_c.set_font("Arial", '', 10)
        pdf_c.cell(0, 10, f"CLIENTE: {cliente_c.upper()}", ln=True)
        pdf_c.cell(0, 10, f"REATIVO: {res_cap['kvar_total']} kVAr", ln=True)
        pdf_out = pdf_c.output(dest='S').encode('latin-1', errors='replace')
        st.download_button("Baixar PDF Capacitores", pdf_out, "relatorio_cap.pdf", "application/pdf")
