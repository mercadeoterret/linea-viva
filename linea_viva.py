"""
LÍNEA VIVA — Sistema de Reposición de Inventario
Térret | Stack: Streamlit + Google Sheets + Shopify Admin API
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import time

# ─── CONFIG & CONSTANTES ────────────────────────────────────────────────────

st.set_page_config(
    page_title="Línea Viva · Térret",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Shopify (llenar en Streamlit Cloud → Secrets)
SHOPIFY_STORE = st.secrets.get("SHOPIFY_STORE", "tu-tienda.myshopify.com")
SHOPIFY_TOKEN = st.secrets.get("SHOPIFY_API_TOKEN", "")
SHOPIFY_API_VERSION = "2024-01"

# Notificaciones — por ahora email vía mailto (WhatsApp API se conecta en iteración 2)
ENCARGADO_EMAIL = st.secrets.get("ENCARGADO_EMAIL", "encargado@terret.co")
ENCARGADO_NOMBRE = st.secrets.get("ENCARGADO_NOMBRE", "Encargado de Producción")

# Producción defaults
FABRICACION_MIN_DIAS = 15
FABRICACION_MAX_DIAS = 30

# ─── ESTILOS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');

/* BASE */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0A0A14 !important;
    color: #E8E8F0 !important;
}
[data-testid="stAppViewContainer"] > .main {
    background-color: #0A0A14;
}
[data-testid="stHeader"] { background: #0A0A14; border-bottom: 1px solid #1A1A2E; }
[data-testid="stSidebar"] { background: #0D0D1A; border-right: 1px solid #1A1A2E; }
section[data-testid="stSidebar"] { background: #0D0D1A !important; }

/* TIPOGRAFÍA */
h1, h2, h3, .bebas { font-family: 'Bebas Neue', sans-serif !important; letter-spacing: 2px; }
p, span, div, label, .stTextInput, .stSelectbox { font-family: 'DM Sans', sans-serif !important; }

/* BOTONES */
.stButton > button {
    background: #D4FF00 !important;
    color: #0A0A14 !important;
    font-family: 'Bebas Neue', sans-serif !important;
    font-size: 16px !important;
    letter-spacing: 2px !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 10px 24px !important;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    background: #BFEA00 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(212, 255, 0, 0.25);
}
.stButton > button:active { transform: translateY(0); }

/* INPUTS */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input,
.stSelectbox > div > div {
    background: #12121F !important;
    border: 1px solid #2A2A3E !important;
    color: #E8E8F0 !important;
    border-radius: 4px !important;
    font-family: 'DM Sans', sans-serif !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: #D4FF00 !important;
    box-shadow: 0 0 0 2px rgba(212, 255, 0, 0.15) !important;
}

/* MÉTRICAS */
[data-testid="stMetric"] {
    background: #12121F;
    border: 1px solid #1E1E30;
    border-radius: 8px;
    padding: 16px 20px;
}
[data-testid="stMetricValue"] { color: #D4FF00 !important; font-family: 'Bebas Neue', sans-serif !important; font-size: 2rem !important; }
[data-testid="stMetricLabel"] { color: #6B6B8A !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 1.5px; }

/* DATAFRAME */
[data-testid="stDataFrame"] { border: 1px solid #1E1E30; border-radius: 8px; }
.dvn-scroller { background: #0D0D1A; }

/* DIVIDER */
hr { border-color: #1A1A2E !important; }

/* ALERTAS CUSTOM */
.alerta-critica {
    background: linear-gradient(135deg, #1A0A0A, #200D0D);
    border: 1px solid #FF3B30;
    border-left: 4px solid #FF3B30;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.alerta-warning {
    background: linear-gradient(135deg, #1A1400, #1F1800);
    border: 1px solid #FFB800;
    border-left: 4px solid #FFB800;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.alerta-ok {
    background: linear-gradient(135deg, #0A1A0A, #0D1F0D);
    border: 1px solid #30D158;
    border-left: 4px solid #30D158;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.producto-nombre { font-family: 'Bebas Neue', sans-serif; font-size: 18px; letter-spacing: 1.5px; color: #E8E8F0; }
.producto-sku { font-size: 11px; color: #6B6B8A; text-transform: uppercase; letter-spacing: 1px; }
.badge-critico { background: #FF3B30; color: white; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; text-transform: uppercase; letter-spacing: 1px; }
.badge-alerta { background: #FFB800; color: #0A0A14; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; text-transform: uppercase; letter-spacing: 1px; }
.badge-ok { background: #30D158; color: #0A0A14; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; text-transform: uppercase; letter-spacing: 1px; }
.dias-stock { font-family: 'Bebas Neue', sans-serif; font-size: 28px; }
.navbar-btn { cursor: pointer; }

/* HEADER */
.linea-viva-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 0 24px 0;
    border-bottom: 1px solid #1A1A2E;
    margin-bottom: 32px;
}
.logo-mark {
    width: 42px; height: 42px;
    background: #D4FF00;
    border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Bebas Neue', sans-serif;
    font-size: 22px;
    color: #0A0A14;
}

/* NAV TABS */
.stTabs [data-baseweb="tab-list"] {
    background: #0D0D1A;
    border-radius: 8px;
    padding: 4px;
    gap: 4px;
    border: 1px solid #1A1A2E;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #6B6B8A;
    font-family: 'Bebas Neue', sans-serif;
    font-size: 15px;
    letter-spacing: 1.5px;
    border-radius: 6px;
    padding: 8px 20px;
}
.stTabs [aria-selected="true"] {
    background: #D4FF00 !important;
    color: #0A0A14 !important;
}

/* FORM ORDEN */
.form-orden {
    background: #0D0D1A;
    border: 1px solid #1E1E30;
    border-radius: 12px;
    padding: 24px;
    margin-top: 16px;
}

/* STATUS CHIP */
.status-pendiente { color: #FFB800; font-weight: 600; }
.status-en-proceso { color: #0A84FF; font-weight: 600; }
.status-completado { color: #30D158; font-weight: 600; }
.status-cancelado { color: #FF3B30; font-weight: 600; }

/* PULSE ANIMATION para críticos */
@keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255,59,48,0); }
    50% { box-shadow: 0 0 0 6px rgba(255,59,48,0.15); }
}
.pulse { animation: pulse-red 2s infinite; }
</style>
""", unsafe_allow_html=True)


# ─── GOOGLE SHEETS ───────────────────────────────────────────────────────────

@st.cache_resource(ttl=300)
def conectar_sheets():
    """Conexión a Google Sheets via service account."""
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_dict = st.secrets.get("gcp_service_account", {})
        if not creds_dict:
            return None
        creds = Credentials.from_service_account_info(dict(creds_dict), scopes=scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Error conectando a Google Sheets: {e}")
        return None


def get_sheet(client, nombre_hoja: str):
    """Obtiene una hoja específica del spreadsheet."""
    try:
        spreadsheet_id = st.secrets.get("SPREADSHEET_ID", "")
        if not spreadsheet_id:
            return None
        sh = client.open_by_key(spreadsheet_id)
        return sh.worksheet(nombre_hoja)
    except gspread.exceptions.WorksheetNotFound:
        return None
    except Exception as e:
        st.error(f"Error accediendo a hoja '{nombre_hoja}': {e}")
        return None


def leer_productos_config(client) -> pd.DataFrame:
    """Lee la hoja 'productos' con umbrales y config."""
    ws = get_sheet(client, "productos")
    if not ws:
        # Datos de demo si no hay Sheets conectado
        return pd.DataFrame({
            "sku": ["TRR-001-BLK-M", "TRR-001-BLK-L", "TRR-002-WHT-S", "TRR-003-GRY-M"],
            "nombre": ["Camiseta Core", "Camiseta Core", "Polo Performance", "Hoodie Training"],
            "variante": ["Negro / M", "Negro / L", "Blanco / S", "Gris / M"],
            "umbral_critico": [10, 10, 8, 5],
            "umbral_alerta": [25, 25, 20, 15],
            "tiempo_fabricacion_dias": [20, 20, 25, 30],
            "activo": [True, True, True, True],
        })
    records = ws.get_all_records()
    return pd.DataFrame(records)


def leer_ordenes(client) -> pd.DataFrame:
    """Lee historial de órdenes de producción."""
    ws = get_sheet(client, "ordenes_produccion")
    if not ws:
        return pd.DataFrame(columns=["id","fecha_creacion","sku","nombre_producto",
                                      "cantidad","fecha_limite","estado","creado_por","notas"])
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=["id","fecha_creacion","sku","nombre_producto",
                                      "cantidad","fecha_limite","estado","creado_por","notas"])
    return pd.DataFrame(records)


def guardar_orden(client, orden: dict) -> bool:
    """Agrega una nueva orden a Google Sheets."""
    ws = get_sheet(client, "ordenes_produccion")
    if not ws:
        return False
    try:
        fila = [
            orden["id"],
            orden["fecha_creacion"],
            orden["sku"],
            orden["nombre_producto"],
            orden["cantidad"],
            orden["fecha_limite"],
            orden["estado"],
            orden["creado_por"],
            orden["notas"],
        ]
        ws.append_row(fila)
        return True
    except Exception as e:
        st.error(f"Error guardando orden: {e}")
        return False


def registrar_alerta(client, sku: str, stock: int, umbral: int, tipo: str):
    """Registra alerta en historial."""
    ws = get_sheet(client, "historial_alertas")
    if not ws:
        return
    try:
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            sku, stock, umbral, tipo, "FALSE"
        ])
    except Exception:
        pass


# ─── SHOPIFY API ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)  # Cache 2 min para no saturar la API
def fetch_inventario_shopify() -> pd.DataFrame:
    """
    Obtiene inventario actual desde Shopify Admin API.
    Retorna DataFrame con sku, nombre, variante, stock_actual.
    """
    if not SHOPIFY_TOKEN:
        # MODO DEMO: datos simulados mientras se configura Shopify
        return _datos_demo_shopify()

    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }

    try:
        # 1. Obtener productos
        url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/products.json"
        params = {"limit": 250, "fields": "id,title,variants"}
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        productos = resp.json().get("products", [])

        # 2. Obtener niveles de inventario
        filas = []
        for prod in productos:
            for var in prod.get("variants", []):
                inventory_item_id = var.get("inventory_item_id")
                sku = var.get("sku", "SIN-SKU")
                variante = var.get("title", "")
                nombre = prod.get("title", "")

                # Fetch inventory level por location (primera location)
                inv_url = f"https://{SHOPIFY_STORE}/admin/api/{SHOPIFY_API_VERSION}/inventory_levels.json"
                inv_resp = requests.get(
                    inv_url,
                    headers=headers,
                    params={"inventory_item_ids": inventory_item_id},
                    timeout=10,
                )
                stock = 0
                if inv_resp.ok:
                    levels = inv_resp.json().get("inventory_levels", [])
                    if levels:
                        stock = levels[0].get("available", 0)

                filas.append({
                    "sku": sku,
                    "nombre": nombre,
                    "variante": variante,
                    "stock_actual": stock,
                    "shopify_variant_id": var.get("id"),
                })

        return pd.DataFrame(filas)

    except requests.exceptions.ConnectionError:
        st.warning("⚠️ No se pudo conectar a Shopify — mostrando datos de demo.")
        return _datos_demo_shopify()
    except Exception as e:
        st.error(f"Error Shopify API: {e}")
        return _datos_demo_shopify()


def _datos_demo_shopify() -> pd.DataFrame:
    """Datos de inventario simulados para desarrollo."""
    return pd.DataFrame({
        "sku": ["TRR-001-BLK-M", "TRR-001-BLK-L", "TRR-002-WHT-S", "TRR-003-GRY-M",
                "TRR-004-BLK-S", "TRR-005-WHT-M"],
        "nombre": ["Camiseta Core", "Camiseta Core", "Polo Performance", "Hoodie Training",
                    "Shorts Run", "Camiseta Core"],
        "variante": ["Negro / M", "Negro / L", "Blanco / S", "Gris / M", "Negro / S", "Blanco / M"],
        "stock_actual": [7, 32, 5, 18, 2, 44],
        "shopify_variant_id": [None]*6,
    })


# ─── LÓGICA DE NEGOCIO ───────────────────────────────────────────────────────

def calcular_estado_inventario(inventario_df: pd.DataFrame, config_df: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza inventario Shopify con umbrales configurados.
    Calcula urgencia y días estimados de agotamiento.
    """
    merged = inventario_df.merge(config_df, on="sku", how="inner", suffixes=("", "_cfg"))

    # Columnas de nombre/variante: preferir las de config si existen
    if "nombre_cfg" in merged.columns:
        merged["nombre"] = merged["nombre_cfg"].fillna(merged["nombre"])
    if "variante_cfg" in merged.columns:
        merged["variante"] = merged["variante_cfg"].fillna(merged["variante"])

    merged = merged[merged["activo"].astype(str).str.upper() == "TRUE"].copy()

    # Clasificación de urgencia
    def clasificar(row):
        s = int(row["stock_actual"])
        crit = int(row["umbral_critico"])
        alert = int(row["umbral_alerta"])
        if s <= crit:
            return "CRÍTICO"
        elif s <= alert:
            return "ALERTA"
        else:
            return "OK"

    merged["urgencia"] = merged.apply(clasificar, axis=1)

    # Días estimados de agotamiento (placeholder: asume venta promedio de 2 unidades/día)
    # TODO: conectar con datos reales de ventas Shopify en iteración 2
    VENTA_DIARIA_PROMEDIO = 2
    merged["dias_agotamiento"] = (merged["stock_actual"] / VENTA_DIARIA_PROMEDIO).astype(int)

    # Fecha límite sugerida para orden de producción
    merged["fecha_limite_sugerida"] = pd.Timestamp.today() + pd.to_timedelta(
        merged["tiempo_fabricacion_dias"].astype(int), unit="d"
    )
    merged["fecha_limite_sugerida"] = merged["fecha_limite_sugerida"].dt.strftime("%Y-%m-%d")

    return merged.sort_values(
        ["urgencia", "stock_actual"],
        key=lambda x: x.map({"CRÍTICO": 0, "ALERTA": 1, "OK": 2}) if x.name == "urgencia" else x
    )


def generar_id_orden(ordenes_df: pd.DataFrame) -> str:
    """Genera ID único para orden de producción."""
    if ordenes_df.empty:
        return "OP-001"
    ultimo = ordenes_df["id"].str.extract(r"(\d+)").astype(float).max().item()
    return f"OP-{int(ultimo)+1:03d}"


# ─── NOTIFICACIONES ──────────────────────────────────────────────────────────

def generar_link_email_alerta(productos_criticos: list) -> str:
    """
    Genera link mailto con resumen de alertas.
    WhatsApp Business API se conecta en iteración 2.
    """
    import urllib.parse

    lista = "\n".join([
        f"• {p['nombre']} ({p['variante']}): {p['stock_actual']} unidades — {p['urgencia']}"
        for p in productos_criticos
    ])

    subject = urllib.parse.quote(f"⚡ LÍNEA VIVA — Alerta de inventario Térret")
    body = urllib.parse.quote(
        f"Hola {ENCARGADO_NOMBRE},\n\n"
        f"Los siguientes productos requieren atención urgente:\n\n"
        f"{lista}\n\n"
        f"Entra a Línea Viva para crear las órdenes de producción.\n\n"
        f"— Sistema automático Térret"
    )
    return f"mailto:{ENCARGADO_EMAIL}?subject={subject}&body={body}"


# ─── VISTAS ──────────────────────────────────────────────────────────────────

def render_header(total_criticos: int, total_alertas: int):
    st.markdown(f"""
    <div class="linea-viva-header">
        <div class="logo-mark">LV</div>
        <div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:26px;letter-spacing:3px;color:#E8E8F0;">
                LÍNEA VIVA
            </div>
            <div style="font-size:11px;color:#6B6B8A;letter-spacing:2px;text-transform:uppercase;">
                Reposición de Inventario · Térret
            </div>
        </div>
        <div style="margin-left:auto;display:flex;gap:12px;align-items:center;">
            {"<span class='badge-critico pulse'>⚡ " + str(total_criticos) + " críticos</span>" if total_criticos else ""}
            {"<span class='badge-alerta'>⚠ " + str(total_alertas) + " alertas</span>" if total_alertas else ""}
            {"<span class='badge-ok'>✓ Todo OK</span>" if not total_criticos and not total_alertas else ""}
        </div>
    </div>
    """, unsafe_allow_html=True)


def vista_dashboard(inventario_estado: pd.DataFrame, ordenes_df: pd.DataFrame, client):
    """Pantalla principal: alertas de stock."""

    criticos = inventario_estado[inventario_estado["urgencia"] == "CRÍTICO"]
    alertas = inventario_estado[inventario_estado["urgencia"] == "ALERTA"]
    ok = inventario_estado[inventario_estado["urgencia"] == "OK"]

    # ── Métricas resumen ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("PRODUCTOS CRÍTICOS", len(criticos), help="Stock por debajo del umbral crítico")
    with col2:
        st.metric("EN ALERTA", len(alertas), help="Stock bajo pero no crítico aún")
    with col3:
        ordenes_pendientes = len(ordenes_df[ordenes_df["estado"] == "pendiente"]) if not ordenes_df.empty else 0
        st.metric("ÓRDENES ACTIVAS", ordenes_pendientes)
    with col4:
        total_units = int(inventario_estado["stock_actual"].sum())
        st.metric("UNIDADES TOTALES", f"{total_units:,}")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Botón enviar alerta ──
    if len(criticos) > 0 or len(alertas) > 0:
        productos_urgentes = pd.concat([criticos, alertas]).to_dict("records")
        link_email = generar_link_email_alerta(productos_urgentes)

        col_btn, col_info = st.columns([2, 5])
        with col_btn:
            st.markdown(
                f'<a href="{link_email}" target="_blank">'
                f'<button style="background:#D4FF00;color:#0A0A14;font-family:Bebas Neue,sans-serif;'
                f'font-size:15px;letter-spacing:2px;border:none;border-radius:4px;padding:10px 24px;'
                f'cursor:pointer;width:100%;">📧 ENVIAR ALERTA AL ENCARGADO</button></a>',
                unsafe_allow_html=True,
            )
        with col_info:
            st.caption(f"Se abrirá tu cliente de email con un resumen para {ENCARGADO_EMAIL}")

    st.markdown("---")

    # ── Tarjetas de productos ──
    def render_producto_card(row, clase_alerta, badge_html):
        dias = int(row["dias_agotamiento"])
        color_dias = "#FF3B30" if dias <= 10 else "#FFB800" if dias <= 20 else "#30D158"

        # Form de nueva orden inline
        form_key = f"form_{row['sku']}"

        with st.container():
            st.markdown(f"""
            <div class="{clase_alerta}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div>
                        <div class="producto-nombre">{row['nombre']}</div>
                        <div class="producto-sku">{row['sku']} · {row['variante']}</div>
                        <div style="margin-top:8px;">{badge_html}</div>
                    </div>
                    <div style="text-align:right;">
                        <div class="dias-stock" style="color:{color_dias};">{dias}</div>
                        <div style="font-size:11px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">días estimados</div>
                    </div>
                </div>
                <div style="display:flex;gap:24px;margin-top:12px;">
                    <div>
                        <div style="font-size:11px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">Stock actual</div>
                        <div style="font-size:20px;font-weight:600;color:#E8E8F0;">{int(row['stock_actual'])} u</div>
                    </div>
                    <div>
                        <div style="font-size:11px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">Umbral crítico</div>
                        <div style="font-size:20px;font-weight:600;color:#E8E8F0;">{int(row['umbral_critico'])} u</div>
                    </div>
                    <div>
                        <div style="font-size:11px;color:#6B6B8A;text-transform:uppercase;letter-spacing:1px;">Fabricación</div>
                        <div style="font-size:20px;font-weight:600;color:#E8E8F0;">{int(row['tiempo_fabricacion_dias'])} días</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Expander para crear orden
            with st.expander(f"➕ CREAR ORDEN PARA {row['nombre'].upper()} — {row['variante'].upper()}"):
                c1, c2, c3 = st.columns([2, 2, 3])
                with c1:
                    cantidad = st.number_input(
                        "Cantidad a producir",
                        min_value=1, value=50, step=10,
                        key=f"cant_{row['sku']}"
                    )
                with c2:
                    fecha_default = datetime.strptime(row["fecha_limite_sugerida"], "%Y-%m-%d").date()
                    fecha_limite = st.date_input(
                        "Fecha límite entrega",
                        value=fecha_default,
                        key=f"fecha_{row['sku']}"
                    )
                with c3:
                    notas = st.text_input(
                        "Notas (opcional)",
                        placeholder="Ej: prioridad alta, tela alternativa...",
                        key=f"notas_{row['sku']}"
                    )

                if st.button(f"CONFIRMAR ORDEN", key=f"btn_{row['sku']}"):
                    nueva_orden = {
                        "id": generar_id_orden(ordenes_df),
                        "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "sku": row["sku"],
                        "nombre_producto": f"{row['nombre']} — {row['variante']}",
                        "cantidad": cantidad,
                        "fecha_limite": str(fecha_limite),
                        "estado": "pendiente",
                        "creado_por": "admin",
                        "notas": notas,
                    }
                    if client:
                        ok_saved = guardar_orden(client, nueva_orden)
                        if ok_saved:
                            st.success(f"✅ Orden {nueva_orden['id']} creada — {cantidad} unidades para {fecha_limite}")
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                    else:
                        # Sin Sheets: solo mostrar éxito (demo)
                        st.success(f"✅ [DEMO] Orden creada — {cantidad} unidades de {row['nombre']} para {fecha_limite}")

    # Mostrar críticos
    if not criticos.empty:
        st.markdown("### 🔴 CRÍTICOS")
        for _, row in criticos.iterrows():
            render_producto_card(row, "alerta-critica", "<span class='badge-critico'>🔴 CRÍTICO</span>")

    # Mostrar alertas
    if not alertas.empty:
        st.markdown("### 🟡 EN ALERTA")
        for _, row in alertas.iterrows():
            render_producto_card(row, "alerta-warning", "<span class='badge-alerta'>⚠ ALERTA</span>")

    # Mostrar OK (colapsado)
    if not ok.empty:
        with st.expander(f"✅ {len(ok)} productos con stock OK"):
            for _, row in ok.iterrows():
                render_producto_card(row, "alerta-ok", "<span class='badge-ok'>✓ OK</span>")


def vista_ordenes(ordenes_df: pd.DataFrame, client):
    """Historial y gestión de órdenes de producción."""

    st.markdown("### ÓRDENES DE PRODUCCIÓN")

    if ordenes_df.empty:
        st.info("No hay órdenes registradas aún. Créalas desde el Dashboard.")
        return

    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        estados = ["Todos"] + list(ordenes_df["estado"].unique())
        filtro_estado = st.selectbox("Filtrar por estado", estados)
    with col_f2:
        filtro_sku = st.text_input("Buscar por SKU o producto", placeholder="Ej: TRR-001")

    df_filtrado = ordenes_df.copy()
    if filtro_estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["estado"] == filtro_estado]
    if filtro_sku:
        mask = (
            df_filtrado["sku"].str.contains(filtro_sku, case=False, na=False) |
            df_filtrado["nombre_producto"].str.contains(filtro_sku, case=False, na=False)
        )
        df_filtrado = df_filtrado[mask]

    # Tabla
    st.dataframe(
        df_filtrado.rename(columns={
            "id": "ID",
            "fecha_creacion": "Creada",
            "sku": "SKU",
            "nombre_producto": "Producto",
            "cantidad": "Cantidad",
            "fecha_limite": "Fecha Límite",
            "estado": "Estado",
            "creado_por": "Creado por",
            "notas": "Notas",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # Actualizar estado de orden
    st.markdown("---")
    st.markdown("#### ACTUALIZAR ESTADO")
    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        ids_disponibles = ordenes_df["id"].tolist()
        orden_sel = st.selectbox("Orden", ids_disponibles)
    with col_u2:
        nuevo_estado = st.selectbox("Nuevo estado", ["pendiente", "en-proceso", "completado", "cancelado"])
    with col_u3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("ACTUALIZAR"):
            if client:
                ws = get_sheet(client, "ordenes_produccion")
                if ws:
                    cell = ws.find(orden_sel)
                    if cell:
                        ws.update_cell(cell.row, 7, nuevo_estado)  # col 7 = estado
                        st.success(f"✅ {orden_sel} → {nuevo_estado}")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
            else:
                st.success(f"✅ [DEMO] {orden_sel} → {nuevo_estado}")


def vista_configuracion(client):
    """Configuración de productos y umbrales."""

    st.markdown("### CONFIGURACIÓN DE PRODUCTOS")
    st.caption("Define qué SKUs monitorear y sus umbrales de alerta.")

    if client:
        config_df = leer_productos_config(client)
    else:
        config_df = leer_productos_config(None)

    st.dataframe(config_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### AGREGAR / EDITAR PRODUCTO")

    with st.form("form_config_producto"):
        col1, col2 = st.columns(2)
        with col1:
            sku = st.text_input("SKU (exacto de Shopify)", placeholder="TRR-001-BLK-M")
            nombre = st.text_input("Nombre producto", placeholder="Camiseta Core")
            variante = st.text_input("Variante", placeholder="Negro / M")
        with col2:
            umbral_critico = st.number_input("Umbral crítico (unidades)", min_value=1, value=10)
            umbral_alerta = st.number_input("Umbral alerta (unidades)", min_value=1, value=25)
            tiempo_fab = st.number_input("Tiempo fabricación (días)", min_value=1, value=20)

        submitted = st.form_submit_button("GUARDAR PRODUCTO")

        if submitted:
            if not sku or not nombre:
                st.error("SKU y nombre son obligatorios.")
            else:
                if client:
                    ws = get_sheet(client, "productos")
                    if ws:
                        ws.append_row([sku, nombre, variante, umbral_critico, umbral_alerta, tiempo_fab, "TRUE"])
                        st.success(f"✅ Producto {sku} guardado.")
                        st.cache_data.clear()
                else:
                    st.success(f"✅ [DEMO] Producto {sku} guardado (sin Sheets conectado).")

    st.markdown("---")
    st.markdown("#### ESTADO DE CONEXIONES")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown(
            f"**Google Sheets:** {'🟢 Conectado' if client else '🔴 No conectado (modo demo)'}"
        )
        st.caption(f"ID: {st.secrets.get('SPREADSHEET_ID', 'no configurado')}")
    with col_s2:
        shopify_ok = bool(SHOPIFY_TOKEN)
        st.markdown(f"**Shopify:** {'🟢 Conectado' if shopify_ok else '🟡 Usando datos de demo'}")
        st.caption(f"Store: {SHOPIFY_STORE}")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # Conexiones
    client = conectar_sheets()

    # Datos
    inventario_shopify = fetch_inventario_shopify()
    config_df = leer_productos_config(client)
    ordenes_df = leer_ordenes(client)
    inventario_estado = calcular_estado_inventario(inventario_shopify, config_df)

    # Conteos para header
    total_criticos = len(inventario_estado[inventario_estado["urgencia"] == "CRÍTICO"])
    total_alertas = len(inventario_estado[inventario_estado["urgencia"] == "ALERTA"])

    # Header global
    render_header(total_criticos, total_alertas)

    # Navegación por tabs
    tab1, tab2, tab3 = st.tabs(["📊  DASHBOARD", "📋  ÓRDENES", "⚙  CONFIGURACIÓN"])

    with tab1:
        vista_dashboard(inventario_estado, ordenes_df, client)

    with tab2:
        vista_ordenes(ordenes_df, client)

    with tab3:
        vista_configuracion(client)

    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align:center;font-size:11px;color:#3A3A5C;letter-spacing:1px;'>LÍNEA VIVA · TÉRRET · "
        + datetime.now().strftime("%d.%m.%Y %H:%M") + "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
