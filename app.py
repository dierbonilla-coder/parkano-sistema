import streamlit as st
import pandas as pd
from pulp import LpProblem, LpVariable, lpSum, LpMinimize, value, LpStatus

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Sistema Parkano v6", layout="wide")


# ─────────────────────────────────────────────
#  TÍTULO
# ─────────────────────────────────────────────
st.title("⚒️ Sistema de Optimización y Balance Metalúrgico — Parkano")

# ─────────────────────────────────────────────
#  BARRA LATERAL — PARÁMETROS EDITABLES
# ─────────────────────────────────────────────
st.sidebar.header("🎯 Parámetros del Blend")

st.sidebar.subheader("Tonelaje (TMH)")
t_min = st.sidebar.number_input("Tonelaje Mínimo (TMH)", value=980.0, step=10.0)
t_max = st.sidebar.number_input("Tonelaje Máximo (TMH)", value=1100.0, step=10.0)

st.sidebar.subheader("Leyes de Cabeza Objetivo")
zn_min = st.sidebar.number_input("Zn Mín (%)",  value=11.0, step=0.1)
zn_max = st.sidebar.number_input("Zn Máx (%)",  value=12.0, step=0.1)
pb_min = st.sidebar.number_input("Pb Mín (%)",  value=0.8,  step=0.05)
pb_max = st.sidebar.number_input("Pb Máx (%)",  value=1.0,  step=0.05)
ag_min = st.sidebar.number_input("Ag Mín (DM)", value=1.1,  step=0.05)
ag_max = st.sidebar.number_input("Ag Máx (DM)", value=1.5,  step=0.05)

st.sidebar.header("⚙️ Parámetros de Planta")
h_perc  = st.sidebar.number_input("Humedad (%)",  value=5.0,  step=0.5) / 100.0
rec_zn  = st.sidebar.number_input("Rec. Zn (%)",  value=95.0, step=1.0) / 100.0
rec_pb  = st.sidebar.number_input("Rec. Pb (%)",  value=85.0, step=1.0) / 100.0
rec_ag  = st.sidebar.number_input("Rec. Ag (%)",  value=90.0, step=1.0) / 100.0

st.sidebar.header("🔒 Parámetros de Concentrados")
ley_conc_zn   = st.sidebar.number_input("Ley Conc. Zn (%)",      value=50.0, step=1.0) / 100.0
ley_conc_pb   = st.sidebar.number_input("Ley Conc. Pb (%)",      value=60.0, step=1.0) / 100.0
ag_min_conc_zn = st.sidebar.number_input("Ag mín en Conc. Zn (DM)", value=2.5, step=0.1)

st.sidebar.header("🔧 Parámetros Operativos")
umbral_lote_grande = st.sidebar.number_input("Umbral lote grande (TMH)", value=100.0, step=10.0,
    help="Lotes ≤ este valor se toman completos (100%). Lotes mayores pueden tomarse parcialmente en toneladas enteras.")

# ─────────────────────────────────────────────
#  FUENTE DE DATOS
# ─────────────────────────────────────────────
sheet_url = st.text_input(
    "🔗 Link de Google Sheets (stock de mineral):",
    "https://docs.google.com/spreadsheets/d/1Pq6jsL26ne6BEvKLON3lr1AIWYyZksyRYVI7vuZ3QLE/edit#gid=0"
)

# ─────────────────────────────────────────────
#  BOTÓN PRINCIPAL
# ─────────────────────────────────────────────
if st.button("🚀 GENERAR BLEND Y BALANCE METALÚRGICO"):
    try:
        # ── 1. LECTURA DE DATOS ──────────────────────────────────────────
        # Extraer el ID del Sheets del URL
        import re
        sheet_id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
        
        if not sheet_id_match:
            st.error("❌ El link del Google Sheets no es válido. Asegúrate de usar un link que contenga '/d/'")
            st.stop()
        
        sheet_id = sheet_id_match.group(1)
        
        # Extraer el GID (ID de la hoja específica) si existe
        gid_match = re.search(r'[#&]gid=(\d+)', sheet_url)
        gid = gid_match.group(1) if gid_match else '0'
        
        # Construir la URL de exportación correctamente
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        
        try:
            df = pd.read_csv(csv_url)
        except Exception as e:
            st.error(f"❌ Error al leer el CSV: {e}")
            st.error("Intenta esto: Asegúrate de que el link sea compartible (public o con permisos de lectura)")
            st.stop()
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # Mapeo flexible de columnas
        c_lote = next((c for c in df.columns if "LOTE" in c or "ID" in c), None)
        c_peso = next((c for c in df.columns if "PESO" in c or "TMH" in c or "TON" in c), None)
        c_zn   = next((c for c in df.columns if c.startswith("ZN") or c == "LEY ZN" or c == "LEY_ZN"), None)
        c_pb   = next((c for c in df.columns if c.startswith("PB") or c == "LEY PB" or c == "LEY_PB"), None)
        c_ag   = next((c for c in df.columns if c.startswith("AG") or c == "LEY AG" or c == "LEY_AG"), None)

        missing = [n for n, c in [("LOTE", c_lote), ("PESO", c_peso), ("ZN", c_zn), ("PB", c_pb), ("AG", c_ag)] if c is None]
        if missing:
            st.error(f"No se encontraron las columnas: {missing}. Columnas detectadas: {list(df.columns)}")
            st.stop()

        for col in [c_peso, c_zn, c_pb, c_ag]:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df_clean = df[df[c_peso] > 0].copy().reset_index(drop=True)

        with st.expander("📂 Ver stock de mineral cargado"):
            st.dataframe(df_clean[[c_lote, c_peso, c_zn, c_pb, c_ag]].rename(columns={
                c_lote: "Lote", c_peso: "TMH", c_zn: "Zn %", c_pb: "Pb %", c_ag: "Ag DM"
            }), use_container_width=True)

        # ── 2. OPTIMIZADOR (PuLP) CON RESTRICCIÓN OPERATIVA ──────────────
        st.info("🔧 **Regla operativa activa:** Lotes ≤100 TMH se toman completos. Lotes >100 TMH pueden tomarse parcialmente en toneladas enteras.")
        
        prob = LpProblem("Blend_Parkano", LpMinimize)
        idx  = df_clean.index.tolist()
        
        # Crear variables según tamaño del lote:
        # - Lotes ≤ umbral: variable binaria (0 o 100% del lote)
        # - Lotes > umbral: variable entera continua (en toneladas enteras)
        vars_lote = {}
        vars_binary = {}
        lotes_pequenos = []
        lotes_grandes = []
        
        for i in idx:
            peso_lote = df_clean.loc[i, c_peso]
            if peso_lote <= umbral_lote_grande:
                # Lote pequeño: usar variable binaria (todo o nada)
                vars_binary[i] = LpVariable(f"usar_lote_{i}", cat='Binary')
                vars_lote[i] = peso_lote * vars_binary[i]
                lotes_pequenos.append(i)
            else:
                # Lote grande: variable entera (toneladas enteras)
                vars_lote[i] = LpVariable(f"tons_lote_{i}", lowBound=0, upBound=peso_lote, cat='Integer')
                lotes_grandes.append(i)

        total_w = lpSum([vars_lote[i] for i in idx])

        # Objetivo: maximizar Zn total (minimizar negativo)
        prob += -lpSum([vars_lote[i] * df_clean.loc[i, c_zn] for i in idx])

        # Restricciones de tonelaje
        prob += total_w >= t_min, "Tonelaje_Minimo"
        prob += total_w <= t_max, "Tonelaje_Maximo"

        # Restricciones de leyes
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_zn] for i in idx]) >= zn_min * total_w, "Zn_Min"
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_zn] for i in idx]) <= zn_max * total_w, "Zn_Max"
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_pb] for i in idx]) >= pb_min * total_w, "Pb_Min"
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_pb] for i in idx]) <= pb_max * total_w, "Pb_Max"
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_ag] for i in idx]) >= ag_min * total_w, "Ag_Min"
        prob += lpSum([vars_lote[i] * df_clean.loc[i, c_ag] for i in idx]) <= ag_max * total_w, "Ag_Max"

        prob.solve()
        status = LpStatus[prob.status]

        if status != 'Optimal':
            st.warning(
                f"⚠️ No se encontró una mezcla factible con los rangos actuales (Estado: {status}). "
                "Prueba ampliando los rangos de ley o de tonelaje."
            )
            st.stop()

        # ── 3. ARMADO DE RESULTADOS DEL BLEND ───────────────────────────
        res_data = []
        for i in idx:
            tmh_i = value(vars_lote[i])
            if tmh_i is not None and tmh_i > 0.01:
                peso_disponible = df_clean.loc[i, c_peso]
                porcentaje_usado = (tmh_i / peso_disponible * 100) if peso_disponible > 0 else 0
                
                # Determinar tipo de asignación
                if i in lotes_pequenos:
                    tipo = "Completo (≤100 TMH)"
                else:
                    tipo = f"Parcial ({porcentaje_usado:.0f}%)" if porcentaje_usado < 99.9 else "Completo"
                
                res_data.append({
                    "Lote":   df_clean.loc[i, c_lote],
                    "TMH Asignadas":    round(tmh_i, 0),  # Redondear para mostrar enteros
                    "TMH Disponibles":  round(peso_disponible, 0),
                    "% Usado": round(porcentaje_usado, 1),
                    "Tipo": tipo,
                    "Zn %":   df_clean.loc[i, c_zn],
                    "Pb %":   df_clean.loc[i, c_pb],
                    "Ag DM":  df_clean.loc[i, c_ag],
                })

        rdf = pd.DataFrame(res_data)

        # Leyes de cabeza ponderadas
        tmh_total  = rdf['TMH Asignadas'].sum()
        zn_cabeza  = (rdf['TMH Asignadas'] * rdf['Zn %']).sum()  / tmh_total
        pb_cabeza  = (rdf['TMH Asignadas'] * rdf['Pb %']).sum()  / tmh_total
        ag_cabeza  = (rdf['TMH Asignadas'] * rdf['Ag DM']).sum() / tmh_total

        # Mostrar tabla blend
        st.subheader("📋 Lotes Seleccionados para el Blend")
        st.dataframe(
            rdf.style.format({
                "TMH Asignadas": "{:.0f}", 
                "TMH Disponibles": "{:.0f}",
                "% Usado": "{:.1f}%",
                "Zn %": "{:.2f}", 
                "Pb %": "{:.2f}",
                "Ag DM": "{:.3f}"
            }),
            use_container_width=True
        )

        # Mostrar estadísticas de uso
        col_stats1, col_stats2, col_stats3 = st.columns(3)
        lotes_completos = len([r for r in res_data if r['% Usado'] >= 99.9])
        lotes_parciales = len(res_data) - lotes_completos
        col_stats1.metric("Total Lotes Usados", len(res_data))
        col_stats2.metric("Lotes Completos", lotes_completos)
        col_stats3.metric("Lotes Parciales", lotes_parciales)

        # Resumen de leyes de cabeza
        st.subheader("⚖️ Leyes de Cabeza del Blend")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("TMH Total", f"{tmh_total:.0f}")
        c2.metric("Zn Cabeza", f"{zn_cabeza:.2f} %")
        c3.metric("Pb Cabeza", f"{pb_cabeza:.2f} %")
        c4.metric("Ag Cabeza", f"{ag_cabeza:.3f} DM")

        # ── 4. BALANCE METALÚRGICO ───────────────────────────────────────
        st.subheader("📊 Balance Metalúrgico Proyectado")

        # Toneladas Secas
        tms_total = tmh_total * (1 - h_perc)

        # Metales finos recuperados (unidades: TM de metal)
        zn_fino_recuperado = tms_total * (zn_cabeza / 100) * rec_zn
        pb_fino_recuperado = tms_total * (pb_cabeza / 100) * rec_pb
        ag_fino_recuperado = tms_total * ag_cabeza * rec_ag

        # ── Concentrado de ZINC ──────────────────────────────────────────
        tms_conc_zn = zn_fino_recuperado / ley_conc_zn
        ag_en_conc_zn_dm = ag_min_conc_zn
        ag_fino_en_conc_zn = tms_conc_zn * ag_en_conc_zn_dm

        # ── Concentrado de PLOMO ─────────────────────────────────────────
        tms_conc_pb = pb_fino_recuperado / ley_conc_pb
        ag_fino_en_conc_pb = ag_fino_recuperado - ag_fino_en_conc_zn
        if tms_conc_pb > 0:
            ag_en_conc_pb_dm = ag_fino_en_conc_pb / tms_conc_pb
        else:
            ag_en_conc_pb_dm = 0.0

        if ag_fino_en_conc_pb < 0:
            st.warning(
                "⚠️ La plata recuperada total es insuficiente para cubrir los 2.5 DM "
                "garantizados en el concentrado de Zn. Revisa el blend o los parámetros."
            )
            ag_en_conc_pb_dm = 0.0

        # Ley Zn en conc. Pb (dilución esperada)
        zn_en_conc_pb = (tms_total * (zn_cabeza / 100) * (1 - rec_zn)) / tms_conc_pb if tms_conc_pb > 0 else 0

        # ── TABLA DE BALANCE ─────────────────────────────────────────────
        balance = pd.DataFrame({
            "Producto":          ["Cabeza (TMS)", "Concentrado Zn", "Concentrado Pb"],
            "TMS":               [round(tms_total, 2),    round(tms_conc_zn, 2),    round(tms_conc_pb, 2)],
            "Ley Zn (%)":        [round(zn_cabeza, 2),    round(ley_conc_zn * 100, 1), round(zn_en_conc_pb * 100, 2)],
            "Ley Pb (%)":        [round(pb_cabeza, 2),    "—",                      round(ley_conc_pb * 100, 1)],
            "Ag (DM)":           [round(ag_cabeza, 3),    round(ag_en_conc_zn_dm, 2), round(ag_en_conc_pb_dm, 2)],
            "Rec. Aplicada":     ["Base",                 f"{rec_zn*100:.0f}% Zn",  f"{rec_pb*100:.0f}% Pb / {rec_ag*100:.0f}% Ag"],
        })
        st.dataframe(balance, use_container_width=True, hide_index=True)

        # Métricas rápidas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("TMH Blend",       f"{tmh_total:.0f}")
        m2.metric("TMS (-Humedad)",  f"{tms_total:.2f}")
        m3.metric("Conc. Zn (TMS)", f"{tms_conc_zn:.2f}")
        m4.metric("Conc. Pb (TMS)", f"{tms_conc_pb:.2f}")

        st.info(
            f"✅ Conc. Zn asegurado a **{ag_en_conc_zn_dm:.2f} DM** de Ag  |  "
            f"Conc. Pb con **{ag_en_conc_pb_dm:.2f} DM** de Ag (plata restante)"
        )

    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.exception(e)
