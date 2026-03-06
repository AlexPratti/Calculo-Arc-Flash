import math
from datetime import datetime, timezone, timedelta, date
from supabase import create_client, Client

# Importações para PDF (ReportLab e FPDF)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfgen import canvas
from fpdf import FPDF





import streamlit as st
import numpy as np
import io
import pandas as pd
import math
from datetime import datetime, timezone, timedelta, date
from supabase import create_client, Client
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, ListFlowable, ListItem
from reportlab.pdfgen import canvas

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="NBR 17227 - Relatório Técnico Profissional", layout="wide")

URL_SUPABASE = "https://lfgqxphittdatzknwkqw.supabase.co" 
KEY_SUPABASE = "sb_publishable_zLiarara0IVVcwQm6oR2IQ_Sb0YOWTe" 

if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(URL_SUPABASE, KEY_SUPABASE)
supabase = st.session_state.supabase


# --- FUNÇÕES TÉCNICAS (PARTE 1 - ARCO ELÉTRICO) ---
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

# --- FUNÇÕES TÉCNICAS (PARTE 3 - CAPACITORES) ---
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
        self.cell(0, 10, 'RELATORIO TECNICO DE CORRECAO DE FATOR DE POTENCIA', 0, 1, 'C')
        self.ln(5)


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

# --- 3. SISTEMA DE LOGIN --- 
if 'auth' not in st.session_state: st.session_state['auth'] = None 

if st.session_state['auth'] is None: 
    st.title("ༀ༁༂ Acesso ao Sistema NBR 17227") 
    
    # Criando as abas de login e solicitação
    t1, t2 = st.tabs(["Entrar", "Solicitar Acesso"]) 
    
    with t1:
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
                    else: 
                        st.error("Acesso negado ou pendente.") 
                except: 
                    st.error("Erro de conexão.") 
    
    with t2:
        ne = st.text_input("Seu E-mail para cadastro", key="reg_email") 
        np_ = st.text_input("Crie uma Senha", type="password", key="reg_pass") 
        if st.button("Enviar Solicitação"): 
            try: 
                supabase.table("usuarios").insert({"email": ne, "senha": np_, "status": "pendente"}).execute() 
                st.success("Solicitação enviada com sucesso!") 
            except Exception as e: 
                st.error(f"Erro ao enviar solicitação: {e}")

    st.stop() 


# --- 4. BASE DE DADOS ---
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
    v_oc, i_bf, t_arc = col1.number_input("Tensão Voc (kV)", 0.208, 15.0, 13.8), col2.number_input("Corrente Ibf (kA)", 0.5, 106.0, 4.85), col3.number_input("Tempo T (ms)", 10.0, 5000.0, 488.0)

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
        c_tab, _ = st.columns([1, 1.5])
        with c_tab:
            st.metric("Corrente de Arco (Iarc)", f"{i_arc:.3f} kA")
            st.metric("Fronteira de Arco (DLA)", f"{dla:.1f} mm")
            st.write("#### Distância X Energia Incidente")
            st.table(pd.DataFrame(sens_list, columns=["Distância (mm)", "Energia (cal/cm²)", "Vestimenta"]))
            st.metric("Energia Incidente", f"{e_trab_cal:.4f} cal/cm²")
            st.metric("Energia Incidente", f"{e_trab_cal*4.184:.2f} J/cm²")
            st.info(f"**Vestimenta (Conforme Cálculo):** {v_norma}"); st.success(f"**Vestimenta (Princípio de Segurança Normativo):** {v_seguranca}")

with tab3:
    if 'res' in st.session_state:
        r = st.session_state['res']
        c1, c2, c3, c4 = st.columns(4)
        cliente, local_eq = c1.text_input("Cliente:", "Empresa Exemplo S.A."), c2.text_input("Local:", "Subestação Principal")
        uf_c, num_c = c3.text_input("UF CREA:", "ES"), c4.text_input("Número CREA:", "")

        def gerar_pdf_profissional():
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2.5*cm, leftMargin=2.5*cm, topMargin=2.5*cm, bottomMargin=2.5*cm)
            styles = getSampleStyleSheet()
            style_just = ParagraphStyle(name='J', parent=styles['Normal'], alignment=TA_JUSTIFY, fontSize=11, leading=16.5)
            style_h2 = ParagraphStyle(name='H2', parent=styles['Heading2'], fontSize=13, leading=18, spaceBefore=15, spaceAfter=10)
            style_list = ParagraphStyle(name='L', parent=styles['Normal'], fontSize=11, leading=14, leftIndent=20)

            class CustomCanvas(canvas.Canvas):
                def __init__(self, *args, **kwargs):
                    canvas.Canvas.__init__(self, *args, **kwargs)
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

            # SUMÁRIO
            elements.append(Paragraph("<b>SUMÁRIO</b>", styles['Title']))
            elements.append(Spacer(1, 1.5*cm))
            toc_data = [["1. Memorial de Cálculo (NBR 17227:2025)", "03"], ["2. Análise do Resultado e Parâmetros", "03"], ["3. Recomendação e Justificativa Técnica", "03"], ["4. Equipamentos de Proteção (EPI) Complementares", "04"], ["5. Tabela de Distância X Energia Incidente", "04"], ["6. Disposições Finais e NR-10", "04"]]
            t_toc = Table(toc_data, colWidths=[13.5*cm, 1.5*cm])
            t_toc.setStyle(TableStyle([('ALIGN', (1,0), (1,-1), 'RIGHT'),('FONTNAME', (0,0), (-1,-1), 'Helvetica'),('FONTSIZE', (0,0), (-1,-1), 11),('BOTTOMPADDING', (0,0), (-1,-1), 10)]))
            elements.append(t_toc)
            elements.append(PageBreak())

            # 1. MEMORIAL DE CÁLCULO
            elements.append(Paragraph("<b>1. MEMORIAL DE CÁLCULO (NBR 17227:2025)</b>", style_h2))
            
            # AJUSTE SOLICITADO: REMOÇÃO DE LATEX E SÍMBOLO DO FATOR DE BORDA
            texto_memorial = (
                "A metodologia aplicada segue rigorosamente a norma <b>NBR 17227:2025</b> para painéis em espaços confinados. "
                "Este estudo técnico fundamenta-se em modelos de interpolação polinomial e determinação de Corrente de Arco (Iarc) "
                "via regressões validadas para as geometrias reais dos equipamentos. O cálculo da Energia Incidente (Ecal) considera "
                "o ajuste dinâmico do fator de borda, refletindo as dimensões volumétricas do invólucro para assegurar que a "
                "exposição residual do trabalhador permaneça abaixo do limiar crítico de queimadura de segundo grau (1,2 cal/cm²)."
            )
            elements.append(Paragraph(texto_memorial, style_just))

            # 2. ANÁLISE DO RESULTADO
            elements.append(Paragraph("<b>2. ANÁLISE DO RESULTADO E PARÂMETROS</b>", style_h2))
            elements.append(Paragraph(f"• Corrente de Arco: <b>{r['I']:.3f} kA</b><br/>• Energia Incidente: <b>{r['E_cal']:.4f} cal/cm²</b> ({r['E_joule']:.2f} J/cm²)<br/>• Fronteira de Arco (DLA): <b>{r['D']:.1f} mm</b><br/>• Gap: <b>{r['Gap']:.1f} mm</b><br/>• Distância de Trabalho: <b>{r['Dist']:.1f} mm</b>", style_just))

            # 3. RECOMENDAÇÃO E JUSTIFICATIVA
            elements.append(Paragraph("<b>3. RECOMENDAÇÃO E JUSTIFICATIVA TÉCNICA</b>", style_h2))
            elements.append(Paragraph(f"Pela classificação estrita da norma, a vestimenta resultante do cálculo nominal seria a <b>{r['V_norma']}</b>. Contudo, este laudo estabelece a utilização obrigatória da vestimenta <b>{r['V_seguranca']}</b>.", style_just))
            elements.append(Spacer(1, 0.3*cm))
            elements.append(Paragraph("<b>Justificativa:</b> Esta recomendação fundamenta-se na gestão estratégica de riscos e na aplicação do Princípio ALARA (*As Low As Reasonably Achievable*). Variações no tempo de atuação da proteção (decorrentes de envelhecimento mecânico de disjuntores) ou no posicionamento antropométrico do operador durante a execução do serviço podem elevar a energia incidente real acima dos limites da categoria nominal. Assim, adota-se um fator de segurança conservador para mitigar incertezas de campo, garantindo proteção efetiva contra o limiar de queimadura mesmo sob condições operacionais adversas.", style_just))

            # 4. EPIs COMPLEMENTARES
            elements.append(Paragraph("<b>4. EQUIPAMENTOS DE PROTEÇÃO (EPI) COMPLEMENTARES</b>", style_h2))
            epi_items = [
                "Protetor Facial contra Arco Elétrico com classificação ATPV adequada;",
                "Balaclava Ignífuga para proteção integral de cabeça e pescoço;",
                "Luvas Isolantes de Borracha acompanhadas de luvas de cobertura em couro;",
                "Calçado de Segurança sem componentes metálicos expostos;",
                "Proteção Ocular e Auditiva (Óculos de segurança e protetores auriculares)."
            ]
            for item in epi_items:
                elements.append(Paragraph(f"• {item}", style_list))
            elements.append(Spacer(1, 0.5*cm))

            # 5. TABELA E 6. DISPOSIÇÕES FINAIS (EM BLOCO ÚNICO)
            t_sens = Table([["Distância (mm)", "Energia (cal/cm²)", "Vestimenta"]] + r['Sens'], colWidths=[5*cm]*3)
            t_sens.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('ALIGN',(0,0),(-1,-1),'LEFT'),('GRID',(0,0),(-1,-1),0.5,colors.grey),('FONTSIZE',(0,0),(-1,-1), 9),('BOTTOMPADDING',(0,0),(-1,-1), 4)]))
            
            final_elements = [
                Paragraph("<b>5. TABELA DE DISTÂNCIA X ENERGIA INCIDENTE</b>", style_h2),
                t_sens,
                Spacer(1, 0.5*cm),
                Paragraph("<b>6. DISPOSIÇÕES FINAIS E NR-10</b>", style_h2),
                Paragraph("Este estudo atende integralmente às exigências da <b>NR-10</b>. A eficácia das medidas de proteção aqui descritas está condicionada ao uso de EPIs com Certificado de Aprovação (CA) válido e à manutenção periódica das proteções do sistema elétrico analisado.", style_just),
                Spacer(1, 2*cm),
                Paragraph(f"________________________________________________<br/><b>Engenheiro Eletricista - CREA {uf_c}/{num_c}</b>", ParagraphStyle(name='Sig', parent=styles['Normal'], alignment=TA_CENTER))
            ]
            elements.append(KeepTogether(final_elements))

            doc.build(elements, canvasmaker=CustomCanvas); return buffer.getvalue()

        st.download_button("📩 Baixar Relatório Profissional (PDF)", gerar_pdf_profissional(), f"Relatorio_Arco_{cliente}.pdf")

# --- PARTE 2: CURTO-CIRCUITO ---
with aba_p2:
    st.title("⚡ Short-Circuit-Calc Pro")
    CABOS_COMERCIAIS = [2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300]
    AMPACIDADE = [24, 32, 41, 57, 76, 101, 125, 151, 192, 232, 269, 309, 353, 415, 473]

    def sugerir_cabo(corrente, secao_queda):
        secao_final = max(secao_queda, 2.5)
        for i, cap in enumerate(AMPACIDADE):
            if cap >= corrente and CABOS_COMERCIAIS[i] >= secao_final: return CABOS_COMERCIAIS[i], cap
        return 300, 473

    with st.sidebar:
        st.header("🔌 Parâmetros da SE")
        p_trafo = st.number_input("Potência Trafo (kVA)", value=225.0, key="se_p")
        v_sec = st.number_input("Tensão (V)", value=380.0, key="se_v")
        z_pct = st.number_input("Impedância Z% (Trafo)", value=5.0, key="se_z")
        dist_se_qgbt = st.number_input("Distância SE ao QGBT (m)", value=15.0, key="se_d")

    n_ccm = st.number_input("Quantidade de CCMs", min_value=1, value=2, key="nccm_p2")
    dist_ccms = {i+1: st.number_input(f"Dist. CCM {i+1} (m)", value=20.0, key=f"d_p2_{i}") for i in range(int(n_ccm))}

    st.header("📋 Cadastro de Motores")
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1.5, 1])
        with c1: n_eq = st.text_input("Equipamento", key="neq_p2")
        with c2: pot_cv = st.selectbox("Motor (CV)", [0.5, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50, 100], index=None, key="pot_p2")
        with c3: q_m = st.number_input("Qtd", min_value=1, value=1, key="qtd_p2")
        with c4: part_m = st.selectbox("Partida", ["Direta", "Estrela-Triângulo", "Inversor", "Soft-Starter"], key="part_p2")
        with c5: dest_m = st.selectbox("CCM", list(range(1, int(n_ccm) + 1)), key="dest_p2")
        if st.button("➕ Adicionar à Lista", key="add_p2"):
            if pot_cv and n_eq:
                nova = pd.DataFrame([{'Selecionar': False, 'Equipamento': n_eq, 'Motor (CV)': float(pot_cv), 'Quantidade': int(q_m), 'Partida': part_m, 'CCM Destino': int(dest_m), 'Status': 'Novo'}])
                st.session_state.df_motores = pd.concat([st.session_state.df_motores, nova], ignore_index=True)
                st.rerun()

    if not st.session_state.df_motores.empty:
        st.header("🏭 Lista de Cargas")
        st.session_state.df_motores = st.data_editor(st.session_state.df_motores, use_container_width=True, key="editor_p2")
        if st.button("🚀 EXECUTAR DIMENSIONAMENTO COMPLETO"):
            icc_qgbt = v_sec / (1.732 * ((z_pct/100)*((v_sec**2)/(p_trafo*1000))))
            res_curto = []
            for i in range(1, int(n_ccm) + 1):
                m_ccm = st.session_state.df_motores[st.session_state.df_motores['CCM Destino'] == i]
                cv_tot = (m_ccm['Motor (CV)'] * m_ccm['Quantidade']).sum()
                if cv_tot == 0: continue
                in_c = (cv_tot * 736) / (v_sec * 1.732 * 0.85 * 0.9)
                s_q = (1.732 * dist_ccms[i] * in_c * 0.85) / (56 * (v_sec * 0.03))
                c_sug, _ = sugerir_cabo(in_c, s_q)
                res_curto.append({"Painel": f"CCM {i}", "Carga (CV)": f"{cv_tot:.1f}", "Cabo": f"{c_sug} mm²", "Icc Local (kA)": round((icc_qgbt * 0.85)/1000, 4)})
            st.session_state.res_ccm = res_curto

    if 'res_ccm' in st.session_state:
        st.table(pd.DataFrame(st.session_state.res_ccm))
        col_s, col_b = st.columns([3, 2])
        escolha = col_s.selectbox("Painel:", [r["Painel"] for r in st.session_state.res_ccm], key="sel_p2")
        if col_b.button("💾 Salvar no Supabase", key="save_p2"):
            dados = next(item for item in st.session_state.res_ccm if item["Painel"] == escolha)
            supabase.table("calculos_curto").insert({"tag_painel": dados["Painel"], "icc_ka": float(dados["Icc Local (kA)"]), "v_sec": float(v_sec)}).execute()
            st.success("Salvo!")

# --- PARTE 3: CAPACITORES ---
with aba_p3:
    st.title("⚡ Calculador de Banco de Capacitores")
    with st.form("form_p3"):
        col_a, col_b = st.columns(2)
        with col_a:
            cli = st.text_input("Cliente", "EMPRESA TESTE", key="cli_p3")
            p_kw = st.number_input("Ativa (kW)", value=150.0, key="pk_p3")
            v_c = st.selectbox("Tensão (V)", [220, 380, 440], index=1, key="v_p3")
        with col_b:
            fpa = st.number_input("FP Atual", value=0.82, key="fpa_p3")
            fpo = st.number_input("FP Alvo", value=0.95, key="fpo_p3")
        if st.form_submit_button("Calcular e Preparar Relatório"):
            res_c = calcular_dimensionamento_cap(p_kw, fpa, fpo, v_c)
            st.success("Calculado!")
            pdf = RelatorioPDFCap()
            pdf.add_page()
            pdf.set_font("Arial", '', 10)
            pdf.cell(0, 10, f"CLIENTE: {cli.upper()}", ln=True)
            pdf.cell(0, 10, f"REATIVO: {res_c['kvar_total']} kVAr", ln=True)
            out = pdf.output(dest='S').encode('latin-1', errors='replace')
            st.download_button("Baixar PDF Capacitores", out, "relatorio_cap.pdf")
