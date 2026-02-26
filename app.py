import streamlit as st
import numpy as np
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- FUNÇÕES CORE (NBR 17227) ---

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

def main():
    st.set_page_config(page_title="NBR 17227 Expert", layout="wide")
    st.title("⚡ Gestão de Risco de Arco Elétrico - NBR 17227:2025")

    equipamentos = {
        "CCM 15 kV": [152, 914.4, 914.4, 914.4, 914.4],
        "Conjunto de manobra 15 kV": [152, 914.4, 1143.0, 762.0, 762.0],
        "CCM e painel típico de BT": [25, 457.2, 355.6, 304.8, 203.3]
    }
    
    tab1, tab2, tab3 = st.tabs(["📏 Tabela 1", "🧪 Cálculos e Resultados", "📄 Relatório"])

    with tab1:
        escolha = st.selectbox("Selecione o Equipamento:", list(equipamentos.keys()))
        info = equipamentos[escolha]
        c = st.columns(5); tts = ["GAP", "D_trab", "Alt", "Larg", "Prof"]
        for i in range(5): c[i].metric(tts[i], f"{info[i]} mm")

    with tab2:
        with st.form("calc_form"):
            c1, c2, c3 = st.columns(3)
            v_oc = c1.number_input("Tensão Voc (kV)", value=13.80)
            i_bf = c1.number_input("Curto Ibf (kA)", value=4.852)
            gap = c2.number_input("Gap G (mm)", value=float(info[0]))
            dist = c2.number_input("Distância D (mm)", value=float(info[1]))
            tempo = c3.number_input("Tempo T (ms)", value=488.0)
            submit = st.form_submit_button("Calcular Resultados Finais")

        if submit:
            k_ia = {600: [-0.04287, 1.035, -0.083, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092],
                    2700: [0.0065, 1.001, -0.024, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729],
                    14300: [0.005795, 1.015, -0.011, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729]}
            k_en = {600: [0.753364, 0.566, 1.752636, 0, 0, -4.783e-9, 1.962e-6, -0.000229, 0.003141, 1.092, 0, -1.598, 0.957],
                    2700: [2.40021, 0.165, 0.354202, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.569, 0.9778],
                    14300: [3.825917, 0.11, -0.999749, -1.557e-12, 4.556e-10, -4.186e-8, 8.346e-7, 5.482e-5, -0.003191, 0.9729, 0, -1.568, 0.99]}
            
            ees = (info[2]/25.4 + info[3]/25.4) / 2.0; cf = -0.0003*ees**2 + 0.03441*ees + 0.4325
            
            # Intermediários
            ia_sts = [calc_ia_step(i_bf, gap, k_ia[v]) for v in [600, 2700, 14300]]
            en_sts = [calc_en_step(ia, i_bf, gap, dist, tempo, k_en[v], cf) for ia, v in zip(ia_sts, [600, 2700, 14300])]
            dl_sts = [calc_dla_step(ia, i_bf, gap, tempo, k_en[v], cf) for ia, v in zip(ia_sts, [600, 2700, 14300])]

            # Finais
            ia_f = interpolar(v_oc, *ia_sts); e_f = interpolar(v_oc, *en_sts)/4.184; dla_f = interpolar(v_oc, *dl_sts)
            var_cf = -0.0001*v_oc**2 + 0.0022*v_oc + 0.02; ia_min = ia_f * (1 - 0.5*var_cf)

            if e_f <= 1.2: cat = "Risco 0"; b_color = "green"
            elif e_f <= 8: cat = "Categoria 2 (8 cal)"; b_color = "orange"
            elif e_f <= 25: cat = "Categoria 3 (25 cal)"; b_color = "red"
            else: cat = "Categoria 4 (40 cal)"; b_color = "red"

            st.session_state['res'] = {"Ia": ia_f, "E": e_f, "DLA": dla_f, "IaMin": ia_min, "Cat": cat, "Voc": v_oc, "VarCf": var_cf}
            
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Ia Final (kA)", f"{ia_f:.5f}"); c2.metric("Ia Reduzida (kA)", f"{ia_min:.5f}")
            c3.metric("Energia (cal/cm²)", f"{e_f:.4f}"); c4.metric("Fronteira (mm)", f"{dla_f:.0f}")
            st.warning(f"🛡️ **Vestimenta Sugerida:** {cat}")

    with tab3:
        if 'res' in st.session_state:
            def export_pdf():
                buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); r = st.session_state['res']
                c.drawString(100, 800, "LAUDO TÉCNICO DE ARCO ELÉTRICO"); c.drawString(100, 780, f"Tensão: {r['Voc']} kV")
                c.drawString(100, 760, f"Ia: {r['Ia']:.5f} kA | Ia_min: {r['IaMin']:.5f} kA")
                c.drawString(100, 740, f"Energia Incidente: {r['E']:.4f} cal/cm2")
                c.drawString(100, 720, f"Fronteira de Arco (DLA): {r['DLA']:.0f} mm")
                c.drawString(100, 700, f"Vestimenta: {r['Cat']}"); c.save(); return buf.getvalue()
            st.download_button("📩 Baixar Laudo PDF", export_pdf(), "laudo.pdf", "application/pdf")
