import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
from datetime import date

st.set_page_config(page_title="TASTY Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0d1117; }
section[data-testid="stSidebar"] { background-color: #161b22; }
.main .block-container { padding: 2rem 2rem 2rem 2rem; max-width: 1400px; }
.kpi-card { background:#161b22; border:1px solid #30363d; border-radius:12px; padding:20px 24px; text-align:center; position:relative; overflow:hidden; }
.kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
.kpi-card.green::before  { background:#00d4aa; }
.kpi-card.red::before    { background:#ff3d57; }
.kpi-card.yellow::before { background:#ffd600; }
.kpi-card.blue::before   { background:#4f8ef7; }
.kpi-label { font-size:11px; font-weight:600; letter-spacing:1.2px; text-transform:uppercase; color:#8b949e; margin-bottom:8px; }
.kpi-value { font-size:28px; font-weight:700; letter-spacing:-0.5px; line-height:1; }
.kpi-value.green  { color:#00d4aa; }
.kpi-value.red    { color:#ff3d57; }
.kpi-value.yellow { color:#ffd600; }
.kpi-value.blue   { color:#4f8ef7; }
.section-title { font-size:13px; font-weight:600; letter-spacing:1px; text-transform:uppercase; color:#00d4aa; border-bottom:1px solid #21262d; padding-bottom:10px; margin-bottom:16px; }
div[data-testid="stFileUploader"] { background:#161b22; border:2px dashed #30363d; border-radius:16px; padding:10px; }
div[data-testid="stFileUploader"]:hover { border-color:#00d4aa; }
.trade-row { display:flex; gap:12px; padding:10px 16px; border-radius:8px; margin-bottom:6px; font-family:'JetBrains Mono',monospace; font-size:12px; align-items:center; }
.trade-row.win  { background:#0d2318; border-left:3px solid #00d4aa; }
.trade-row.loss { background:#1f0d12; border-left:3px solid #ff3d57; }
.trade-row.open { background:#1a1a0d; border-left:3px solid #ffd600; }
.trade-cell { min-width:100px; }
.trade-cell.sym { font-weight:700; font-size:13px; min-width:60px; }
.trade-cell.win  { color:#00d4aa; font-weight:700; }
.trade-cell.loss { color:#ff3d57; font-weight:700; }
.trade-cell.muted { color:#8b949e; }
.trade-header { display:flex; gap:12px; padding:8px 16px; font-size:10px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:#484f58; margin-bottom:4px; }
.open-pos-card { background:#161b22; border:1px solid #30363d; border-left:3px solid #ffd600; border-radius:8px; padding:12px 16px; margin-bottom:8px; font-family:'JetBrains Mono',monospace; font-size:13px; color:#e6edf3; }
footer{visibility:hidden;} #MainMenu{visibility:hidden;} header{visibility:hidden;}
</style>
""", unsafe_allow_html=True)


# ── Helpers de parsing ────────────────────────────────────────────────────────

def parse_price(p):
    m = re.search(r'([\d.]+)\s*(db|cr)', str(p).lower())
    if m:
        return float(m.group(1)) * (1 if m.group(2) == 'cr' else -1)
    try:
        return float(p)
    except:
        return 0.0

def detect_file_date(filename):
    m = re.search(r'(\d{2})(\d{2})(\d{2})', str(filename))
    if m:
        return f'20{m.group(1)}-{m.group(2)}-{m.group(3)}'
    return str(date.today())

def parse_date(t, fdate):
    t = str(t).strip()
    yr = fdate[:4]
    m = re.match(r'(\d+)/(\d+),?\s*([\d:]+)([ap])?', t)
    if m:
        mo, dy, tp, ap_c = m.group(1), m.group(2), m.group(3), m.group(4)
        if tp.count(':') == 1: tp += ':00'
        if ap_c:
            ap = 'PM' if ap_c == 'p' else 'AM'
            try:
                return pd.to_datetime(f'{yr}/{mo}/{dy} {tp} {ap}', format='%Y/%m/%d %H:%M:%S %p', errors='coerce')
            except:
                pass
        try:
            return pd.to_datetime(f'{yr}/{mo}/{dy} {tp}', format='%Y/%m/%d %H:%M:%S', errors='coerce')
        except:
            pass
    m2 = re.match(r'([\d:]+)([ap])?$', t)
    if m2:
        tp, ap_c = m2.group(1), m2.group(2)
        if tp.count(':') == 1: tp += ':00'
        if ap_c:
            ap = 'PM' if ap_c == 'p' else 'AM'
            try:
                return pd.to_datetime(f'{fdate} {tp} {ap}', format='%Y-%m-%d %H:%M:%S %p', errors='coerce')
            except:
                pass
        try:
            return pd.to_datetime(f'{fdate} {tp}', format='%Y-%m-%d %H:%M:%S', errors='coerce')
        except:
            pass
    return pd.NaT

def get_action(desc):
    desc = str(desc)
    if 'STC' in desc and 'BTC' in desc: return 'Close Spread'
    if 'BTO' in desc and 'STO' in desc: return 'Open Spread'
    if 'BTO' in desc: return 'Buy to Open'
    if 'STO' in desc: return 'Sell to Open'
    if 'STC' in desc: return 'Sell to Close'
    if 'BTC' in desc: return 'Buy to Close'
    return ''


# ── Novo parsing de legs ──────────────────────────────────────────────────────

def get_legs(desc):
    """
    Extrai cada leg de uma ordem (suporta multi-leg com múltiplas linhas).
    Retorna lista de dicts: qty, expiry, strike, action, sign.
    """
    legs = []
    for line in str(desc).strip().split('\n'):
        line = line.strip()
        m = re.match(
            r'(-?\d+)\s+'
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+)\w*\s*'
            r'(?:\d+d\s+)?'
            r'([\d.]+)\s+(?:Call|Put)\s+'
            r'(BTO|STO|STC|BTC)',
            line
        )
        if m:
            qty_raw = int(m.group(1))
            expiry  = f"{m.group(2)} {m.group(3)}"
            strike  = float(m.group(4))
            action  = m.group(5)
            legs.append({
                'qty':    abs(qty_raw),
                'expiry': expiry,
                'strike': strike,
                'action': action,
                'sign':   -1 if qty_raw < 0 else 1,
            })
    return legs


def expand_rows(df):
    """
    Expande cada linha do CSV em uma sub-row por leg.

    Regra de alocação do net:
    - Single-leg (BTO, STO, STC, BTC isolados): net vai inteiro para a leg.
    - Multi-leg de ABERTURA (BTO+STO na mesma ordem, ex: spread):
        net líquido vai só para a leg BTO; STO recebe 0 (já embutido no preço).
    - Multi-leg de FECHAMENTO: net total vai só na primeira leg (i==0);
        match_trades agrupa pelo Order # e usa o net total da ordem.
    """
    rows = []
    for _, row in df.iterrows():
        legs = get_legs(row['Description'])
        if not legs:
            continue
        net_pts  = parse_price(row['MarketOrFill'])  # cr=positivo, db=negativo
        net_dol  = net_pts * 100

        is_open_order  = all(l['action'] in ('BTO', 'STO') for l in legs)
        is_close_order = all(l['action'] in ('STC', 'BTC') for l in legs)
        is_mixed_open  = is_open_order and len(legs) > 1  # spread aberto numa ordem

        for i, leg in enumerate(legs):
            is_open  = leg['action'] in ('BTO', 'STO')
            is_close = leg['action'] in ('STC', 'BTC')

            if is_mixed_open:
                # Spread aberto numa ordem: net líquido só na leg BTO
                net = net_dol if leg['action'] == 'BTO' else 0.0
            elif is_close_order:
                # Fechamento: net total só na primeira leg
                net = net_dol if i == 0 else 0.0
            else:
                # Single-leg de qualquer tipo
                net = net_dol

            rows.append({
                'Symbol':   row['Symbol'],
                'Order':    row['Order #'],
                'datetime': row.get('datetime', pd.NaT),
                'date':     row.get('date', None),
                'expiry':   leg['expiry'],
                'strike':   leg['strike'],
                'action':   leg['action'],
                'qty':      leg['qty'],
                'net':      net,
                'is_open':  is_open,
                'is_close': is_close,
            })
    return pd.DataFrame(rows)


def match_trades(expanded_df):
    """
    Matching por Order # de fechamento.

    Lógica:
    1. Aberturas (BTO/STO) entram numa fila FIFO por (Symbol, Expiry, Strike).
    2. Todas as legs de fechamento que pertencem ao mesmo Order # são agrupadas
       numa única operação de fechamento — porque o tastytrade reporta um preço
       net único para toda a ordem, independente de quantos strikes ela toca.
    3. Para cada ordem de fechamento, somamos todos os open costs dos openers
       que ela consome (de todos os strikes envolvidos) e geramos UM único trade
       com o PnL líquido real: soma(open costs) + close net.
    4. Posições não fechadas ficam como 'Aberto'.
    """
    # ── Passo 1: separar aberturas e fechamentos ──────────────────────────────
    df_sorted = expanded_df.sort_values('datetime').reset_index(drop=True)

    # Fila de aberturas por (Symbol, Expiry, Strike)
    open_queue = {}   # key -> [{'date', 'qty', 'net', 'order'}]

    # Agrupa as legs de fechamento por Order # (para processar juntas)
    # Formato: { order_id -> [rows de fechamento] }
    close_orders = {}
    close_order_meta = {}  # order_id -> {symbol, date, datetime, net}

    for _, row in df_sorted.iterrows():
        key = (row['Symbol'], row['expiry'], row['strike'])

        if row['is_open']:
            open_queue.setdefault(key, []).append({
                'date':   row['date'],
                'qty':    row['qty'],
                'net':    row['net'],
                'order':  row['Order'],
                'expiry': row['expiry'],
                'strike': row['strike'],
            })

        elif row['is_close']:
            oid = row['Order']
            close_orders.setdefault(oid, []).append(row)
            # Guarda metadados da ordem (só precisa uma vez)
            if oid not in close_order_meta:
                close_order_meta[oid] = {
                    'symbol':   row['Symbol'],
                    'date':     row['date'],
                    'datetime': row['datetime'],
                    'net':      row['net'],   # net total da ordem (já em $, só na 1ª leg)
                }

    # ── Passo 2: processar cada ordem de fechamento como bloco único ──────────
    trades = []

    # Ordena as ordens de fechamento cronologicamente
    sorted_close_orders = sorted(
        close_orders.items(),
        key=lambda x: close_order_meta[x[0]]['datetime']
    )

    for oid, legs in sorted_close_orders:
        meta       = close_order_meta[oid]
        close_net  = meta['net']      # crédito/débito líquido da ordem inteira (em $)
        close_date = meta['date']
        symbol     = meta['symbol']

        # Descreve os strikes fechados nesta ordem (para exibição)
        strikes_closed = sorted(set(r['strike'] for r in legs))
        expiry         = legs[0]['expiry']

        # Consome openers de cada leg e acumula open cost total
        total_open_cost = 0.0
        open_date_min   = None
        consumed        = []   # lista de (strike, qty_matched, open_cost_parcial)

        for leg in legs:
            key          = (symbol, leg['expiry'], leg['strike'])
            queue        = open_queue.get(key, [])
            qty_to_close = leg['qty']

            while qty_to_close > 0 and queue:
                opener  = queue[0]
                matched = min(opener['qty'], qty_to_close)

                open_cost_parcial = opener['net'] * (matched / opener['qty']) if opener['qty'] > 0 else 0
                total_open_cost  += open_cost_parcial

                if open_date_min is None or opener['date'] < open_date_min:
                    open_date_min = opener['date']

                consumed.append({
                    'strike':    leg['strike'],
                    'qty':       matched,
                    'open_cost': open_cost_parcial,
                })

                opener['qty'] -= matched
                qty_to_close  -= matched
                if opener['qty'] == 0:
                    queue.pop(0)

        # PnL da operação inteira = open costs acumulados + net do fechamento
        pnl = total_open_cost + close_net
        pct = round((pnl / abs(total_open_cost)) * 100, 1) if total_open_cost != 0 else 0

        # Strike descritivo: "205/220/265" se multi-leg, ou o único strike
        strike_label = '/'.join(str(int(s)) if s == int(s) else str(s) for s in strikes_closed)

        trades.append({
            'Symbol':       symbol,
            'Expiry':       expiry,
            'Strike':       strike_label,
            'Open Date':    str(open_date_min) if open_date_min else '—',
            'Close Date':   str(close_date),
            'Open Cost':    round(total_open_cost, 2),
            'Close Credit': round(close_net, 2),
            'PnL ($)':      round(pnl, 2),
            'PnL (%)':      pct,
            'Result':       'Win' if pnl > 0 else ('Loss' if pnl < 0 else 'BE'),
            'Status':       'Fechado',
        })

    # ── Passo 3: posições ainda abertas ──────────────────────────────────────
    for key, queue in open_queue.items():
        for opener in queue:
            if opener['qty'] > 0:
                strike_s = str(int(key[2])) if key[2] == int(key[2]) else str(key[2])
                trades.append({
                    'Symbol':       key[0],
                    'Expiry':       key[1],
                    'Strike':       strike_s,
                    'Open Date':    str(opener['date']),
                    'Close Date':   '—',
                    'Open Cost':    round(opener['net'], 2),
                    'Close Credit': 0.0,
                    'PnL ($)':      0.0,
                    'PnL (%)':      0.0,
                    'Result':       '—',
                    'Status':       'Aberto',
                })

    return pd.DataFrame(trades)


# ── Pipeline principal ────────────────────────────────────────────────────────

def process_csv(df, fdate):
    df = df.copy()
    df['datetime'] = df['Time'].apply(lambda t: parse_date(t, fdate))
    df['date']     = df['datetime'].dt.date
    df['action']   = df['Description'].apply(get_action)
    df = df.sort_values('datetime').reset_index(drop=True)

    # Net por linha (para gráfico de fluxo de caixa diário bruto)
    df['net_pts'] = df['MarketOrFill'].apply(parse_price)
    df['net']     = df['net_pts'] * 100  # qty=1 por ordem (preço já é net do spread)

    # Expande em legs e faz o matching FIFO
    expanded  = expand_rows(df)
    trades_df = match_trades(expanded)

    # P&L diário baseado nos trades fechados
    closed_tmp = trades_df[trades_df['Status'] == 'Fechado'].copy()
    if not closed_tmp.empty:
        closed_tmp['Close Date'] = pd.to_datetime(closed_tmp['Close Date'], errors='coerce')
        daily_closed = closed_tmp.groupby('Close Date')['PnL ($)'].sum().reset_index()
        daily_closed.columns = ['Date', 'Daily PnL']
        daily_closed['Cumulative PnL'] = daily_closed['Daily PnL'].cumsum()
    else:
        daily_closed = pd.DataFrame(columns=['Date', 'Daily PnL', 'Cumulative PnL'])

    sym_pnl = trades_df[trades_df['Status'] == 'Fechado'].groupby('Symbol')['PnL ($)'].sum().sort_values()

    open_positions = trades_df[trades_df['Status'] == 'Aberto']

    return df, trades_df, daily_closed, sym_pnl, open_positions


# ── UI ────────────────────────────────────────────────────────────────────────

_, col_title = st.columns([1, 8])
with col_title:
    st.markdown("""
    <div style="padding:8px 0 24px 0;">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8b949e;margin-bottom:4px;">tastytrade</div>
        <div style="font-size:32px;font-weight:700;color:#e6edf3;letter-spacing:-1px;">Trading Dashboard</div>
    </div>""", unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div class="section-title">📂 Importar CSV</div>', unsafe_allow_html=True)
uploaded = st.file_uploader("Arraste o CSV do tastytrade aqui ou clique para selecionar", type=['csv'])

if uploaded is None:
    st.markdown("""
    <div style="text-align:center;padding:40px;color:#8b949e;">
        <div style="font-size:48px;margin-bottom:16px;">📈</div>
        <div style="font-size:16px;font-weight:500;color:#e6edf3;margin-bottom:8px;">Faça upload do seu CSV para começar</div>
        <div style="font-size:13px;">No tastytrade: <strong>History → Activity → Export</strong></div>
    </div>""", unsafe_allow_html=True)
    st.stop()

try:
    fdate  = detect_file_date(uploaded.name)
    raw_df = pd.read_csv(uploaded)
    df, trades_df, daily_closed, sym_pnl, open_positions = process_csv(raw_df, fdate)
except Exception as e:
    st.error(f"Erro ao processar o CSV: {e}")
    st.stop()

all_dates = sorted(df['date'].dropna().unique())
min_date  = all_dates[0]
max_date  = all_dates[-1]

st.markdown('<div class="section-title">📅 Filtro de Período</div>', unsafe_allow_html=True)
col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
with col_f1:
    date_start = st.date_input("De",  value=min_date, min_value=min_date, max_value=max_date, key="ds")
with col_f2:
    date_end   = st.date_input("Até", value=max_date, min_value=min_date, max_value=max_date, key="de")
with col_f3:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("Hoje"):   date_start = max_date; date_end = max_date
    with b2:
        if st.button("Semana"):
            import datetime; date_end = max_date
            date_start = max_date - datetime.timedelta(days=max_date.weekday())
    with b3:
        if st.button("Mês"):  date_start = max_date.replace(day=1); date_end = max_date
    with b4:
        if st.button("Tudo"): date_start = min_date; date_end = max_date

if date_start > date_end:
    date_start = min_date; date_end = max_date

# Filtra trades fechados pelo Close Date
tdf_f = trades_df.copy()
tdf_f['_cd'] = pd.to_datetime(tdf_f['Close Date'], errors='coerce').dt.date
tdf_f = tdf_f[
    (tdf_f['Status'] == 'Aberto') |
    ((tdf_f['_cd'] >= date_start) & (tdf_f['_cd'] <= date_end))
].drop(columns=['_cd'])

if not daily_closed.empty:
    dc_f = daily_closed.copy()
    dc_f['_d'] = pd.to_datetime(dc_f['Date'], errors='coerce').dt.date
    dc_f = dc_f[(dc_f['_d'] >= date_start) & (dc_f['_d'] <= date_end)].drop(columns=['_d'])
    dc_f['Cumulative PnL'] = dc_f['Daily PnL'].cumsum()
else:
    dc_f = daily_closed.copy()

sym_pnl_f = tdf_f[tdf_f['Status'] == 'Fechado'].groupby('Symbol')['PnL ($)'].sum().sort_values()
sym_pnl_f = sym_pnl_f[sym_pnl_f != 0]

st.markdown("---")
trades_df    = tdf_f
daily_closed = dc_f
sym_pnl      = sym_pnl_f
closed       = trades_df[trades_df['Status'] == 'Fechado'].copy()
opened       = trades_df[trades_df['Status'] == 'Aberto'].copy()

# ── KPIs ──────────────────────────────────────────────────────────────────────
net_pnl      = closed['PnL ($)'].sum()                              if not closed.empty else 0.0
gross_profit = closed[closed['PnL ($)'] > 0]['PnL ($)'].sum()      if not closed.empty else 0.0
gross_loss   = abs(closed[closed['PnL ($)'] < 0]['PnL ($)'].sum()) if not closed.empty else 0.0

total_trades  = len(closed)
wins          = int((closed['PnL ($)'] > 0).sum()) if not closed.empty else 0
losses        = int((closed['PnL ($)'] < 0).sum()) if not closed.empty else 0
win_rate      = wins / total_trades if total_trades > 0 else 0
avg_win       = closed[closed['PnL ($)'] > 0]['PnL ($)'].mean() if wins   > 0 else 0
avg_loss      = closed[closed['PnL ($)'] < 0]['PnL ($)'].mean() if losses > 0 else 0
profit_factor = avg_win / abs(avg_loss) if avg_loss != 0 else 0

period_label = f"{date_start.strftime('%d/%m/%Y')} → {date_end.strftime('%d/%m/%Y')}"
st.success(f"✅  {uploaded.name}  —  {total_trades} trades fechados  |  {len(opened)} abertos  |  📅 {period_label}")

def kpi(label, value, color):
    return f'<div class="kpi-card {color}"><div class="kpi-label">{label}</div><div class="kpi-value {color}">{value}</div></div>'

st.markdown('<div class="section-title">📊 Performance</div>', unsafe_allow_html=True)
nc = "green" if net_pnl >= 0 else "red"
wc = "green" if win_rate >= 0.5 else "red"

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(kpi("Net P&L",       f"${net_pnl:,.2f}",      nc),       unsafe_allow_html=True)
with c2: st.markdown(kpi("Credit",        f"${gross_profit:,.2f}", "green"),   unsafe_allow_html=True)
with c3: st.markdown(kpi("Debit",         f"-${gross_loss:,.2f}",  "red"),     unsafe_allow_html=True)
with c4: st.markdown(kpi("Profit Factor", f"{profit_factor:.2f}x", "yellow"),  unsafe_allow_html=True)
st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
c5, c6, c7, c8 = st.columns(4)
with c5: st.markdown(kpi("Total Trades", str(total_trades),       "blue"),   unsafe_allow_html=True)
with c6: st.markdown(kpi("Win Rate",     f"{win_rate*100:.1f}%",  wc),       unsafe_allow_html=True)
with c7: st.markdown(kpi("Avg Win",      f"${avg_win:,.2f}",      "green"),  unsafe_allow_html=True)
with c8: st.markdown(kpi("Avg Loss",     f"${avg_loss:,.2f}",     "red"),    unsafe_allow_html=True)
st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

# ── Gráfico Cumulative P&L ────────────────────────────────────────────────────
st.markdown('<div class="section-title">📈 Cumulative P&L — Trades Fechados</div>', unsafe_allow_html=True)
if not daily_closed.empty:
    fig = go.Figure()
    dates_str = daily_closed['Date'].astype(str).tolist()
    cum_vals  = daily_closed['Cumulative PnL'].tolist()
    for i in range(len(cum_vals) - 1):
        x0, x1 = dates_str[i], dates_str[i+1]
        y0, y1 = cum_vals[i], cum_vals[i+1]
        color = '#00d4aa' if (y0 >= 0 and y1 >= 0) else '#ff3d57' if (y0 < 0 and y1 < 0) else '#ffd600'
        fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode='lines',
            line=dict(color=color, width=2.5), showlegend=False, hoverinfo='skip'))
    pt_colors = ['#00d4aa' if v >= 0 else '#ff3d57' for v in cum_vals]
    fig.add_trace(go.Scatter(x=dates_str, y=cum_vals, mode='markers',
        marker=dict(size=7, color=pt_colors, line=dict(color='#0d1117', width=2)),
        hovertemplate='<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>', showlegend=False))
    fig.add_trace(go.Scatter(x=dates_str, y=[max(v, 0) for v in cum_vals],
        fill='tozeroy', fillcolor='rgba(0,212,170,0.07)', line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=dates_str, y=[min(v, 0) for v in cum_vals],
        fill='tozeroy', fillcolor='rgba(255,61,87,0.07)', line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_hline(y=0, line_dash="dash", line_color="#30363d", line_width=1)
    fig.update_layout(
        paper_bgcolor='#161b22', plot_bgcolor='#161b22',
        font=dict(family='Inter', color='#8b949e'), height=320,
        margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
        xaxis=dict(showgrid=False, tickfont=dict(size=11), tickangle=-30, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.0f', tickfont=dict(size=11), zeroline=False),
        hoverlabel=dict(bgcolor='#21262d', font_size=13, bordercolor='#30363d'))
    st.plotly_chart(fig, use_container_width=True)

col_bar, col_pie = st.columns([3, 2])
with col_bar:
    st.markdown('<div class="section-title">🏆 P&L por Símbolo</div>', unsafe_allow_html=True)
    if not sym_pnl.empty:
        colors_bar = ['#ff3d57' if v < 0 else '#00d4aa' for v in sym_pnl.values]
        fig2 = go.Figure(go.Bar(
            x=sym_pnl.values, y=sym_pnl.index, orientation='h',
            marker_color=colors_bar,
            hovertemplate='<b>%{y}</b>: $%{x:,.2f}<extra></extra>'))
        fig2.update_layout(
            paper_bgcolor='#161b22', plot_bgcolor='#161b22',
            font=dict(family='Inter', color='#8b949e'), height=300,
            margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
            xaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.0f', tickfont=dict(size=11),
                       zeroline=True, zerolinecolor='#30363d'),
            yaxis=dict(showgrid=False, tickfont=dict(size=12, color='#e6edf3')))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Sem dados no período.")

with col_pie:
    st.markdown('<div class="section-title">⚖️ Win / Loss</div>', unsafe_allow_html=True)
    if (wins + losses) > 0:
        be_c   = int((closed['PnL ($)'] == 0).sum()) if not closed.empty else 0
        labels = ['Wins', 'Losses']; vals = [wins, losses]; cp = ['#00d4aa', '#ff3d57']
        if be_c > 0: labels.append('BE'); vals.append(be_c); cp.append('#ffd600')
        fig3 = go.Figure(go.Pie(
            labels=labels, values=vals, hole=0.6,
            marker=dict(colors=cp, line=dict(color='#161b22', width=3)),
            textfont=dict(size=13),
            hovertemplate='<b>%{label}</b>: %{value} (%{percent})<extra></extra>'))
        fig3.update_layout(
            paper_bgcolor='#161b22', plot_bgcolor='#161b22',
            font=dict(family='Inter', color='#8b949e'), height=300,
            margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
            legend=dict(font=dict(size=12, color='#e6edf3'), bgcolor='#161b22', bordercolor='#30363d'),
            annotations=[dict(text=f'{win_rate*100:.0f}%', x=0.5, y=0.5,
                font=dict(size=26, color='#e6edf3', family='Inter'), showarrow=False)])
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Sem trades fechados no período.")

st.markdown('<div class="section-title">📅 P&L Diário — Trades Fechados</div>', unsafe_allow_html=True)
if not daily_closed.empty:
    colors_d = ['#00d4aa' if v >= 0 else '#ff3d57' for v in daily_closed['Daily PnL']]
    fig4 = go.Figure(go.Bar(
        x=daily_closed['Date'].astype(str), y=daily_closed['Daily PnL'],
        marker_color=colors_d,
        hovertemplate='<b>%{x}</b>: $%{y:,.2f}<extra></extra>'))
    fig4.update_layout(
        paper_bgcolor='#161b22', plot_bgcolor='#161b22',
        font=dict(family='Inter', color='#8b949e'), height=220,
        margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
        xaxis=dict(showgrid=False, tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.0f',
                   tickfont=dict(size=11), zeroline=True, zerolinecolor='#30363d'))
    st.plotly_chart(fig4, use_container_width=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Trade Log", "📂 Posições Abertas", "🗂 Transações Raw"])

with tab1:
    st.markdown('<div class="section-title">Trades Fechados</div>', unsafe_allow_html=True)
    if not closed.empty:
        st.markdown("""
        <div class="trade-header">
            <div style="min-width:55px">Symbol</div>
            <div style="min-width:70px">Expiry</div>
            <div style="min-width:70px">Strike</div>
            <div style="min-width:100px">Open Date</div>
            <div style="min-width:100px">Close Date</div>
            <div style="min-width:110px">Open Cost</div>
            <div style="min-width:110px">Close Credit</div>
            <div style="min-width:100px">PnL ($)</div>
            <div style="min-width:75px">PnL (%)</div>
            <div style="min-width:55px">Result</div>
        </div>""", unsafe_allow_html=True)
        for _, row in closed.sort_values('Close Date').iterrows():
            pnl = row['PnL ($)']; pct = row['PnL (%)']; res = row['Result']
            css    = 'win' if res == 'Win' else 'loss' if res == 'Loss' else 'none'
            pnl_c  = 'win' if pnl > 0 else 'loss'
            oc_val = row['Open Cost']
            oc = f"+${oc_val:,.2f}" if pd.notna(oc_val) and oc_val >= 0 else f"-${abs(oc_val):,.2f}" if pd.notna(oc_val) else '—'
            cc_val = row['Close Credit']
            cc = f"+${cc_val:,.2f}" if cc_val >= 0 else f"-${abs(cc_val):,.2f}"
            pnl_s = f"${pnl:,.2f}"; pct_s = f"{pct:+.1f}%" if pd.notna(pct) else '—'
            sym_color = '#00d4aa' if css == 'win' else '#ff3d57' if css == 'loss' else '#e6edf3'
            strike_s  = str(row['Strike']) if pd.notna(row.get('Strike')) else '—'
            st.markdown(f"""
            <div class="trade-row {css}">
                <div class="trade-cell sym" style="color:{sym_color}">{row['Symbol']}</div>
                <div class="trade-cell muted">{row['Expiry']}</div>
                <div class="trade-cell muted">{strike_s}</div>
                <div class="trade-cell muted">{row['Open Date']}</div>
                <div class="trade-cell muted">{row['Close Date']}</div>
                <div class="trade-cell muted">{oc}</div>
                <div class="trade-cell muted">{cc}</div>
                <div class="trade-cell {pnl_c}">{pnl_s}</div>
                <div class="trade-cell {pnl_c}">{pct_s}</div>
                <div class="trade-cell {pnl_c}" style="font-weight:700">{res}</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("Nenhum trade fechado no período.")

with tab2:
    st.markdown('<div class="section-title">Posições Abertas</div>', unsafe_allow_html=True)
    if not opened.empty:
        for _, op in opened.iterrows():
            net_v  = op['Open Cost']
            color  = '#ff3d57' if net_v < 0 else '#00d4aa'
            net_s  = f"+${net_v:,.2f}" if net_v >= 0 else f"-${abs(net_v):,.2f}"
            strike_s = str(op['Strike']) if pd.notna(op.get('Strike')) else '—'
            st.markdown(f"""<div class="open-pos-card">
                <span style="color:#ffd600;font-weight:600;">{op['Symbol']}</span>
                &nbsp;|&nbsp; <span style="color:#8b949e;">{op['Expiry']} · {strike_s}</span>
                &nbsp;|&nbsp; Net: <span style="color:{color};">{net_s}</span>
                &nbsp;|&nbsp; <span style="color:#8b949e;">desde {op['Open Date']}</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.success("✅ Nenhuma posição aberta.")

with tab3:
    st.markdown('<div class="section-title">Todas as Transações</div>', unsafe_allow_html=True)
    disp_raw = df[['Symbol', 'datetime', 'action', 'net']].copy()
    disp_raw.columns = ['Symbol', 'Data/Hora', 'Ação', 'Net ($)']
    disp_raw['Net ($)'] = disp_raw['Net ($)'].map('${:,.2f}'.format)
    st.dataframe(disp_raw, use_container_width=True, hide_index=True)

st.markdown("""
<div style="text-align:center;color:#484f58;font-size:12px;padding:20px 0;">
    TASTY Dashboard · Powered by Streamlit · Net P&L = fluxo de caixa real (pontos × contratos × 100)
</div>""", unsafe_allow_html=True)
