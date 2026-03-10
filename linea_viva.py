"""
LINEA VIVA v6 — Sistema de Reposicion de Inventario
Terret | Sidebar por estado de decision
Sin HTML complejo — componentes nativos Streamlit para evitar bugs de render
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import urllib.parse
import uuid

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

# ── REGLAS ───────────────────────────────────────────────────────────────────

def calcular_estado(stock, ventas60d, dias_inv):
    try:
        s = float(stock)
        v = float(ventas60d)
        raw = str(dias_inv).lower().strip()
        d = 9999 if raw in ("inf", "", "nan") else float(raw)
    except:
        return "SIN_ACTIVIDAD"

    if v == 0 and s == 0:        return "SIN_ACTIVIDAD"
    if s == 0 and v >= 10:       return "URGENTE"
    if v <= 2:                   return "LIQUIDAR"
    if v >= 10 and d < 15:       return "URGENTE"
    if v >= 10 and d <= 60:      return "SALUDABLE"
    if v >= 10:                  return "MONITOREAR"
    if 3 <= v <= 9 and d < 15:   return "EVALUAR"
    return "MONITOREAR"

ESTADOS = {
    "URGENTE":       {"icon": "⚡", "label": "Urgente",        "color": "#FF3B30", "desc": "Quiebre o menos de 15 dias. Pedir esta semana."},
    "EVALUAR":       {"icon": "⚠️", "label": "Evaluar",        "color": "#FFB800", "desc": "Rotacion baja y stock acabandose. Decision manual."},
    "MONITOREAR":    {"icon": "👁",  "label": "Monitorear",     "color": "#4488FF", "desc": "Sin accion urgente. Revisar en proximo ciclo."},
    "LIQUIDAR":      {"icon": "📦", "label": "Liquidar",       "color": "#FF6B35", "desc": "0-2 ventas en 60d. Precio especial o retiro."},
    "SALUDABLE":     {"icon": "✅", "label": "Saludable",      "color": "#00C853", "desc": "Stock ideal. Sin accion requerida."},
    "SIN_ACTIVIDAD": {"icon": "⚪", "label": "Sin movimiento", "color": "#3A3A5C", "desc": "Stock 0 y ventas 0. Revisar si archivar."},
}

# ── CSS GLOBAL ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #07070F !important;
    color: #E2E2F0 !important;
    font-family: 'DM Sans', sans-serif;
}
[data-testid="stAppViewContainer"] > .main { background: #07070F; }
[data-testid="stHeader"] { background: #07070F !important; border-bottom: 1px solid #1C1C2E; }

section[data-testid="stSidebar"] {
    background: #0F0F1A !important;
    border-right: 1px solid #1C1C2E !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #E2E2F0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: 0px !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 9px 10px !important;
    text-align: left !important;
    width: 100%;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.05) !important;
    transform: none !important;
}

[data-testid="stMetric"] {
    background: #0F0F1A;
    border: 1px solid #1C1C2E;
    border-radius: 6px;
    padding: 10px 14px;
}
[data-testid="stMetricValue"] {
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 1.8rem !important;
    color: #D4FF00 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 9px !important;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #5A5A7A !important;
}

.stButton > button {
    background: #D4FF00 !important;
    color: #07070F !important;
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 13px !important;
    letter-spacing: 2px !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 8px 16px !important;
    width: 100%;
}
.stButton > button:hover { opacity: 0.85 !important; }

.stTextInput input, .stNumberInput input, .stDateInput input {
    background: #0F0F1A !important;
    border: 1px solid #1C1C2E !important;
    color: #E2E2F0 !important;
    border-radius: 4px !important;
    font-size: 13px !important;
}
.stSelectbox [data-baseweb="select"] > div {
    background: #0F0F1A !important;
    border-color: #1C1C2E !important;
}
hr { border-color: #1C1C2E !important; }
</style>
""", unsafe_allow_html=True)


# ── LOGIN ────────────────────────────────────────────────────────────────────

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if st.session_state.logged_in:
        return
    st.markdown(
        "<div style='max-width:320px;margin:80px auto;text-align:center;'>"
        "<div style='background:#D4FF00;width:48px;height:48px;border-radius:7px;"
        "display:flex;align-items:center;justify-content:center;"
        "font-family:Bebas Neue,sans-serif;font-size:24px;color:#07070F;"
        "margin:0 auto 18px;'>LV</div>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:28px;letter-spacing:3px;"
        "color:#E2E2F0;margin-bottom:4px;'>LINEA VIVA</div>"
        "<div style='font-size:10px;color:#5A5A7A;letter-spacing:2px;"
        "text-transform:uppercase;margin-bottom:32px;'>Terret · Inventario</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 2, 1])
    with col:
        pwd = st.text_input("Contrasena", type="password", placeholder="••••••••", label_visibility="collapsed")
        if st.button("ENTRAR"):
            if pwd == st.secrets.get("APP_PASSWORD", ""):
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Contrasena incorrecta.")
    st.stop()


# ── SHEETS ───────────────────────────────────────────────────────────────────

@st.cache_resource(ttl=300)
def conectar():
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ],
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
                ws.append_row(["ID", "Fecha", "SKU", "Producto", "Variante",
                                "Cantidad", "Fecha_Limite", "Estado", "Notas"])
            return ws
    except Exception as e:
        st.error(f"Error '{nombre}': {e}")
        return None


@st.cache_data(ttl=120)
def leer_inv(_c):
    ws = get_ws(_c, HOJA_INVENTARIO)
    if not ws:
        return pd.DataFrame()
    r = ws.get_all_records()
    return pd.DataFrame(r) if r else pd.DataFrame()


@st.cache_data(ttl=60)
def leer_ord(_c):
    ws = get_ws(_c, HOJA_ORDENES)
    if not ws:
        return pd.DataFrame()
    r = ws.get_all_records()
    return pd.DataFrame(r) if r else pd.DataFrame(
        columns=["ID", "Fecha", "SKU", "Producto", "Variante",
                 "Cantidad", "Fecha_Limite", "Estado", "Notas"]
    )


def guardar_orden(client, o):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws:
        return False
    try:
        ws.append_row([o["id"], o["fecha"], o["sku"], o["producto"], o["variante"],
                       o["cantidad"], o["fecha_limite"], "pendiente", o.get("notas", "")])
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False


def actualizar_estado_orden(client, oid, estado):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws:
        return False
    try:
        cell = ws.find(oid)
        if cell:
            ws.update_cell(cell.row, 8, estado)
            return True
    except:
        pass
    return False


def nuevo_id(df):
    if df.empty or "ID" not in df.columns:
        return "OP-001"
    nums = df["ID"].dropna().astype(str).str.extract(r"(\d+)").dropna().astype(int)
    return f"OP-{int(nums.max().item()) + 1:03d}" if not nums.empty else "OP-001"


# ── PREPARAR ─────────────────────────────────────────────────────────────────

def preparar(df):
    if df.empty:
        return df
    df = df.copy()

    rename = {
        "Stock Actual": "Stock", "Ventas 60d": "Ventas60d",
        "Ventas/Dia": "VentasDia", "Dias de Inventario": "DiasInv",
        "Stock Minimo": "StockMin", "Decision": "Decision",
        "Prioridad": "Prioridad", "Tipo": "Tipo",
    }
    rename_alt = {
        "Ventas/Día": "VentasDia", "Días de Inventario": "DiasInv",
        "Stock Mínimo": "StockMin", "🧠 Decisión": "Decision",
    }
    df = df.rename(columns={**rename_alt, **{k: v for k, v in rename.items() if k in df.columns}})

    for c in list(df.columns):
        if "Decision" not in df.columns and ("decisi" in c.lower() or "\U0001f9e0" in c):
            df = df.rename(columns={c: "Decision"}); break
    for c in list(df.columns):
        if "Stock" not in df.columns and "stock" in c.lower() and "min" not in c.lower():
            df = df.rename(columns={c: "Stock"}); break
    for c in list(df.columns):
        if "DiasInv" not in df.columns and ("dia" in c.lower() or "inv" in c.lower()) and "stock" not in c.lower():
            df = df.rename(columns={c: "DiasInv"}); break
    for c in list(df.columns):
        if "Ventas60d" not in df.columns and "ventas" in c.lower() and "60" in c:
            df = df.rename(columns={c: "Ventas60d"}); break
    for c in list(df.columns):
        if "Tipo" not in df.columns and "tipo" in c.lower():
            df = df.rename(columns={c: "Tipo"}); break

    if "Decision" not in df.columns:
        st.error(f"Columna Decision no encontrada. Columnas: {list(df.columns)}")
        return pd.DataFrame()

    for col, default in [("Tipo", "Sin tipo"), ("Ventas60d", 0), ("Stock", 0), ("DiasInv", 9999)]:
        if col not in df.columns:
            df[col] = default

    df["Ventas60d"] = pd.to_numeric(df["Ventas60d"], errors="coerce").fillna(0)
    df["Stock"]     = pd.to_numeric(df["Stock"],     errors="coerce").fillna(0)
    df["DiasInv_n"] = pd.to_numeric(df["DiasInv"],   errors="coerce").fillna(9999)
    df["_estado"]   = df.apply(
        lambda r: calcular_estado(r["Stock"], r["Ventas60d"], r["DiasInv_n"]), axis=1
    )
    df["_bs"] = df["Ventas60d"] >= UMBRAL_BS
    return df


def agrupar(df, estado):
    sub = df[df["_estado"] == estado]
    if sub.empty:
        return {}
    resultado = {}
    for tipo, dt in sub.groupby("Tipo", sort=True):
        grupos = []
        for prod, g in dt.groupby("Producto", sort=False):
            g = g.copy()
            g["_dias_sort"] = pd.to_numeric(g["DiasInv"], errors="coerce").fillna(9999)
            g = g.sort_values("_dias_sort")
            grupos.append({
                "producto":   prod,
                "es_bs":      bool(g["_bs"].any()),
                "ventas_max": float(g["Ventas60d"].max()),
                "variantes":  g,
                "n":          len(g),
            })
        grupos = sorted(grupos, key=lambda x: -x["ventas_max"])
        resultado[tipo] = grupos
    return resultado


# ── HELPERS DE COLOR ─────────────────────────────────────────────────────────

def color_dias(estado):
    return {
        "URGENTE":    "#FF3B30",
        "EVALUAR":    "#FFB800",
        "LIQUIDAR":   "#FFB800",
        "MONITOREAR": "#4488FF",
        "SALUDABLE":  "#00C853",
    }.get(estado, "#5A5A7A")


def color_borde(estado):
    return {
        "URGENTE":    "#FF3B30",
        "EVALUAR":    "#FFB800",
        "LIQUIDAR":   "#FF6B35",
        "MONITOREAR": "#4488FF",
        "SALUDABLE":  "#00C853",
    }.get(estado, "#3A3A5C")


# ── RENDER VARIANTE ──────────────────────────────────────────────────────────

def render_variante(row, mostrar_form, ordenes_df, client, key_prefix=""):
    var    = str(row.get("Variante", "—"))
    stock  = int(row.get("Stock", 0))
    sku    = str(row.get("SKU", "—"))
    estado = str(row.get("_estado", ""))
    v60    = int(row.get("Ventas60d", 0))

    try:
        dias_int = int(float(str(row.get("DiasInv", 9999))))
        dias_str = str(dias_int)
    except:
        dias_int = None
        dias_str = "—"

    c_dias = color_dias(estado)
    bg     = "rgba(255,59,48,0.05)" if estado == "URGENTE" else \
             "rgba(255,184,0,0.03)" if estado == "EVALUAR" else "transparent"

    # Fila — HTML 100% cerrado, sin elementos Streamlit dentro
    st.markdown(
        "<div style='"
        "display:grid;"
        "grid-template-columns:2fr 1fr 1fr 1.2fr;"
        "gap:8px;"
        "padding:8px 14px;"
        "border-top:1px solid #1C1C2E;"
        "align-items:center;"
        "font-size:13px;"
        "background:" + bg + ";'>"
        "<div style='font-weight:500;'>" + var + "</div>"
        "<div style='font-family:DM Mono,monospace;color:#5A5A7A;font-size:12px;'>" + str(stock) + " u</div>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:22px;line-height:1;color:" + c_dias + ";'>" + dias_str + "</div>"
        "<div style='font-size:12px;color:#5A5A7A;'>" + str(v60) + " u</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if not mostrar_form:
        return

    # Key unica por widget — combina prefix + sku + uuid corto
    _uk = key_prefix + sku + "_" + uuid.uuid4().hex[:6]
    cf1, cf2, cf3, cf4 = st.columns([2, 2, 2, 2])
    with cf1:
        cant = st.number_input(
            "Cantidad", min_value=1, value=50, step=10,
            key="c_" + _uk,
        )
    with cf2:
        fecha_def = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
        fecha = st.date_input(
            "Fecha limite", value=fecha_def,
            key="f_" + _uk,
        )
    with cf3:
        notas = st.text_input(
            "Notas", placeholder="Opcional",
            key="n_" + _uk,
        )
    with cf4:
        st.write("")
        if st.button("PROGRAMAR", key="b_" + _uk):
            orden = {
                "id": nuevo_id(ordenes_df), "sku": sku,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "producto": str(row.get("Producto", "—")), "variante": var,
                "cantidad": cant, "fecha_limite": str(fecha), "notas": notas,
            }
            if guardar_orden(client, orden):
                st.success("Orden " + orden["id"] + " — " + var + " · " + str(cant) + " u")
                st.cache_data.clear()


# ── RENDER PRODUCTO ──────────────────────────────────────────────────────────

def render_producto(grupo, estado, mostrar_form, ordenes_df, client, uid="0"):
    prod      = grupo["producto"]
    es_bs     = grupo["es_bs"]
    variantes = grupo["variantes"]
    n         = grupo["n"]

    c_borde   = color_borde(estado)
    # uid es un entero incremental global — 100% unico sin importar el nombre
    prod_key  = "p" + uid
    tallas    = str(n) + " talla" + ("s" if n > 1 else "")
    bs_html   = " · <span style='color:#D4FF00;font-size:10px;'>⭐ BS</span>" if es_bs else ""

    # Header — completamente cerrado
    st.markdown(
        "<div style='"
        "background:#0F0F1A;"
        "border:1px solid #1C1C2E;"
        "border-left:3px solid " + c_borde + ";"
        "border-radius:8px 8px 0 0;"
        "padding:11px 14px;"
        "display:flex;"
        "align-items:center;"
        "gap:10px;'>"
        "<div style='font-weight:600;font-size:14px;flex:1;line-height:1.2;'>"
        + prod.upper() +
        "</div>"
        "<div style='font-size:11px;color:#5A5A7A;'>"
        + tallas + bs_html +
        "</div>"
        "</div>"
        "<div style='"
        "background:#0F0F1A;"
        "border:1px solid #1C1C2E;"
        "border-top:none;"
        "border-left:3px solid " + c_borde + ";"
        "display:grid;"
        "grid-template-columns:2fr 1fr 1fr 1.2fr;"
        "gap:8px;"
        "padding:5px 14px;"
        "font-size:9px;"
        "color:#5A5A7A;"
        "letter-spacing:1.5px;"
        "text-transform:uppercase;"
        "font-family:DM Mono,monospace;'>"
        "<div>TALLA / VARIANTE</div>"
        "<div>STOCK</div>"
        "<div>DIAS INV.</div>"
        "<div>VENTAS 60D</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Variantes
    for var_idx, (_, row) in enumerate(variantes.iterrows()):
        render_variante(row, mostrar_form, ordenes_df, client, key_prefix=prod_key + "_v" + str(var_idx) + "_")

    # Pie de tarjeta — cerrado
    st.markdown(
        "<div style='"
        "background:#0F0F1A;"
        "border:1px solid #1C1C2E;"
        "border-top:none;"
        "border-left:3px solid " + c_borde + ";"
        "border-radius:0 0 8px 8px;"
        "height:6px;'>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Programar todas
    if mostrar_form and n > 1:
        st.markdown(
            "<div style='"
            "background:rgba(212,255,0,0.03);"
            "border:1px solid rgba(212,255,0,0.12);"
            "border-radius:6px;"
            "padding:10px 14px 6px 14px;"
            "margin-top:4px;'>"
            "<div style='font-size:10px;color:#5A5A7A;letter-spacing:1.5px;"
            "text-transform:uppercase;margin-bottom:8px;'>"
            "Programar todas — " + str(n) + " tallas"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        _pk = prod_key + "_" + uuid.uuid4().hex[:6]
        pc1, pc2, pc3 = st.columns([2, 2, 3])
        with pc1:
            cant_all = st.number_input(
                "Cant. por talla", min_value=1, value=50, step=10,
                key="ca_" + _pk,
            )
        with pc2:
            fecha_def = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
            fecha_all = st.date_input("Fecha limite", value=fecha_def, key="fa_" + _pk)
        with pc3:
            st.write("")
            if st.button("PROGRAMAR " + str(n) + " TALLAS", key="ba_" + _pk):
                creadas = []
                for _, row in variantes.iterrows():
                    o = {
                        "id": nuevo_id(leer_ord(client)),
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "sku": str(row.get("SKU", "—")), "producto": prod,
                        "variante": str(row.get("Variante", "—")),
                        "cantidad": cant_all, "fecha_limite": str(fecha_all),
                        "notas": "Orden masiva",
                    }
                    if guardar_orden(client, o):
                        creadas.append(o["id"])
                if creadas:
                    st.success(str(len(creadas)) + " ordenes creadas — " + ", ".join(creadas))
                    st.cache_data.clear()

    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)


# ── SIDEBAR ──────────────────────────────────────────────────────────────────

def render_sidebar(conteos):
    with st.sidebar:
        st.markdown(
            "<div style='padding:16px 4px 14px 4px;border-bottom:1px solid #1C1C2E;margin-bottom:10px;'>"
            "<div style='display:flex;align-items:center;gap:10px;'>"
            "<div style='background:#D4FF00;width:30px;height:30px;border-radius:4px;"
            "display:flex;align-items:center;justify-content:center;"
            "font-family:Bebas Neue,sans-serif;font-size:15px;color:#07070F;flex-shrink:0;'>LV</div>"
            "<div>"
            "<div style='font-family:Bebas Neue,sans-serif;font-size:16px;letter-spacing:2px;"
            "color:#E2E2F0;line-height:1;'>LINEA VIVA</div>"
            "<div style='font-size:9px;color:#5A5A7A;letter-spacing:1px;text-transform:uppercase;'>"
            "Terret · Inventario</div>"
            "</div>"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        vista_actual = st.session_state.get("vista", "URGENTE")

        for estado, cfg in ESTADOS.items():
            cnt   = conteos.get(estado, 0)
            icon  = cfg["icon"]
            label = cfg["label"]
            btn_label = icon + "  " + label + "   " + str(cnt)
            if st.button(btn_label, key="nav_" + estado):
                st.session_state.vista = estado
                st.rerun()

        st.markdown("<hr style='border-color:#1C1C2E;margin:10px 0;'>", unsafe_allow_html=True)

        if st.button("📋  Ordenes", key="nav_ordenes"):
            st.session_state.vista = "ORDENES"
            st.rerun()

        st.markdown(
            "<div style='margin-top:20px;font-size:9px;color:#2A2A3E;padding:0 4px;'>"
            + datetime.now().strftime("%d/%m/%Y %H:%M") +
            "</div>",
            unsafe_allow_html=True,
        )


# ── VISTA ESTADO ─────────────────────────────────────────────────────────────

def vista_estado(df, ordenes_df, client, estado):
    cfg   = ESTADOS[estado]
    color = cfg["color"]
    mostrar_form = estado in ("URGENTE", "EVALUAR")

    # Banner
    st.markdown(
        "<div style='"
        "background:#0F0F1A;"
        "border:1px solid #1C1C2E;"
        "border-left:4px solid " + color + ";"
        "border-radius:8px;"
        "padding:14px 18px;"
        "margin-bottom:20px;"
        "display:flex;"
        "align-items:center;"
        "gap:14px;'>"
        "<div style='font-size:24px;'>" + cfg["icon"] + "</div>"
        "<div>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:20px;letter-spacing:2px;color:"
        + color + ";'>" + cfg["label"].upper() + "</div>"
        "<div style='font-size:12px;color:#5A5A7A;margin-top:2px;'>" + cfg["desc"] + "</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    sub = df[df["_estado"] == estado]

    if sub.empty:
        st.markdown(
            "<div style='text-align:center;padding:60px 0;color:#5A5A7A;'>"
            "<div style='font-size:36px;margin-bottom:12px;'>" + cfg["icon"] + "</div>"
            "<div style='font-family:Bebas Neue,sans-serif;font-size:18px;letter-spacing:2px;'>"
            "Sin productos en este estado</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # Metricas
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("SKUs",       len(sub))
    with c2: st.metric("Productos",  sub["Producto"].nunique())
    with c3: st.metric("Categorias", sub["Tipo"].nunique())

    # Filtros
    t1, t2 = st.columns([3, 2])
    with t1:
        buscar = st.text_input("Buscar", placeholder="Buscar producto...", label_visibility="collapsed")
    with t2:
        tipos_disp = sorted(sub["Tipo"].dropna().unique().tolist())
        tipo_sel = st.selectbox("Categoria", ["Todas"] + tipos_disp, label_visibility="collapsed")

    # Email urgentes
    if estado == "URGENTE":
        prods_u = sub["Producto"].unique()
        lista = "\n".join("- " + p for p in prods_u[:15])
        s = urllib.parse.quote("URGENTE: Reposicion Terret")
        b = urllib.parse.quote("Productos urgentes (" + str(len(prods_u)) + "):\n\n" + lista + "\n\nEntra a Linea Viva.")
        st.markdown(
            "<a href='mailto:" + ALERTA_EMAIL + "?subject=" + s + "&body=" + b + "'>"
            "<button style='background:#FF3B30;color:white;font-family:Bebas Neue,sans-serif;"
            "font-size:12px;letter-spacing:2px;border:none;border-radius:4px;"
            "padding:7px 16px;cursor:pointer;margin-bottom:8px;'>"
            "ENVIAR ALERTA — " + str(len(prods_u)) + " productos urgentes"
            "</button></a>",
            unsafe_allow_html=True,
        )

    # Agrupar y filtrar
    grupos_tipo = agrupar(df, estado)
    if tipo_sel != "Todas":
        grupos_tipo = {k: v for k, v in grupos_tipo.items() if k == tipo_sel}
    if buscar:
        grupos_tipo = {
            t: [g for g in gs if buscar.lower() in g["producto"].lower()]
            for t, gs in grupos_tipo.items()
        }
        grupos_tipo = {t: gs for t, gs in grupos_tipo.items() if gs}

    if not grupos_tipo:
        st.info("Sin resultados.")
        return

    prod_counter = [0]  # contador global mutable para keys unicas
    for tipo, grupos in grupos_tipo.items():
        st.markdown(
            "<div style='"
            "font-family:DM Mono,monospace;"
            "font-size:9px;"
            "letter-spacing:3px;"
            "color:#3A3A5C;"
            "text-transform:uppercase;"
            "padding:20px 0 6px 0;"
            "border-bottom:1px solid #1C1C2E;"
            "margin-bottom:8px;'>"
            + tipo.upper() + " &nbsp;·&nbsp; " + str(len(grupos)) + " productos"
            "</div>",
            unsafe_allow_html=True,
        )
        for grupo in grupos:
            prod_counter[0] += 1
            render_producto(grupo, estado, mostrar_form, ordenes_df, client, uid=str(prod_counter[0]))


# ── VISTA ORDENES ─────────────────────────────────────────────────────────────

def vista_ordenes(ordenes_df, client):
    st.markdown(
        "<div style='font-family:Bebas Neue,sans-serif;font-size:22px;"
        "letter-spacing:3px;color:#E2E2F0;margin-bottom:16px;'>"
        "ORDENES DE PRODUCCION</div>",
        unsafe_allow_html=True,
    )

    if ordenes_df.empty or len(ordenes_df.columns) < 2:
        st.info("No hay ordenes aun.")
        return

    c1, c2 = st.columns(2)
    with c1:
        opts = ["Todos"]
        if "Estado" in ordenes_df.columns:
            opts += list(ordenes_df["Estado"].dropna().unique())
        filtro = st.selectbox("Estado", opts)
    with c2:
        buscar = st.text_input("Buscar", placeholder="Producto, SKU...")

    df_f = ordenes_df.copy()
    if filtro != "Todos" and "Estado" in df_f.columns:
        df_f = df_f[df_f["Estado"] == filtro]
    if buscar:
        mask = df_f.apply(
            lambda col: col.astype(str).str.contains(buscar, case=False, na=False)
        ).any(axis=1)
        df_f = df_f[mask]

    st.dataframe(df_f, use_container_width=True, hide_index=True)
    st.markdown("---")

    if "ID" in ordenes_df.columns and not ordenes_df["ID"].dropna().empty:
        st.markdown(
            "<div style='font-size:13px;font-weight:600;margin-bottom:8px;'>Actualizar estado</div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            oid = st.selectbox("Orden", ordenes_df["ID"].dropna().tolist())
        with c2:
            nuevo_estado = st.selectbox("Estado", ["pendiente", "en-proceso", "completado", "cancelado"])
        with c3:
            st.write("")
            if st.button("ACTUALIZAR"):
                if actualizar_estado_orden(client, oid, nuevo_estado):
                    st.success(oid + " → " + nuevo_estado)
                    st.cache_data.clear()


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    check_login()

    client  = conectar()
    df_raw  = leer_inv(client) if client else pd.DataFrame()
    ordenes = leer_ord(client) if client else pd.DataFrame()
    df      = preparar(df_raw) if not df_raw.empty else pd.DataFrame()

    conteos = {}
    if not df.empty:
        for estado in ESTADOS:
            conteos[estado] = int(df[df["_estado"] == estado]["Producto"].nunique())

    if "vista" not in st.session_state:
        st.session_state.vista = "URGENTE"

    render_sidebar(conteos)

    vista = st.session_state.get("vista", "URGENTE")

    if vista == "ORDENES":
        vista_ordenes(ordenes, client)
    elif vista in ESTADOS:
        if df.empty:
            st.warning("Sin datos. Ejecuta actualizarTodo en Apps Script.")
        else:
            vista_estado(df, ordenes, client, vista)

    st.markdown(
        "<div style='font-size:10px;color:#1C1C2E;text-align:right;margin-top:40px;'>"
        "LINEA VIVA · TERRET · " + datetime.now().strftime("%d.%m.%Y %H:%M") + "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
