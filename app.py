import streamlit as st
import pandas as pd
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, value, LpStatus
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

st.set_page_config(page_title="Sistema Parkano - Control Total", layout="wide")

def enviar_correo(asunto, cuerpo_html, destinatario):
    remitente = "mezclasparkano@gmail.com"
    password = "shre kfdy flin hscs" 
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo_html, 'html'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return str(e)

st.title("⚒️ Generador de Blend y Balance Metalúrgico - Parkano")

st.sidebar.header("🎯 Parámetros del Blend")
t_min = st.sidebar.number_input("Tonelaje Mínimo (TMH)", value=980.0)
t_max = st.sidebar.number_input("Tonelaje Máximo (TMH)", value=1100.0)

st.sidebar.subheader("Leyes de Cabeza Objetivos")
zn_obj = st.sidebar.slider("Zinc (Zn %)", 0.0, 25.0, (11.0, 12.0))
pb_obj = st.sidebar.slider("Plomo (Pb %)", 0.0, 5.0, (0.8, 1.0))
ag_obj = st.sidebar.slider("Plata (Ag DM)", 0.0, 5.0, (1.1, 1.5))

st.sidebar.header("⚙️ Parámetros Planta")
h_perc = st.sidebar.number_input("Humedad (%)", value=5.0) / 100
rec_zn = st.sidebar.number_input("Rec. Zn (%)", value=95.0) / 100
rec_pb = st.sidebar.number_input("Rec. Pb (%)", value=85.0) / 100
rec_ag = st.sidebar.number_input("Rec. Ag (%)", value=90.0) / 100

st.sidebar.subheader("Concentrados")
ley_conc_zn = st.sidebar.number_input("Ley Zn en Conc. Zn (%)", value=50.0)
ag_min_zn = st.sidebar.number_input("Ag Mínima en Conc. Zn (DM)", value=2.5)
ley_conc_pb = st.sidebar.number_input("Ley Pb en Conc. Pb (%)", value=60.0)

sheet_url = st.text_input("Pega el link de Google Sheets aquí:", "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0")

if st.button("🚀 CALCULAR BLEND Y BALANCE"):
    try:
        base_url = sheet_url.split('/edit')[0]
        gid = sheet_url.split('gid=')[1] if 'gid=' in sheet_url else '0'
        csv_url = f"{base_url}/export?format=csv&gid={gid}"
        df = pd.read_csv(csv_url)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        c_lote = next((c for c in df.columns if "LOTE" in c), None)
        c_peso = next((c for c in df.columns if "PESO" in c), None)
        c_zn = next((c for c in df.columns if "ZN" in c or "ZINC" in c), None)
        c_pb = next((c for c in df.columns if "PB" in c or "PLOMO" in c), None)
        c_ag = next((c for c in df.columns if "AG" in c or "PLATA" in c), None)

        if not all([c_lote, c_peso, c_zn, c_pb, c_ag]):
            st.error("❌ No se encontraron las columnas en el Excel. Revisa que existan encabezados válidos.")
            st.stop()

        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df_clean = df[df[c_peso] > 0.1].copy()

        prob = LpProblem("Parkano", LpMinimize)
        idx = df_clean.index
        vars = LpVariable.dicts("L", idx, lowBound=0)
        total_w = lpSum([vars[i] for i in idx])
        
        prob += total_w
        prob += total_w >= t_min
        prob += total_w <= t_max
        for i in idx: prob += vars[i] <= df_clean.loc[i, c_peso]
        
        for rango, col in zip([zn_obj, pb_obj, ag_obj], [c_zn, c_pb, c_ag]):
            prob += lpSum([vars[i] * df_clean.loc[i, col] for i in idx]) >= rango[0] * total_w
            prob += lpSum([vars[i] * df_clean.loc[i, col] for i in idx]) <= rango[1] * total_w

        prob.solve()

        if LpStatus[prob.status] == 'Optimal':
            res = []
            for i in idx:
                val = value(vars[i])
                if val > 0.01:
                    res.append({"Lote": df_clean.loc[i, c_lote], "TMH": val, "Zn%": df_clean.loc[i, c_zn], "Pb%": df_clean.loc[i, c_pb], "Ag DM": df_clean.loc[i, c_ag]})
            rdf = pd.DataFrame(res)
            st.subheader("📋 1. Reporte de Mezcla (Blend Seleccionado)")
            st.dataframe(rdf.style.format({"TMH": "{:.2f}", "Zn%": "{:.2f}%", "Pb%": "{:.2f}%", "Ag DM": "{:.2f}"}))

            tmh_total = rdf['TMH'].sum()
            z_cab = (rdf['TMH'] * rdf['Zn%']).sum() / tmh_total
            p_cab = (rdf['TMH'] * rdf['Pb%']).sum() / tmh_total
            a_cab = (rdf['TMH'] * rdf['Ag DM']).sum() / tmh_total
            tms_total = tmh_total * (1 - h_perc)
            
            tms_c_zn = (tms_total * (z_cab/100) * rec_zn) / (ley_conc_zn/100)
            tms_c_pb = (tms_total * (p_cab/100) * rec_pb) / (ley_conc_pb/100)
            
            ag_en_zn_fino = tms_c_zn * ag_min_zn
            fino_ag_total = tms_total * a_cab * rec_ag
            ley_ag_pb = (fino_ag_total - ag_en_zn_fino) / tms_c_pb if tms_c_pb > 0 else 0

            st.subheader("📊 2. Balance Metalúrgico Proyectado")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("### Alimentación (Cabeza)")
                st.metric("Total TMH", f"{tmh_total:.2f}")
                st.metric("Total TMS (-5%)", f"{tms_total:.2f}")
                st.text(f"Leyes Cabeza:\n• Zn: {z_cab:.2f}%\n• Pb: {p_cab:.2f}%\n• Ag: {a_cab:.2f} DM")
            with c2:
                st.markdown("### Concentrado Zinc")
                st.metric("Masa Zn (TMS)", f"{tms_c_zn:.2f}")
                st.text(f"• Ley Zn: {ley_conc_zn:.2f}%\n• Ley Ag Asegurada: {ag_min_zn:.2f} DM")
            with c3:
                st.markdown("### Concentrado Plomo")
                st.metric("Masa Pb (TMS)", f"{tms_c_pb:.2f}")
                st.text(f"• Ley Pb: {ley_conc_pb:.2f}%\n• Ley Ag Remanente: {ley_ag_pb:.2f} DM")

            tabla_html = rdf.to_html(index=False, justify='center', border=1)
            cuerpo = f"""<html><body><h2>Reporte de Operación - Parkano</h2>{tabla_html}</body></html>"""
            estado = enviar_correo("Reporte de Blend y Balance Proyectado", cuerpo, "diego.bonilla@parkano.com.bo")
            if estado is True: st.success("✅ ¡Blend enviado!")
            else: st.warning(f"⚠️ Correo falló: {estado}")
        else: st.error("❌ Condición No Factible.")
    except Exception as e: st.error(f"Error: {e}")
