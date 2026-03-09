"""
LÍNEA VIVA v2 — Sistema de Reposición de Inventario
Térret | Streamlit + Google Sheets
UX agrupado por producto → variantes por talla
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import urllib.parse

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
[data-testid="stHeader"] { background: #0A0A14 !important; border-bottom: 1px solid #1A1A2E; }
section[data-testid="stSidebar"] { background: #0D0D1A !important; }
h1,h2,h3 { font-family:'Bebas Neue',sans-serif !important; letter-spacing:2px; }
* { font-family:'DM Sans',sans-serif; }

/* BOTONES */
.stButton > button {
    background:#D4FF00 !important; color:#0A0A14 !important;
    font-family:'Bebas Neue',sans-serif !important; font-size:14px !important;
    letter-spacing:2px !important; border:none !important;
    border-radius:4px !important; padding:8px 18px !important;
    transition:all 0.15s ease; width:100%;
}
.stButton > button:hover { background:#BFEA00 !important; transform:translateY(-1px); }

/* INPUTS */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input,
.stSelectbox > div > div {
    background:#12121F !important; border:1px solid #2A2A3E !important;
    color:#E8E8F0 !important; border-radius:4px !important;
}

/* MÉTRICAS */
[data-testid="stMetric"] {
    background:#12121F; border:1px solid #1E1E30; border-radius:8px; padding:14px 18px;
}
[data-testid="stMetricValue"] { color:#D4FF00 !important; font-family:'Bebas Neue',sans-serif !important; font-size:1.8rem !important; }
[data-testid="stMetricLabel"] { color:#6B6B8A !important; font-size:10px !important; text-transform:uppercase; letter-spacing:1.5px; }

/* TABS */
.stTabs [data-baseweb="tab-list"] {
    background:#0D0D1A; border-radius:8px; padding:4px; gap:4px; border:1px solid #1A1A2E;
}
.stTabs [data-baseweb="tab"] {
    background:transparent; color:#6B6B8A; font-family:'Bebas Neue',sans-serif;
    font-size:14px; letter-spacing:1.5px; border-radius:6px; padding:8px 18px;
}
.stTabs [aria-selected="true"] { background:#D4FF00 !important; color:#0A0A14 !important; }

hr { border-color:#1A1A2E !important; }

/* BADGES */
.badge-critico { background:#FF3B30; color:white; font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; text-transform:uppercase; letter-spacing:1px; display:inline-block; }
.badge-alerta  { background:#FFB800; color:#0A0A14; font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; text-transform:uppercase; letter-spacing:1px; display:inline-block; }
.badge-ok      { background:#30D158; color:#0A0A14; font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; text-transform:uppercase; letter-spacing:1px; display:inline-block; }
.badge-info    { background:#2A2A3E; color:#9B9BB8; font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; text-transform:uppercase; letter-spacing:1px; display:inline-block; }

/* TABLA DE VARIANTES */
.tabla-variantes {
    width:100%; border-collapse:collapse; margin-top:12px;
}
.tabla-variantes th {
    font-size:10px; color:#6B6B8A; text-transform:uppercase; letter-spacing:1.5px;
    padding:6px 12px; text-align:left; border-bottom:1px solid #1A1A2E;
}
.tabla-variantes td {
    padding:10px 12px; border-bottom:1px solid #12121F; font-size:14px; vertical-align:middle;
}
.tabla-variantes tr:last-child td { border-bottom:none; }
.dias-critico { color:#FF3B30; font-family:'Bebas Neue',sans-serif; font-size:20px; }
.dias-alerta  { color:#FFB800; font-family:'Bebas Neue',sans-serif; font-size:20px; }
.dias-ok      { color:#30D158; font-family:'Bebas Neue',sans-serif; font-size:20px; }

/* EXPANDER custom */
[data-testid="stExpander"] {
    background:#0D0D1A !important; border:1px solid #1E1E30 !important;
    border-radius:8px !important; margin-bottom:8px !important;
}
[data-testid="stExpander"] summary {
    padding:14px 18px !important;
}

/* FORM ORDEN inline */
.form-orden {
    background:#12121F; border:1px solid #1E1E30; border-radius:8px;
    padding:16px; margin-top:8px;
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
            <div style='font-family:Bebas Neue,sans-serif;font-size:30px;letter-spacing:3px;
                        color:#E8E8F0;margin-bottom:4px;'>LÍNEA VIVA</div>
            <div style='font-size:11px;color:#6B6B8A;letter-spacing:2px;
                        text-transform:uppercase;margin-bottom:36px;'>Térret · Inventario</div>
        </div>
        """, unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            pwd = st.text_input("Contraseña", type="password", placeholder="••••••••")
            if st.button("ENTRAR"):
                if pwd == st.secrets.get("APP_PASSWORD", ""):
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta.")
        st.stop()


# ─── GOOGLE SHEETS ───────────────────────────────────────────────────────────

@st.cache_resource(ttl=300)
def conectar_sheets():
    try:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error Google Sheets: {e}")
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
        st.error(f"Error accediendo a '{nombre}': {e}")
        return None


@st.cache_data(ttl=120)
def leer_inventario(_client):
    ws = get_ws(_client, HOJA_INVENTARIO)
    if not ws: return pd.DataFrame()
    records = ws.get_all_records()
    return pd.DataFrame(records) if records else pd.DataFrame()


@st.cache_data(ttl=60)
def leer_ordenes(_client):
    ws = get_ws(_client, HOJA_ORDENES)
    if not ws: return pd.DataFrame()
    records = ws.get_all_records()
    return pd.DataFrame(records) if records else pd.DataFrame(
        columns=["ID","Fecha","SKU","Producto","Variante","Cantidad","Fecha_Limite","Estado","Notas"])


def guardar_orden(client, orden):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws: return False
    try:
        ws.append_row([orden["id"], orden["fecha"], orden["sku"], orden["producto"],
                       orden["variante"], orden["cantidad"], orden["fecha_limite"],
                       "pendiente", orden["notas"]])
        return True
    except Exception as e:
        st.error(f"Error guardando: {e}")
        return False


def actualizar_estado(client, orden_id, nuevo_estado):
    ws = get_ws(client, HOJA_ORDENES)
    if not ws: return False
    try:
        cell = ws.find(orden_id)
        if cell:
            ws.update_cell(cell.row, 8, nuevo_estado)
            return True
    except Exception as e:
        st.error(f"Error: {e}")
    return False


def nuevo_id(ordenes_df):
    if ordenes_df.empty or "ID" not in ordenes_df.columns: return "OP-001"
    nums = ordenes_df["ID"].dropna().astype(str).str.extract(r"(\d+)").dropna().astype(int)
    return f"OP-{int(nums.max().item())+1:03d}" if not nums.empty else "OP-001"


# ─── LÓGICA ─────────────────────────────────────────────────────────────────

def urgencia(decision):
    d = str(decision).upper()
    if "QUIEBRE" in d or "REPROGRAMAR" in d: return "CRÍTICO"
    if "EVALUAR" in d or "MONITOREAR" in d:  return "ALERTA"
    if "SALUDABLE" in d:                      return "OK"
    if "LIQUIDAR" in d:                       return "LIQUIDAR"
    return "INFO"


def preparar_df(df):
    if df.empty: return df
    df = df.copy()

    # Detectar columna de decisión
    col_dec = "🧠 Decisión" if "🧠 Decisión" in df.columns else (
              "Decision" if "Decision" in df.columns else df.columns[9] if len(df.columns) > 9 else df.columns[-1])

    # Normalizar nombres de columnas clave
    rename = {}
    for c in df.columns:
        cl = c.lower().replace(" ","_")
        if "producto" in cl and "nombre" not in cl: rename[c] = "Producto"
        elif "variante" in cl: rename[c] = "Variante"
        elif "sku" in cl: rename[c] = "SKU"
        elif "stock" in cl and "min" not in cl: rename[c] = "Stock"
        elif "ventas" in cl and "60" in cl: rename[c] = "Ventas60d"
        elif "día" in cl or "dias" in cl: rename[c] = "DiasInv"
        elif c == col_dec: rename[c] = "Decision"

    df = df.rename(columns=rename)

    df["_urgencia"] = df["Decision"].apply(urgencia)
    df["_orden"]    = df["_urgencia"].map({"CRÍTICO":0,"ALERTA":1,"OK":2,"LIQUIDAR":3,"INFO":4})
    return df


def agrupar_productos(df):
    """
    Agrupa variantes por nombre de producto.
    Retorna lista de dicts con el peor estado del grupo.
    """
    if df.empty: return []

    grupos = []
    for producto, grupo in df.groupby("Producto", sort=False):
        mejor_orden = grupo["_orden"].min()
        peor_urgencia = grupo.loc[grupo["_orden"] == mejor_orden, "_urgencia"].iloc[0]
        n_criticos = len(grupo[grupo["_urgencia"] == "CRÍTICO"])
        n_alertas  = len(grupo[grupo["_urgencia"] == "ALERTA"])
        grupos.append({
            "producto": producto,
            "urgencia": peor_urgencia,
            "orden": mejor_orden,
            "n_variantes": len(grupo),
            "n_criticos": n_criticos,
            "n_alertas": n_alertas,
            "variantes": grupo.sort_values("_orden"),
        })

    return sorted(grupos, key=lambda x: x["orden"])


# ─── RENDER ─────────────────────────────────────────────────────────────────

def badge(u):
    if u == "CRÍTICO":  return "<span class='badge-critico'>🔴 CRÍTICO</span>"
    if u == "ALERTA":   return "<span class='badge-alerta'>⚠ ALERTA</span>"
    if u == "OK":       return "<span class='badge-ok'>✓ OK</span>"
    if u == "LIQUIDAR": return "<span class='badge-info'>📦 LIQUIDAR</span>"
    return "<span class='badge-info'>INFO</span>"


def color_dias(d):
    try:
        n = int(float(str(d)))
        if n <= 15: return "dias-critico"
        if n <= 30: return "dias-alerta"
        return "dias-ok"
    except: return "dias-ok"


def render_grupo(grupo, ordenes_df, client):
    u        = grupo["urgencia"]
    producto = grupo["producto"]
    variantes = grupo["variantes"]
    nc = grupo["n_criticos"]
    na = grupo["n_alertas"]

    # Color del borde según urgencia
    border_color = {"CRÍTICO":"#FF3B30","ALERTA":"#FFB800","OK":"#30D158"}.get(u,"#2A2A3E")
    bg_color     = {"CRÍTICO":"#1A0A0A","ALERTA":"#1A1400","OK":"#0A1A0A"}.get(u,"#0D0D1A")

    # Resumen de variantes para el header
    resumen = ""
    if nc: resumen += f"<span class='badge-critico'>{nc} crítica{'s' if nc>1 else ''}</span> "
    if na: resumen += f"<span class='badge-alerta'>{na} en alerta</span> "
    if not nc and not na: resumen = f"<span class='badge-ok'>{grupo['n_variantes']} tallas OK</span>"

    label = f"{badge(u)}&nbsp;&nbsp;<strong style='font-family:Bebas Neue,sans-serif;font-size:17px;letter-spacing:1.5px;'>{producto.upper()}</strong>&nbsp;&nbsp;{resumen}"

    with st.expander(label, expanded=(u == "CRÍTICO")):
        st.markdown(f"""
        <div style='background:{bg_color};border:1px solid {border_color};
                    border-radius:8px;padding:4px 0;margin-bottom:8px;'>
        <table class='tabla-variantes'>
            <thead>
                <tr>
                    <th>Talla / Variante</th>
                    <th>Stock</th>
                    <th>Días</th>
                    <th>Ventas 60d</th>
                    <th>Estado</th>
                </tr>
            </thead>
            <tbody>
        """, unsafe_allow_html=True)

        for _, row in variantes.iterrows():
            var   = row.get("Variante","—")
            stock = row.get("Stock","—")
            dias  = row.get("DiasInv","—")
            v60   = row.get("Ventas60d","—")
            urg   = row.get("_urgencia","INFO")
            cls   = color_dias(dias)

            st.markdown(f"""
                <tr>
                    <td><strong>{var}</strong></td>
                    <td>{stock} u</td>
                    <td><span class='{cls}'>{dias}</span></td>
                    <td>{int(float(str(v60))) if str(v60).replace('.','').isdigit() else v60} u</td>
                    <td>{badge(urg)}</td>
                </tr>
            """, unsafe_allow_html=True)

        st.markdown("</tbody></table></div>", unsafe_allow_html=True)

        # ── Sección de programar ──
        urgentes = variantes[variantes["_urgencia"].isin(["CRÍTICO","ALERTA"])]

        if not urgentes.empty:
            st.markdown("---")

            # Opción 1: Programar talla individual
            st.markdown("**Programar por talla:**")
            for _, row in urgentes.iterrows():
                var = row.get("Variante","—")
                sku = row.get("SKU","—")

                with st.container():
                    c1, c2, c3, c4 = st.columns([2, 2, 3, 2])
                    with c1:
                        st.markdown(f"<div style='padding-top:8px;font-weight:600;'>{var}</div>", unsafe_allow_html=True)
                    with c2:
                        cant = st.number_input("Cant.", min_value=1, value=50, step=10,
                                               key=f"cant_{sku}", label_visibility="collapsed")
                    with c3:
                        fecha_def  = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
                        fecha_lim  = st.date_input("Fecha", value=fecha_def,
                                                   key=f"fecha_{sku}", label_visibility="collapsed")
                    with c4:
                        if st.button("PROGRAMAR", key=f"btn_{sku}"):
                            orden = {
                                "id": nuevo_id(ordenes_df),
                                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "sku": sku, "producto": producto, "variante": var,
                                "cantidad": cant, "fecha_limite": str(fecha_lim), "notas": "",
                            }
                            if guardar_orden(client, orden):
                                st.success(f"✅ {orden['id']} — {var} · {cant} u · {fecha_lim}")
                                st.cache_data.clear()

            # Opción 2: Programar todas las tallas urgentes de un solo
            if len(urgentes) > 1:
                st.markdown("---")
                st.markdown("**O programar todas las tallas urgentes a la vez:**")
                c1, c2, c3 = st.columns([2, 3, 2])
                with c1:
                    cant_all  = st.number_input("Cant. por talla", min_value=1, value=50, step=10,
                                                key=f"cant_all_{producto}")
                with c2:
                    fecha_def = (datetime.today() + pd.Timedelta(days=FABRICACION_DIAS)).date()
                    fecha_all = st.date_input("Fecha límite", value=fecha_def,
                                              key=f"fecha_all_{producto}")
                with c3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(f"PROGRAMAR {len(urgentes)} TALLAS", key=f"btn_all_{producto}"):
                        ids_creados = []
                        for _, row in urgentes.iterrows():
                            orden = {
                                "id": nuevo_id(leer_ordenes(client)),
                                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "sku": row.get("SKU","—"), "producto": producto,
                                "variante": row.get("Variante","—"),
                                "cantidad": cant_all, "fecha_limite": str(fecha_all), "notas": "Orden masiva",
                            }
                            if guardar_orden(client, orden):
                                ids_creados.append(orden["id"])
                        if ids_creados:
                            st.success(f"✅ {len(ids_creados)} órdenes creadas — {', '.join(ids_creados)}")
                            st.cache_data.clear()


def render_header(n_criticos, n_alertas):
    badge_html = ""
    if n_criticos: badge_html += f"<span class='badge-critico'>⚡ {n_criticos} críticos</span> "
    if n_alertas:  badge_html += f"<span class='badge-alerta'>⚠ {n_alertas} en alerta</span>"
    if not n_criticos and not n_alertas: badge_html = "<span class='badge-ok'>✓ Todo OK</span>"

    st.markdown(f"""
    <div style='display:flex;align-items:center;gap:16px;padding:8px 0 28px 0;
                border-bottom:1px solid #1A1A2E;margin-bottom:24px;'>
        <div style='background:#D4FF00;width:42px;height:42px;border-radius:6px;flex-shrink:0;
                    display:flex;align-items:center;justify-content:center;
                    font-family:Bebas Neue,sans-serif;font-size:20px;color:#0A0A14;'>LV</div>
        <div>
            <div style='font-family:Bebas Neue,sans-serif;font-size:24px;letter-spacing:3px;
                        color:#E8E8F0;line-height:1;'>LÍNEA VIVA</div>
            <div style='font-size:10px;color:#6B6B8A;letter-spacing:2px;text-transform:uppercase;'>Reposición · Térret</div>
        </div>
        <div style='margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap;'>{badge_html}</div>
    </div>
    """, unsafe_allow_html=True)


# ─── VISTAS ──────────────────────────────────────────────────────────────────

def vista_dashboard(df, ordenes_df, client):
    if df.empty:
        st.warning("No hay datos. Ejecuta `actualizarTodo` en Apps Script primero.")
        return

    df_prep = preparar_df(df)
    grupos  = agrupar_productos(df_prep)

    if not grupos:
        st.info("Sin productos para mostrar.")
        return

    # Métricas
    total_criticos = sum(g["n_criticos"] for g in grupos)
    total_alertas  = sum(g["n_alertas"]  for g in grupos)
    prods_urgentes = sum(1 for g in grupos if g["urgencia"] in ["CRÍTICO","ALERTA"])
    pend = len(ordenes_df[ordenes_df["Estado"]=="pendiente"]) if not ordenes_df.empty and "Estado" in ordenes_df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("SKUs CRÍTICOS",    total_criticos)
    with c2: st.metric("SKUs EN ALERTA",   total_alertas)
    with c3: st.metric("PRODUCTOS URGENTES", prods_urgentes)
    with c4: st.metric("ÓRDENES ACTIVAS",  pend)

    # Email alerta
    if total_criticos or total_alertas:
        lista = "\n".join([
            f"• {g['producto']}: {g['n_criticos']} críticas, {g['n_alertas']} en alerta"
            for g in grupos if g["urgencia"] in ["CRÍTICO","ALERTA"]
        ])
        subject = urllib.parse.quote("⚡ LÍNEA VIVA — Productos urgentes Térret")
        body    = urllib.parse.quote(f"Productos que requieren reprogramación:\n\n{lista}\n\nEntra a Línea Viva.")
        link    = f"mailto:{ALERTA_EMAIL}?subject={subject}&body={body}"
        st.markdown(
            f'<div style="margin:16px 0 8px 0;">'
            f'<a href="{link}"><button style="background:#D4FF00;color:#0A0A14;'
            f'font-family:\'Bebas Neue\',sans-serif;font-size:13px;letter-spacing:2px;'
            f'border:none;border-radius:4px;padding:9px 20px;cursor:pointer;">'
            f'📧 ENVIAR ALERTA AL REPROGRAMADOR</button></a></div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # Filtro rápido
    col_f1, col_f2 = st.columns([3,2])
    with col_f1:
        filtro = st.radio("Mostrar", ["Solo urgentes","Todos"], horizontal=True)
    with col_f2:
        buscar = st.text_input("Buscar producto", placeholder="Ej: medias, camiseta...", label_visibility="collapsed")

    grupos_filtrados = grupos
    if filtro == "Solo urgentes":
        grupos_filtrados = [g for g in grupos if g["urgencia"] in ["CRÍTICO","ALERTA"]]
    if buscar:
        grupos_filtrados = [g for g in grupos_filtrados if buscar.lower() in g["producto"].lower()]

    if not grupos_filtrados:
        st.info("No hay productos urgentes en este momento. ✅")
        return

    st.markdown(f"<div style='font-size:12px;color:#6B6B8A;margin-bottom:16px;'>{len(grupos_filtrados)} productos</div>", unsafe_allow_html=True)

    for grupo in grupos_filtrados:
        render_grupo(grupo, ordenes_df, client)


def vista_ordenes(ordenes_df, client):
    st.markdown("### ÓRDENES DE PRODUCCIÓN")

    if ordenes_df.empty or len(ordenes_df.columns) < 2:
        st.info("No hay órdenes aún. Créalas desde el Dashboard.")
        return

    c1, c2 = st.columns(2)
    with c1:
        opts   = ["Todos"] + (list(ordenes_df["Estado"].dropna().unique()) if "Estado" in ordenes_df.columns else [])
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
        with c1: orden_sel    = st.selectbox("Orden", ordenes_df["ID"].dropna().tolist())
        with c2: nuevo_estado = st.selectbox("Estado", ["pendiente","en-proceso","completado","cancelado"])
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("ACTUALIZAR"):
                if actualizar_estado(client, orden_sel, nuevo_estado):
                    st.success(f"✅ {orden_sel} → {nuevo_estado}")
                    st.cache_data.clear()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    check_login()

    client  = conectar_sheets()
    df      = leer_inventario(client) if client else pd.DataFrame()
    ordenes = leer_ordenes(client)    if client else pd.DataFrame()

    df_prep    = preparar_df(df) if not df.empty else df
    grupos     = agrupar_productos(df_prep) if not df_prep.empty else []
    n_criticos = sum(g["n_criticos"] for g in grupos)
    n_alertas  = sum(g["n_alertas"]  for g in grupos)

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
