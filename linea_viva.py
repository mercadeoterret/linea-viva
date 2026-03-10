"""
LINEA VIVA v5 — Sistema de Reposicion de Inventario
Terret | Sidebar por estado de decision
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import urllib.parse

st.set_page_config(
    page_title="Linea Viva · Terret",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

SPREADSHEET_ID   = "1M6bCu6fSXE1ReYBqBvC78zdX-0fbGuCdmSn6JdgUv9s"
HOJA_INVENTARIO  = "Dashboard_Inventario"
HOJA_ORDENES     = "Ordenes_Produccion"
ALERTA_EMAIL     = "mercadeo@terretsports.com"
FABRICACION_DIAS = 20
UMBRAL_BS        = 20

# ── REGLAS (segun reglas_dashboard.pdf de Terret) ────────────────────────────

def calcular_estado(stock, ventas60d, dias_inv):
    try:
        s = float(stock)
        v = float(ventas60d)
        d = float(str(dias_inv)) if str(dias_inv).lower() not in ("inf","","nan") else 9999
    except:
        return "SIN_ACTIVIDAD"

    if v == 0 and s == 0:   return "SIN_ACTIVIDAD"
    if s == 0 and v >= 10:  return "URGENTE"       # quiebre de stock
    if v <= 2:              return "LIQUIDAR"       # 0-2 ventas: producto muerto
    if v >= 10 and d < 15:  return "URGENTE"        # reprogramar ya
    if v >= 10 and d <= 60: return "SALUDABLE"
    if v >= 10:             return "MONITOREAR"     # sobrestock
    if 3 <= v <= 9 and d < 15: return "EVALUAR"    # rotacion baja y agotandose
    return "MONITOREAR"                             # rotacion baja con stock

ESTADOS = {
    "URGENTE":       {"icon":"⚡","label":"Urgente",       "color":"#FF3B30","desc":"Quiebre o menos de 15 dias. Pedir esta semana."},
    "EVALUAR":       {"icon":"⚠️","label":"Evaluar",       "color":"#FFB800","desc":"Rotacion baja y stock acabandose. Decision manual."},
    "MONITOREAR":    {"icon":"👁","label":"Monitorear",    "color":"#4488FF","desc":"Sin accion urgente. Revisar en proximo ciclo."},
    "LIQUIDAR":      {"icon":"📦","label":"Liquidar",      "color":"#FF6B35","desc":"0-2 ventas en 60d. Precio especial o retiro."},
    "SALUDABLE":     {"icon":"✅","label":"Saludable",     "color":"#00C853","desc":"Stock ideal. Sin accion requerida."},
    "SIN_ACTIVIDAD": {"icon":"⚪","label":"Sin movimiento","color":"#3A3A5C","desc":"Stock 0 y ventas 0. Revisar si archivar."},
}

# ── ESTILOS ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
    --bg:     #07070F;
    --surf:   #0F0F1A;
    --border: #1C1C2E;
    --muted:  #3A3A5C;
    --text:   #E2E2F0;
    --dim:    #5A5A7A;
    --accent: #D4FF00;
    --red:    #FF3B30;
    --amber:  #FFB800;
    --green:  #00C853;
    --blue:   #4488FF;
    --orange: #FF6B35;
}
html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important; color: var(--text) !important;
    font-family: 'DM Sans', sans-serif;
}
[data-testid="stAppViewContainer"] > .main { background: var(--bg); }
[data-testid="stHeader"] { background: var(--bg) !important; border-bottom: 1px solid var(--border); }

section[data-testid="stSidebar"] {
    background: var(--surf) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: var(--text) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: 0.3px !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 9px 12px !important;
    text-align: left !important;
    width: 100%;
    justify-content: flex-start !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.06) !important;
    transform: none !important;
}
section[data-testid="stSidebar"] .stButton > button:focus {
    background: rgba(212,255,0,0.10) !important;
    color: var(--accent) !important;
    transform: none !important;
    box-shadow: none !important;
}

[data-testid="stMetric"] {
    background: var(--surf); border: 1px solid var(--border);
    border-radius: 6px; padding: 10px 14px;
}
[data-testid="stMetricValue"] {
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 1.8rem !important; color: var(--accent) !important;
}
[data-testid="stMetricLabel"] {
    font-size: 9px !important; letter-spacing: 1.5px;
    text-transform: uppercase; color: var(--dim) !important;
}
.stButton > button {
    background: var(--accent) !important; color: #07070F !important;
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 13px !important; letter-spacing: 2px !important;
    border: none !important; border-radius: 4px !important;
    padding: 8px 16px !important; width: 100%;
}
.stButton > button:hover { opacity: 0.85 !important; }

.stTextInput input, .stNumberInput input, .stDateInput input {
    background: var(--surf) !important; border: 1px solid var(--border) !important;
    color: var(--text) !important; border-radius: 4px !important; font-size: 13px !important;
}
.stSelectbox [data-baseweb="select"] > div {
    background: var(--surf) !important; border-color: var(--border) !important;
}
hr { border-color: var(--border) !important; }

.tipo-sep {
    font-family: 'DM Mono', monospace; font-size: 9px; letter-spacing: 3px;
    color: var(--muted); text-transform: uppercase;
    padding: 20px 0 6px 0; border-bottom: 1px solid var(--border); margin-bottom: 8px;
}
.prod-card {
    background: var(--surf); border: 1px solid var(--border);
    border-radius: 8px; margin-bottom: 6px; overflow: hidden;
}
.prod-header {
    display: flex; align-items: center; gap: 10px; padding: 12px 14px;
}
.prod-nombre { font-weight: 600; font-size: 14px; flex: 1; line-height: 1.2; }
.tag {
    font-family: 'DM Mono', monospace; font-size: 10px;
    padding: 2px 8px; border-radius: 3px; white-space: nowrap;
}
.tag-red    { background: rgba(255,59,48,0.15);  color: var(--red); }
.tag-amber  { background: rgba(255,184,0,0.15);  color: var(--amber); }
.tag-blue   { background: rgba(68,136,255,0.15); color: var(--blue); }
.tag-orange { background: rgba(255,107,53,0.15); color: var(--orange); }
.tag-muted  { background: rgba(58,58,92,0.4);   color: var(--dim); }
.tag-green  { background: rgba(0,200,83,0.15);   color: var(--green); }
.tag-bs     { background: rgba(212,255,0,0.12);  color: var(--accent); font-size: 9px; }

.var-header {
    display: grid; grid-template-columns: 2fr 1fr 1fr 1.2fr;
    gap: 8px; padding: 5px 14px;
    border-top: 1px solid var(--border);
    font-size: 9px; color: var(--dim); letter-spacing: 1.5px;
    text-transform: uppercase; font-family: 'DM Mono', monospace;
}
.var-row {
    display: grid; grid-template-columns: 2fr 1fr 1fr 1.2fr;
    gap: 8px; padding: 8px 14px;
    border-top: 1px solid var(--border); align-items: center; font-size: 13px;
}
.var-row-critica { background: rgba(255,59,48,0.04); }
.var-row-alerta  { background: rgba(255,184,0,0.03); }
.vname  { font-weight: 500; }
.vstock { font-family: 'DM Mono', monospace; color: var(--dim); font-size: 12px; }
.vdias-rojo  { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--red);   line-height:1; }
.vdias-amber { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--amber); line-height:1; }
.vdias-green { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--green); line-height:1; }
.vdias-blue  { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--blue);  line-height:1; }
.vdias-dim   { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--dim);   line-height:1; }

.prog-panel {
    background: rgba(212,255,0,0.03);
    border-top: 1px solid rgba(212,255,0,0.12);
    padding: 12px 14px 14px 14px;
}
.banner {
    border-radius: 8px; padding: 14px 18px; margin-bottom: 20px;
    display: flex; align-items: center; gap: 14px;
    background: var(--surf); border: 1px solid var(--border);
}
.banner-icon   { font-size: 24px; flex-shrink: 0; }
.banner-title  { font-family: 'Bebas Neue', sans-serif; font-size: 20px; letter-spacing: 2px; }
.banner-desc   { font-size: 12px; color: var(--dim); margin-top: 2px; }
</style>
""", unsafe_allow_html=True)


# ── LOGIN ─────────────────────────────────────────────────────────────────────
def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if not st.session_state.logged_in:
        st.markdown("""
        <div style='max-width:340px;margin:80px auto;text-align:center;'>
            <div style='background:#D4FF00;width:48px;height:48px;border-radius:7px;
                        display:flex;align-items:center;justify-content:center;
                        font-family:Bebas Neue,sans-serif;font-size:24px;color:#07070F;
                        margin:0 auto 18px;'>LV</div>
            <div style='font-family:Bebas Neue,sans-serif;font-size:28px;letter-spacing:3px;color:#E2E2F0;margin-bottom:2px;'>LINEA VIVA</div>
            <div style='font-size:10px;color:#5A5A7A;letter-spacing:2px;text-transform:uppercase;margin-bottom:32px;'>Terret · Inventario</div>
        </div>
        """, unsafe_allow_html=True)
        _, col, _ = st.columns([1,2,1])
        with col:
            pwd = st.text_input("", type="password", placeholder="Contrasena", label_visibility="collapsed")
            if st.button("ENTRAR"):
                if pwd == st.secrets.get("APP_PASSWORD",""):
                    st.session_state.logged_in = True; st.rerun()
                else:
                    st.error("Contrasena incorrecta.")
        st.stop()


# ── SHEETS ────────────────────────────────────────────────────────────────────
@st.cache_resource(ttl=300)
def conectar():
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error Sheets: {e}"); return None

def get_ws(client, nombre):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try: return sh.worksheet(nombre)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=nombre, rows=1000, cols=20)
            if nombre == HOJA_ORDENES:
                ws.append_row(["ID","Fecha","SKU","Producto","Variante","Cantidad","Fecha_Limite","Estado","Notas"])
            return ws
    except Exception as e:
        st.error(f"Error '{nombre}': {e}"); return None

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
        columns=["ID","Fecha","SKU","Producto","Variante","Cantidad","Fecha_Limite","Estado","Notas"])

def guardar_orden(client, o):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws: return False
    try:
        ws.append_row([o["id"],o["fecha"],o["sku"],o["producto"],o["variante"],
                       o["cantidad"],o["fecha_limite"],"pendiente",o.get("notas","")])
        return True
    except Exception as e:
        st.error(f"Error: {e}"); return False

def actualizar_estado_orden(client, oid, estado):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws: return False
    try:
        cell = ws.find(oid)
        if cell: ws.update_cell(cell.row, 8, estado); return True
    except: pass
    return False

def nuevo_id(df):
    if df.empty or "ID" not in df.columns: return "OP-001"
    nums = df["ID"].dropna().astype(str).str.extract(r"(\d+)").dropna().astype(int)
    return f"OP-{int(nums.max().item())+1:03d}" if not nums.empty else "OP-001"


# ── PREPARAR ──────────────────────────────────────────────────────────────────
def preparar(df):
    if df.empty: return df
    df = df.copy()
    rename = {"Stock Actual":"Stock","Ventas 60d":"Ventas60d","Ventas/Dia":"VentasDia",
              "Dias de Inventario":"DiasInv","Stock Minimo":"StockMin",
              "Decision":"Decision","Prioridad":"Prioridad","Tipo":"Tipo"}
    rename_alt = {"Ventas/Día":"VentasDia","Días de Inventario":"DiasInv",
                  "Stock Mínimo":"StockMin","🧠 Decisión":"Decision"}
    df = df.rename(columns={**rename_alt, **{k:v for k,v in rename.items() if k in df.columns}})

    for c in list(df.columns):
        if "Decision" not in df.columns and ("decisi" in c.lower() or "\U0001f9e0" in c):
            df = df.rename(columns={c:"Decision"}); break
    for c in list(df.columns):
        if "Stock" not in df.columns and "stock" in c.lower() and "min" not in c.lower():
            df = df.rename(columns={c:"Stock"}); break
    for c in list(df.columns):
        if "DiasInv" not in df.columns and ("dia" in c.lower() or "inv" in c.lower()) and "stock" not in c.lower():
            df = df.rename(columns={c:"DiasInv"}); break
    for c in list(df.columns):
        if "Ventas60d" not in df.columns and "ventas" in c.lower() and "60" in c:
            df = df.rename(columns={c:"Ventas60d"}); break
    for c in list(df.columns):
        if "Tipo" not in df.columns and "tipo" in c.lower():
            df = df.rename(columns={c:"Tipo"}); break

    if "Decision" not in df.columns:
        st.error(f"Columna Decision no encontrada. Columnas: {list(df.columns)}"); return pd.DataFrame()

    for col, default in [("Tipo","Sin tipo"),("Ventas60d",0),("Stock",0),("DiasInv",9999)]:
        if col not in df.columns: df[col] = default

    df["Ventas60d"] = pd.to_numeric(df["Ventas60d"], errors="coerce").fillna(0)
    df["Stock"]     = pd.to_numeric(df["Stock"],     errors="coerce").fillna(0)
    df["DiasInv_n"] = pd.to_numeric(df["DiasInv"],   errors="coerce").fillna(9999)
    df["_estado"]   = df.apply(lambda r: calcular_estado(r["Stock"], r["Ventas60d"], r["DiasInv_n"]), axis=1)
    df["_bs"]       = df["Ventas60d"] >= UMBRAL_BS
    return df


def agrupar(df, estado):
    sub = df[df["_estado"] == estado]
    if sub.empty: return {}
    resultado = {}
    for tipo, dt in sub.groupby("Tipo", sort=True):
        grupos = []
        for prod, g in dt.groupby("Producto", sort=False):
            g = g.copy()
            g["_dias_sort"] = pd.to_numeric(g["DiasInv"], errors="coerce").fillna(9999)
            g = g.sort_values("_dias_sort")
            grupos.append({
                "producto":   prod,
                "es_bs":      g["_bs"].any(),
                "ventas_max": g["Ventas60d"].max(),
                "variantes":  g,
                "n":          len(g),
            })
        grupos = sorted(grupos, key=lambda x: -x["ventas_max"])
        resultado[tipo] = grupos
    return resultado


# ── RENDER ────────────────────────────────────────────────────────────────────
def dias_clase(dias_int, estado):
    if estado in ("URGENTE",):       return "vdias-rojo"
    if estado in ("EVALUAR","LIQUIDAR"): return "vdias-amber"
    if estado == "MONITOREAR":       return "vdias-blue"
    if estado == "SALUDABLE":        return "vdias-green"
    return "vdias-dim"


def render_variante(row, mostrar_form, ordenes_df, client, key_prefix=""):
    var    = str(row.get("Variante","—"))
    stock  = row.get("Stock", 0)
    sku    = str(row.get("SKU","—"))
    estado = row.get("_estado","")
    v60    = row.get("Ventas60d", 0)

    try: dias_int = int(float(str(row.get("DiasInv","—"))))
    except: dias_int = None

    dias_str = str(dias_int) if dias_int is not None else "—"
    d_cls    = dias_clase(dias_int, estado)
    r_cls    = "var-row-critica" if estado=="URGENTE" else "var-row-alerta" if estado=="EVALUAR" else ""

    st.markdown(f"""
    <div class="var-row {r_cls}">
        <div class="vname">{var}</div>
        <div class="vstock">{int(stock)} u</div>
        <div class="{d_cls}">{dias_str}</div>
        <div style="font-size:12px;color:var(--dim);">{int(v60)} u</div>
    </div>""", unsafe_allow_html=True)

    if mostrar_form:
        cf1, cf2, cf3, cf4 = st.columns([2,2,2,2])
        with cf1:
            cant = st.number_input("Cantidad", min_value=1, value=50, step=10,
                                   key=f"c_{key_prefix}{sku}")
        with cf2:
            fecha_def = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
            fecha = st.date_input("Fecha limite", value=fecha_def,
                                  key=f"f_{key_prefix}{sku}")
        with cf3:
            notas = st.text_input("Notas", placeholder="Opcional",
                                  key=f"n_{key_prefix}{sku}")
        with cf4:
            st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)
            if st.button("PROGRAMAR", key=f"b_{key_prefix}{sku}"):
                orden = {"id": nuevo_id(ordenes_df), "sku": sku,
                         "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                         "producto": row.get("Producto","—"), "variante": var,
                         "cantidad": cant, "fecha_limite": str(fecha), "notas": notas}
                if guardar_orden(client, orden):
                    st.success(f"✅ {orden['id']} — {var} · {cant} u · {fecha}")
                    st.cache_data.clear()
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)


def render_producto(grupo, estado, mostrar_form, ordenes_df, client):
    prod      = grupo["producto"]
    es_bs     = grupo["es_bs"]
    variantes = grupo["variantes"]
    n         = grupo["n"]
    bs_tag    = '<span class="tag tag-bs">⭐ BS</span>' if es_bs else ""

    st.markdown(f"""
    <div class="prod-card">
        <div class="prod-header">
            <div class="prod-nombre">{prod.upper()}</div>
            <div style="display:flex;gap:6px;align-items:center;">
                {bs_tag}
                <span style="font-size:11px;color:var(--dim);">{n} talla{"s" if n>1 else ""}</span>
            </div>
        </div>
        <div class="var-header">
            <div>TALLA / VARIANTE</div><div>STOCK</div><div>DIAS INV.</div><div>VENTAS 60D</div>
        </div>
    </div>""", unsafe_allow_html=True)

    for _, row in variantes.iterrows():
        render_variante(row, mostrar_form, ordenes_df, client, key_prefix=f"{prod[:6]}_")

    if mostrar_form and len(variantes) > 1:
        st.markdown('<div class="prog-panel">', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:10px;color:var(--dim);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;">Programar todas — {len(variantes)} tallas</div>', unsafe_allow_html=True)
        pc1, pc2, pc3 = st.columns([2,2,3])
        with pc1:
            cant_all = st.number_input("Cant. por talla", min_value=1, value=50, step=10, key=f"ca_{prod}")
        with pc2:
            fecha_def = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
            fecha_all = st.date_input("Fecha limite", value=fecha_def, key=f"fa_{prod}")
        with pc3:
            st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)
            if st.button(f"PROGRAMAR {len(variantes)} TALLAS", key=f"ba_{prod}"):
                creadas = []
                for _, row in variantes.iterrows():
                    o = {"id": nuevo_id(leer_ord(client)),
                         "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                         "sku": str(row.get("SKU","—")), "producto": prod,
                         "variante": str(row.get("Variante","—")),
                         "cantidad": cant_all, "fecha_limite": str(fecha_all), "notas": "Orden masiva"}
                    if guardar_orden(client, o): creadas.append(o["id"])
                if creadas:
                    st.success(f"✅ {len(creadas)} ordenes — {', '.join(creadas)}")
                    st.cache_data.clear()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
def render_sidebar(conteos):
    with st.sidebar:
        # Logo
        st.markdown("""
        <div style='padding:20px 4px 16px 4px;border-bottom:1px solid #1C1C2E;margin-bottom:12px;'>
            <div style='display:flex;align-items:center;gap:10px;'>
                <div style='background:#D4FF00;width:30px;height:30px;border-radius:4px;
                            display:flex;align-items:center;justify-content:center;
                            font-family:Bebas Neue,sans-serif;font-size:15px;color:#07070F;flex-shrink:0;'>LV</div>
                <div>
                    <div style='font-family:Bebas Neue,sans-serif;font-size:16px;letter-spacing:2px;color:#E2E2F0;line-height:1;'>LINEA VIVA</div>
                    <div style='font-size:9px;color:#5A5A7A;letter-spacing:1px;text-transform:uppercase;'>Terret · Inventario</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        vista_actual = st.session_state.get("vista","URGENTE")

        for estado, cfg in ESTADOS.items():
            cnt   = conteos.get(estado, 0)
            active = vista_actual == estado

            # Color del badge segun urgencia
            badge_color = {"URGENTE":"#FF3B30","EVALUAR":"#FFB800"}.get(estado, "#3A3A5C")
            badge_text  = {"URGENTE":"white","EVALUAR":"#07070F"}.get(estado, "#5A5A7A")
            label_color = "#D4FF00" if active else "#E2E2F0"
            bg          = "background:rgba(212,255,0,0.08);" if active else ""

            btn_label = f"{cfg['icon']}  {cfg['label']}  {cnt}"
            if st.button(btn_label, key=f"nav_{estado}"):
                st.session_state.vista = estado
                st.rerun()

        st.markdown("<div style='border-top:1px solid #1C1C2E;margin:12px 0;'></div>", unsafe_allow_html=True)

        ordenes_active = vista_actual == "ORDENES"
        if st.button("📋  Ordenes", key="nav_ordenes"):
            st.session_state.vista = "ORDENES"; st.rerun()

        st.markdown(f"""
        <div style='margin-top:24px;font-size:9px;color:#2A2A3E;letter-spacing:1px;padding:0 4px;'>
            {datetime.now().strftime('%d/%m/%Y %H:%M')}
        </div>""", unsafe_allow_html=True)


# ── VISTAS ────────────────────────────────────────────────────────────────────
def vista_estado(df, ordenes_df, client, estado):
    cfg = ESTADOS[estado]
    mostrar_form = estado in ("URGENTE","EVALUAR")
    color = cfg["color"]

    # Banner de seccion
    st.markdown(f"""
    <div class="banner" style="border-left:4px solid {color};">
        <div class="banner-icon">{cfg["icon"]}</div>
        <div>
            <div class="banner-title" style="color:{color};">{cfg["label"].upper()}</div>
            <div class="banner-desc">{cfg["desc"]}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    sub = df[df["_estado"] == estado]

    if sub.empty:
        st.markdown(f"""
        <div style='text-align:center;padding:60px 0;color:var(--dim);'>
            <div style='font-size:36px;margin-bottom:12px;'>{cfg["icon"]}</div>
            <div style='font-family:Bebas Neue,sans-serif;font-size:18px;letter-spacing:2px;'>
                Sin productos en este estado
            </div>
        </div>""", unsafe_allow_html=True)
        return

    # Metricas rapidas
    n_skus  = len(sub)
    n_prods = sub["Producto"].nunique()
    n_tipos = sub["Tipo"].nunique()
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("SKUs", n_skus)
    with c2: st.metric("Productos", n_prods)
    with c3: st.metric("Categorias", n_tipos)

    # Barra de herramientas
    t1, t2 = st.columns([3, 2])
    with t1:
        buscar = st.text_input("", placeholder="Buscar producto...", label_visibility="collapsed")
    with t2:
        tipos_disp = sorted(sub["Tipo"].dropna().unique().tolist())
        tipo_sel = st.selectbox("", ["Todas las categorias"] + tipos_disp, label_visibility="collapsed")

    # Alerta email para urgentes
    if estado == "URGENTE":
        prods_u = sub["Producto"].unique()
        lista = "\n".join([f"- {p}" for p in prods_u[:15]])
        s = urllib.parse.quote("URGENTE: Reposicion Terret")
        b = urllib.parse.quote(f"Productos urgentes ({len(prods_u)}):\n\n{lista}\n\nEntra a Linea Viva.")
        st.markdown(
            f'<a href="mailto:{ALERTA_EMAIL}?subject={s}&body={b}">'
            f'<button style="background:#FF3B30;color:white;font-family:Bebas Neue,sans-serif;'
            f'font-size:12px;letter-spacing:2px;border:none;border-radius:4px;'
            f'padding:7px 16px;cursor:pointer;margin-bottom:4px;">'
            f'📧 ENVIAR ALERTA — {len(prods_u)} productos urgentes</button></a>',
            unsafe_allow_html=True)

    # Agrupar y filtrar
    grupos_tipo = agrupar(df, estado)

    if tipo_sel != "Todas las categorias":
        grupos_tipo = {k:v for k,v in grupos_tipo.items() if k == tipo_sel}
    if buscar:
        grupos_tipo = {t:[g for g in gs if buscar.lower() in g["producto"].lower()]
                       for t,gs in grupos_tipo.items()}
        grupos_tipo = {t:gs for t,gs in grupos_tipo.items() if gs}

    if not grupos_tipo:
        st.info("Sin resultados.")
        return

    for tipo, grupos in grupos_tipo.items():
        st.markdown(f'<div class="tipo-sep">{tipo.upper()} &nbsp;·&nbsp; {len(grupos)} productos</div>',
                    unsafe_allow_html=True)
        for grupo in grupos:
            render_producto(grupo, estado, mostrar_form, ordenes_df, client)


def vista_ordenes(ordenes_df, client):
    st.markdown("""
    <div style='font-family:Bebas Neue,sans-serif;font-size:22px;letter-spacing:3px;
                color:#E2E2F0;margin-bottom:16px;'>ORDENES DE PRODUCCION</div>""",
                unsafe_allow_html=True)

    if ordenes_df.empty or len(ordenes_df.columns) < 2:
        st.info("No hay ordenes aun."); return

    c1, c2 = st.columns(2)
    with c1:
        opts = ["Todos"] + list(ordenes_df["Estado"].dropna().unique()) if "Estado" in ordenes_df.columns else ["Todos"]
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

    if "ID" in ordenes_df.columns and not ordenes_df["ID"].dropna().empty:
        st.markdown('<div style="font-size:13px;font-weight:600;margin-bottom:8px;">Actualizar estado</div>',
                    unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1: oid    = st.selectbox("Orden", ordenes_df["ID"].dropna().tolist())
        with c2: estado = st.selectbox("Estado", ["pendiente","en-proceso","completado","cancelado"])
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("ACTUALIZAR"):
                if actualizar_estado_orden(client, oid, estado):
                    st.success(f"✅ {oid} → {estado}"); st.cache_data.clear()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    check_login()

    client  = conectar()
    df_raw  = leer_inv(client) if client else pd.DataFrame()
    ordenes = leer_ord(client) if client else pd.DataFrame()
    df      = preparar(df_raw) if not df_raw.empty else pd.DataFrame()

    # Conteos por estado (en productos unicos)
    conteos = {}
    if not df.empty:
        for estado in ESTADOS:
            conteos[estado] = df[df["_estado"]==estado]["Producto"].nunique()

    if "vista" not in st.session_state:
        st.session_state.vista = "URGENTE"

    render_sidebar(conteos)

    vista = st.session_state.get("vista","URGENTE")

    if vista == "ORDENES":
        vista_ordenes(ordenes, client)
    elif vista in ESTADOS:
        if df.empty:
            st.warning("Sin datos. Ejecuta actualizarTodo en Apps Script.")
        else:
            vista_estado(df, ordenes, client, vista)

    st.markdown(
        f"<div style='font-size:10px;color:#1C1C2E;text-align:right;margin-top:40px;'>"
        f"LINEA VIVA · TERRET · {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>",
        unsafe_allow_html=True)

if __name__ == "__main__":
    main()
