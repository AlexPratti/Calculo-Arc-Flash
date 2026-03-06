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

# --- 1. CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="NBR 17227 - Relatório Técnico", layout="wide")

# Dados de Conexão Supabase
URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co" 
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe" 

if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(URL_SUPABASE, KEY_SUPABASE)
supabase = st.session_state.supabase

# --- 2. FUNÇÕES TÉCNICAS (NBR 17227:2025) ---
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

# --- 3. BARRA LATERAL (Hiperlinks Visíveis Sempre) ---
with st.sidebar:
    st.title("Outros Cálculos")
    st.link_button("Corrente de Curto-Circuito", "https://short-circuit-calc-e5u5dmgap2uqfdtbkc3d4e.streamlit.app", use_container_width=True)
    st.link_button("Banco de Capacitores", "https://c-lculobancocapacitores-tne9epqsrh64gtwaakzyax.streamlit.app", use_container_width=True)

# --- 4. SISTEMA DE LOGIN ---
if 'auth' not in st.session_state: 
    st.session_state['auth'] = None 

if st.session_state['auth'] is None: 
    st.title("ༀ༁༂ Acesso ao Sistema NBR 17227") 
    t1, t2 = st.tabs(["Entrar", "Solicitar Acesso"]) 
    
    with t1:
        u = st.text_input("E-mail") 
        p = st.text_input("Senha", type="password") 
        if st.button("Acessar", use_container_width=True): 
            if u == "admin" and p == "101049app": 
                st.session_state['auth'] = {"role": "admin", "user": "Administrador"} 
                st.rerun() 
            else: 
                try: 
                    res = supabase.table("usuarios").select("*").eq("email", u).eq("senha", p).execute() 
                    if res.data and res.data[0]['status'] == 'ativo': 
                        st.session_state['auth'] = {"role": "user", "user": u} 
                        st.rerun() 
                    else: 
                        st.error("Acesso negado ou pendente.") 
                except: 
                    st.error("Erro na conexão com banco de dados.")
    with t2:
        st.subheader("Solicitar Novo Acesso")
        u_novo = st.text_input("E-mail para Cadastro", key="new_u")
        p_novo = st.text_input("Senha para Cadastro", type="password", key="new_p")
        
        if st.button("Enviar Solicitação", use_container_width=True):
            if u_novo and p_novo:
                try:
                    # Insere o novo usuário com status 'pendente' no Supabase
                    supabase.table("usuarios").insert({
                        "email": u_novo, 
                        "senha": p_novo, 
                        "status": "pendente"
                    }).execute()
                    st.success("✅ Solicitação enviada! Aguarde a aprovação do administrador.")
                except Exception as e:
                    st.error(f"Erro ao solicitar: {e}")
            else:
                st.warning("Preencha todos os campos.")
else:
    # --- ÁREA LOGADA (TUDO DAQUI PARA BAIXO SÓ APARECE APÓS LOGIN) ---
    
    # Adicionando botão Sair na Sidebar
    with st.sidebar:
        st.divider()
        st.write(f"Conectado como: **{st.session_state['auth']['user']}**")
        if st.button("🚪 Sair do Sistema", use_container_width=True):
            st.session_state['auth'] = None
            st.rerun()

    # --- 5. BASE DE DADOS ---
    equip_data = {
        "CCM 15 kV": {"gap": 152.0, "dist": 914.4, "dims": {"914,4 x 914,4 x 914,4": [914.4, 914.4, 914.4, ""]}},
        "Conjunto de manobra 15 kV": {"gap": 152.0, "dist": 914.4, "dims": {"1143 x 762 x 762": [1143.0, 762.0, 762.0, ""]}},
        "CCM 5 kV": {"gap": 104.0, "dist": 914.4, "dims": {"660,4 x 660,4 x 660,4": [660.4, 660.4, 660.4, ""]}},
        "Conjunto de manobra 5 kV": {"gap": 104.0, "dist": 914.4, "dims": {"914,4 x 914,4 x 914,4": [914.4, 914.4, 914.4, ""], "1143 x 762 x 762": [1143.0, 762.0, 762.0, ""]}},
        "CCM e painel raso de BT": {"gap": 25.0, "dist": 457.2, "dims": {"355,6 x 304,8 x ≤ 203,2": [355.6, 304.8, 203.2, "≤"]}},
        "CCM e painel típico de BT": {"gap": 25.0, "dist": 457.2, "dims": {"355,6 x 304,8 x > 203,2": [355.6, 304.8, 203.2, ">"]}},
        "Conjunto de manobra BT": {"gap": 32.0, "dist": 609.6, "dims": {"508 x 508 x 508": [508.0, 508.0, 508.0, ""]}},
        "Caixa de junção de cabos": {"gap": 13.0, "dist": 457.2, "dims": {"355,6 x 304,8 x ≤ 203,2": [355.6, 304.8, 203.2, "≤"], "355,6 x 304,8 x > 203,2": [355.6, 304.8, 203.2, ">"]}}
    }

    tab1, tab2, tab3 = st.tabs(["Equipamento/Dimensões", "Cálculos e Resultados", "Relatório Final"])

    with tab1:
        st.subheader("Configuração do Equipamento")
        equip_sel = st.selectbox("Selecione o Equipamento:", list(equip_data.keys()))
        info = equip_data[equip_sel]
        sel_dim = st.selectbox("Selecione o Invólucro:", list(info["dims"].keys()))
        v_a, v_l, v_p, v_s = info["dims"][sel_dim]
        
        c1, c2, c3, c4 = st.columns(4)
        alt, larg = c1.number_input("Altura [A] (mm)", value=float(v_a)), c2.number_input("Largura [L] (mm)", value=float(v_l))
        sinal_op = ["", "≤", ">"]
        sinal_f = c3.selectbox("Sinal P", sinal_op, index=sinal_op.index(v_s) if v_s in sinal_op else 0)
        prof = c4.number_input("Profundidade [P] (mm)", value=float(v_p))
        gap_f, dist_f = st.number_input("GAP (mm)", value=float(info["gap"])), st.number_input("Distância Trabalho (mm)", value=float(info["dist"]))

    with tab2:
        st.subheader("Análise de Arco Elétrico")
        col1, col2, col3 = st.columns(3)
        v_oc = col1.number_input("Tensão Voc (kV)", 0.208, 15.0, 13.8)
        i_bf = col2.number_input("Corrente Ibf (kA)", 0.5, 106.0, 4.85)
        t_arc = col3.number_input("Tempo T (ms)", 10.0, 5000.0, 488.0)

        if st.button("Executar Estudo"):
            k_v = [0.6, 2.7, 14.3]
            k_ia = {0.6: [-0.04287, 1.035, -0.083, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092], 
                    2.7: [0.0065, 1.001, -0.024, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729], 
                    14.3: [0.005795, 1.015, -0.011, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729]}
            k_en = {0.6: [0.753364, 0.566, 1.752636, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092, 0, -1.598, 0.957], 
                    2.7: [2.40021, 0.165, 0.354202, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.569, 0.9778], 
                    14.3: [3.825917, 0.11, -0.999749, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.568, 0.99]}
            
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
            v_norma = definir_vestimenta(e_trab_cal)
            v_seguranca = "CAT 2" if (1.2 < e_trab_cal <= 4) else v_norma
            
            st.session_state['res'] = {"I": i_arc, "D": dla, "E_cal": e_trab_cal, "E_joule": e_trab_cal*4.184, "V_norma": v_norma, "V_seguranca": v_seguranca, "Sens": sens_list, "Equip": equip_sel, "Gap": gap_f, "Dist": dist_f}
            
            st.divider()
            st.subheader("Resultados do Estudo")
            # Métricas Principais
            st.metric("Corrente de Arco (Iarc)", f"{i_arc:.3f} kA")
            st.metric("Fronteira de Arco (DLA)", f"{dla:.1f} mm")
            
            st.write("") # Espaço extra
            
            # --- ENERGIAS EM DESTAQUE TOTAL ---
            # Título e valor em negrito e tamanho grande
            st.markdown(f"### **Energia Incidente: {e_trab_cal*4.184:.2f} J/cm²**")
            st.markdown(f"### **Energia Incidente: {e_trab_cal:.4f} cal/cm²**")

            st.write("") # Espaço extra

            st.write("#### Tabela de Sensibilidade")
            st.table(pd.DataFrame(sens_list, columns=["Distância (mm)", "Energia (cal/cm²)", "Vestimenta"]))

            # --- CAIXAS DE VESTIMENTA COM TEXTOS E TÍTULOS MAIORES ---
            st.markdown(f"""
                <div style="background-color: #15324d; padding: 25px; border-radius: 12px; border-left: 8px solid #2196f3; margin-bottom: 15px;">
                    <p style="color: white; margin: 0; font-size: 20px; font-weight: 500;">Vestimenta (Conforme Cálculo):</p>
                    <p style="color: #2196f3; margin: 0; font-size: 42px; font-weight: 900; letter-spacing: 2px;">{v_norma}</p>
                </div>
            
                <div style="background-color: #1b3d2f; padding: 25px; border-radius: 12px; border-left: 8px solid #4caf50;">
                    <p style="color: white; margin: 0; font-size: 20px; font-weight: 500;">Vestimenta (Princípio de Segurança Normativo):</p>
                    <p style="color: #4caf50; margin: 0; font-size: 42px; font-weight: 900; letter-spacing: 2px;">{v_seguranca}</p>
                </div>
            """, unsafe_allow_html=True)

            
            # st.table(pd.DataFrame(sens_list, columns=["Distância (mm)", "Energia (cal/cm²)", "Vestimenta"]))
            # st.info(f"**Vestimenta (Cálculo):** {v_norma}")
            # st.success(f"**Vestimenta (Segurança):** {v_seguranca}")

            

    with tab3:
        if 'res' in st.session_state:
            r = st.session_state['res']
            c1, c2, c3, c4 = st.columns(4)
            cliente = c1.text_input("Cliente:", "Empresa Exemplo S.A.")
            local_eq = c2.text_input("Local:", "Subestação Principal")
            uf_c = c3.text_input("UF CREA:", "ES")
            num_c = c4.text_input("Número CREA:", "")

            def gerar_pdf_profissional():
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2.5*cm, leftMargin=2.5*cm, topMargin=2.5*cm, bottomMargin=2.5*cm)
                styles = getSampleStyleSheet()
                style_just = ParagraphStyle(name='J', parent=styles['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=16.5)
                style_h2 = ParagraphStyle(name='H2', parent=styles['Heading2'], fontSize=13, leading=18, spaceBefore=15, spaceAfter=10)
                style_list = ParagraphStyle(name='L', parent=styles['Normal'], fontSize=11, leading=14, leftIndent=20)

                class CustomCanvas(canvas.Canvas):
                    def showPage(self):
                        if self._pageNumber >= 3:
                            self.setFont("Helvetica", 10)
                            self.drawRightString(19*cm, 1.5*cm, f"{self._pageNumber}")
                        canvas.Canvas.showPage(self)

                elements = []
                # CAPA
                elements.append(Spacer(1, 6*cm))
                elements.append(Paragraph("<b>RELATÓRIO TÉCNICO DE CÁLCULO DE ENERGIA INCIDENTE</b>", ParagraphStyle(name='CT', parent=styles['Title'], fontSize=22, alignment=TA_CENTER)))
                elements.append(Spacer(1, 2*cm))
                elements.append(Paragraph(f"CLIENTE: {cliente.upper()}<br/>LOCAL: {local_eq.upper()}<br/>EQUIPAMENTO: {r['Equip'].upper()}", ParagraphStyle(name='CS', parent=styles['Normal'], fontSize=13, alignment=TA_CENTER, leading=22)))
                elements.append(Spacer(1, 10*cm))
                elements.append(Paragraph(f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y')}", ParagraphStyle(name='CD', parent=styles['Normal'], fontSize=11, alignment=TA_CENTER)))
                elements.append(PageBreak())

                # 1. MEMORIAL
                elements.append(Paragraph("<b>1. MEMORIAL DE CÁLCULO (NBR 17227:2025)</b>", style_h2))
                texto_memorial = "A metodologia aplicada segue rigorosamente a norma <b>NBR 17227:2025</b> para painéis em espaços confinados..."
                elements.append(Paragraph(texto_memorial, style_just))

                # 2. ANÁLISE
                elements.append(Paragraph("<b>2. ANÁLISE DO RESULTADO E PARÂMETROS</b>", style_h2))
                elements.append(Paragraph(f"• Corrente de Arco: <b>{r['I']:.3f} kA</b><br/>• Energia Incidente: <b>{r['E_cal']:.4f} cal/cm²</b><br/>• DLA: <b>{r['D']:.1f} mm</b>", style_just))

                # 3. RECOMENDAÇÃO
                elements.append(Paragraph("<b>3. RECOMENDAÇÃO TÉCNICA</b>", style_h2))
                elements.append(Paragraph(f"Utilização obrigatória da vestimenta <b>{r['V_seguranca']}</b>.", style_just))

                # 4. EPIs
                elements.append(Paragraph("<b>4. EPIs COMPLEMENTARES</b>", style_h2))
                epi_items = ["Protetor Facial", "Balaclava Ignífuga", "Luvas Isolantes", "Calçado de Segurança"]
                for item in epi_items:
                    elements.append(Paragraph(f"• {item}", style_list))

                # 5. TABELA FINAL
                elements.append(Paragraph("<b>5. TABELA DE DISTÂNCIA X ENERGIA</b>", style_h2))
                t_sens = Table([["Distância (mm)", "Energia (cal/cm²)", "Vestimenta"]] + r['Sens'], colWidths=[5*cm]*3)
                t_sens.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey), ('GRID',(0,0),(-1,-1),0.5,colors.grey)]))
                elements.append(t_sens)

                # ASSINATURA
                elements.append(Spacer(1, 2*cm))
                elements.append(Paragraph(f"________________________________<br/><b>Engenheiro Eletricista - CREA {uf_c}/{num_c}</b>", ParagraphStyle(name='Sig', parent=styles['Normal'], alignment=TA_CENTER)))

                doc.build(elements, canvasmaker=CustomCanvas); return buffer.getvalue()

            st.download_button("📩 Baixar Relatório Profissional (PDF)", gerar_pdf_profissional(), f"Relatorio_Arco_{cliente}.pdf")
