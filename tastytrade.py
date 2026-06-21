import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import pdfplumber
from datetime import date
from collections import defaultdict, deque

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


# ── Parser do Statement / Confirmation PDF ────────────────────────────────────

def parse_pdf(uploaded_file) -> list[dict]:
    """
    Extrai transações de statements mensais ou confirmations diários da Apex.
    Retorna lista de dicts: date, bs, sym, put_call, expiry, strike, qty, price, net
    """
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    transactions = []

    pattern = re.compile(
        r'(BOUGHT|SOLD)\s+'
        r'(\d{2}/\d{2}/\d{2})\s+'   # trade date MM/DD/YY
        r'M\s+'                       # account type
        r'(CALL|PUT)\s+'              # tipo
        r'(\w+)\s+'                   # symbol
        r'(\d{2}/\d{2}/\d{2})\s+'    # expiry MM/DD/YY
        r'([\d.]+)\s+'               # strike
        r'(\d+)\s+'                  # qty
        r'([\d.,]+)'                 # price
    )

    for m in pattern.finditer(text):
        bs     = m.group(1)
        date_s = m.group(2)          # MM/DD/YY
        pc     = m.group(3)
        sym    = m.group(4)
        expiry = m.group(5)          # MM/DD/YY
        strike = float(m.group(6))
        qty    = int(m.group(7))
        price  = float(m.group(8).replace(',', ''))

        # Converte datas para YYYY-MM-DD
        mo, dy, yr = date_s.split('/')
        date_fmt = f"20{yr}-{mo}-{dy}"
        mo2, dy2, yr2 = expiry.split('/')
        expiry_fmt = f"20{yr2}-{mo2}-{dy2}"

        net = price * qty * 100 * (1 if bs == 'SOLD' else -1)

        transactions.append({
            'date'    : date_fmt,
            'bs'      : bs,
            'sym'     : sym,
            'put_call': pc,
            'expiry'  : expiry_fmt,
            'strike'  : strike,
            'qty'     : qty,
            'price'   : price,
            'net'     : net,
        })

    return transactions


# ── FIFO matcher → Trade Log ──────────────────────────────────────────────────

def build_trade_log(txns: list[dict]) -> pd.DataFrame:
    """
    FIFO por (sym, expiry, strike):
    - BOUGHT → empilha preço de entrada
    - SOLD   → desempilha e calcula PnL = (sell - buy) * qty * 100
    Retorna DataFrame com trades fechados e posições abertas.
    """
    # Ordena cronologicamente
    txns_sorted = sorted(txns, key=lambda x: x['date'])

    # Pilha por chave: lista de {'price': float, 'date': str}
    stacks = defaultdict(deque)
    trades = []

    for t in txns_sorted:
        key = (t['sym'], t['expiry'], t['strike'], t['put_call'])

        if t['bs'] == 'BOUGHT':
            # Empilha 1 entrada por contrato
            for _ in range(t['qty']):
                stacks[key].append({'price': t['price'], 'date': t['date']})

        else:  # SOLD
            qty_need = t['qty']
            while qty_need > 0 and stacks[key]:
                opener   = stacks[key].popleft()
                pnl      = (t['price'] - opener['price']) * 100
                pct      = round((pnl / (opener['price'] * 100)) * 100, 1) if opener['price'] else 0
                trades.append({
                    'Symbol'      : t['sym'],
                    'Type'        : t['put_call'],
                    'Strike'      : t['strike'],
                    'Expiry'      : t['expiry'],
                    'Open Date'   : opener['date'],
                    'Close Date'  : t['date'],
                    'Buy Price'   : opener['price'],
                    'Sell Price'  : t['price'],
                    'PnL ($)'     : round(pnl, 2),
                    'PnL (%)'     : pct,
                    'Result'      : 'Win' if pnl > 0 else ('Loss' if pnl < 0 else 'BE'),
                    'Status'      : 'Fechado',
                })
                qty_need -= 1

    # Posições abertas (ainda na pilha)
    for key, stack in stacks.items():
        sym, expiry, strike, pc = key
        for opener in stack:
            trades.append({
                'Symbol'    : sym,
                'Type'      : pc,
                'Strike'    : strike,
                'Expiry'    : expiry,
                'Open Date' : opener['date'],
                'Close Date': '—',
                'Buy Price' : opener['price'],
                'Sell Price': None,
                'PnL ($)'   : 0.0,
                'PnL (%)'   : 0.0,
                'Result'    : '—',
                'Status'    : 'Aberto',
            })

    return pd.DataFrame(trades)


# ── UI ────────────────────────────────────────────────────────────────────────

_, col_title = st.columns([1, 8])
with col_title:
    st.markdown("""
    <div style="padding:8px 0 24px 0;">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8b949e;margin-bottom:4px;">tastytrade · apex clearing</div>
        <div style="font-size:32px;font-weight:700;color:#e6edf3;letter-spacing:-1px;">Trading Dashboard</div>
    </div>""", unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div class="section-title">📂 Importar PDFs</div>', unsafe_allow_html=True)
st.markdown('<div style="color:#8b949e;font-size:13px;margin-bottom:12px;">Faça upload dos <b>statements mensais</b> e/ou <b>confirmations diários</b> da Apex. Pode selecionar múltiplos arquivos de uma vez.</div>', unsafe_allow_html=True)

uploaded_files = st.file_uploader(
    "Arraste os PDFs aqui ou clique para selecionar",
    type=['pdf'],
    accept_multiple_files=True
)

if not uploaded_files:
    st.markdown("""
    <div style="text-align:center;padding:40px;color:#8b949e;">
        <div style="font-size:48px;margin-bottom:16px;">📄</div>
        <div style="font-size:16px;font-weight:500;color:#e6edf3;margin-bottom:8px;">Faça upload dos PDFs para começar</div>
        <div style="font-size:13px;">No tastytrade/Apex: <strong>Statements mensais</strong> ou <strong>Trade Confirmations diárias</strong></div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# Processa todos os PDFs enviados
all_txns = []
errors   = []
for f in uploaded_files:
    try:
        txns = parse_pdf(f)
        all_txns.extend(txns)
    except Exception as e:
        errors.append(f"{f.name}: {e}")

if errors:
    for err in errors:
        st.error(f"Erro ao processar: {err}")

if not all_txns:
    st.warning("Nenhuma transação encontrada nos PDFs enviados.")
    st.stop()

# Remove duplicatas (mesmo arquivo enviado duas vezes)
seen = set()
unique_txns = []
for t in all_txns:
    key = (t['date'], t['bs'], t['sym'], t['expiry'], t['strike'], t['qty'], t['price'])
    if key not in seen:
        seen.add(key)
        unique_txns.append(t)

all_txns = sorted(unique_txns, key=lambda x: x['date'])

# Monta trade log via FIFO
trades_df = build_trade_log(all_txns)
closed    = trades_df[trades_df['Status'] == 'Fechado'].copy()
opened    = trades_df[trades_df['Status'] == 'Aberto'].copy()

# Datas disponíveis
all_dates  = sorted(set(t['date'] for t in all_txns))
min_date   = date.fromisoformat(all_dates[0])
max_date   = date.fromisoformat(all_dates[-1])

# ── Filtro de período ─────────────────────────────────────────────────────────
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

ds = date_start.isoformat()
de = date_end.isoformat()

# Filtra trades fechados no período
closed_f = closed[
    (closed['Close Date'] >= ds) & (closed['Close Date'] <= de)
].copy() if not closed.empty else closed.copy()

# PnL por símbolo no período
sym_pnl = closed_f.groupby('Symbol')['PnL ($)'].sum().sort_values() if not closed_f.empty else pd.Series(dtype=float)
sym_pnl = sym_pnl[sym_pnl != 0]

# PnL diário no período
if not closed_f.empty:
    daily = closed_f.groupby('Close Date')['PnL ($)'].sum().reset_index()
    daily.columns = ['Date', 'Daily PnL']
    daily['Cumulative PnL'] = daily['Daily PnL'].cumsum()
else:
    daily = pd.DataFrame(columns=['Date', 'Daily PnL', 'Cumulative PnL'])

st.markdown("---")

n_files   = len(uploaded_files)
n_txns    = len(all_txns)
n_closed  = len(closed_f)
n_open    = len(opened)
period_s  = f"{date_start.strftime('%d/%m/%Y')} → {date_end.strftime('%d/%m/%Y')}"
st.success(f"✅  {n_files} PDF(s) · {n_txns} transações · {n_closed} trades fechados · {n_open} abertos  |  📅 {period_s}")

# ── KPIs ──────────────────────────────────────────────────────────────────────
net_pnl      = closed_f['PnL ($)'].sum()                               if not closed_f.empty else 0.0
gross_profit = closed_f[closed_f['PnL ($)'] > 0]['PnL ($)'].sum()     if not closed_f.empty else 0.0
gross_loss   = abs(closed_f[closed_f['PnL ($)'] < 0]['PnL ($)'].sum())if not closed_f.empty else 0.0
total_trades = len(closed_f)
wins         = int((closed_f['PnL ($)'] > 0).sum()) if not closed_f.empty else 0
losses       = int((closed_f['PnL ($)'] < 0).sum()) if not closed_f.empty else 0
win_rate     = wins / total_trades if total_trades > 0 else 0
avg_win      = closed_f[closed_f['PnL ($)'] > 0]['PnL ($)'].mean() if wins   > 0 else 0
avg_loss     = closed_f[closed_f['PnL ($)'] < 0]['PnL ($)'].mean() if losses > 0 else 0
profit_factor= avg_win / abs(avg_loss) if avg_loss != 0 else 0

def kpi(label, value, color):
    return f'<div class="kpi-card {color}"><div class="kpi-label">{label}</div><div class="kpi-value {color}">{value}</div></div>'

st.markdown('<div class="section-title">📊 Performance</div>', unsafe_allow_html=True)
nc = "green" if net_pnl >= 0 else "red"
wc = "green" if win_rate >= 0.5 else "red"

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(kpi("Net P&L",       f"${net_pnl:,.2f}",      nc),      unsafe_allow_html=True)
with c2: st.markdown(kpi("Gross Profit",  f"${gross_profit:,.2f}", "green"),  unsafe_allow_html=True)
with c3: st.markdown(kpi("Gross Loss",    f"-${gross_loss:,.2f}",  "red"),    unsafe_allow_html=True)
with c4: st.markdown(kpi("Profit Factor", f"{profit_factor:.2f}x", "yellow"), unsafe_allow_html=True)
st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
c5, c6, c7, c8 = st.columns(4)
with c5: st.markdown(kpi("Total Trades", str(total_trades),       "blue"),  unsafe_allow_html=True)
with c6: st.markdown(kpi("Win Rate",     f"{win_rate*100:.1f}%",  wc),      unsafe_allow_html=True)
with c7: st.markdown(kpi("Avg Win",      f"${avg_win:,.2f}",      "green"), unsafe_allow_html=True)
with c8: st.markdown(kpi("Avg Loss",     f"${avg_loss:,.2f}",     "red"),   unsafe_allow_html=True)
st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

# ── Gráfico Cumulative P&L ────────────────────────────────────────────────────
st.markdown('<div class="section-title">📈 Cumulative P&L</div>', unsafe_allow_html=True)
if not daily.empty:
    fig = go.Figure()
    dates_str = daily['Date'].astype(str).tolist()
    cum_vals  = daily['Cumulative PnL'].tolist()
    for i in range(len(cum_vals) - 1):
        x0, x1 = dates_str[i], dates_str[i+1]
        y0, y1 = cum_vals[i], cum_vals[i+1]
        color = '#00d4aa' if (y0 >= 0 and y1 >= 0) else '#ff3d57' if (y0 < 0 and y1 < 0) else '#ffd600'
        fig.add_trace(go.Scatter(x=[x0,x1], y=[y0,y1], mode='lines',
            line=dict(color=color, width=2.5), showlegend=False, hoverinfo='skip'))
    pt_colors = ['#00d4aa' if v >= 0 else '#ff3d57' for v in cum_vals]
    fig.add_trace(go.Scatter(x=dates_str, y=cum_vals, mode='markers',
        marker=dict(size=7, color=pt_colors, line=dict(color='#0d1117', width=2)),
        hovertemplate='<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>', showlegend=False))
    fig.add_trace(go.Scatter(x=dates_str, y=[max(v,0) for v in cum_vals],
        fill='tozeroy', fillcolor='rgba(0,212,170,0.07)', line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=dates_str, y=[min(v,0) for v in cum_vals],
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
        be_c   = int((closed_f['PnL ($)'] == 0).sum()) if not closed_f.empty else 0
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

st.markdown('<div class="section-title">📅 P&L Diário</div>', unsafe_allow_html=True)
if not daily.empty:
    colors_d = ['#00d4aa' if v >= 0 else '#ff3d57' for v in daily['Daily PnL']]
    fig4 = go.Figure(go.Bar(
        x=daily['Date'].astype(str), y=daily['Daily PnL'],
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
    if not closed_f.empty:
        st.markdown("""
        <div class="trade-header">
            <div style="min-width:55px">Symbol</div>
            <div style="min-width:45px">Type</div>
            <div style="min-width:70px">Strike</div>
            <div style="min-width:90px">Expiry</div>
            <div style="min-width:95px">Open Date</div>
            <div style="min-width:95px">Close Date</div>
            <div style="min-width:90px">Buy Price</div>
            <div style="min-width:90px">Sell Price</div>
            <div style="min-width:95px">PnL ($)</div>
            <div style="min-width:70px">PnL (%)</div>
            <div style="min-width:55px">Result</div>
        </div>""", unsafe_allow_html=True)
        for _, row in closed_f.sort_values('Close Date').iterrows():
            pnl = row['PnL ($)']; pct = row['PnL (%)']; res = row['Result']
            css   = 'win' if res == 'Win' else 'loss' if res == 'Loss' else 'none'
            pnl_c = 'win' if pnl > 0 else 'loss'
            sym_color = '#00d4aa' if css == 'win' else '#ff3d57' if css == 'loss' else '#e6edf3'
            pnl_s = f"${pnl:,.2f}"; pct_s = f"{pct:+.1f}%"
            st.markdown(f"""
            <div class="trade-row {css}">
                <div class="trade-cell sym" style="color:{sym_color}">{row['Symbol']}</div>
                <div class="trade-cell muted">{row['Type']}</div>
                <div class="trade-cell muted">{row['Strike']:.1f}</div>
                <div class="trade-cell muted">{row['Expiry']}</div>
                <div class="trade-cell muted">{row['Open Date']}</div>
                <div class="trade-cell muted">{row['Close Date']}</div>
                <div class="trade-cell muted">${row['Buy Price']:.2f}</div>
                <div class="trade-cell muted">${row['Sell Price']:.2f}</div>
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
            cost = op['Buy Price'] * 100
            st.markdown(f"""<div class="open-pos-card">
                <span style="color:#ffd600;font-weight:600;">{op['Symbol']}</span>
                &nbsp;|&nbsp; <span style="color:#8b949e;">{op['Type']} {op['Strike']:.1f} · exp {op['Expiry']}</span>
                &nbsp;|&nbsp; Compra: <span style="color:#ff3d57;">${op['Buy Price']:.2f}</span>
                &nbsp;|&nbsp; Custo: <span style="color:#ff3d57;">-${cost:.0f}</span>
                &nbsp;|&nbsp; <span style="color:#8b949e;">desde {op['Open Date']}</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.success("✅ Nenhuma posição aberta.")

with tab3:
    st.markdown('<div class="section-title">Todas as Transações</div>', unsafe_allow_html=True)
    raw_df = pd.DataFrame(all_txns)[['date','bs','sym','put_call','strike','expiry','qty','price','net']]
    raw_df.columns = ['Data','B/S','Symbol','Tipo','Strike','Expiry','Qty','Preço','Net ($)']
    raw_df['Net ($)'] = raw_df['Net ($)'].map('${:,.2f}'.format)
    st.dataframe(raw_df.sort_values('Data'), use_container_width=True, hide_index=True)

st.markdown("""
<div style="text-align:center;color:#484f58;font-size:12px;padding:20px 0;">
    TASTY Dashboard · Apex Clearing · PnL = (sell − buy) × qty × 100
</div>""", unsafe_allow_html=True)
