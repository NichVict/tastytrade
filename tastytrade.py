import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
from datetime import date, datetime

st.set_page_config(
    page_title="TASTY Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0d1117; }
section[data-testid="stSidebar"] { background-color: #161b22; }
.main .block-container { padding: 2rem 2rem 2rem 2rem; max-width: 1400px; }

.kpi-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
}
.kpi-card.green::before  { background: #00d4aa; }
.kpi-card.red::before    { background: #ff3d57; }
.kpi-card.yellow::before { background: #ffd600; }
.kpi-card.blue::before   { background: #4f8ef7; }

.kpi-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #8b949e;
    margin-bottom: 8px;
}
.kpi-value { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; line-height: 1; }
.kpi-value.green  { color: #00d4aa; }
.kpi-value.red    { color: #ff3d57; }
.kpi-value.yellow { color: #ffd600; }
.kpi-value.blue   { color: #4f8ef7; }

.section-title {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #00d4aa;
    border-bottom: 1px solid #21262d;
    padding-bottom: 10px;
    margin-bottom: 16px;
}

div[data-testid="stFileUploader"] {
    background: #161b22;
    border: 2px dashed #30363d;
    border-radius: 16px;
    padding: 10px;
}
div[data-testid="stFileUploader"]:hover { border-color: #00d4aa; }
.stDataFrame { border-radius: 8px; overflow: hidden; }

.open-pos-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-left: 3px solid #ffd600;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: #e6edf3;
}

footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


def parse_price(p):
    p = str(p).strip()
    m = re.search(r'([\d.]+)\s*(db|cr)', p.lower())
    if m:
        val = float(m.group(1))
        return val if m.group(2) == 'cr' else -val
    try:
        return float(p)
    except:
        return 0.0

def parse_date(t):
    t = str(t).strip()
    # Formato completo: "6/02, 3:03p"
    m = re.match(r'(\d+)/(\d+),?\s*([\d:]+)([ap])?', t)
    if m:
        month, day = m.group(1), m.group(2)
        time_part = m.group(3)
        ampm = m.group(4)
        if time_part.count(':') == 1:
            time_part += ':00'
        if ampm:
            ap = 'PM' if ampm == 'p' else 'AM'
            try:
                return pd.to_datetime(f'2025/{month}/{day} {time_part} {ap}',
                                      format='%Y/%m/%d %H:%M:%S %p', errors='coerce')
            except:
                pass
        try:
            return pd.to_datetime(f'2025/{month}/{day} {time_part}',
                                  format='%Y/%m/%d %H:%M:%S', errors='coerce')
        except:
            pass
    # Só hora: "3:03:06p" — usa data de hoje
    m2 = re.match(r'([\d:]+)([ap])?$', t)
    if m2:
        time_part = m2.group(1)
        ampm = m2.group(2)
        if time_part.count(':') == 1:
            time_part += ':00'
        today = date.today()
        if ampm:
            ap = 'PM' if ampm == 'p' else 'AM'
            try:
                return pd.to_datetime(f'{today} {time_part} {ap}',
                                      format='%Y-%m-%d %H:%M:%S %p', errors='coerce')
            except:
                pass
        try:
            return pd.to_datetime(f'{today} {time_part}',
                                  format='%Y-%m-%d %H:%M:%S', errors='coerce')
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

def is_close(desc):
    desc = str(desc)
    if 'STC' in desc and 'BTC' in desc: return True
    if 'STC' in desc and 'BTO' not in desc: return True
    if 'BTC' in desc and 'STO' not in desc and 'STC' not in desc: return True
    return False

def process_csv(df):
    df = df.copy()
    df['net']      = df['MarketOrFill'].apply(parse_price)
    df['datetime'] = df['Time'].apply(parse_date)
    df['date']     = df['datetime'].dt.date
    df['action']   = df['Description'].apply(get_action)
    df = df.sort_values('datetime').reset_index(drop=True)

    trades = []
    open_stack = {}

    for _, row in df.iterrows():
        sym  = row['Symbol']
        net  = row['net']
        desc = str(row['Description'])
        d    = row['date']

        if is_close(desc):
            if sym in open_stack and open_stack[sym]:
                opener = open_stack[sym].pop(0)
                pnl = round(opener['net'] + net, 2)
                trades.append({
                    'Symbol': sym, 'Open Date': opener['date'], 'Close Date': d,
                    'Open Cost': opener['net'], 'Close Credit': net,
                    'PnL': pnl, 'Result': 'Win' if pnl > 0 else ('Loss' if pnl < 0 else 'BE')
                })
            else:
                trades.append({
                    'Symbol': sym, 'Open Date': '(abertura anterior)', 'Close Date': d,
                    'Open Cost': None, 'Close Credit': net, 'PnL': None, 'Result': '—'
                })
        else:
            if sym not in open_stack:
                open_stack[sym] = []
            open_stack[sym].append({'net': net, 'date': d, 'desc': desc})

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    closed_with_pnl = trades_df[trades_df['PnL'].notna()] if not trades_df.empty else pd.DataFrame()
    if not closed_with_pnl.empty:
        closed_with_pnl = closed_with_pnl.copy()
        closed_with_pnl['Close Date'] = pd.to_datetime(closed_with_pnl['Close Date'], errors='coerce')
        daily = closed_with_pnl.groupby('Close Date')['PnL'].sum().reset_index()
        daily.columns = ['Date', 'Daily PnL']
    else:
        daily = df.groupby('date')['net'].sum().reset_index()
        daily.columns = ['Date', 'Daily PnL']
    daily['Cumulative PnL'] = daily['Daily PnL'].cumsum()

    open_positions = {sym: stack for sym, stack in open_stack.items() if stack}
    return df, trades_df, daily, open_positions


_, col_title = st.columns([1, 8])
with col_title:
    st.markdown("""
    <div style="padding:8px 0 24px 0;">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8b949e;margin-bottom:4px;">tastytrade</div>
        <div style="font-size:32px;font-weight:700;color:#e6edf3;letter-spacing:-1px;">Trading Dashboard</div>
    </div>""", unsafe_allow_html=True)

st.markdown("---")
st.markdown('<div class="section-title">📂 Importar CSV</div>', unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Arraste o CSV do tastytrade aqui ou clique para selecionar",
    type=['csv'],
    help="Exporte o histórico de atividades do tastytrade em CSV"
)

if uploaded is None:
    st.markdown("""
    <div style="text-align:center;padding:40px;color:#8b949e;">
        <div style="font-size:48px;margin-bottom:16px;">📈</div>
        <div style="font-size:16px;font-weight:500;color:#e6edf3;margin-bottom:8px;">Faça upload do seu CSV para começar</div>
        <div style="font-size:13px;">No tastytrade: <strong>History → Activity → Export</strong></div>
    </div>""", unsafe_allow_html=True)
    st.stop()

try:
    raw_df = pd.read_csv(uploaded)
    df, trades_df, daily, open_positions = process_csv(raw_df)
except Exception as e:
    st.error(f"Erro ao processar o CSV: {e}")
    st.stop()

st.success(f"✅  {uploaded.name}  —  {len(df)} transações  |  {len(trades_df)} operações registadas")
st.markdown("---")

closed = trades_df[trades_df['PnL'].notna()] if not trades_df.empty else pd.DataFrame()

if not closed.empty:
    total_trades  = len(closed)
    wins          = (closed['PnL'] > 0).sum()
    losses        = (closed['PnL'] < 0).sum()
    win_rate      = wins / total_trades if total_trades > 0 else 0
    gross_profit  = closed[closed['PnL'] > 0]['PnL'].sum()
    gross_loss    = abs(closed[closed['PnL'] < 0]['PnL'].sum())
    net_pnl       = closed['PnL'].sum()
    avg_win       = closed[closed['PnL'] > 0]['PnL'].mean() if wins > 0 else 0
    avg_loss      = closed[closed['PnL'] < 0]['PnL'].mean() if losses > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
else:
    total_trades = len(trades_df)
    wins = losses = 0
    win_rate = gross_loss = avg_win = avg_loss = profit_factor = 0
    gross_profit = df[df['net'] > 0]['net'].sum()
    net_pnl = df['net'].sum()

st.markdown('<div class="section-title">📊 Performance</div>', unsafe_allow_html=True)
net_color = "green" if net_pnl >= 0 else "red"
wr_color  = "green" if win_rate >= 0.5 else "red"

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="kpi-card {net_color}"><div class="kpi-label">Net P&L</div><div class="kpi-value {net_color}">${net_pnl:,.2f}</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="kpi-card green"><div class="kpi-label">Gross Profit</div><div class="kpi-value green">${gross_profit:,.2f}</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="kpi-card red"><div class="kpi-label">Gross Loss</div><div class="kpi-value red">-${gross_loss:,.2f}</div></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="kpi-card yellow"><div class="kpi-label">Profit Factor</div><div class="kpi-value yellow">{profit_factor:.2f}x</div></div>', unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
c5, c6, c7, c8 = st.columns(4)
with c5:
    st.markdown(f'<div class="kpi-card blue"><div class="kpi-label">Total Trades</div><div class="kpi-value blue">{total_trades}</div></div>', unsafe_allow_html=True)
with c6:
    st.markdown(f'<div class="kpi-card {wr_color}"><div class="kpi-label">Win Rate</div><div class="kpi-value {wr_color}">{win_rate*100:.1f}%</div></div>', unsafe_allow_html=True)
with c7:
    st.markdown(f'<div class="kpi-card green"><div class="kpi-label">Avg Win</div><div class="kpi-value green">${avg_win:,.2f}</div></div>', unsafe_allow_html=True)
with c8:
    st.markdown(f'<div class="kpi-card red"><div class="kpi-label">Avg Loss</div><div class="kpi-value red">${avg_loss:,.2f}</div></div>', unsafe_allow_html=True)

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

if not daily.empty:
    st.markdown('<div class="section-title">📈 Cumulative P&L</div>', unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily['Date'].astype(str), y=daily['Cumulative PnL'],
        fill='tozeroy', fillcolor='rgba(0,212,170,0.08)',
        line=dict(color='#00d4aa', width=2.5), mode='lines+markers',
        marker=dict(size=6, color='#00d4aa', line=dict(color='#0d1117', width=2)),
        hovertemplate='<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>'
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="#30363d", line_width=1)
    fig.update_layout(
        paper_bgcolor='#161b22', plot_bgcolor='#161b22',
        font=dict(family='Inter', color='#8b949e'),
        height=300, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, tickfont=dict(size=11), tickangle=-30, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.2f', tickfont=dict(size=11), zeroline=False),
        hoverlabel=dict(bgcolor='#21262d', font_size=13, bordercolor='#30363d'),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

col_bar, col_pie = st.columns([3, 2])

with col_bar:
    st.markdown('<div class="section-title">🏆 P&L por Símbolo</div>', unsafe_allow_html=True)
    sym_pnl = closed.groupby('Symbol')['PnL'].sum().sort_values() if not closed.empty else df.groupby('Symbol')['net'].sum().sort_values()
    colors = ['#ff3d57' if v < 0 else '#00d4aa' for v in sym_pnl.values]
    fig2 = go.Figure(go.Bar(
        x=sym_pnl.values, y=sym_pnl.index, orientation='h',
        marker_color=colors, hovertemplate='<b>%{y}</b>: $%{x:,.2f}<extra></extra>',
    ))
    fig2.update_layout(
        paper_bgcolor='#161b22', plot_bgcolor='#161b22',
        font=dict(family='Inter', color='#8b949e'),
        height=260, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.2f', tickfont=dict(size=11), zeroline=True, zerolinecolor='#30363d'),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color='#e6edf3')),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

with col_pie:
    st.markdown('<div class="section-title">⚖️ Win / Loss</div>', unsafe_allow_html=True)
    if (wins + losses) > 0:
        be_count = int((closed['PnL'] == 0).sum()) if not closed.empty else 0
        labels = ['Wins', 'Losses']; values = [int(wins), int(losses)]; colors_pie = ['#00d4aa', '#ff3d57']
        if be_count > 0:
            labels.append('BE'); values.append(be_count); colors_pie.append('#ffd600')
        fig3 = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.6,
            marker=dict(colors=colors_pie, line=dict(color='#161b22', width=3)),
            textfont=dict(size=13, family='Inter'),
            hovertemplate='<b>%{label}</b>: %{value} (%{percent})<extra></extra>',
        ))
        fig3.update_layout(
            paper_bgcolor='#161b22', plot_bgcolor='#161b22',
            font=dict(family='Inter', color='#8b949e'),
            height=260, margin=dict(l=10, r=10, t=10, b=10),
            showlegend=True,
            legend=dict(font=dict(size=12, color='#e6edf3'), bgcolor='#161b22', bordercolor='#30363d'),
            annotations=[dict(text=f'{win_rate*100:.0f}%', x=0.5, y=0.5,
                              font=dict(size=26, color='#e6edf3', family='Inter'), showarrow=False)]
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Faça upload de um CSV com histórico completo para ver Win/Loss.")

if not daily.empty:
    st.markdown('<div class="section-title">📅 P&L Diário</div>', unsafe_allow_html=True)
    colors_d = ['#00d4aa' if v >= 0 else '#ff3d57' for v in daily['Daily PnL']]
    fig4 = go.Figure(go.Bar(
        x=daily['Date'].astype(str), y=daily['Daily PnL'],
        marker_color=colors_d, hovertemplate='<b>%{x}</b>: $%{y:,.2f}<extra></extra>',
    ))
    fig4.update_layout(
        paper_bgcolor='#161b22', plot_bgcolor='#161b22',
        font=dict(family='Inter', color='#8b949e'),
        height=200, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(showgrid=True, gridcolor='#21262d', tickformat='$,.2f', tickfont=dict(size=11), zeroline=True, zerolinecolor='#30363d'),
        showlegend=False,
    )
    st.plotly_chart(fig4, use_container_width=True)

tab1, tab2, tab3 = st.tabs(["📋 Trade Log", "📂 Posições Abertas", "🗂 Transações Raw"])

with tab1:
    st.markdown('<div class="section-title">Operações</div>', unsafe_allow_html=True)
    if not trades_df.empty:
        disp = trades_df.copy()
        disp['Open Cost']    = disp['Open Cost'].apply(lambda x: f'${x:,.2f}' if pd.notna(x) else '—')
        disp['Close Credit'] = disp['Close Credit'].apply(lambda x: f'${x:,.2f}' if pd.notna(x) else '—')
        disp['PnL']          = disp['PnL'].apply(lambda x: f'${x:,.2f}' if pd.notna(x) else '—')
        st.dataframe(disp, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma operação encontrada.")

with tab2:
    st.markdown('<div class="section-title">Posições Ainda Abertas</div>', unsafe_allow_html=True)
    if open_positions:
        for sym, stack in open_positions.items():
            for pos in stack:
                st.markdown(f"""
                <div class="open-pos-card">
                    <span style="color:#ffd600;font-weight:600;">{sym}</span>
                    &nbsp;|&nbsp; Custo: <span style="color:#ff3d57;">${pos['net']:,.2f}</span>
                    &nbsp;|&nbsp; <span style="color:#8b949e;">{pos.get('date','')}</span>
                </div>""", unsafe_allow_html=True)
    else:
        st.success("Nenhuma posição aberta neste arquivo.")

with tab3:
    st.markdown('<div class="section-title">Todas as Transações</div>', unsafe_allow_html=True)
    disp_raw = df[['Symbol','datetime','action','net','Status','Description']].copy()
    disp_raw.columns = ['Symbol','Data/Hora','Ação','Net ($)','Status','Descrição']
    disp_raw['Net ($)'] = disp_raw['Net ($)'].map('${:,.2f}'.format)
    st.dataframe(disp_raw, use_container_width=True, hide_index=True)

st.markdown("""
<div style="text-align:center;color:#484f58;font-size:12px;padding:20px 0;">
    TASTY Dashboard · Powered by Streamlit · Dados do tastytrade
</div>""", unsafe_allow_html=True)
