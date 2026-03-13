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
import plotly.graph_objects as go
import plotly.express as px
import requests

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
HOJA_REPORTE     = "Reporte_Urgente"
# URL del Web App de Apps Script — pegar aqui despues de deployar
WEBAPP_URL       = st.secrets.get("WEBAPP_URL", "")
FABRICACION_DIAS = 30   # lead time conservador (rango 20-30 dias)
UMBRAL_BS        = 25   # umbral best seller (ESTRELLA segun reglas)
LEAD_TIME_DIAS   = 30


# ── REGLAS ───────────────────────────────────────────────────────────────────

def calcular_estado(stock, ventas60d, dias_inv):
    """
    Logica expandida — base RTF + ajustes de negocio Terret.
    LEAD_TIME_DIAS = 30d (conservador, rango real 20-30d)
    """
    try:
        s = float(stock)
        v = float(ventas60d)
        raw = str(dias_inv).lower().strip()
        cob = 9999 if raw in ("inf", "", "nan") else float(raw)
    except:
        return "HUECO"

    # ── Casos especiales — prioridad absoluta ────────────────────────────────
    if s == 0 and v == 0:
        return "HUECO"

    # Liquidar: pocas ventas con exceso de stock — capital inmovilizado
    if v <= 3 and cob > 90:
        return "LIQUIDAR"

    # Reprogramar: quiebre o cobertura critica con ventas activas
    if (cob <= LEAD_TIME_DIAS and v > 3) or (s == 0 and v > 0):
        return "REPROGRAMAR"

    # ── Segmentacion por volumen de ventas ───────────────────────────────────
    if v >= 25:
        return "ESTRELLA" if cob <= 120 else "SOBRESTOCK"

    if v >= 10:
        return "ALTA_ROTACION" if cob <= 120 else "SOBRESTOCK"

    # ── Rotacion baja (ventas 4-9) ───────────────────────────────────────────
    if v >= 4:
        if cob <= 90:
            return "SALUDABLE"
        return "MONITOREAR"

    # ventas 1-3 con cobertura <= 90d — rota poco pero no es urgente
    return "MONITOREAR"


ESTADOS = {
    "REPROGRAMAR":   {"icon": "⚡", "label": "Reprogramar",   "color": "#FF3B30", "desc": "Cobertura <= 30 dias con ventas activas, o quiebre. Pedir ya."},
    "ESTRELLA":      {"icon": "⭐", "label": "Estrella",      "color": "#2D6A4F", "desc": "Ventas >= 25 en 60d. Best seller — nunca dejar sin stock."},
    "ALTA_ROTACION": {"icon": "🔥", "label": "Alta Rotacion", "color": "#FFB800", "desc": "Ventas >= 10 en 60d. Monitorear de cerca."},
    "SOBRESTOCK":    {"icon": "🔴", "label": "Sobrestock",    "color": "#FF6B35", "desc": "Cobertura > 120 dias. Pausar pedidos."},
    "SALUDABLE":     {"icon": "✅", "label": "Saludable",     "color": "#00C853", "desc": "Ventas 4-9, cobertura 31-90d. Stock equilibrado."},
    "MONITOREAR":    {"icon": "👁",  "label": "Monitorear",   "color": "#4488FF", "desc": "Ventas 4-9, cobertura > 90d. Revisar proximo ciclo."},
    "LIQUIDAR":      {"icon": "📦", "label": "Liquidar",      "color": "#FF9500", "desc": "Ventas <= 3 y cobertura > 90d. Precio especial o retiro."},
    "HUECO":         {"icon": "⚪", "label": "Hueco",         "color": "#B8B0A4", "desc": "Stock 0 y ventas 0. Posiblemente descontinuado."},
}

ORDEN_SIDEBAR = ["REPROGRAMAR", "ESTRELLA", "ALTA_ROTACION", "SOBRESTOCK", "SALUDABLE", "MONITOREAR", "LIQUIDAR", "HUECO"]


# ── CSS GLOBAL ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #F5F0E8 !important;
    color: #1A1A14 !important;
    font-family: 'DM Sans', sans-serif;
}
[data-testid="stAppViewContainer"] > .main { background: #F5F0E8; }
[data-testid="stHeader"] { background: #F5F0E8 !important; border-bottom: 1px solid #D4CFC4; }

section[data-testid="stSidebar"] {
    background: #EDEAE0 !important;
    border-right: 1px solid #D4CFC4 !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #1A1A14 !important;
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
    background: rgba(45,106,79,0.08) !important;
    transform: none !important;
}

[data-testid="stMetric"] {
    background: #EDEAE0;
    border: 1px solid #D4CFC4;
    border-radius: 6px;
    padding: 10px 14px;
}
[data-testid="stMetricValue"] {
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 1.8rem !important;
    color: #2D6A4F !important;
}
[data-testid="stMetricLabel"] {
    font-size: 9px !important;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #6B6456 !important;
}

.stButton > button {
    background: #2D6A4F !important;
    color: #F5F0E8 !important;
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
    background: #EDEAE0 !important;
    border: 1px solid #D4CFC4 !important;
    color: #1A1A14 !important;
    border-radius: 4px !important;
    font-size: 13px !important;
}
.stSelectbox [data-baseweb="select"] > div {
    background: #EDEAE0 !important;
    border-color: #D4CFC4 !important;
}
hr { border-color: #D4CFC4 !important; }
</style>
""", unsafe_allow_html=True)


# ── LOGIN NATIVO (SIN IFRAMES) ───────────────────────────────────────────────

def check_login():
    if st.session_state.get("logged_in"):
        return

    client_id = st.secrets.get("GOOGLE_CLIENT_ID", "")
    client_secret = st.secrets.get("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = st.secrets.get("REDIRECT_URI", "https://linea-viva-gklx8ezcupejpncx2nzpjw.streamlit.app/")

    query_params = st.query_params
    auth_code = query_params.get("code")

    if not auth_code:
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account"
        }
        login_url = f"{auth_url}?{urllib.parse.urlencode(params)}"

        st.markdown(
            "<div style='max-width:360px;margin:80px auto;text-align:center;'>"
            "<div style='background:#2D6A4F;width:56px;height:56px;border-radius:10px;"
            "display:flex;align-items:center;justify-content:center;"
            "font-family:Bebas Neue,sans-serif;font-size:26px;color:#F5F0E8;"
            "margin:0 auto 20px;'>LV</div>"
            "<div style='font-family:Bebas Neue,sans-serif;font-size:30px;letter-spacing:3px;"
            "color:#1A1A14;margin-bottom:4px;'>LINEA VIVA</div>"
            "<div style='font-size:10px;color:#6B6456;letter-spacing:2px;"
            "text-transform:uppercase;margin-bottom:40px;'>Terret · Inventario</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        
        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.link_button("🔑 INICIAR SESIÓN CON GOOGLE", login_url, use_container_width=True)
            
        st.stop()

    else:
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        
        response = requests.post(token_url, data=data)
        
        if response.status_code == 200:
            tokens = response.json()
            access_token = tokens.get("access_token")
            
            user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info_response = requests.get(user_info_url, headers=headers)
            
            if user_info_response.status_code == 200:
                user_info = user_info_response.json()
                user_email = user_info.get("email", "").lower()
                user_domain = user_email.split("@")[-1] if "@" in user_email else ""
                
                allowed_domains = [d.strip().lower() for d in st.secrets.get("ALLOWED_DOMAINS", "terretsports.com,terret.co").split(",") if d.strip()]
                allowed_emails  = [e.strip().lower() for e in st.secrets.get("ALLOWED_EMAILS", "").split(",") if e.strip()]
                
                autorizado = (user_domain in allowed_domains) or (user_email in allowed_emails)
                
                if not autorizado:
                    st.error(f"Acceso denegado: {user_email}. Solo cuentas @terretsports.com y @terret.co.")
                    st.query_params.clear() 
                    if st.button("Probar con otra cuenta"):
                        st.rerun()
                    st.stop()
                
                st.session_state.logged_in = True
                st.session_state.user_email = user_email
                st.session_state.user_name = user_info.get("name", "")
                
                st.query_params.clear()
                st.rerun() 
                
        else:
            st.error("La sesión ha expirado o hubo un error de conexión con Google.")
            st.query_params.clear()
            if st.button("Volver a intentar"):
                st.rerun()
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
        st.error("No se pudo acceder a Ordenes_Produccion. Verifica que la hoja exista en el Sheet.")
        return False
    try:
        ws.append_row([o["id"], o["fecha"], o["sku"], o["producto"], o["variante"],
                       o["cantidad"], o["fecha_limite"], "pendiente", o.get("notas", "")])
        return True
    except Exception as e:
        st.error("Error al guardar: " + str(e))
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


def escribir_reporte(client, sub_df):
    ws = get_ws(client, HOJA_REPORTE)
    if not ws:
        return False
    try:
        ws.clear()
        headers = ["Producto", "Tipo", "Variante", "SKU",
                   "Stock Actual", "Dias Inventario", "Ventas 60d",
                   "Unidades Sugeridas", "Estado Variante"]
        ws.append_row(headers)

        rows = []
        for _, row in sub_df.iterrows():
            stk  = int(row.get("Stock", 0))
            v60  = int(row.get("Ventas60d", 0))
            try:
                dias_n = float(str(row.get("DiasInv_n", row.get("DiasInv", 9999))))
            except:
                dias_n = 9999
            sug, _ = sugerir_cantidad(stk, v60, dias_n, "URGENTE")
            estado_var = "QUIEBRE" if stk == 0 else str(int(dias_n)) + " dias"
            rows.append([
                str(row.get("Producto", "")),
                str(row.get("Tipo", "")),
                str(row.get("Variante", "")),
                str(row.get("SKU", "")),
                stk,
                int(dias_n) if dias_n < 9999 else 0,
                v60,
                sug,
                estado_var,
            ])
        if rows:
            ws.append_rows(rows)

        ws.update("A1", [["_generado", datetime.now().strftime("%Y-%m-%d %H:%M"),
                          "_total", len(rows)]], value_input_option="RAW")
        ws.insert_row(headers, index=2)
        return True
    except Exception as e:
        st.error("Error escribiendo reporte: " + str(e))
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

    for col in ["Costo", "Precio Venta"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["_valor_costo"]  = df["Stock"] * df["Costo"]
    df["_valor_venta"]  = df["Stock"] * df["Precio Venta"]
    return df


def agrupar(df, estado):
    sub = df[df["_estado"] == estado]
    if sub.empty:
        return {}
    
    resultado_temp = {}
    
    for tipo, dt in sub.groupby("Tipo", sort=False):
        grupos = []
        for prod, g in dt.groupby("Producto", sort=False):
            g = g.copy()
            g["_dias_sort"] = pd.to_numeric(g["DiasInv"], errors="coerce").fillna(9999)
            g = g.sort_values("_dias_sort")
            grupos.append({
                "producto":     prod,
                "es_bs":        bool(g["_bs"].any()),
                "ventas_max":   float(g["Ventas60d"].max()),
                "ventas_total": float(g["Ventas60d"].sum()),
                "dias_min":     float(g["_dias_sort"].min()),
                "variantes":    g,
                "n":            len(g),
            })
            
        grupos = sorted(grupos, key=lambda x: (-x["ventas_total"], x["dias_min"], x["producto"]))
        
        ventas_cat = sum(x["ventas_total"] for x in grupos)
        dias_cat = min((x["dias_min"] for x in grupos), default=9999)
        
        resultado_temp[tipo] = {
            "grupos": grupos,
            "ventas_cat": ventas_cat,
            "dias_cat": dias_cat
        }
        
    tipos_ordenados = sorted(resultado_temp.items(), key=lambda item: (-item[1]["ventas_cat"], item[1]["dias_cat"]))
    resultado = {tipo: datos["grupos"] for tipo, datos in tipos_ordenados}
    
    return resultado


# ── HELPERS DE COLOR ─────────────────────────────────────────────────────────

def color_dias(estado):
    return {
        "REPROGRAMAR":   "#FF3B30",
        "ESTRELLA":      "#2D6A4F",
        "ALTA_ROTACION": "#FFB800",
        "SOBRESTOCK":    "#FF6B35",
        "SALUDABLE":     "#00C853",
        "MONITOREAR":    "#4488FF",
        "LIQUIDAR":      "#FF9500",
        "HUECO":         "#B8B0A4",
    }.get(estado, "#6B6456")


def color_borde(estado):
    return {
        "REPROGRAMAR":   "#FF3B30",
        "ESTRELLA":      "#2D6A4F",
        "ALTA_ROTACION": "#FFB800",
        "SOBRESTOCK":    "#FF6B35",
        "SALUDABLE":     "#00C853",
        "MONITOREAR":    "#4488FF",
        "LIQUIDAR":      "#FF9500",
        "HUECO":         "#B8B0A4",
    }.get(estado, "#B8B0A4")


# ── SUGERENCIA DE REPOSICION ─────────────────────────────────────────────────

DIAS_OBJETIVO    = 60   
DIAS_FABRICACION = 20  
MULTIPLO        = 6    

def sugerir_cantidad(stock, ventas60d, dias_inv, estado):
    try:
        s  = float(stock)
        v  = float(ventas60d)
        d  = float(dias_inv) if str(dias_inv).lower() not in ("inf","nan","") else 9999
    except:
        return 0, "Sin datos"

    if estado == "LIQUIDAR": return 0, "Liquidar — no reponer"
    if estado == "HUECO": return 0, "Sin actividad — no reponer"
    if v == 0: return 0, "Sin ventas — no reponer"

    ventas_dia = v / 60.0
    stock_al_recibir = max(0, s - ventas_dia * DIAS_FABRICACION)
    necesarias = (ventas_dia * DIAS_OBJETIVO) - stock_al_recibir

    if necesarias <= 0:
        cobertura = int(d)
        return 0, "Stock OK — " + str(cobertura) + " dias de cobertura"

    cantidad = int((int(necesarias) // MULTIPLO + 1) * MULTIPLO) if necesarias % MULTIPLO else int(necesarias)
    cantidad = max(MULTIPLO, cantidad)

    dias_con_pedido = int((s + cantidad) / ventas_dia) if ventas_dia > 0 else 9999
    return cantidad, str(dias_con_pedido) + " dias con pedido"


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

    st.markdown(
        "<div style='"
        "display:grid;"
        "grid-template-columns:2fr 1fr 1fr 1.2fr;"
        "gap:8px;"
        "padding:8px 14px;"
        "border-top:1px solid #D4CFC4;"
        "align-items:center;"
        "font-size:13px;"
        "background:" + bg + ";'>"
        "<div style='font-weight:500;'>" + var + "</div>"
        "<div style='font-family:DM Mono,monospace;color:#6B6456;font-size:12px;'>" + str(stock) + " u</div>"
        "<div style='font-family:Bebas Neue,sans-serif;font-size:22px;line-height:1;color:" + c_dias + ";'>" + dias_str + "</div>"
        "<div style='font-size:12px;color:#6B6456;'>" + str(v60) + " u</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if not mostrar_form:
        return

    try:
        dias_n = float(str(row.get("DiasInv_n", row.get("DiasInv", 9999))))
    except:
        dias_n = 9999
    sugerencia, sug_label = sugerir_cantidad(stock, v60, dias_n, estado)
    valor_default = max(1, sugerencia) if sugerencia > 0 else 12

    sug_color = "#FF3B30" if estado == "URGENTE" else "#FFB800" if estado == "EVALUAR" else "#4488FF"
    sug_texto = str(sugerencia) + " u sugeridas · " + sug_label if sugerencia > 0 else sug_label
    st.markdown(
        "<div style='font-size:10px;color:" + sug_color + ";font-family:DM Mono,monospace;"
        "letter-spacing:1px;padding:3px 14px 6px 14px;background:rgba(0,0,0,0.2);'>"
        "⟶ " + sug_texto +
        "</div>",
        unsafe_allow_html=True,
    )

    _uk = key_prefix + sku + "_" + uuid.uuid4().hex[:6]
    cf1, cf2, cf3, cf4 = st.columns([2, 2, 2, 2])
    with cf1:
        cant = st.number_input(
            "Cantidad", min_value=1, value=valor_default, step=MULTIPLO,
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
    prod_key  = "p" + uid
    tallas    = str(n) + " talla" + ("s" if n > 1 else "")
    bs_html   = " · <span style='color:#2D6A4F;font-size:10px;'>⭐ BS</span>" if es_bs else ""

    st.markdown(
        "<div style='"
        "background:#EDEAE0;"
        "border:1px solid #D4CFC4;"
        "border-left:3px solid " + c_borde + ";"
        "border-radius:8px 8px 0 0;"
        "padding:11px 14px;"
        "display:flex;"
        "align-items:center;"
        "gap:10px;'>"
        "<div style='font-weight:600;font-size:14px;flex:1;line-height:1.2;'>"
        + prod.upper() +
        "</div>"
        "<div style='font-size:11px;color:#6B6456;'>"
        + tallas + bs_html +
        "</div>"
        "</div>"
        "<div style='"
        "background:#EDEAE0;"
        "border:1px solid #D4CFC4;"
        "border-top:none;"
        "border-left:3px solid " + c_borde + ";"
        "display:grid;"
        "grid-template-columns:2fr 1fr 1fr 1.2fr;"
        "gap:8px;"
        "padding:5px 14px;"
        "font-size:9px;"
        "color:#6B6456;"
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

    for var_idx, (_, row) in enumerate(variantes.iterrows()):
        render_variante(row, mostrar_form, ordenes_df, client, key_prefix=prod_key + "_v" + str(var_idx) + "_")

    st.markdown(
        "<div style='"
        "background:#EDEAE0;"
        "border:1px solid #D4CFC4;"
        "border-top:none;"
        "border-left:3px solid " + c_borde + ";"
        "border-radius:0 0 8px 8px;"
        "height:6px;'>"
        "</div>",
        unsafe_allow_html=True,
    )

    if mostrar_form and n > 1:
        st.markdown(
            "<div style='"
            "background:rgba(212,255,0,0.03);"
            "border:1px solid rgba(212,255,0,0.12);"
            "border-radius:6px;"
            "padding:10px 14px 6px 14px;"
            "margin-top:4px;'>"
            "<div style='font-size:10px;color:#6B6456;letter-spacing:1.5px;"
            "text-transform:uppercase;margin-bottom:8px;'>"
            "Programar todas — " + str(n) + " tallas"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        sug_valores = []
        for _, vrow in variantes.iterrows():
            try: dias_vn = float(str(vrow.get("DiasInv_n", vrow.get("DiasInv", 9999))))
            except: dias_vn = 9999
            sv, _ = sugerir_cantidad(vrow.get("Stock",0), vrow.get("Ventas60d",0), dias_vn, estado)
            if sv > 0: sug_valores.append(sv)
        sug_todas = int(sum(sug_valores) / len(sug_valores)) if sug_valores else 12
        sug_todas = max(MULTIPLO, (sug_todas // MULTIPLO) * MULTIPLO)

        _pk = prod_key + "_" + uuid.uuid4().hex[:6]
        pc1, pc2, pc3 = st.columns([2, 2, 3])
        with pc1:
            cant_all = st.number_input(
                "Cantidad por talla", min_value=1, value=sug_todas, step=MULTIPLO,
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


# ── VISTA DASHBOARD ───────────────────────────────────────────────────────────

def vista_dashboard(df, ordenes_df):
    if df.empty:
        st.warning("Sin datos. Ejecuta actualizarTodo en Apps Script.")
        return

    # --- INICIO MAGIA DE SUCURSALES Y TIPO DE STOCK ---
    cols_sucursales = [c for c in df.columns if str(c).startswith("Stock ") and c not in ["Stock Actual", "Stock Minimo", "Stock", "Stock Fisico Total"]]
    
    if cols_sucursales:
        nombres_sucursales = [c.replace("Stock ", "") for c in cols_sucursales]
        
        # UI: Controles en dos columnas
        c1, c2 = st.columns(2)
        with c1:
            sucursal_sel = st.selectbox("📍 Filtrar por sucursal:", ["Todas las sucursales"] + nombres_sucursales)
        with c2:
            tipo_inv = st.radio("📊 Tipo de inventario:", ["Disponible (Venta/Reposición)", "Físico (Contable/Real)"], horizontal=True)
            
        df = df.copy()
        
        # Determinar qué columna de Google Sheets usar según lo que elija el usuario
        if sucursal_sel == "Todas las sucursales":
            if "Físico" in tipo_inv:
                col_usar = "Stock Fisico Total" if "Stock Fisico Total" in df.columns else "Stock"
            else:
                col_usar = "Stock" # El disponible global
        else:
            if "Físico" in tipo_inv:
                col_usar = "Fisico " + sucursal_sel
            else:
                col_usar = "Stock " + sucursal_sel
                
        # Inyectamos la columna elegida para que todo el dashboard la use
        df["Stock"] = pd.to_numeric(df.get(col_usar, df["Stock"]), errors="coerce").fillna(0)
        
        # ---> EL NUEVO AJUSTE: FILTRAR SKUS VACÍOS DE LA SUCURSAL <---
        if sucursal_sel != "Todas las sucursales":
            # Nos quedamos solo con los productos que tienen al menos 1 unidad en esta sucursal
            df = df[df["Stock"] > 0]
            
        df["_valor_costo"] = df["Stock"] * df["Costo"]
        df["_valor_venta"] = df["Stock"] * df["Precio Venta"]
        
        st.markdown("<hr style='border-color:#D4CFC4;margin:10px 0 20px 0;'>", unsafe_allow_html=True)
    # --- FIN MAGIA DE SUCURSALES ---

    tiene_costos = df["Costo"].sum() > 0
    tiene_precios = df["Precio Venta"].sum() > 0

    # ── HEADER ────────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-family:Bebas Neue,sans-serif;font-size:26px;"
        "letter-spacing:3px;color:#1A1A14;margin-bottom:4px;'>DASHBOARD</div>"
        "<div style='font-size:11px;color:#6B6456;letter-spacing:1px;"
        "text-transform:uppercase;margin-bottom:20px;'>"
        "Vision general del inventario · " + datetime.now().strftime("%d/%m/%Y %H:%M") +
        "</div>",
        unsafe_allow_html=True,
    )

    # ── METRICAS PRINCIPALES ──────────────────────────────────────────────────
    total_skus     = len(df)
    total_prods    = df["Producto"].nunique()
    total_stock    = int(df["Stock"].sum())
    reprogramar_n  = int(df[df["_estado"] == "REPROGRAMAR"]["Producto"].nunique())
    estrella_n     = int(df[df["_estado"] == "ESTRELLA"]["Producto"].nunique())
    valor_costo    = df["_valor_costo"].sum()
    valor_venta    = df["_valor_venta"].sum()

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("SKUs totales", total_skus)
    with c2: st.metric("Productos", total_prods)
    with c3: st.metric("Unidades en stock", f"{total_stock:,}")
    with c4: st.metric("A reprogramar", reprogramar_n)

    if tiene_costos or tiene_precios:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Valor inventario (costo)",
                      "$" + f"{valor_costo:,.0f}" if valor_costo > 0 else "—")
        with c2:
            st.metric("Valor inventario (venta)",
                      "$" + f"{valor_venta:,.0f}" if valor_venta > 0 else "—")
        with c3:
            margen = ((valor_venta - valor_costo) / valor_costo * 100) if valor_costo > 0 else 0
            st.metric("Margen potencial", f"{margen:.1f}%" if margen > 0 else "—")

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ── FILA 1: PASTEL DE SEGMENTOS + STOCK CRITICO ───────────────────────────
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown(
            "<div style='font-family:Bebas Neue,sans-serif;font-size:14px;"
            "letter-spacing:2px;color:#6B6456;margin-bottom:8px;'>SEGMENTOS</div>",
            unsafe_allow_html=True,
        )
        # Contar productos por segmento
        seg_counts = df.groupby("_estado")["Producto"].nunique().reset_index()
        seg_counts.columns = ["Estado", "Productos"]
        seg_counts = seg_counts[seg_counts["Productos"] > 0]

        colores_seg = {
            "REPROGRAMAR":   "#FF3B30",
            "ESTRELLA":      "#2D6A4F",
            "ALTA_ROTACION": "#FFB800",
            "SALUDABLE":     "#00C853",
            "LIQUIDAR":      "#FF6B35",
            "HUECO":         "#B8B0A4",
        }
        labels_seg = {
            "REPROGRAMAR":   "Reprogramar",
            "ESTRELLA":      "Estrella",
            "ALTA_ROTACION": "Alta Rotacion",
            "SALUDABLE":     "Saludable",
            "LIQUIDAR":      "Liquidar",
            "HUECO":         "Hueco",
        }

        colores = [colores_seg.get(e, "#6B6456") for e in seg_counts["Estado"]]
        labels  = [labels_seg.get(e, e) for e in seg_counts["Estado"]]

        fig_pie = go.Figure(go.Pie(
            labels=labels,
            values=seg_counts["Productos"],
            hole=0.55,
            marker=dict(colors=colores, line=dict(color="#F5F0E8", width=2)),
            textinfo="label+percent",
            textfont=dict(size=11, color="#1A1A14"),
            hovertemplate="<b>%{label}</b><br>%{value} productos<br>%{percent}<extra></extra>",
        ))
        fig_pie.update_layout(
            paper_bgcolor="#EDEAE0",
            plot_bgcolor="#EDEAE0",
            font=dict(color="#1A1A14", family="DM Sans"),
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
            showlegend=False,
            annotations=[dict(
                text="<b>" + str(total_prods) + "</b><br><span style='font-size:10px'>productos</span>",
                x=0.5, y=0.5, font_size=16, showarrow=False,
                font=dict(color="#1A1A14"),
            )],
        )
        st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})

    with col_right:
        st.markdown(
            "<div style='font-family:Bebas Neue,sans-serif;font-size:14px;"
            "letter-spacing:2px;color:#6B6456;margin-bottom:8px;'>STOCK CRITICO — TOP 10</div>",
            unsafe_allow_html=True,
        )
        
        criticos = df[df["_estado"] == "REPROGRAMAR"].copy()
        criticos = criticos.groupby("Producto").agg(
            dias_min=("DiasInv_n", "min"),
            stock_total=("Stock", "sum"),
            ventas=("Ventas60d", "sum"),
        ).reset_index()
        criticos = criticos.sort_values("dias_min").head(10)

        if criticos.empty:
            st.markdown(
                "<div style='text-align:center;padding:40px;color:#6B6456;'>"
                "Sin productos criticos</div>",
                unsafe_allow_html=True,
            )
        else:
            fig_bar = go.Figure(go.Bar(
                x=criticos["dias_min"],
                y=criticos["Producto"],
                orientation="h",
                marker=dict(
                    color=criticos["dias_min"],
                    colorscale=[[0, "#FF3B30"], [0.5, "#FFB800"], [1, "#FFB800"]],
                    showscale=False,
                ),
                text=criticos["dias_min"].astype(str) + "d",
                textposition="outside",
                textfont=dict(size=10, color="#1A1A14"),
                hovertemplate="<b>%{y}</b><br>%{x} dias<extra></extra>",
            ))
            fig_bar.update_layout(
                paper_bgcolor="#EDEAE0",
                plot_bgcolor="#EDEAE0",
                font=dict(color="#1A1A14", family="DM Sans"),
                margin=dict(t=10, b=10, l=180, r=60),
                height=310,
                xaxis=dict(
                    showgrid=True, gridcolor="#D4CFC4",
                    zeroline=False, showticklabels=False,
                    range=[0, max(criticos["dias_min"].max() * 1.3, 35)],
                ),
                yaxis=dict(showgrid=False, tickfont=dict(size=10), automargin=True),
                shapes=[dict(
                    type="line", x0=LEAD_TIME_DIAS, x1=LEAD_TIME_DIAS,
                    y0=-0.5, y1=len(criticos) - 0.5,
                    line=dict(color="#FF3B30", width=1, dash="dot"),
                )],
                annotations=[dict(
                    x=LEAD_TIME_DIAS, y=len(criticos) - 0.5,
                    text="Lead time", showarrow=False,
                    font=dict(size=8, color="#CC2200"),
                    xanchor="left",
                )],
            )
            st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    # ── FILA 2: TOP 10 VENTAS + BARRAS POR CATEGORIA ─────────────────────────
    col_left2, col_right2 = st.columns([1, 1])

    with col_left2:
        top_c1, top_c2, top_c3 = st.columns([3, 1, 1])
        with top_c1:
            st.markdown(
                "<div style='font-family:Bebas Neue,sans-serif;font-size:14px;"
                "letter-spacing:2px;color:#6B6456;margin-bottom:8px;'>TOP VENTAS 60D</div>",
                unsafe_allow_html=True,
            )
        with top_c2:
            n_top = st.select_slider("", options=[10, 15, 20, 30, 50], value=10,
                                     key="slider_top_ventas",
                                     label_visibility="collapsed")
        with top_c3:
            vista_sku = st.toggle("Por SKU", key="toggle_top_sku", value=False)

        if vista_sku:
            top_data = df[["Producto", "Variante", "SKU", "Ventas60d", "_estado"]].copy()
            top_data = top_data.sort_values("Ventas60d", ascending=True).tail(n_top)
            top_data["etiqueta"] = top_data["SKU"] + "  " + top_data["Variante"].str[:18]
            y_vals  = top_data["etiqueta"].tolist()
            x_vals  = top_data["Ventas60d"].tolist()
            estados = top_data["_estado"].tolist()
            hover   = [
                "<b>" + row["Producto"] + "</b><br>SKU: " + row["SKU"] +
                "<br>Variante: " + row["Variante"] +
                "<br>" + str(int(row["Ventas60d"])) + " u<extra></extra>"
                for _, row in top_data.iterrows()
            ]
        else:
            top_data = df.groupby("Producto").agg(
                Ventas60d=("Ventas60d", "sum"),
                _estado=("_estado", "first"),
            ).reset_index()
            top_data = top_data.sort_values("Ventas60d", ascending=True).tail(n_top)
            y_vals  = top_data["Producto"].tolist()
            x_vals  = top_data["Ventas60d"].tolist()
            estados = top_data["_estado"].tolist()
            hover   = [
                "<b>" + p + "</b><br>" + str(int(v)) + " u<extra></extra>"
                for p, v in zip(y_vals, x_vals)
            ]

        colores_top = [
            "#2D6A4F" if e == "ESTRELLA" else
            "#FFB800" if e == "ALTA_ROTACION" else
            "#FF3B30" if e == "REPROGRAMAR" else "#4488FF"
            for e in estados
        ]

        fig_top = go.Figure(go.Bar(
            x=x_vals, y=y_vals,
            orientation="h",
            marker=dict(color=colores_top),
            text=[str(int(v)) + " u" for v in x_vals],
            textposition="outside",
            textfont=dict(size=10, color="#1A1A14"),
            hovertemplate=hover,
        ))
        altura_top = max(340, n_top * 34)
        fig_top.update_layout(
            paper_bgcolor="#EDEAE0",
            plot_bgcolor="#EDEAE0",
            font=dict(color="#1A1A14", family="DM Sans"),
            margin=dict(t=10, b=10, l=240, r=70),
            height=altura_top,
            xaxis=dict(showgrid=True, gridcolor="#D4CFC4", zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, tickfont=dict(size=10), automargin=True),
        )
        st.plotly_chart(fig_top, use_container_width=True, config={"displayModeBar": False})

    with col_right2:
        st.markdown(
            "<div style='font-family:Bebas Neue,sans-serif;font-size:14px;"
            "letter-spacing:2px;color:#6B6456;margin-bottom:8px;'>STOCK POR CATEGORIA</div>",
            unsafe_allow_html=True,
        )
        por_tipo = df.groupby("Tipo").agg(
            stock=("Stock", "sum"),
            valor_costo=("_valor_costo", "sum"),
            valor_venta=("_valor_venta", "sum"),
            productos=("Producto", "nunique"),
        ).reset_index().sort_values("stock", ascending=True)

        if tiene_costos:
            x_vals  = por_tipo["valor_costo"]
            x_label = "Valor (costo)"
            text_v  = ["$" + f"{v:,.0f}" for v in por_tipo["valor_costo"]]
        else:
            x_vals  = por_tipo["stock"]
            x_label = "Unidades"
            text_v  = [str(int(v)) + " u" for v in por_tipo["stock"]]

        fig_cat = go.Figure(go.Bar(
            x=x_vals,
            y=por_tipo["Tipo"].str[:20],
            orientation="h",
            marker=dict(color="#4488FF", opacity=0.8),
            text=text_v,
            textposition="outside",
            textfont=dict(size=9,  color="#1A1A14"),
            hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
        ))
        fig_cat.update_layout(
            paper_bgcolor="#EDEAE0",
            plot_bgcolor="#EDEAE0",
            font=dict(color="#1A1A14", family="DM Sans"),
            margin=dict(t=10, b=10, l=10, r=80),
            height=300,
            xaxis=dict(showgrid=True, gridcolor="#D4CFC4", zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, tickfont=dict(size=9)),
        )
        st.plotly_chart(fig_cat, use_container_width=True, config={"displayModeBar": False})

    # ── FILA 3: VALOR DE INVENTARIO (si hay datos) + TABLA RESUMEN ───────────
    if tiene_costos or tiene_precios:
        st.markdown(
            "<div style='font-family:Bebas Neue,sans-serif;font-size:14px;"
            "letter-spacing:2px;color:#6B6456;margin:8px 0;'>VALOR DE INVENTARIO POR CATEGORIA</div>",
            unsafe_allow_html=True,
        )
        por_tipo_v = df.groupby("Tipo").agg(
            valor_costo=("_valor_costo", "sum"),
            valor_venta=("_valor_venta", "sum"),
        ).reset_index().sort_values("valor_venta", ascending=True)

        n_cats  = len(por_tipo_v)
        altura  = max(320, n_cats * 38)
        cats    = por_tipo_v["Tipo"].tolist()
        costos  = por_tipo_v["valor_costo"].tolist()
        ventas  = por_tipo_v["valor_venta"].tolist()

        fig_val = go.Figure()

        fig_val.add_trace(go.Bar(
            name="Precio venta",
            x=ventas,
            y=cats,
            orientation="h",
            marker=dict(color="#2D6A4F", opacity=0.85),
            text=["$" + f"{v/1e6:.1f}M" if v >= 1e6 else "$" + f"{v:,.0f}" for v in ventas],
            textposition="outside",
            textfont=dict(size=9, color="#2D6A4F"),
            hovertemplate="<b>%{y}</b><br>Venta: $%{x:,.0f}<extra></extra>",
        ))

        fig_val.add_trace(go.Bar(
            name="Costo",
            x=costos,
            y=cats,
            orientation="h",
            marker=dict(color="#4488FF", opacity=0.9),
            text=["$" + f"{v/1e6:.1f}M" if v >= 1e6 else "$" + f"{v:,.0f}" for v in costos],
            textposition="inside",
            textfont=dict(size=8, color="#1A1A14"),
            hovertemplate="<b>%{y}</b><br>Costo: $%{x:,.0f}<extra></extra>",
        ))

        fig_val.update_layout(
            barmode="overlay",
            paper_bgcolor="#EDEAE0",
            plot_bgcolor="#EDEAE0",
            font=dict(color="#1A1A14", family="DM Sans"),
            margin=dict(t=30, b=20, l=160, r=90),
            height=altura,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.01, x=0,
                font=dict(size=10), bgcolor="rgba(0,0,0,0)",
                traceorder="reversed",
            ),
            xaxis=dict(
                showgrid=True, gridcolor="#D4CFC4", zeroline=False,
                tickprefix="$", tickformat=",.0f", tickfont=dict(size=9),
            ),
            yaxis=dict(
                showgrid=False, tickfont=dict(size=10),
                automargin=False, categoryorder="array",
                categoryarray=cats,
            ),
        )
        st.plotly_chart(fig_val, use_container_width=True, config={"displayModeBar": False})

    # ── TABLA RESUMEN POR SEGMENTO ────────────────────────────────────────────
    st.markdown(
        "<div style='font-family:Bebas Neue,sans-serif;font-size:14px;"
        "letter-spacing:2px;color:#6B6456;margin:8px 0;'>RESUMEN POR SEGMENTO</div>",
        unsafe_allow_html=True,
    )
    resumen = []
    for estado in ORDEN_SIDEBAR:
        cfg  = ESTADOS[estado]
        sub  = df[df["_estado"] == estado]
        if sub.empty:
            continue
        row = {
            "Segmento":  cfg["icon"] + " " + cfg["label"],
            "Productos": sub["Producto"].nunique(),
            "SKUs":      len(sub),
            "Stock total": int(sub["Stock"].sum()),
            "Ventas 60d": int(sub["Ventas60d"].sum()),
        }
        if tiene_costos:
            row["Valor costo"] = "$" + f"{sub['_valor_costo'].sum():,.0f}"
        if tiene_precios:
            row["Valor venta"] = "$" + f"{sub['_valor_venta'].sum():,.0f}"
        resumen.append(row)

    df_resumen = pd.DataFrame(resumen)
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    if not tiene_costos:
        st.markdown(
            "<div style='font-size:10px;color:#B8B0A4;margin-top:8px;'>"
            "* Valor de inventario no disponible. Agrega las columnas Costo y Precio Venta "
            "al Sheet via Apps Script para verlo.</div>",
            unsafe_allow_html=True,
        )


# ── SIDEBAR ──────────────────────────────────────────────────────────────────

def render_sidebar(conteos):
    with st.sidebar:
        st.markdown(
            "<div style='padding:16px 4px 14px 4px;border-bottom:1px solid #D4CFC4;margin-bottom:10px;'>"
            "<div style='display:flex;align-items:center;gap:10px;'>"
            "<div style='background:#2D6A4F;width:30px;height:30px;border-radius:4px;"
            "display:flex;align-items:center;justify-content:center;"
            "font-family:Bebas Neue,sans-serif;font-size:15px;color:#F5F0E8;flex-shrink:0;'>LV</div>"
            "<div>"
            "<div style='font-family:Bebas Neue,sans-serif;font-size:16px;letter-spacing:2px;"
            "color:#1A1A14;line-height:1;'>LINEA VIVA</div>"
            "<div style='font-size:9px;color:#6B6456;letter-spacing:1px;text-transform:uppercase;'>"
            "Terret · Inventario</div>"
            "</div>"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        vista_actual = st.session_state.get("vista", "DASHBOARD")

        active_db = vista_actual == "DASHBOARD"
        lbl_db = "📊  Dashboard" + ("  ←" if active_db else "")
        if st.button(lbl_db, key="nav_DASHBOARD"):
            st.session_state.vista = "DASHBOARD"
            st.rerun()

        st.markdown("<hr style='border-color:#D4CFC4;margin:6px 0;'>", unsafe_allow_html=True)

        for estado in ORDEN_SIDEBAR:
            cfg = ESTADOS[estado]
            cnt   = conteos.get(estado, 0)
            icon  = cfg["icon"]
            label = cfg["label"]
            btn_label = icon + "  " + label + "   " + str(cnt)
            if st.button(btn_label, key="nav_" + estado):
                st.session_state.vista = estado
                st.rerun()

        st.markdown("<hr style='border-color:#D4CFC4;margin:6px 0;'>", unsafe_allow_html=True)

        if st.button("📋  Ordenes", key="nav_ordenes"):
            st.session_state.vista = "ORDENES"
            st.rerun()

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        if st.button("🔄  Refrescar pantalla", key="btn_refresh"):
            st.cache_data.clear()
            st.rerun()

        if st.button("⚡ Sincronizar Shopify", key="btn_sync"):
            if not WEBAPP_URL:
                st.error("Falta la WEBAPP_URL en los secrets de Streamlit.")
            else:
                with st.spinner("Sincronizando con Shopify... esto puede tomar 1 o 2 minutos."):
                    try:
                        respuesta = requests.post(WEBAPP_URL, json={"accion": "actualizarTodo"}, timeout=150)
                        
                        if respuesta.status_code == 200:
                            data = respuesta.json()
                            if data.get("ok"):
                                st.success("¡Sincronización exitosa!")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error("Error en Apps Script: " + data.get("error", "Desconocido"))
                        else:
                            st.error("Error de conexión con Google.")
                    except requests.exceptions.Timeout:
                        st.warning("La sincronización está tomando mucho tiempo, pero sigue en proceso. Refresca la pantalla en un minuto.")
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.markdown(
            "<div style='margin-top:8px;font-size:9px;color:#C8C2B4;padding:0 4px;'>"
            + datetime.now().strftime("%d/%m/%Y %H:%M") +
            "</div>",
            unsafe_allow_html=True,
        )


# ── VISTA ESTADO ─────────────────────────────────────────────────────────────

def vista_estado(df, ordenes_df, client, estado):
    cfg   = ESTADOS[estado]
    color = cfg["color"]
    mostrar_form = estado == "REPROGRAMAR"

    st.markdown(
        "<div style='"
        "background:#EDEAE0;"
        "border:1px solid #D4CFC4;"
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
        "<div style='font-size:12px;color:#6B6456;margin-top:2px;'>" + cfg["desc"] + "</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    sub = df[df["_estado"] == estado]

    if sub.empty:
        st.markdown(
            "<div style='text-align:center;padding:60px 0;color:#6B6456;'>"
            "<div style='font-size:36px;margin-bottom:12px;'>" + cfg["icon"] + "</div>"
            "<div style='font-family:Bebas Neue,sans-serif;font-size:18px;letter-spacing:2px;'>"
            "Sin productos en este estado</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    c1, c2, c3 = st.columns(3)
    with c1: st.metric("SKUs",       len(sub))
    with c2: st.metric("Productos",  sub["Producto"].nunique())
    with c3: st.metric("Categorias", sub["Tipo"].nunique())

    t1, t2 = st.columns([3, 2])
    with t1:
        buscar = st.text_input("Buscar", placeholder="Buscar producto...", label_visibility="collapsed")
    with t2:
        tipos_disp = sorted(sub["Tipo"].dropna().unique().tolist())
        tipo_sel = st.selectbox("Categoria", ["Todas"] + tipos_disp, label_visibility="collapsed")

    if estado == "REPROGRAMAR":
        prods_u = sub["Producto"].unique()
        n_urgentes = len(prods_u)

        st.markdown(
            "<div style='margin-bottom:8px;'>",
            unsafe_allow_html=True,
        )
        if st.button("📧  ENVIAR ALERTA — " + str(n_urgentes) + " productos a reprogramar", key="btn_alerta_email"):
            with st.spinner("Preparando reporte y enviando email..."):
                ok_sheet = escribir_reporte(client, sub)
                if not ok_sheet:
                    st.error("No se pudo escribir el reporte en Sheets.")
                elif not WEBAPP_URL:
                    st.warning(
                        "Datos escritos en Sheets correctamente. "
                        "Falta configurar WEBAPP_URL en secrets para enviar el email automaticamente."
                    )
                else:
                    try:
                        ws_rep = get_ws(client, HOJA_REPORTE)
                        if ws_rep:
                            ws_rep.update("A1", [["ENVIAR"]])
                            st.success(
                                "✅ Reporte listo — Apps Script enviará el email a " +
                                ALERTA_EMAIL + " en los proximos segundos."
                            )
                    except Exception as e:
                        st.error("Error activando trigger: " + str(e))
        st.markdown("</div>", unsafe_allow_html=True)

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

    prod_counter = [0] 
    for tipo, grupos in grupos_tipo.items():
        st.markdown(
            "<div style='"
            "font-family:DM Mono,monospace;"
            "font-size:9px;"
            "letter-spacing:3px;"
            "color:#B8B0A4;"
            "text-transform:uppercase;"
            "padding:20px 0 6px 0;"
            "border-bottom:1px solid #D4CFC4;"
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
        "letter-spacing:3px;color:#1A1A14;margin-bottom:16px;'>"
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
        st.session_state.vista = "DASHBOARD"

    render_sidebar(conteos)

    vista = st.session_state.get("vista", "DASHBOARD")

    if vista == "DASHBOARD":
        vista_dashboard(df, ordenes)
    elif vista == "ORDENES":
        vista_ordenes(ordenes, client)
    elif vista in ESTADOS:
        if df.empty:
            st.warning("Sin datos. Ejecuta actualizarTodo en Apps Script.")
        else:
            vista_estado(df, ordenes, client, vista)

    st.markdown(
        "<div style='font-size:10px;color:#D4CFC4;text-align:right;margin-top:40px;'>"
        "LINEA VIVA · TERRET · " + datetime.now().strftime("%d.%m.%Y %H:%M") + "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
