"""
LÍNEA VIVA — Sistema de Reposición de Inventario
Térret | Streamlit + Google Sheets
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Línea Viva · Térret",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SPREADSHEET_ID   = "1M6bCu6fSXE1ReYBqBvC78zdX-0fbGuCdmSn6JdgUv9s"
HOJA_INVENTARIO  = "Dashboard_Inventario"
HOJA_ORDENES     = "Ordenes_Produccion"
ALERTA_EMAIL     = "mercadeo@terretsports.com"
FABRICACION_DIAS = 20

# ─── ESTILOS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background-color: #0A0A14 !important; color: #E8E8F0 !important;
}
[data-testid="stAppViewContainer"] > .main { background-color: #0A0A14; }
[data-testid="stHeader"] { background: #0A0A14; border-bottom: 1px solid #1A1A2E; }
section[data-testid="stSidebar"] { background: #0D0D1A !important; }
h1, h2, h3 { font-family: 'Bebas Neue', sans-serif !important; letter-spacing: 2px; }

.stButton > button {
    background: #D4FF00 !important; color: #0A0A14 !important;
    font-family: 'Bebas Neue', sans-serif !important; font-size: 16px !important;
    letter-spacing: 2px !important; border: none !important;
    border-radius: 4px !important; padding: 10px 24px !important;
    transition: all 0.15s ease; width: 100%;
}
.stButton > button:hover { background: #BFEA00 !important; transform: translateY(-1px); }

.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input {
    background: #12121F !important; border: 1px solid #2A2A3E !important;
    color: #E8E8F0 !important; border-radius: 4px !important;
}

[data-testid="stMetric"] {
    background: #12121F; border: 1px solid #1E1E30; border-radius: 8px; padding: 16px 20px;
}
[data-testid="stMetricValue"] { color: #D4FF00 !important; font-family: 'Bebas Neue', sans-serif !important; font-size: 2rem !important; }
[data-testid="stMetricLabel"] { color: #6B6B8A !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 1.5px; }

.stTabs [data-baseweb="tab-list"] {
    background: #0D0D1A; border-radius: 8px; padding: 4px; gap: 4px; border: 1px solid #1A1A2E;
}
.stTabs [data-baseweb="tab"] {
    background: transparent; color: #6B6B8A; font-family: 'Bebas Neue', sans-serif;
    font-size: 15px; letter-spacing: 1.5px; border-radius: 6px; padding: 8px 20px;
}
.stTabs [aria-selected="true"] { background: #D4FF00 !important; color: #0A0A14 !important; }
hr { border-color: #1A1A2E !important; }

.card-critico {
    background: linear-gradient(135deg, #1A0A0A, #200D0D);
    border: 1px solid #FF3B30; border-left: 4px solid #FF3B30;
    border-radius: 8px; padding: 20px; margin-bottom: 12px;
}
.card-alerta {
    background: linear-gradient(135deg, #1A1400, #1F1800);
    border: 1px solid #FFB800; border-left: 4px solid #FFB800;
    border-radius: 8px; padding: 20px; margin-bottom: 12px;
}
.card-ok {
    background: linear-gradient(135deg, #0A1A0A, #0D1F0D);
    border: 1px solid #30D158; border-left: 4px solid #30D158;
    border-radius: 8px; padding: 20px; margin-bottom: 12px;
}
.badge-critico { background:#FF3B30; color:white; font-size:10px; font-weight:700; padding:3px 10px; border-radius:20px; text-transform:uppercase; letter-spacing:1px; }
.badge-alerta  { background:#FFB800; color:#0A0A14; font-size:10px; font-weight:700; padding:3px 10px; border-radius:20px; text-transform:uppercase; letter-spacing:1px; }
.badge-ok      { background:#30D158; color:#0A0A14; font-size:10px; font-weight:700; padding:3px 10px; border-radius:20px; text-transform:uppercase; letter-spacing:1px; }
</style>
""", unsafe_allow_html=True)


# ─── LOGIN ──────────────────────────────────────────────────────────────────

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.markdown("""
        <div style='max-width:380px;margin:80px auto;text-align:center;'>
            <div style='background:#D4FF00;width:56px;height:56px;border-radius:8px;
                        display:flex;align-items:center;justify-content:center;
                        font-family:Bebas Neue,sans-serif;font-size:28px;color:#0A0A14;
                        margin:0 auto 24px auto;'>LV</div>
            <div style='font-family:Bebas Neue,sans-serif;font-size:32px;letter-spacing:3px;color:#E8E8F0;margin-bottom:4px;'>LÍNEA VIVA</div>
            <div style='font-size:12px;color:#6B6B8A;letter-spacing:2px;text-transform:uppercase;margin-bottom:40px;'>Térret · Inventario</div>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            if st.button("ENTRAR"):
                if password == st.secrets.get("APP_PASSWORD", ""):
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta.")
        st.stop()


# ─── GOOGLE SHEETS ───────────────────────────────────────────────────────────

@st.cache_resource(ttl=300)
def conectar_sheets():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=scope
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error conectando a Google Sheets: {e}")
        return None


def get_worksheet(client, nombre):
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
        st.error(f"Error accediendo a '{nombre}': {e}")
        return None


@st.cache_data(ttl=120)
def leer_inventario(_client):
    ws = get_worksheet(_client, HOJA_INVENTARIO)
    if not ws:
        return pd.DataFrame()
    records = ws.get_all_records()
    return pd.DataFrame(records) if records else pd.DataFrame()


@st.cache_data(ttl=60)
def leer_ordenes(_client):
    ws = get_worksheet(_client, HOJA_ORDENES)
    if not ws:
        return pd.DataFrame()
    records = ws.get_all_records()
    return pd.DataFrame(records) if records else pd.DataFrame(
        columns=["ID","Fecha","SKU","Producto","Variante","Cantidad","Fecha_Limite","Estado","Notas"]
    )


def guardar_orden(client, orden):
    ws = get_worksheet(client, HOJA_ORDENES)
    if not ws:
        return False
    try:
        ws.append_row([
            orden["id"], orden["fecha"], orden["sku"], orden["producto"],
            orden["variante"], orden["cantidad"], orden["fecha_limite"],
            "pendiente", orden["notas"]
        ])
        return True
    except Exception as e:
        st.error(f"Error guardando orden: {e}")
        return False


def actualizar_estado_orden(client, orden_id, nuevo_estado):
    ws = get_worksheet(client, HOJA_ORDENES)
    if not ws:
        return False
    try:
        cell = ws.find(orden_id)
        if cell:
            ws.update_cell(cell.row, 8, nuevo_estado)
            return True
    except Exception as e:
        st.error(f"Error actualizando: {e}")
    return False


def generar_id_orden(ordenes_df):
    if ordenes_df.empty or "ID" not in ordenes_df.columns:
        return "OP-001"
    numeros = ordenes_df["ID"].dropna().astype(str).str.extract(r"(\d+)").dropna().astype(int)
    return f"OP-{int(numeros.max().item())+1:03d}" if not numeros.empty else "OP-001"


# ─── LÓGICA ─────────────────────────────────────────────────────────────────

def clasificar_urgencia(decision):
    d = str(decision).upper()
    if "QUIEBRE" in d or "REPROGRAMAR" in d: return "CRÍTICO"
    if "EVALUAR" in d or "MONITOREAR" in d:  return "ALERTA"
    if "SALUDABLE" in d:                      return "OK"
    return "INFO"


def enriquecer(df):
    if df.empty:
        return df
    df = df.copy()
    col_decision = "🧠 Decisión" if "🧠 Decisión" in df.columns else df.columns[9] if len(df.columns) > 9 else df.columns[-1]
    df["_urgencia"] = df[col_decision].apply(clasificar_urgencia)
    df["_orden"]    = df["_urgencia"].map({"CRÍTICO":0,"ALERTA":1,"OK":2,"INFO":3})
    df["_decision_col"] = col_decision
    return df.sort_values("_orden")


# ─── VISTAS ──────────────────────────────────────────────────────────────────

def render_header(n_criticos, n_alertas):
    badge = ""
    if n_criticos: badge += f"<span class='badge-critico'>⚡ {n_criticos} críticos</span> "
    if n_alertas:  badge += f"<span class='badge-alerta'>⚠ {n_alertas} en alerta</span>"
    if not n_criticos and not n_alertas: badge = "<span class='badge-ok'>✓ Todo OK</span>"

    st.markdown(f"""
    <div style='display:flex;align-items:center;gap:16px;padding:8px 0 28px 0;
                border-bottom:1px solid #1A1A2E;margin-bottom:32px;'>
        <div style='background:#D4FF00;width:44px;height:44px;border-radius:6px;
                    display:flex;align-items:center;justify-content:center;
                    font-family:Bebas Neue,sans-serif;font-size:22px;color:#0A0A14;flex-shrink:0;'>LV</div>
        <div>
            <div style='font-family:Bebas Neue,sans-serif;font-size:26px;letter-spacing:3px;
                        color:#E8E8F0;line-height:1;'>LÍNEA VIVA</div>
            <div style='font-size:11px;color:#6B6B8A;letter-spacing:2px;text-transform:uppercase;'>Reposición · Térret</div>
        </div>
        <div style='margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap;'>{badge}</div>
    </div>
    """, unsafe_allow_html=True)


def render_card(row, clase, badge_html, ordenes_df, client):
    # Detectar nombres de columna flexiblemente
    def get(row, *keys):
        for k in keys:
            if k in row.index and row[k] not in [None, ""]:
                return row[k]
        return "—"

    producto = get(row, "Producto", "producto")
    variante = get(row, "Variante", "variante")
    sku      = get(row, "SKU", "sku")
    stock    = get(row, "Stock Actual", "Stock_Actual", "stock_actual")
    dias     = get(row, "Días de Inventario", "Dias_Inventario", "dias_inventario")
    ventas   = get(row, "Ventas 60d", "Ventas_60d", "ventas_60d")
    decision = get(row, "🧠 Decisión", "Decision", "decision")

    try:
        dias_num   = int(float(str(dias)))
        color_dias = "#FF3B30" if dias_num <= 15 else "#FFB800" if dias_num <= 30 else "#30D158"
        dias_str   = str(dias_num)
    except:
        color_dias = "#6B6B8A"
        dias_str   = str(dias)

    st.markdown(f"""
    <div class="{clase}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
            <div>
                <div style="font-family:'Bebas Neue',sans-serif;font-size:20px;letter-spacing:1.5px;color:#E8E8F0;">{producto}</div>
                <div style="font-size:11px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">{sku} · {variante}</div>
                <div style="margin-top:10px;">{badge_html}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-family:'Bebas Neue',sans-serif;font-size:32px;color:{color_dias};">{dias_str}</div>
                <div style="font-size:10px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">días de inv.</div>
            </div>
        </div>
        <div style="display:flex;gap:28px;margin-top:14px;flex-wrap:wrap;">
            <div><div style="font-size:10px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">Stock</div>
                 <div style="font-size:18px;font-weight:600;">{stock} u</div></div>
            <div><div style="font-size:10px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">Ventas 60d</div>
                 <div style="font-size:18px;font-weight:600;">{int(float(str(ventas))) if str(ventas).replace('.','').isdigit() else ventas} u</div></div>
            <div><div style="font-size:10px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">Decisión</div>
                 <div style="font-size:13px;font-weight:600;">{decision}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander(f"➕  PROGRAMAR — {str(producto).upper()} / {str(variante).upper()}"):
        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            cantidad = st.number_input("Cantidad", min_value=1, value=50, step=10, key=f"cant_{sku}")
        with c2:
            fecha_default = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
            fecha_limite  = st.date_input("Fecha límite entrega", value=fecha_default, key=f"fecha_{sku}")
        with c3:
            notas = st.text_input("Notas", placeholder="Ej: tela alternativa, urgente...", key=f"notas_{sku}")

        if st.button("CONFIRMAR ORDEN", key=f"btn_{sku}"):
            nueva = {
                "id": generar_id_orden(ordenes_df),
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sku": sku, "producto": producto, "variante": variante,
                "cantidad": cantidad, "fecha_limite": str(fecha_limite), "notas": notas,
            }
            if guardar_orden(client, nueva):
                st.success(f"✅ Orden {nueva['id']} creada — {cantidad} u para {fecha_limite}")
                st.cache_data.clear()


def vista_dashboard(df, ordenes_df, client):
    if df.empty:
        st.warning("No hay datos aún. Ejecuta `actualizarTodo` en Apps Script primero.")
        return

    df_e = enriquecer(df)
    criticos = df_e[df_e["_urgencia"] == "CRÍTICO"]
    alertas  = df_e[df_e["_urgencia"] == "ALERTA"]
    ok       = df_e[df_e["_urgencia"] == "OK"]

    # Métricas
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("CRÍTICOS", len(criticos))
    with c2: st.metric("EN ALERTA", len(alertas))
    with c3:
        pend = len(ordenes_df[ordenes_df["Estado"] == "pendiente"]) if not ordenes_df.empty and "Estado" in ordenes_df.columns else 0
        st.metric("ÓRDENES ACTIVAS", pend)
    with c4:
        col_stock = "Stock Actual" if "Stock Actual" in df.columns else df.columns[4] if len(df.columns) > 4 else None
        total = int(df[col_stock].sum()) if col_stock else 0
        st.metric("UNIDADES TOTALES", f"{total:,}")

    # Email alerta
    urgentes = pd.concat([criticos, alertas])
    if not urgentes.empty:
        st.markdown("<br>", unsafe_allow_html=True)
        import urllib.parse
        lista = "\n".join([
            f"• {row.get('Producto', '?')} — {row.get('Variante','?')}: {row.get('Stock Actual','?')} u"
            for _, row in urgentes.iterrows()
        ])
        subject = urllib.parse.quote("⚡ LÍNEA VIVA — Productos urgentes Térret")
        body    = urllib.parse.quote(f"Productos que requieren reprogramación:\n\n{lista}\n\nEntra a Línea Viva para registrar las órdenes.")
        link    = f"mailto:{ALERTA_EMAIL}?subject={subject}&body={body}"
        st.markdown(
            f'<a href="{link}"><button style="background:#D4FF00;color:#0A0A14;font-family:\'Bebas Neue\',sans-serif;'
            f'font-size:14px;letter-spacing:2px;border:none;border-radius:4px;padding:10px 24px;cursor:pointer;">'
            f'📧 ENVIAR ALERTA AL REPROGRAMADOR</button></a>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    if not criticos.empty:
        st.markdown("### 🔴 REPROGRAMAR AHORA")
        for _, row in criticos.iterrows():
            render_card(row, "card-critico", "<span class='badge-critico'>🔴 CRÍTICO</span>", ordenes_df, client)

    if not alertas.empty:
        st.markdown("### 🟡 EN ALERTA")
        for _, row in alertas.iterrows():
            render_card(row, "card-alerta", "<span class='badge-alerta'>⚠ ALERTA</span>", ordenes_df, client)

    if not ok.empty:
        with st.expander(f"✅  {len(ok)} productos con stock saludable"):
            for _, row in ok.iterrows():
                render_card(row, "card-ok", "<span class='badge-ok'>✓ OK</span>", ordenes_df, client)


def vista_ordenes(ordenes_df, client):
    st.markdown("### ÓRDENES DE PRODUCCIÓN")

    if ordenes_df.empty or len(ordenes_df.columns) < 2:
        st.info("No hay órdenes aún. Créalas desde el Dashboard.")
        return

    c1, c2 = st.columns(2)
    with c1:
        opciones = ["Todos"] + (list(ordenes_df["Estado"].dropna().unique()) if "Estado" in ordenes_df.columns else [])
        filtro   = st.selectbox("Estado", opciones)
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
        with c1: orden_sel    = st.selectbox("Orden", ordenes_df["ID"].dropna().tolist())
        with c2: nuevo_estado = st.selectbox("Estado", ["pendiente","en-proceso","completado","cancelado"])
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("ACTUALIZAR"):
                if actualizar_estado_orden(client, orden_sel, nuevo_estado):
                    st.success(f"✅ {orden_sel} → {nuevo_estado}")
                    st.cache_data.clear()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    check_login()

    client  = conectar_sheets()
    df      = leer_inventario(client) if client else pd.DataFrame()
    ordenes = leer_ordenes(client)    if client else pd.DataFrame()

    df_e       = enriquecer(df) if not df.empty else df
    n_criticos = len(df_e[df_e["_urgencia"] == "CRÍTICO"]) if "_urgencia" in df_e.columns else 0
    n_alertas  = len(df_e[df_e["_urgencia"] == "ALERTA"])  if "_urgencia" in df_e.columns else 0

    render_header(n_criticos, n_alertas)

    tab1, tab2 = st.tabs(["📊  DASHBOARD", "📋  ÓRDENES"])
    with tab1: vista_dashboard(df, ordenes, client)
    with tab2: vista_ordenes(ordenes, client)

    st.markdown(
        f"<div style='text-align:center;font-size:11px;color:#2A2A3E;margin-top:40px;letter-spacing:1px;'>"
        f"LÍNEA VIVA · TÉRRET · {datetime.now().strftime('%d.%m.%Y %H:%M')}</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
