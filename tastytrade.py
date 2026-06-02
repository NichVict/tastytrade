
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
.open-pos-card { background:#161b22; border:1px solid #30363d; border-left:3px solid #ffd600; border-radius:8px; padding:12px 16px; margin-bottom:8px; font-family:'JetBrains Mono',monospace; font-size:13px; color:#e6edf3; }
footer{visibility:hidden;} #MainMenu{visibility:hidden;} header{visibility:hidden;}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_price(p):
    p = str(p).strip()
    m = re.search(r'([\d.]+)\s*(db|cr)', p.lower())
    if m:
        val = float(m.group(1))
        return val if m.group(2) == 'cr' else -val
    try: return float(p)
    except: return 0.0

def get_qty(desc):
    """Quantidade máxima de contratos na descrição."""
    nums = re.findall(r'(?:^|[\n\s])-?(\d+)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', str(desc))
    return max((int(n) for n in nums), default=1)

def detect_file_date(filename):
    """Extrai data do nome: tastytrade_activity_260602 → 2026-06-02."""
    m = re.search(r'(\d{2})(\d{2})(\d{2})', str(filename))
    if m:
        return f'20{m.group(1)}-{m.group(2)}-{m.group(3)}'
    return str(date.today())

def parse_date(t, fdate):
    t = str(t).strip()
    yr = fdate[:4]
    # "6/02, 3:03p" — com data
    m = re.match(r'(\d+)/(\d+),?\s*([\d:]+)([ap])?', t)
    if m:
        mo, dy, tp, ap_c = m.group(1), m.group(2), m.group(3), m.group(4)
        if tp.count(':') == 1: tp += ':00'
        if ap_c:
            ap = 'PM' if ap_c == 'p' else 'AM'
            try: return pd.to_datetime(f'{yr}/{mo}/{dy} {tp} {ap}', format='%Y/%m/%d %H:%M:%S %p', errors='coerce')
            except: pass
        try: return pd.to_datetime(f'{yr}/{mo}/{dy} {tp}', format='%Y/%m/%d %H:%M:%S', errors='coerce')
        except: pass
    # "3:03:06p" — só hora → usa data do arquivo
    m2 = re.match(r'([\d:]+)([ap])?$', t)
    if m2:
        tp, ap_c = m2.group(1), m2.group(2)
        if tp.count(':') == 1: tp += ':00'
        if ap_c:
            ap = 'PM' if ap_c == 'p' else 'AM'
            try: return pd.to_datetime(f'{fdate} {tp} {ap}', format='%Y-%m-%d %H:%M:%S %p', errors='coerce')
            except: pass
        try: return pd.to_datetime(f'{fdate} {tp}', format='%Y-%m-%d %H:%M:%S', errors='coerce')
        except: pass
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

def process_csv(df, fdate):
    df = df.copy()
    df['net_pts']  = df['MarketOrFill'].apply(parse_price)
    df['qty']      = df['Description'].apply(get_qty)
    # Dólares reais = pontos × contratos × 100
    df['net']      = df['net_pts'] * df['qty'] * 100
    df['datetime'] = df['Time'].apply(lambda t: parse_date(t, fdate))
    df['date']     = df['datetime'].dt.date
    df['action']   = df['Description'].apply(get_action)
    df = df.sort_values('datetime').reset_index(drop=True)

    # P&L diário = soma dos nets por data (fluxo de caixa real)
    daily = df.groupby('date')['net'].sum().reset_index()
    daily.columns = ['Date', 'Daily PnL']
    daily['Cumulative PnL'] = daily['Daily PnL'].cumsum()

    # P&L por símbolo
    sym_pnl = df.groupby('Symbol')['net'].sum().sort_values()

    # Trade log: casar pernas pelo Order # (agrupa pernas do mesmo order)
    df['order_base'] = df['Order #'].apply(lambda x: str(x).split('-')[0])

    trades = []
    open_stack = {}

    for order_id, grp in df.groupby('order_base'):
        total_net = grp['net'].sum()
        sym = grp['Symbol'].iloc[0]
        d = grp['date'].iloc[0]
        all_desc = ' '.join(grp['Description'].tolist())
        has_open  = 'BTO' in all_desc or 'STO' in all_desc
        has_close = 'STC' in all_desc or 'BTC' in all_desc

        if has_open and not has_close:
            open_stack.setdefault(sym, []).append({'net': total_net, 'date': d, 'order': order_id})
        elif has_close and not has_open:
            if sym in open_stack and open_stack[sym]:
                opener = open_stack[sym].pop(0)
                pnl = round(opener['net'] + total_net, 2)
                trades.append({'Symbol': sym, 'Open Date': str(opener['date']),
                               'Close Date': str(d), 'Open Cost': opener['net'],
                               'Close Credit': total_net, 'PnL': pnl,
                               'Result': 'Win' if pnl > 0 else ('Loss' if pnl < 0 else 'BE')})
            else:
                trades.append({'Symbol': sym, 'Open Date': '(anterior)',
                               'Close Date': str(d), 'Open Cost': None,
                               'Close Credit': total_net, 'PnL': None, 'Result': '—'})
        # MIXED = spread aberto com 2 ordens separadas → trata como OPEN
        elif has_open and has_close:
            open_stack.setdefault(sym, []).append({'net': total_net, 'date': d, 'order': order_id})

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=['Symbol','Open Date','Close Date','Open Cost','Close Credit','PnL','Result'])
    open_positions = {sym: stack for sym, stack in open_stack.items() if stack}

    return df, trades_df, daily, sym_pnl, open_positions


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
    fdate = detect_file_date(uploaded.name)
    raw_df = pd.read_csv(uploaded)
    df, trades_df, daily, sym_pnl, open_positions = process_csv(raw_df, fdate)
except Exception as e:
    st.error(f"Erro ao processar o CSV: {e}")
    st.stop()

closed = trades_df[trades_df['PnL'].notna()].copy() if not trades_df.empty else pd.DataFrame()

# KPIs baseados no fluxo de caixa real (bate com tastytrade)
net_pnl      = df['net'].sum()
gross_profit = df[df['net'] > 0]['net'].sum()
gross_loss   = abs(df[df['net'] < 0]['net'].sum())

total_trades = len(closed) if not closed.empty else 0
wins   = int((closed['PnL'] > 0).sum()) if not closed.empty else 0
losses = int((closed['PnL'] < 0).sum()) if not closed.empty else 0
win_rate = wins / total_trades if total_trades > 0 else 0
avg_win  = closed[closed['PnL'] > 0]['PnL'].mean() if wins > 0 else 0
avg_loss = closed[closed['PnL'] < 0]['PnL'].mean() if losses > 0 else 0
profit_factor = avg_win / avg_loss if gross_loss > 0 else 0

st.success(f"✅  {uploaded.name}  —  {len(df)} transações  |  {len(df['Symbol'].unique())} símbolos  |  data: {fdate}")
st.markdown("---")

# ── KPIs ──────────────────────────────────────────────────────────────────────

def kpi(label, value, color):
    return f'<div class="kpi-card {color}"><div class="kpi-label">{label}</div><div class="kpi-value {color}">{value}</div></div>'

st.markdown('<div class="section-title">📊 Performance</div>', unsafe_allow_html=True)
nc = "green" if net_pnl >= 0 else "red"
wc = "green" if win_rate >= 0.5 else "red"

c1,c2,c3,c4 = st.columns(4)
with c1: st.markdown(kpi("Net P&L",      f"${net_pnl:,.2f}",      nc),      unsafe_allow_html=True)
with c2: st.markdown(kpi("CREDIT", f"${gross_profit:,.2f}", "green"),  unsafe_allow_html=True)
with c3: st.markdown(kpi("DEBIT",   f"-${gross_loss:,.2f}",  "red"),    unsafe_allow_html=True)
with c4: st.markdown(kpi("Profit Factor",f"{profit_factor:.2f}x", "yellow"), unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
c5,c6,c7,c8 = st.columns(4)
with c5: st.markdown(kpi("Total Trades", str(total_trades),         "blue"),  unsafe_allow_html=True)
with c6: st.markdown(kpi("Win Rate",     f"{win_rate*100:.1f}%",    wc),      unsafe_allow_html=True)
with c7: st.markdown(kpi("Avg Win",      f"${avg_win:,.2f}",        "green"), unsafe_allow_html=True)
with c8: st.markdown(kpi("Avg Loss",     f"${avg_loss:,.2f}",       "red"),   unsafe_allow_html=True)
st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

# ── Gráfico Cumulative P&L ────────────────────────────────────────────────────

st.markdown('<div class="section-title">📈 Cumulative P&L</div>', unsafe_allow_html=True)
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=daily['Date'].astype(str), y=daily['Cumulative PnL'],
    fill='tozeroy', fillcolor='rgba(0,212,170,0.08)',
    line=dict(color='#00d4aa', width=2.5), mode='lines+markers',
    marker=dict(size=6, color='#00d4aa', line=dict(color='#0d1117', width=2)),
    hovertemplate='<b>%{x}</b><br>Cumulative: $%{y:,.2f}<extra></extra>'
))
fig.add_hline(y=0, line_dash="dash", line_color="#30363d", line_width=1)
fig.update_layout(
    paper_bgcolor='#161b22', plot_bgcolor='#161b22',
    font=dict(family='Inter', color='#8b949e'), height=300,
    margin=dict(l=10,r=10,t=10,b=10), showlegend=False,
    xaxis=dict(showgrid=False, tickfont=dict(size=11), tickangle=-30, zeroline=False),
    yaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.0f', tickfont=dict(size=11), zeroline=False),
    hoverlabel=dict(bgcolor='#21262d', font_size=13, bordercolor='#30363d'),
)
st.plotly_chart(fig, use_container_width=True)

# ── P&L por Símbolo + Win/Loss ────────────────────────────────────────────────

col_bar, col_pie = st.columns([3, 2])

with col_bar:
    st.markdown('<div class="section-title">🏆 P&L por Símbolo</div>', unsafe_allow_html=True)
    colors_bar = ['#ff3d57' if v < 0 else '#00d4aa' for v in sym_pnl.values]
    fig2 = go.Figure(go.Bar(
        x=sym_pnl.values, y=sym_pnl.index, orientation='h',
        marker_color=colors_bar, hovertemplate='<b>%{y}</b>: $%{x:,.2f}<extra></extra>'))
    fig2.update_layout(
        paper_bgcolor='#161b22', plot_bgcolor='#161b22',
        font=dict(family='Inter', color='#8b949e'), height=280,
        margin=dict(l=10,r=10,t=10,b=10), showlegend=False,
        xaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.0f', tickfont=dict(size=11), zeroline=True, zerolinecolor='#30363d'),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color='#e6edf3')))
    st.plotly_chart(fig2, use_container_width=True)

with col_pie:
    st.markdown('<div class="section-title">⚖️ Win / Loss</div>', unsafe_allow_html=True)
    if (wins + losses) > 0:
        be_c = int((closed['PnL'] == 0).sum()) if not closed.empty else 0
        labels = ['Wins','Losses']; vals = [wins, losses]; cp = ['#00d4aa','#ff3d57']
        if be_c > 0: labels.append('BE'); vals.append(be_c); cp.append('#ffd600')
        fig3 = go.Figure(go.Pie(labels=labels, values=vals, hole=0.6,
            marker=dict(colors=cp, line=dict(color='#161b22', width=3)),
            textfont=dict(size=13), hovertemplate='<b>%{label}</b>: %{value} (%{percent})<extra></extra>'))
        fig3.update_layout(
            paper_bgcolor='#161b22', plot_bgcolor='#161b22',
            font=dict(family='Inter', color='#8b949e'), height=280,
            margin=dict(l=10,r=10,t=10,b=10), showlegend=True,
            legend=dict(font=dict(size=12, color='#e6edf3'), bgcolor='#161b22', bordercolor='#30363d'),
            annotations=[dict(text=f'{win_rate*100:.0f}%', x=0.5, y=0.5,
                              font=dict(size=26, color='#e6edf3', family='Inter'), showarrow=False)])
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Sem trades fechados neste período.")

# ── P&L Diário ────────────────────────────────────────────────────────────────

st.markdown('<div class="section-title">📅 P&L Diário</div>', unsafe_allow_html=True)
colors_d = ['#00d4aa' if v >= 0 else '#ff3d57' for v in daily['Daily PnL']]
fig4 = go.Figure(go.Bar(
    x=daily['Date'].astype(str), y=daily['Daily PnL'],
    marker_color=colors_d, hovertemplate='<b>%{x}</b>: $%{y:,.2f}<extra></extra>'))
fig4.update_layout(
    paper_bgcolor='#161b22', plot_bgcolor='#161b22',
    font=dict(family='Inter', color='#8b949e'), height=200,
    margin=dict(l=10,r=10,t=10,b=10), showlegend=False,
    xaxis=dict(showgrid=False, tickangle=-30, tickfont=dict(size=11)),
    yaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.0f', tickfont=dict(size=11), zeroline=True, zerolinecolor='#30363d'))
st.plotly_chart(fig4, use_container_width=True)

# ── Tabelas ───────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📋 Trade Log", "📂 Posições Abertas", "🗂 Transações Raw"])

with tab1:
    st.markdown('<div class="section-title">Operações Fechadas</div>', unsafe_allow_html=True)
    if not closed.empty:
        disp = closed.copy()
        disp['Open Cost']    = disp['Open Cost'].apply(lambda x: f'${x:,.2f}' if pd.notna(x) else '—')
        disp['Close Credit'] = disp['Close Credit'].apply(lambda x: f'${x:,.2f}' if pd.notna(x) else '—')
        disp['PnL']          = disp['PnL'].apply(lambda x: f'${x:,.2f}' if pd.notna(x) else '—')
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma operação fechada neste arquivo.")

with tab2:
    st.markdown('<div class="section-title">Posições Abertas</div>', unsafe_allow_html=True)
    if open_positions:
        for sym, stack in open_positions.items():
            for pos in stack:
                color = '#ff3d57' if pos['net'] < 0 else '#00d4aa'
                st.markdown(f"""<div class="open-pos-card">
                    <span style="color:#ffd600;font-weight:600;">{sym}</span>
                    &nbsp;|&nbsp; Net: <span style="color:{color};">${pos['net']:,.2f}</span>
                    &nbsp;|&nbsp; <span style="color:#8b949e;">{pos.get('date','')}</span>
                </div>""", unsafe_allow_html=True)
    else:
        st.success("✅ Nenhuma posição aberta neste arquivo.")

with tab3:
    st.markdown('<div class="section-title">Todas as Transações</div>', unsafe_allow_html=True)
    disp_raw = df[['Symbol','datetime','action','net','qty','Status']].copy()
    disp_raw.columns = ['Symbol','Data/Hora','Ação','Net ($)','Contratos','Status']
    disp_raw['Net ($)'] = disp_raw['Net ($)'].map('${:,.2f}'.format)
    st.dataframe(disp_raw, use_container_width=True, hide_index=True)

st.markdown("""
<div style="text-align:center;color:#484f58;font-size:12px;padding:20px 0;">
    TASTY Dashboard · Powered by Streamlit · Net P&L = fluxo de caixa real (pontos × contratos × 100)
</div>""", unsafe_allow_html=True)
