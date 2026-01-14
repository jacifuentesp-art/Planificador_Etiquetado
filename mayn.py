import streamlit as st
import pandas as pd
import datetime as dt
import math
import io

# Configuración de página
st.set_page_config(page_title="DHL | Planner Dashboard", layout="wide")

# Estilos personalizados
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: white; border: 1px solid #eee; padding: 15px; border-radius: 10px; }
    .stDataFrame { background-color: white; border-radius: 10px; }
    h1, h2, h3 { color: #D40000; }
    </style>
    """, unsafe_allow_html=True)

# --- LÓGICA DE PROCESAMIENTO ---
def procesar_logica(df):
    INICIO_H, FIN_H, SETUP_MIN = 8, 15, 2
    LINEAS_TOTALES = 12
    dias_semana = [dt.datetime(2026, 1, i, INICIO_H, 0) for i in range(12, 17)] 
    lineas_reloj = {i: dias_semana[0] for i in range(1, LINEAS_TOTALES + 1)}
    plan = []
    
    for _, fila in df.iterrows():
        marca = str(fila['Marca']).upper()
        cajas_totales = int(fila['Unit Quantity'])
        p_auto, p_man = fila['Cajas por hora línea automatica'], fila['Cajas por hora línea manual']
        es_choco = any(x in marca for x in ["MKA", "MILKA"])
        
        if es_choco or p_auto > p_man:
            modalidad, prod_usada, opciones = "Automatica", p_auto, [1, 2]
        else:
            modalidad, prod_usada, opciones = "Manual", p_man, list(range(3, 13))

        n_linea = opciones[0]
        for l in opciones:
            if lineas_reloj[l] < dias_semana[-1].replace(hour=FIN_H):
                n_linea = l
                break

        cajas_pendientes = cajas_totales
        while cajas_pendientes > 0:
            tiempo_actual = lineas_reloj[n_linea]
            if tiempo_actual >= dias_semana[-1].replace(hour=FIN_H):
                prox = [o for o in opciones if o > n_linea]
                if prox: n_linea = prox[0]; continue
                else: break

            fin_dia = tiempo_actual.replace(hour=FIN_H, minute=0)
            horas_disp = (fin_dia - tiempo_actual).total_seconds() / 3600
            if horas_disp <= 0:
                actual_idx = [i for i, d in enumerate(dias_semana) if d.date() == tiempo_actual.date()]
                if actual_idx and actual_idx[0] + 1 < len(dias_semana):
                    lineas_reloj[n_linea] = dias_semana[actual_idx[0] + 1]
                    continue
                else: break

            procesar = min(cajas_pendientes, math.floor(horas_disp * prod_usada))
            if procesar <= 0: break

            tiempo_fin = tiempo_actual + dt.timedelta(hours=procesar/prod_usada)
            plan.append({
                'Línea': n_linea, 'Día': tiempo_actual.strftime('%A'), 'Producto': fila['Descripcion'],
                'Marca': marca, 'Modalidad': modalidad, 'Hora Inicio': tiempo_actual.strftime('%H:%M'),
                'Hora Fin': tiempo_fin.strftime('%H:%M'), 'Cajas': int(procesar)
            })
            cajas_pendientes -= procesar
            lineas_reloj[n_linea] = tiempo_fin + dt.timedelta(minutes=SETUP_MIN)

    res_df = pd.DataFrame(plan)
    traduccion = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles','Thursday':'Jueves','Friday':'Viernes'}
    if not res_df.empty: res_df['Día'] = res_df['Día'].map(traduccion)
    return res_df

# --- INTERFAZ STREAMLIT ---
st.title("🚀 Panel de Control DHL")

archivo = st.file_uploader("Cargar Demanda Semanal (Excel)", type=["xlsx"])

if archivo:
    df_raw = pd.read_excel(archivo)
    df_plan = procesar_logica(df_raw)
    
    if not df_plan.empty:
        # --- FILTROS DE VISTA (No afectan el proceso, solo lo que ves) ---
        st.sidebar.header("🔍 Filtros de Visualización")
        filtro_dia = st.sidebar.multiselect("Filtrar por Día:", options=df_plan['Día'].unique(), default=df_plan['Día'].unique())
        filtro_linea = st.sidebar.multiselect("Filtrar por Línea:", options=sorted(df_plan['Línea'].unique()), default=sorted(df_plan['Línea'].unique()))
        filtro_marca = st.sidebar.multiselect("Filtrar por Marca:", options=df_plan['Marca'].unique(), default=df_plan['Marca'].unique())

        # Aplicar filtros a una copia para mostrar
        df_display = df_plan[
            (df_plan['Día'].isin(filtro_dia)) & 
            (df_plan['Línea'].isin(filtro_linea)) &
            (df_plan['Marca'].isin(filtro_marca))
        ]

        # --- INDICADORES ---
        l_total = df_plan['Línea'].nunique()
        c1, c2, c3 = st.columns(3)
        c1.metric("Líneas Activas", l_total)
        c2.metric("Headcount", l_total * 6)
        c3.metric("Total Cajas", f"{df_display['Cajas'].sum():,}")

        # --- GRÁFICO DE CARGA ---
        st.subheader("📊 Carga de Trabajo por Día (Cajas)")
        carga_dia = df_display.groupby('Día')['Cajas'].sum().reindex(["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"])
        st.bar_chart(carga_dia)

        # --- TABLA INTERACTIVA ---
        st.subheader("📅 Planificación Detallada")
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # --- BOTONES DE DESCARGA ---
        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_plan.to_excel(writer, index=False, sheet_name='Plan_Completo')
            df_display.to_excel(writer, index=False, sheet_name='Vista_Filtrada')
        
        st.download_button(
            label="📥 Descargar Planificación Completa",
            data=buffer,
            file_name="Plan_DHL_Final.xlsx",
            mime="application/vnd.ms-excel"
        )