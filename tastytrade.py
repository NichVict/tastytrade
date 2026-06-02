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
.trade-row.none { background:#161b22; border-left:3px solid #8b949e; }
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


def parse_price(p):
    m = re.search(r'([\d.]+)\s*(db|cr)', str(p).lower())
    if m: return float(m.group(1)) * (1 if m.group(2)=='cr' else -1)
    try: return float(p)
    except: return 0.0

def get_qty(desc):
    nums = re.findall(r'(?:^|[\n\s])-?(\d+)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', str(desc))
    return max((int(n) for n in nums), default=1)

def detect_file_date(filename):
    m = re.search(r'(\d{2})(\d{2})(\d{2})', str(filename))
    if m: return f'20{m.group(1)}-{m.group(2)}-{m.group(3)}'
    return str(date.today())

def parse_date(t, fdate):
    t = str(t).strip(); yr = fdate[:4]
    m = re.match(r'(\d+)/(\d+),?\s*([\d:]+)([ap])?', t)
    if m:
        mo,dy,tp,ap_c = m.group(1),m.group(2),m.group(3),m.group(4)
        if tp.count(':')==1: tp+=':00'
        if ap_c:
            ap='PM' if ap_c=='p' else 'AM'
            try: return pd.to_datetime(f'{yr}/{mo}/{dy} {tp} {ap}',format='%Y/%m/%d %H:%M:%S %p',errors='coerce')
            except: pass
        try: return pd.to_datetime(f'{yr}/{mo}/{dy} {tp}',format='%Y/%m/%d %H:%M:%S',errors='coerce')
        except: pass
    m2 = re.match(r'([\d:]+)([ap])?$', t)
    if m2:
        tp,ap_c = m2.group(1),m2.group(2)
        if tp.count(':')==1: tp+=':00'
        if ap_c:
            ap='PM' if ap_c=='p' else 'AM'
            try: return pd.to_datetime(f'{fdate} {tp} {ap}',format='%Y-%m-%d %H:%M:%S %p',errors='coerce')
            except: pass
        try: return pd.to_datetime(f'{fdate} {tp}',format='%Y-%m-%d %H:%M:%S',errors='coerce')
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

def get_strikes_set(desc):
    return set(re.findall(r'([\d.]+)\s+(?:Call|Put)', str(desc)))

def process_csv(df, fdate):
    df = df.copy()
    df['net_pts']  = df['MarketOrFill'].apply(parse_price)
    df['qty']      = df['Description'].apply(get_qty)
    df['net']      = df['net_pts'] * df['qty'] * 100
    df['datetime'] = df['Time'].apply(lambda t: parse_date(t, fdate))
    df['date']     = df['datetime'].dt.date
    df['action']   = df['Description'].apply(get_action)
    df = df.sort_values('datetime').reset_index(drop=True)
    df['order_base'] = df['Order #'].apply(lambda x: str(x).split('-')[0])

    daily_cash = df.groupby('date')['net'].sum().reset_index()
    daily_cash.columns = ['Date', 'Daily PnL']
    daily_cash['Cumulative PnL'] = daily_cash['Daily PnL'].cumsum()
    sym_pnl = df.groupby('Symbol')['net'].sum().sort_values()

    records = []
    for order_id, grp in df.groupby('order_base'):
        total_net = grp['net'].sum()
        sym = grp['Symbol'].iloc[0]; d = grp['date'].iloc[0]
        min_dt = grp['datetime'].min()
        all_desc = '\n'.join(grp['Description'].tolist())
        has_bto='BTO' in all_desc; has_sto='STO' in all_desc
        has_stc='STC' in all_desc; has_btc='BTC' in all_desc
        is_open  = (has_bto or has_sto) and not (has_stc or has_btc)
        is_close = (has_stc or has_btc) and not (has_bto or has_sto)
        strikes = get_strikes_set(all_desc)
        records.append({'order_id': order_id, 'sym': sym, 'date': d,
                        'datetime': min_dt, 'net': total_net,
                        'is_open': is_open, 'is_close': is_close, 'strikes': strikes})

    records_df = pd.DataFrame(records).sort_values('datetime').reset_index(drop=True)
    open_pool = []; trades = []

    for _, row in records_df.iterrows():
        if row['is_open']:
            open_pool.append({'sym': row['sym'], 'date': row['date'], 'net': row['net'],
                'all_strikes': set(row['strikes']), 'pending_strikes': set(row['strikes']),
                'closed_net': 0.0, 'last_close_date': None})
        elif row['is_close']:
            sym = row['sym']; close_strikes = row['strikes']
            best_idx = None; best_overlap = -1
            for i, op in enumerate(open_pool):
                if op['sym'] != sym: continue
                if close_strikes and op['pending_strikes']:
                    overlap = len(close_strikes & op['pending_strikes'])
                    if overlap > best_overlap: best_overlap = overlap; best_idx = i
                elif not close_strikes and best_idx is None:
                    best_idx = i; best_overlap = 0

            if best_idx is not None and best_overlap > 0:
                op = open_pool[best_idx]
                op['closed_net'] += row['net']; op['last_close_date'] = row['date']
                op['pending_strikes'] -= close_strikes
                if not op['pending_strikes']:
                    pnl = round(op['net'] + op['closed_net'], 2)
                    pct = round((pnl / abs(op['net'])) * 100, 1) if op['net'] != 0 else 0
                    trades.append({'Symbol': op['sym'], 'Open Date': str(op['date']),
                        'Close Date': str(op['last_close_date']), 'Open Cost': op['net'],
                        'Close Credit': op['closed_net'], 'PnL ($)': pnl, 'PnL (%)': pct,
                        'Result': 'Win' if pnl > 0 else 'Loss'})
                    open_pool.pop(best_idx)
            elif best_idx is not None:
                op = open_pool[best_idx]
                op['closed_net'] += row['net']; op['last_close_date'] = row['date']
                pnl = round(op['net'] + op['closed_net'], 2)
                pct = round((pnl / abs(op['net'])) * 100, 1) if op['net'] != 0 else 0
                trades.append({'Symbol': op['sym'], 'Open Date': str(op['date']),
                    'Close Date': str(op['last_close_date']), 'Open Cost': op['net'],
                    'Close Credit': op['closed_net'], 'PnL ($)': pnl, 'PnL (%)': pct,
                    'Result': 'Win' if pnl > 0 else 'Loss'})
                open_pool.pop(best_idx)
            else:
                trades.append({'Symbol': sym, 'Open Date': '(anterior)',
                    'Close Date': str(row['date']), 'Open Cost': None,
                    'Close Credit': row['net'], 'PnL ($)': None, 'PnL (%)': None, 'Result': '—'})

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(
        columns=['Symbol','Open Date','Close Date','Open Cost','Close Credit','PnL ($)','PnL (%)','Result'])

    closed_tmp = [t for t in trades if t.get('PnL ($)') is not None]
    if closed_tmp:
        ct = pd.DataFrame(closed_tmp)
        ct['Close Date'] = pd.to_datetime(ct['Close Date'], errors='coerce')
        daily_closed = ct.groupby('Close Date')['PnL ($)'].sum().reset_index()
        daily_closed.columns = ['Date', 'Daily PnL']
        daily_closed['Cumulative PnL'] = daily_closed['Daily PnL'].cumsum()
    else:
        daily_closed = daily_cash.copy()

    open_positions = {op['sym']: op for op in open_pool}
    return df, trades_df, daily_closed, sym_pnl, open_positions


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
    df, trades_df, daily_closed, sym_pnl, open_positions = process_csv(raw_df, fdate)
except Exception as e:
    st.error(f"Erro ao processar o CSV: {e}")
    st.stop()

# ── Filtro de período ─────────────────────────────────────────────────────────
all_dates = sorted(df['date'].dropna().unique())
min_date  = all_dates[0]
max_date  = all_dates[-1]

st.markdown('<div class="section-title">📅 Filtro de Período</div>', unsafe_allow_html=True)
col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
with col_f1:
    date_start = st.date_input("De", value=min_date, min_value=min_date, max_value=max_date, key="date_start")
with col_f2:
    date_end = st.date_input("Até", value=max_date, min_value=min_date, max_value=max_date, key="date_end")
with col_f3:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
    with col_btn1:
        if st.button("Hoje"):
            date_start = max_date; date_end = max_date
    with col_btn2:
        if st.button("Esta semana"):
            import datetime
            date_end = max_date
            date_start = max_date - datetime.timedelta(days=max_date.weekday())
    with col_btn3:
        if st.button("Este mês"):
            date_start = max_date.replace(day=1); date_end = max_date
    with col_btn4:
        if st.button("Tudo"):
            date_start = min_date; date_end = max_date

if date_start > date_end:
    st.warning("⚠️ Data inicial maior que data final — usando período completo.")
    date_start = min_date; date_end = max_date

df_f = df[(df['date'] >= date_start) & (df['date'] <= date_end)].copy()

if not trades_df.empty:
    trades_df_f = trades_df.copy()
    trades_df_f['_cd'] = pd.to_datetime(trades_df_f['Close Date'], errors='coerce').dt.date
    trades_df_f = trades_df_f[(trades_df_f['_cd'] >= date_start) & (trades_df_f['_cd'] <= date_end)].drop(columns=['_cd'])
else:
    trades_df_f = trades_df.copy()

if not daily_closed.empty:
    dc_f = daily_closed.copy()
    dc_f['_d'] = pd.to_datetime(dc_f['Date'], errors='coerce').dt.date
    dc_f = dc_f[(dc_f['_d'] >= date_start) & (dc_f['_d'] <= date_end)].drop(columns=['_d'])
    dc_f['Cumulative PnL'] = dc_f['Daily PnL'].cumsum()
else:
    dc_f = daily_closed.copy()

sym_pnl_f = df_f.groupby('Symbol')['net'].sum().sort_values()
sym_pnl_f = sym_pnl_f[sym_pnl_f != 0]

st.markdown("---")
df = df_f; trades_df = trades_df_f; daily_closed = dc_f; sym_pnl = sym_pnl_f

closed = trades_df[trades_df['PnL ($)'].notna()].copy() if not trades_df.empty else pd.DataFrame()

net_pnl       = df['net'].sum()
gross_profit  = df[df['net'] > 0]['net'].sum()
gross_loss    = abs(df[df['net'] < 0]['net'].sum())
profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
total_trades  = len(closed)
wins   = int((closed['PnL ($)'] > 0).sum()) if not closed.empty else 0
losses = int((closed['PnL ($)'] < 0).sum()) if not closed.empty else 0
win_rate = wins / total_trades if total_trades > 0 else 0
avg_win  = closed[closed['PnL ($)'] > 0]['PnL ($)'].mean() if wins > 0 else 0
avg_loss = closed[closed['PnL ($)'] < 0]['PnL ($)'].mean() if losses > 0 else 0

period_label = f"{date_start.strftime('%d/%m/%Y')} → {date_end.strftime('%d/%m/%Y')}"
st.success(f"✅  {uploaded.name}  —  {len(df)} transações  |  {total_trades} operações fechadas  |  📅 {period_label}")

def kpi(label, value, color):
    return f'<div class="kpi-card {color}"><div class="kpi-label">{label}</div><div class="kpi-value {color}">{value}</div></div>'

st.markdown('<div class="section-title">📊 Performance</div>', unsafe_allow_html=True)
nc = "green" if net_pnl >= 0 else "red"
wc = "green" if win_rate >= 0.5 else "red"

c1,c2,c3,c4 = st.columns(4)
with c1: st.markdown(kpi("Net P&L",      f"${net_pnl:,.2f}",      nc),      unsafe_allow_html=True)
with c2: st.markdown(kpi("Gross Profit", f"${gross_profit:,.2f}", "green"),  unsafe_allow_html=True)
with c3: st.markdown(kpi("Gross Loss",   f"-${gross_loss:,.2f}",  "red"),    unsafe_allow_html=True)
with c4: st.markdown(kpi("Profit Factor",f"{profit_factor:.2f}x", "yellow"), unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
c5,c6,c7,c8 = st.columns(4)
with c5: st.markdown(kpi("Total Trades", str(total_trades),      "blue"),  unsafe_allow_html=True)
with c6: st.markdown(kpi("Win Rate",     f"{win_rate*100:.1f}%", wc),      unsafe_allow_html=True)
with c7: st.markdown(kpi("Avg Win",      f"${avg_win:,.2f}",     "green"), unsafe_allow_html=True)
with c8: st.markdown(kpi("Avg Loss",     f"${avg_loss:,.2f}",    "red"),   unsafe_allow_html=True)
st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

st.markdown('<div class="section-title">📈 Cumulative P&L — Operações Fechadas</div>', unsafe_allow_html=True)
if not daily_closed.empty:
    fig = go.Figure()
    dates_str = daily_closed['Date'].astype(str).tolist()
    cum_vals  = daily_closed['Cumulative PnL'].tolist()
    for i in range(len(cum_vals)-1):
        x0,x1=dates_str[i],dates_str[i+1]; y0,y1=cum_vals[i],cum_vals[i+1]
        color='#00d4aa' if (y0>=0 and y1>=0) else '#ff3d57' if (y0<0 and y1<0) else '#ffd600'
        fig.add_trace(go.Scatter(x=[x0,x1],y=[y0,y1],mode='lines',
            line=dict(color=color,width=2.5),showlegend=False,hoverinfo='skip'))
    pt_colors=['#00d4aa' if v>=0 else '#ff3d57' for v in cum_vals]
    fig.add_trace(go.Scatter(x=dates_str,y=cum_vals,mode='markers',
        marker=dict(size=7,color=pt_colors,line=dict(color='#0d1117',width=2)),
        hovertemplate='<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>',showlegend=False))
    fig.add_trace(go.Scatter(x=dates_str,y=[max(v,0) for v in cum_vals],
        fill='tozeroy',fillcolor='rgba(0,212,170,0.07)',line=dict(width=0),showlegend=False,hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=dates_str,y=[min(v,0) for v in cum_vals],
        fill='tozeroy',fillcolor='rgba(255,61,87,0.07)',line=dict(width=0),showlegend=False,hoverinfo='skip'))
    fig.add_hline(y=0,line_dash="dash",line_color="#30363d",line_width=1)
    fig.update_layout(paper_bgcolor='#161b22',plot_bgcolor='#161b22',
        font=dict(family='Inter',color='#8b949e'),height=320,
        margin=dict(l=10,r=10,t=10,b=10),showlegend=False,
        xaxis=dict(showgrid=False,tickfont=dict(size=11),tickangle=-30,zeroline=False),
        yaxis=dict(showgrid=True,gridcolor='#21262d',tickformat='$,.0f',tickfont=dict(size=11),zeroline=False),
        hoverlabel=dict(bgcolor='#21262d',font_size=13,bordercolor='#30363d'))
    st.plotly_chart(fig,use_container_width=True)

col_bar,col_pie = st.columns([3,2])
with col_bar:
    st.markdown('<div class="section-title">🏆 P&L por Símbolo</div>',unsafe_allow_html=True)
    if not sym_pnl.empty:
        colors_bar=['#ff3d57' if v<0 else '#00d4aa' for v in sym_pnl.values]
        fig2=go.Figure(go.Bar(x=sym_pnl.values,y=sym_pnl.index,orientation='h',
            marker_color=colors_bar,hovertemplate='<b>%{y}</b>: $%{x:,.2f}<extra></extra>'))
        fig2.update_layout(paper_bgcolor='#161b22',plot_bgcolor='#161b22',
            font=dict(family='Inter',color='#8b949e'),height=300,
            margin=dict(l=10,r=10,t=10,b=10),showlegend=False,
            xaxis=dict(showgrid=True,gridcolor='#21262d',tickformat='$,.0f',tickfont=dict(size=11),zeroline=True,zerolinecolor='#30363d'),
            yaxis=dict(showgrid=False,tickfont=dict(size=12,color='#e6edf3')))
        st.plotly_chart(fig2,use_container_width=True)
    else:
        st.info("Sem dados no período selecionado.")

with col_pie:
    st.markdown('<div class="section-title">⚖️ Win / Loss</div>',unsafe_allow_html=True)
    if (wins+losses)>0:
        be_c=int((closed['PnL ($)']==0).sum()) if not closed.empty else 0
        labels=['Wins','Losses']; vals=[wins,losses]; cp=['#00d4aa','#ff3d57']
        if be_c>0: labels.append('BE'); vals.append(be_c); cp.append('#ffd600')
        fig3=go.Figure(go.Pie(labels=labels,values=vals,hole=0.6,
            marker=dict(colors=cp,line=dict(color='#161b22',width=3)),
            textfont=dict(size=13),hovertemplate='<b>%{label}</b>: %{value} (%{percent})<extra></extra>'))
        fig3.update_layout(paper_bgcolor='#161b22',plot_bgcolor='#161b22',
            font=dict(family='Inter',color='#8b949e'),height=300,
            margin=dict(l=10,r=10,t=10,b=10),showlegend=True,
            legend=dict(font=dict(size=12,color='#e6edf3'),bgcolor='#161b22',bordercolor='#30363d'),
            annotations=[dict(text=f'{win_rate*100:.0f}%',x=0.5,y=0.5,
                font=dict(size=26,color='#e6edf3',family='Inter'),showarrow=False)])
        st.plotly_chart(fig3,use_container_width=True)
    else:
        st.info("Sem trades fechados no período.")

st.markdown('<div class="section-title">📅 P&L Diário — Operações Fechadas</div>',unsafe_allow_html=True)
if not daily_closed.empty:
    colors_d=['#00d4aa' if v>=0 else '#ff3d57' for v in daily_closed['Daily PnL']]
    fig4=go.Figure(go.Bar(x=daily_closed['Date'].astype(str),y=daily_closed['Daily PnL'],
        marker_color=colors_d,hovertemplate='<b>%{x}</b>: $%{y:,.2f}<extra></extra>'))
    fig4.update_layout(paper_bgcolor='#161b22',plot_bgcolor='#161b22',
        font=dict(family='Inter',color='#8b949e'),height=220,
        margin=dict(l=10,r=10,t=10,b=10),showlegend=False,
        xaxis=dict(showgrid=False,tickangle=-30,tickfont=dict(size=11)),
        yaxis=dict(showgrid=True,gridcolor='#21262d',tickformat='$,.0f',tickfont=dict(size=11),zeroline=True,zerolinecolor='#30363d'))
    st.plotly_chart(fig4,use_container_width=True)

tab1,tab2,tab3 = st.tabs(["📋 Trade Log","📂 Posições Abertas","🗂 Transações Raw"])

with tab1:
    st.markdown('<div class="section-title">Operações Fechadas</div>',unsafe_allow_html=True)
    if not closed.empty:
        st.markdown("""
        <div class="trade-header">
            <div style="min-width:60px">Symbol</div>
            <div style="min-width:110px">Open Date</div>
            <div style="min-width:110px">Close Date</div>
            <div style="min-width:110px">Open Cost</div>
            <div style="min-width:120px">Close Credit</div>
            <div style="min-width:110px">PnL ($)</div>
            <div style="min-width:80px">PnL (%)</div>
            <div style="min-width:60px">Result</div>
        </div>""",unsafe_allow_html=True)
        for _,row in closed.iterrows():
            pnl=row['PnL ($)']; pct=row['PnL (%)']; res=row['Result']
            css='win' if res=='Win' else 'loss' if res=='Loss' else 'none'
            pnl_c='win' if pnl>0 else 'loss'
            oc_val=row['Open Cost']
            oc=f"+${oc_val:,.2f}" if pd.notna(oc_val) and oc_val>=0 else f"-${abs(oc_val):,.2f}" if pd.notna(oc_val) else '—'
            cc_val=row['Close Credit']
            cc=f"+${cc_val:,.2f}" if cc_val>=0 else f"-${abs(cc_val):,.2f}"
            pnl_s=f"${pnl:,.2f}"; pct_s=f"{pct:+.1f}%" if pd.notna(pct) else '—'
            sym_color='#00d4aa' if css=='win' else '#ff3d57' if css=='loss' else '#e6edf3'
            st.markdown(f"""
            <div class="trade-row {css}">
                <div class="trade-cell sym" style="color:{sym_color}">{row['Symbol']}</div>
                <div class="trade-cell muted">{row['Open Date']}</div>
                <div class="trade-cell muted">{row['Close Date']}</div>
                <div class="trade-cell muted">{oc}</div>
                <div class="trade-cell muted">{cc}</div>
                <div class="trade-cell {pnl_c}">{pnl_s}</div>
                <div class="trade-cell {pnl_c}">{pct_s}</div>
                <div class="trade-cell {pnl_c}" style="font-weight:700">{res}</div>
            </div>""",unsafe_allow_html=True)
    else:
        st.info("Nenhuma operação fechada no período selecionado.")

with tab2:
    st.markdown('<div class="section-title">Posições Abertas</div>',unsafe_allow_html=True)
    if open_positions:
        for sym,op in open_positions.items():
            net_v=op['net']; color='#ff3d57' if net_v<0 else '#00d4aa'
            net_s=f"+${net_v:,.2f}" if net_v>=0 else f"-${abs(net_v):,.2f}"
            st.markdown(f"""<div class="open-pos-card">
                <span style="color:#ffd600;font-weight:600;">{sym}</span>
                &nbsp;|&nbsp; Net: <span style="color:{color};">{net_s}</span>
                &nbsp;|&nbsp; <span style="color:#8b949e;">{op.get('date','')}</span>
            </div>""",unsafe_allow_html=True)
    else:
        st.success("✅ Nenhuma posição aberta neste arquivo.")

with tab3:
    st.markdown('<div class="section-title">Todas as Transações</div>',unsafe_allow_html=True)
    disp_raw=df[['Symbol','datetime','action','net','qty','Status']].copy()
    disp_raw.columns=['Symbol','Data/Hora','Ação','Net ($)','Contratos','Status']
    disp_raw['Net ($)']=disp_raw['Net ($)'].map('${:,.2f}'.format)
    st.dataframe(disp_raw,use_container_width=True,hide_index=True)

st.markdown("""
<div style="text-align:center;color:#484f58;font-size:12px;padding:20px 0;">
    TASTY Dashboard · Powered by Streamlit · Net P&L = fluxo de caixa real (pontos × contratos × 100)
</div>""",unsafe_allow_html=True)
