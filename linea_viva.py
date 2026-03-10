"""
LINEA VIVA v4 - Sistema de Reposicion de Inventario
Terret | Streamlit + Google Sheets
Agrupacion: Tipo de producto > Producto > Talla
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import urllib.parse

st.set_page_config(
    page_title="Linea Viva - Terret",
    page_icon="lightning",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SPREADSHEET_ID   = "1M6bCu6fSXE1ReYBqBvC78zdX-0fbGuCdmSn6JdgUv9s"
HOJA_INVENTARIO  = "Dashboard_Inventario"
HOJA_ORDENES     = "Ordenes_Produccion"
ALERTA_EMAIL     = "mercadeo@terretsports.com"
FABRICACION_DIAS = 20
UMBRAL_BS        = 20  # ventas 60d para ser best seller — ajustar segun temporada

# ─── ESTILOS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background-color: #0A0A14 !important; color: #E8E8F0 !important;
}
[data-testid="stAppViewContainer"] > .main { background-color: #0A0A14; }
[data-testid="stHeader"] { background: #0A0A14 !important; border-bottom: 1px solid #1A1A2E; }
section[data-testid="stSidebar"] { background: #0D0D1A !important; }
* { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Bebas Neue', sans-serif !important; letter-spacing: 2px; }

.stButton > button {
    background: #D4FF00 !important; color: #0A0A14 !important;
    font-family: 'Bebas Neue', sans-serif !important; font-size: 14px !important;
    letter-spacing: 2px !important; border: none !important;
    border-radius: 4px !important; padding: 8px 16px !important;
    width: 100%; transition: all 0.15s ease;
}
.stButton > button:hover { background: #BFEA00 !important; transform: translateY(-1px); }

.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input {
    background: #12121F !important; border: 1px solid #2A2A3E !important;
    color: #E8E8F0 !important; border-radius: 4px !important;
}
[data-testid="stMetric"] {
    background: #12121F; border: 1px solid #1E1E30;
    border-radius: 8px; padding: 14px 18px;
}
[data-testid="stMetricValue"] {
    color: #D4FF00 !important; font-family: 'Bebas Neue', sans-serif !important; font-size: 1.8rem !important;
}
[data-testid="stMetricLabel"] {
    color: #6B6B8A !important; font-size: 10px !important;
    text-transform: uppercase; letter-spacing: 1.5px;
}
.stTabs [data-baseweb="tab-list"] {
    background: #0D0D1A; border-radius: 8px; padding: 4px; gap: 4px; border: 1px solid #1A1A2E;
}
.stTabs [data-baseweb="tab"] {
    background: transparent; color: #6B6B8A;
    font-family: 'Bebas Neue', sans-serif; font-size: 14px;
    letter-spacing: 1.5px; border-radius: 6px; padding: 8px 18px;
}
.stTabs [aria-selected="true"] { background: #D4FF00 !important; color: #0A0A14 !important; }

[data-testid="stExpander"] { border-radius: 8px !important; margin-bottom: 6px !important; }
hr { border-color: #1A1A2E !important; }

.tipo-header {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 13px; letter-spacing: 3px;
    color: #6B6B8A; text-transform: uppercase;
    border-bottom: 1px solid #1A1A2E;
    padding-bottom: 6px; margin: 24px 0 12px 0;
}
.fila-critica {
    background: #12121F; border-left: 3px solid #FF3B30;
    border-radius: 4px; padding: 10px 14px; margin-bottom: 6px;
}
.fila-alerta {
    background: #12121F; border-left: 3px solid #FFB800;
    border-radius: 4px; padding: 10px 14px; margin-bottom: 6px;
}
.fila-ok {
    background: #0D0D1A; border-left: 3px solid #2A2A3E;
    border-radius: 4px; padding: 8px 14px; margin-bottom: 4px;
}
.talla-nombre { font-weight: 600; font-size: 15px; }
.lbl { font-size: 10px; color: #6B6B8A; text-transform: uppercase; letter-spacing: 1px; }
.bs-badge {
    background: #D4FF00; color: #0A0A14;
    font-size: 9px; font-weight: 700;
    padding: 1px 7px; border-radius: 20px;
    text-transform: uppercase; letter-spacing: 1px;
    display: inline-block; margin-left: 6px;
    vertical-align: middle;
}
</style>
""", unsafe_allow_html=True)


# ─── LOGIN ──────────────────────────────────────────────────────────────────

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if not st.session_state.logged_in:
        st.markdown("""
        <div style='max-width:360px;margin:80px auto;text-align:center;'>
            <div style='background:#D4FF00;width:52px;height:52px;border-radius:8px;
                        display:flex;align-items:center;justify-content:center;
                        font-family:Bebas Neue,sans-serif;font-size:26px;color:#0A0A14;
                        margin:0 auto 20px auto;'>LV</div>
            <div style='font-family:Bebas Neue,sans-serif;font-size:30px;letter-spacing:3px;color:#E8E8F0;margin-bottom:4px;'>LINEA VIVA</div>
            <div style='font-size:11px;color:#6B6B8A;letter-spacing:2px;text-transform:uppercase;margin-bottom:36px;'>Terret - Inventario</div>
        </div>
        """, unsafe_allow_html=True)
        _, col, _ = st.columns([1, 2, 1])
        with col:
            pwd = st.text_input("Contrasena", type="password", placeholder="........")
            if st.button("ENTRAR"):
                if pwd == st.secrets.get("APP_PASSWORD", ""):
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Contrasena incorrecta.")
        st.stop()


# ─── SHEETS ─────────────────────────────────────────────────────────────────

@st.cache_resource(ttl=300)
def conectar():
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error Sheets: {e}")
        return None


def get_ws(client, nombre):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            return sh.worksheet(nombre)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=nombre, rows=1000, cols=20)
            if nombre == HOJA_ORDENES:
                ws.append_row(["ID","Fecha","SKU","Producto","Variante",
                                "Cantidad","Fecha_Limite","Estado","Notas"])
            return ws
    except Exception as e:
        st.error(f"Error '{nombre}': {e}")
        return None


@st.cache_data(ttl=120)
def leer_inv(_c):
    ws = get_ws(_c, HOJA_INVENTARIO)
    if not ws: return pd.DataFrame()
    r = ws.get_all_records()
    return pd.DataFrame(r) if r else pd.DataFrame()


@st.cache_data(ttl=60)
def leer_ord(_c):
    ws = get_ws(_c, HOJA_ORDENES)
    if not ws: return pd.DataFrame()
    r = ws.get_all_records()
    return pd.DataFrame(r) if r else pd.DataFrame(
        columns=["ID","Fecha","SKU","Producto","Variante",
                 "Cantidad","Fecha_Limite","Estado","Notas"])


def guardar_orden(client, o):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws: return False
    try:
        ws.append_row([o["id"],o["fecha"],o["sku"],o["producto"],o["variante"],
                       o["cantidad"],o["fecha_limite"],"pendiente",o["notas"]])
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False


def actualizar_estado(client, oid, estado):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws: return False
    try:
        cell = ws.find(oid)
        if cell:
            ws.update_cell(cell.row, 8, estado)
            return True
    except: pass
    return False


def nuevo_id(df):
    if df.empty or "ID" not in df.columns: return "OP-001"
    nums = df["ID"].dropna().astype(str).str.extract(r"(\d+)").dropna().astype(int)
    return f"OP-{int(nums.max().item())+1:03d}" if not nums.empty else "OP-001"


# ─── LOGICA ─────────────────────────────────────────────────────────────────

def get_urgencia(decision):
    d = str(decision).upper()
    if "QUIEBRE" in d or "REPROGRAMAR" in d: return "CRITICO"
    if "EVALUAR" in d or "MONITOREAR" in d:  return "ALERTA"
    if "SALUDABLE" in d:                      return "OK"
    if "LIQUIDAR" in d:                       return "LIQUIDAR"
    return "INFO"


def preparar(df):
    if df.empty: return df
    df = df.copy()

    # Nombres exactos del Apps Script actualizado
    rename = {
        "Stock Actual":       "Stock",
        "Ventas 60d":         "Ventas60d",
        "Ventas/Dia":         "VentasDia",
        "Dias de Inventario": "DiasInv",
        "Stock Minimo":       "StockMin",
        "Decision":           "Decision",
        "Prioridad":          "Prioridad",
        "Tipo":               "Tipo",
    }
    # Tambien intentar nombres con tildes por si el sheet los tiene
    rename_alt = {
        "Ventas/Día":          "VentasDia",
        "Días de Inventario":  "DiasInv",
        "Stock Mínimo":        "StockMin",
        "🧠 Decisión":         "Decision",
    }
    df = df.rename(columns={**rename_alt, **{k:v for k,v in rename.items() if k in df.columns}})

    # Fallback por patron
    for c in list(df.columns):
        cl = c.lower()
        if "Decision" not in df.columns and ("decisi" in cl or "\U0001f9e0" in c):
            df = df.rename(columns={c: "Decision"}); break
    for c in list(df.columns):
        cl = c.lower()
        if "Stock" not in df.columns and "stock" in cl and "min" not in cl:
            df = df.rename(columns={c: "Stock"}); break
    for c in list(df.columns):
        cl = c.lower()
        if "DiasInv" not in df.columns and ("dia" in cl or "inv" in cl) and "stock" not in cl:
            df = df.rename(columns={c: "DiasInv"}); break
    for c in list(df.columns):
        cl = c.lower()
        if "Ventas60d" not in df.columns and "ventas" in cl and "60" in cl:
            df = df.rename(columns={c: "Ventas60d"}); break
    for c in list(df.columns):
        cl = c.lower()
        if "Tipo" not in df.columns and "tipo" in cl:
            df = df.rename(columns={c: "Tipo"}); break

    if "Decision" not in df.columns:
        st.error(f"No encontre columna de decision. Columnas disponibles: {list(df.columns)}")
        return pd.DataFrame()

    # Columnas que pueden no existir aun
    if "Tipo" not in df.columns:
        df["Tipo"] = "Sin tipo"
    if "Ventas60d" not in df.columns:
        df["Ventas60d"] = 0

    df["Ventas60d"] = pd.to_numeric(df["Ventas60d"], errors="coerce").fillna(0)
    df["_urg"]      = df["Decision"].apply(get_urgencia)
    df["_orden"]    = df["_urg"].map({"CRITICO":0,"ALERTA":1,"OK":2,"LIQUIDAR":3,"INFO":4})
    df["_bs"]       = df["Ventas60d"] >= UMBRAL_BS  # True = best seller
    return df


def agrupar_por_tipo(df):
    """Retorna dict: {tipo: [grupos_de_producto]}"""
    if df.empty: return {}

    resultado = {}
    for tipo, df_tipo in df.groupby("Tipo", sort=True):
        grupos = []
        for prod, g in df_tipo.groupby("Producto", sort=False):
            g = g.sort_values("_orden")
            peor_orden = g["_orden"].min()
            peor_urg   = g.loc[g["_orden"]==peor_orden, "_urg"].iloc[0]
            es_bs      = g["_bs"].any()
            grupos.append({
                "producto":   prod,
                "urgencia":   peor_urg,
                "orden":      peor_orden,
                "n_criticos": (g["_urg"]=="CRITICO").sum(),
                "n_alertas":  (g["_urg"]=="ALERTA").sum(),
                "es_bs":      es_bs,
                "ventas_max": g["Ventas60d"].max(),
                "variantes":  g,
            })
        grupos = sorted(grupos, key=lambda x: x["orden"])
        resultado[tipo] = grupos

    return resultado


# ─── RENDER ─────────────────────────────────────────────────────────────────

def render_fila(row, clase, mostrar_form, ordenes_df, client):
    var   = str(row.get("Variante", "—"))
    stock = row.get("Stock", "—")
    dias  = row.get("DiasInv", "—")
    v60   = row.get("Ventas60d", "—")
    sku   = str(row.get("SKU", "—"))

    try: dias_int = int(float(str(dias)))
    except: dias_int = None

    try: v60_int = int(float(str(v60)))
    except: v60_int = v60

    color = "#FF3B30" if (isinstance(dias_int,int) and dias_int<=15) else \
            "#FFB800" if (isinstance(dias_int,int) and dias_int<=30) else "#30D158"

    st.markdown(f'<div class="{clase}">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    with c1:
        st.markdown(f'<div class="talla-nombre">{var}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="lbl">Stock</div><div style="font-size:16px;font-weight:600;">{stock} u</div>', unsafe_allow_html=True)
    with c3:
        dias_str = str(dias_int) if dias_int is not None else str(dias)
        st.markdown(f'<div class="lbl">Dias</div><div style="font-family:Bebas Neue,sans-serif;font-size:22px;color:{color};">{dias_str}</div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="lbl">Ventas 60d</div><div style="font-size:16px;font-weight:600;">{v60_int} u</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if mostrar_form:
        cf1, cf2, cf3, cf4 = st.columns([3, 2, 2, 2])
        with cf2:
            cant = st.number_input("u", min_value=1, value=50, step=10,
                                   key=f"c_{sku}", label_visibility="collapsed")
        with cf3:
            fecha_def = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
            fecha     = st.date_input("f", value=fecha_def,
                                      key=f"f_{sku}", label_visibility="collapsed")
        with cf4:
            if st.button("PROGRAMAR", key=f"b_{sku}"):
                orden = {
                    "id": nuevo_id(ordenes_df),
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "sku": sku, "producto": row.get("Producto","—"),
                    "variante": var, "cantidad": cant,
                    "fecha_limite": str(fecha), "notas": "",
                }
                if guardar_orden(client, orden):
                    st.success(f"Orden {orden['id']} - {var} - {cant} u - {fecha}")
                    st.cache_data.clear()

        st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)


def render_grupo(grupo, ordenes_df, client):
    u        = grupo["urgencia"]
    producto = grupo["producto"]
    nc       = grupo["n_criticos"]
    na       = grupo["n_alertas"]
    es_bs    = grupo["es_bs"]
    variantes = grupo["variantes"]

    icono = {"CRITICO":"🔴","ALERTA":"⚠️","OK":"✅","LIQUIDAR":"📦"}.get(u,"•")
    resumen = ""
    if nc: resumen += f"  -  {nc} critica{'s' if nc>1 else ''}"
    if na: resumen += f"  -  {na} en alerta"
    if not nc and not na: resumen = f"  -  {variantes.shape[0]} tallas OK"

    bs_txt = " ⭐ BS" if es_bs else ""
    label  = f"{icono}  {producto.upper()}{bs_txt}{resumen}"

    with st.expander(label, expanded=(u == "CRITICO")):
        urgentes = variantes[variantes["_urg"].isin(["CRITICO","ALERTA"])]
        ok_vars  = variantes[~variantes["_urg"].isin(["CRITICO","ALERTA"])]

        if not urgentes.empty:
            for _, row in urgentes.iterrows():
                clase = "fila-critica" if row["_urg"] == "CRITICO" else "fila-alerta"
                render_fila(row, clase, mostrar_form=True, ordenes_df=ordenes_df, client=client)

            # Programar todas a la vez
            if len(urgentes) > 1:
                st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)
                cp1, cp2, cp3 = st.columns([2, 2, 3])
                with cp1:
                    cant_all = st.number_input("Cant. por talla", min_value=1, value=50, step=10,
                                               key=f"ca_{producto}")
                with cp2:
                    fecha_def = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
                    fecha_all = st.date_input("Fecha limite", value=fecha_def, key=f"fa_{producto}")
                with cp3:
                    st.markdown('<div style="height:22px;"></div>', unsafe_allow_html=True)
                    if st.button(f"PROGRAMAR {len(urgentes)} TALLAS A LA VEZ", key=f"ba_{producto}"):
                        creadas = []
                        for _, row in urgentes.iterrows():
                            o = {
                                "id": nuevo_id(leer_ord(client)),
                                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "sku": str(row.get("SKU","—")),
                                "producto": producto,
                                "variante": str(row.get("Variante","—")),
                                "cantidad": cant_all,
                                "fecha_limite": str(fecha_all),
                                "notas": "Orden masiva",
                            }
                            if guardar_orden(client, o):
                                creadas.append(o["id"])
                        if creadas:
                            st.success(f"{len(creadas)} ordenes creadas - {', '.join(creadas)}")
                            st.cache_data.clear()

        if not ok_vars.empty:
            with st.expander(f"   Ver {len(ok_vars)} tallas OK"):
                for _, row in ok_vars.iterrows():
                    render_fila(row, "fila-ok", mostrar_form=False,
                                ordenes_df=ordenes_df, client=client)


def render_header(nc, na):
    b = ""
    if nc: b += f"<span style='background:#FF3B30;color:white;font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;'>⚡ {nc} criticos</span> "
    if na: b += f"<span style='background:#FFB800;color:#0A0A14;font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;'>⚠ {na} en alerta</span>"
    if not nc and not na: b = "<span style='background:#30D158;color:#0A0A14;font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;'>Todo OK</span>"

    st.markdown(f"""
    <div style='display:flex;align-items:center;gap:16px;padding:8px 0 24px 0;
                border-bottom:1px solid #1A1A2E;margin-bottom:24px;'>
        <div style='background:#D4FF00;width:40px;height:40px;border-radius:6px;flex-shrink:0;
                    display:flex;align-items:center;justify-content:center;
                    font-family:Bebas Neue,sans-serif;font-size:20px;color:#0A0A14;'>LV</div>
        <div>
            <div style='font-family:Bebas Neue,sans-serif;font-size:24px;letter-spacing:3px;color:#E8E8F0;line-height:1;'>LINEA VIVA</div>
            <div style='font-size:10px;color:#6B6B8A;letter-spacing:2px;text-transform:uppercase;'>Reposicion - Terret</div>
        </div>
        <div style='margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;'>{b}</div>
    </div>
    """, unsafe_allow_html=True)


# ─── VISTAS ──────────────────────────────────────────────────────────────────

def vista_dashboard(df, ordenes_df, client):
    if df.empty:
        st.warning("Sin datos. Ejecuta actualizarTodo en Apps Script.")
        return

    df_p = preparar(df)
    if df_p.empty: return

    tipos_grupos = agrupar_por_tipo(df_p)
    todos_grupos = [g for gs in tipos_grupos.values() for g in gs]

    total_c = sum(g["n_criticos"] for g in todos_grupos)
    total_a = sum(g["n_alertas"]  for g in todos_grupos)
    prods_u = sum(1 for g in todos_grupos if g["urgencia"] in ["CRITICO","ALERTA"])
    pend    = (ordenes_df["Estado"]=="pendiente").sum() if "Estado" in ordenes_df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("SKUs CRITICOS",      total_c)
    with c2: st.metric("SKUs EN ALERTA",     total_a)
    with c3: st.metric("PRODUCTOS URGENTES", prods_u)
    with c4: st.metric("ORDENES ACTIVAS",    pend)

    # Boton alerta email
    if total_c or total_a:
        lista = "\n".join([
            f"- {g['producto']}: {g['n_criticos']} criticas, {g['n_alertas']} en alerta"
            for g in todos_grupos if g["urgencia"] in ["CRITICO","ALERTA"]
        ])
        s = urllib.parse.quote("LINEA VIVA - Productos urgentes Terret")
        b = urllib.parse.quote(f"Productos urgentes:\n\n{lista}\n\nEntra a Linea Viva.")
        st.markdown(
            f'<div style="margin:16px 0 4px 0;">'
            f'<a href="mailto:{ALERTA_EMAIL}?subject={s}&body={b}">'
            f'<button style="background:#D4FF00;color:#0A0A14;font-family:Bebas Neue,sans-serif;'
            f'font-size:13px;letter-spacing:2px;border:none;border-radius:4px;'
            f'padding:9px 20px;cursor:pointer;">ENVIAR ALERTA</button></a></div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # Filtros
    col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
    with col_f1:
        filtro_urg = st.radio("Ver", ["Solo urgentes", "Todos"], horizontal=True)
    with col_f2:
        filtro_bs  = st.radio("Tipo", ["Todos", "Solo best sellers"], horizontal=True)
    with col_f3:
        buscar = st.text_input("", placeholder="Buscar producto...", label_visibility="collapsed")

    # Filtro de tipos de producto (tabs si hay varios)
    tipos_disponibles = sorted(tipos_grupos.keys())
    if len(tipos_disponibles) > 1:
        tipo_sel = st.selectbox("Categoria", ["Todos los tipos"] + tipos_disponibles)
    else:
        tipo_sel = "Todos los tipos"

    # Aplicar filtros y renderizar
    sin_resultados = True
    for tipo, grupos in sorted(tipos_grupos.items()):
        if tipo_sel != "Todos los tipos" and tipo != tipo_sel:
            continue

        grupos_f = grupos
        if filtro_urg == "Solo urgentes":
            grupos_f = [g for g in grupos_f if g["urgencia"] in ["CRITICO","ALERTA"]]
        if filtro_bs == "Solo best sellers":
            grupos_f = [g for g in grupos_f if g["es_bs"]]
        if buscar:
            grupos_f = [g for g in grupos_f if buscar.lower() in g["producto"].lower()]

        if not grupos_f:
            continue

        sin_resultados = False

        # Header de tipo
        st.markdown(f'<div class="tipo-header">{tipo.upper()}</div>', unsafe_allow_html=True)
        for g in grupos_f:
            render_grupo(g, ordenes_df, client)

    if sin_resultados:
        st.success("Sin productos urgentes con los filtros actuales.")


def vista_ordenes(ordenes_df, client):
    st.markdown("### ORDENES DE PRODUCCION")

    if ordenes_df.empty or len(ordenes_df.columns) < 2:
        st.info("No hay ordenes aun.")
        return

    c1, c2 = st.columns(2)
    with c1:
        opts   = ["Todos"] + list(ordenes_df["Estado"].dropna().unique()) if "Estado" in ordenes_df.columns else ["Todos"]
        filtro = st.selectbox("Estado", opts)
    with c2:
        buscar = st.text_input("Buscar", placeholder="Producto, SKU...")

    df_f = ordenes_df.copy()
    if filtro != "Todos" and "Estado" in df_f.columns:
        df_f = df_f[df_f["Estado"] == filtro]
    if buscar:
        mask = df_f.apply(lambda col: col.astype(str).str.contains(buscar, case=False, na=False)).any(axis=1)
        df_f = df_f[mask]

    st.dataframe(df_f, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### ACTUALIZAR ESTADO")
    if "ID" in ordenes_df.columns and not ordenes_df["ID"].dropna().empty:
        c1, c2, c3 = st.columns(3)
        with c1: oid    = st.selectbox("Orden", ordenes_df["ID"].dropna().tolist())
        with c2: estado = st.selectbox("Estado", ["pendiente","en-proceso","completado","cancelado"])
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("ACTUALIZAR"):
                if actualizar_estado(client, oid, estado):
                    st.success(f"{oid} - {estado}")
                    st.cache_data.clear()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    check_login()

    client  = conectar()
    df      = leer_inv(client) if client else pd.DataFrame()
    ordenes = leer_ord(client) if client else pd.DataFrame()

    df_p   = preparar(df) if not df.empty else df
    grupos = [g for gs in agrupar_por_tipo(df_p).values() for g in gs] if not df_p.empty and "_urg" in df_p.columns else []
    nc     = sum(g["n_criticos"] for g in grupos)
    na     = sum(g["n_alertas"]  for g in grupos)

    render_header(nc, na)

    tab1, tab2 = st.tabs(["DASHBOARD", "ORDENES"])
    with tab1: vista_dashboard(df, ordenes, client)
    with tab2: vista_ordenes(ordenes, client)

    st.markdown(
        f"<div style='text-align:center;font-size:11px;color:#2A2A3E;margin-top:40px;'>"
        f"LINEA VIVA - TERRET - {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
