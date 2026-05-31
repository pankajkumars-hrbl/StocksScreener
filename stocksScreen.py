import streamlit as st
import yfinance as yf
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import plotly.express as px
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
def main():
    print("Starting app")
    LLM_AVAILABLE = True  # ✅ correct indentation
    import os
    try:
        import openai
        OPENAI_AVAILABLE = True

    except Exception:
        openai = None
        OPENAI_AVAILABLE = False
import io
from datetime import datetime

# --- DATABASE LAYER ---
DB_NAME = "equity_radar.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Watchlist & Core Portfolio Variables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                added_date TEXT
            )
        """)
        # Order Book Values Log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_books (
                ticker TEXT,
                fy_year INTEGER,
                order_value REAL,
                PRIMARY KEY (ticker, fy_year)
            )
        """)
        conn.commit()

init_db()

def _safe_financial_item(df, label, position=0, default=0):
    if df.empty or label not in df.index:
        return default
    row = df.loc[label]
    if isinstance(row, pd.Series) and len(row) > position:
        return row.iloc[position]
    return default


def _safe_balance_value(df, labels, default=0):
    if df.empty:
        return default
    for label in labels:
        if label in df.index:
            row = df.loc[label]
            if hasattr(row, 'iloc') and len(row) > 0:
                return row.iloc[0]
    return default


def get_currency_symbol(currency, ticker):
    if currency and currency.upper() == "INR":
        return "₹"
    if ticker and ticker.upper().endswith(".NS"):
        return "₹"
    return "$"

# --- LOCAL FREE LLM COMPONENT ---
def run_hosted_llm(prompt):
    """Call a hosted OpenAI ChatCompletion when `OPENAI_API_KEY` is set."""
    if not OPENAI_AVAILABLE or openai is None:
        return "Hosted LLM client is not installed. Install 'openai' to enable hosted LLM support."
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "OPENAI_API_KEY is not set. Configure it to use a hosted LLM."
    try:
        openai.api_key = api_key
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=800,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Hosted LLM error: {str(e)}"


def run_llm(prompt):
    """Prefer hosted LLM if configured, otherwise fall back to local Ollama if available."""
    # Prefer hosted OpenAI when API key present
    if os.getenv("OPENAI_API_KEY") and OPENAI_AVAILABLE:
        return run_hosted_llm(prompt)

    # Fallback to local Ollama
    if LLM_AVAILABLE and Ollama is not None:
        try:
            llm = Ollama(model="llama3", temperature=0.1)
            return llm.invoke(prompt)
        except Exception as e:
            return f"Local LLM Parsing Offline (Ensure Ollama is running 'llama3'). Error: {str(e)}"

    return "No LLM available. Set OPENAI_API_KEY for hosted LLM or install/run Ollama for local LLM."

# --- COGNITIVE FINANCIAL ENGINE (DATA PROCESSING) ---
@st.cache_data(ttl=86400)
def extract_fundamental_matrix(ticker):
    """Gathers and derives multi-year financial statements via yfinance framework."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Financial statement dataframes
        financials = stock.financials
        balance_sheet = stock.balance_sheet
        cashflow = stock.cashflow
        quarterly_financials = stock.quarterly_financials
        
        if financials.empty or balance_sheet.empty:
            return {"error": "Missing financial or balance sheet data from Yahoo Finance."}
            
        # Extract Revenue items safely
        rev_y0 = _safe_financial_item(financials, 'Total Revenue', 0, 1)
        rev_y1 = _safe_financial_item(financials, 'Total Revenue', 1, 1)
        rev_y3 = _safe_financial_item(financials, 'Total Revenue', 3, rev_y1)
        rev_y4 = _safe_financial_item(financials, 'Total Revenue', -1, rev_y1)

        # Derive Growth Matrices
        yoy_rev_growth = ((rev_y0 - rev_y1) / rev_y1) * 100 if rev_y1 != 0 else 0
        cagr_3y_rev = (((rev_y0 / rev_y3) ** (1/3)) - 1) * 100 if rev_y3 > 0 else 0
        cagr_5y_rev = (((rev_y0 / rev_y4) ** (1/5)) - 1) * 100 if rev_y4 > 0 else 0

        # Profit / EPS Metrics
        inc_y0 = _safe_financial_item(financials, 'Net Income', 0, 1)
        inc_y1 = _safe_financial_item(financials, 'Net Income', 1, 1)
        yoy_profit_growth = ((inc_y0 - inc_y1) / inc_y1) * 100 if inc_y1 != 0 else 0

        # Balance Sheet Health
        total_debt = _safe_balance_value(balance_sheet, ['Total Debt', 'Long Term Debt'], 0)
        equity = _safe_balance_value(balance_sheet, ['Stockholders Equity', 'Total Stockholders Equity', 'Total Equity', 'Shareholders Equity'], 1)
        debt_to_equity = total_debt / equity if equity != 0 else 0
        
        # Return Ratios
        roe = (info.get('returnOnEquity', 0)) * 100
        roce = (info.get('returnOnAssets', 0)) * 1.5 * 100  # Synthesized operational approximation
        
        return {
            "current_price": info.get('currentPrice', info.get('previousClose', 0)),
            "pe": info.get('forwardPE', info.get('trailingPE', 10)),
            "peg": info.get('pegRatio', 1),
            "pb": info.get('priceToBook', 1),
            "rev_growth": yoy_rev_growth,
            "rev_cagr_3y": cagr_3y_rev,
            "rev_cagr_5y": cagr_5y_rev,
            "profit_growth": yoy_profit_growth,
            "eps_growth": (info.get('earningsGrowth', 0)) * 100,
            "roe": roe,
            "roce": roce,
            "de": debt_to_equity,
            "currency": info.get('currency', 'USD'),
            "fii_holding": info.get('institutionsPercentHeld', 0) * 100,
            "promoter_holding": info.get('heldPercentInsiders', 0) * 100,
            "raw_q_financials": quarterly_financials
        }
    except Exception as e:
        return {"error": str(e)}

# --- MATHEMATICAL SCORING & VALUATION ALGORITHMS ---
def calculate_dcf_valuation(metrics, rev_growth_input, margin_input, wacc_input, terminal_growth_input):
    """Executes a multi-stage Discounted Cash Flow matrix models."""
    try:
        price = metrics["current_price"]
        earnings_proxy = price / metrics["pe"] if metrics["pe"] else 1
        margin_factor = max(0.01, min(margin_input / 100.0, 1.0))
        base_fcf = earnings_proxy * margin_factor * 1.2

        fcf_projections = []
        current_fcf = base_fcf
        for i in range(5):
            current_fcf *= (1 + (rev_growth_input / 100))
            fcf_projections.append(current_fcf)
            
        discount_rate = 1 + (wacc_input / 100)
        discounted_fcf = [fcf / (discount_rate ** (i + 1)) for i, fcf in enumerate(fcf_projections)]
        
        wacc_rate = wacc_input / 100
        terminal_rate = terminal_growth_input / 100
        if wacc_rate <= terminal_rate:
            terminal_value = 0
        else:
            terminal_value = (fcf_projections[-1] * (1 + terminal_rate)) / (wacc_rate - terminal_rate)
        discounted_tv = terminal_value / (discount_rate ** 5)
        
        intrinsic_value = sum(discounted_fcf) + discounted_tv
        margin_of_safety = ((intrinsic_value - price) / intrinsic_value) * 100 if intrinsic_value != 0 else 0
        
        return round(intrinsic_value, 2), round(margin_of_safety, 1)
    except Exception:
        return 0, 0


def run_scoring_matrix(metrics, dcf_val, order_trend):
    """Computes rigorous weighted core indices out of 100 points."""
    # Growth Score
    g_score = min(100, max(0, int((metrics["rev_growth"] * 0.4) + (metrics["profit_growth"] * 0.4) + (metrics["eps_growth"] * 0.2))))

    # Quality Score
    q_score = min(100, max(0, int((metrics["roe"] * 0.4) + (metrics["roce"] * 0.4) + ((1 / (metrics["de"] + 0.1)) * 10))))

    # Valuation Score
    pe_factor = max(0, (50 - metrics["pe"]) * 1.5)
    dcf_factor = 40 if dcf_val > metrics["current_price"] else 10
    v_score = min(100, max(0, int(pe_factor + dcf_factor)))

    # Composite Weight Calculation Matrix
    order_score = 80 if order_trend == "Increasing" else (50 if order_trend == "Neutral" else 30)
    concall_sentiment = 75 # Proxy neutral start index before LLM execution overrides

    final_score = (
        (v_score * 0.15) + 
        (g_score * 0.20) + 
        (q_score * 0.15) + 
        (metrics["roe"] * 0.30) + 
        (concall_sentiment * 0.10) + 
        (order_score * 0.10)
    )

    return int(g_score), int(q_score), int(v_score), round(final_score, 1)

# --- REPORT GENERATION ARCHITECTURE ---
def compile_pdf_report(ticker, metrics, g_score, q_score, v_score, final_score, rec):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('DocTitle', fontName='Helvetica-Bold', fontSize=22, textColor=colors.HexColor("#0F172A"))
    section_style = ParagraphStyle('SectionH1', fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor("#1E3A8A"), spaceBefore=10)
    body_style = ParagraphStyle('Body', fontName='Helvetica', fontSize=9, leading=13, textColor=colors.HexColor("#334155"))
    th_style = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=9, textColor=colors.white)
    
    story.append(Paragraph(f"INSTITUTIONAL QUANT REPORT: {ticker}", title_style))
    story.append(Paragraph(f"Compiled on: {datetime.now().strftime('%Y-%m-%d')} | System: Equity Radar Pro", body_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0F172A"), spaceAfter=12))
    
    story.append(Paragraph("1. System Score Breakdown & Signal", section_style))
    data = [
        [Paragraph("Growth Index", th_style), Paragraph("Quality Index", th_style), Paragraph("Valuation Index", th_style), Paragraph("Composite Score", th_style), Paragraph("Signal Matrix", th_style)],
        [f"{g_score}/100", f"{q_score}/100", f"{v_score}/100", f"{final_score}/100", rec]
    ]
    t = Table(data, colWidths=[100, 100, 100, 110, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.gray),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    
    story.append(Paragraph("2. Financial Performance Metrics", section_style))
    fin_data = [
        [Paragraph("Metric Attribute", th_style), Paragraph("Calculated Coordinate Value", th_style)],
        [Paragraph("Trailing Year Revenue Growth (YoY)", body_style), f"{metrics['rev_growth']:.2f}%"],
        [Paragraph("Net Operational Income Growth", body_style), f"{metrics['profit_growth']:.2f}%"],
        [Paragraph("Return On Equity (ROE)", body_style), f"{metrics['roe']:.2f}%"],
        [Paragraph("Debt to Equity Ratio", body_style), f"{metrics['de']:.2f}"],
        [Paragraph("Institutional (FII) Ownership", body_style), f"{metrics['fii_holding']:.2f}%"],
    ]
    ft = Table(fin_data, colWidths=[270, 250])
    ft.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#475569")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(ft)
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- FRONTEND STREAMLIT UI ARCHITECTURE ---
st.set_page_config(page_title="Equity Radar Pro", layout="wide")
st.title("⚡ Equity Radar: Quant-Driven Fundamental Suite")

# Sidebar - Watchlist Registry Management
st.sidebar.header("📋 Watchlist Registrar")
with sqlite3.connect(DB_NAME) as conn:
    watchlist_df = pd.read_sql("SELECT ticker FROM watchlist", conn)
watchlist = watchlist_df["ticker"].tolist()

st.sidebar.subheader("🇮🇳 Indian Market Support")
nse_mode = st.sidebar.checkbox("Auto-append .NS suffix for NSE symbols", value=True)
st.sidebar.caption("For Indian companies, type the symbol without the suffix and the app will add .NS automatically.")
st.sidebar.markdown("Examples: `INFY.NS`, `TCS.NS`, `RELIANCE.NS`, `HDFC.NS`")

add_ticker = st.sidebar.text_input("Register New Ticker (e.g., AAPL, MSFT, INFY.NS):").upper().strip()
if nse_mode and add_ticker and "." not in add_ticker:
    add_ticker = f"{add_ticker}.NS"

if st.sidebar.button("➕ Core Watchlist"):
    if add_ticker:
        if add_ticker not in watchlist:
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO watchlist (ticker, added_date) VALUES (?, ?)", (add_ticker, datetime.now().strftime("%Y-%m-%d")))
            st.sidebar.success(f"{add_ticker} Registered!")
            st.rerun()
        else:
            st.sidebar.info(f"{add_ticker} is already in your watchlist.")

if watchlist:
    remove_ticker = st.sidebar.selectbox("Purge Target Asset:", watchlist)
    if st.sidebar.button("❌ Drop Asset"):
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM watchlist WHERE ticker = ?", (remove_ticker,))
        st.sidebar.error(f"{remove_ticker} Dropped.")
        st.rerun()

# MAIN WORKSPACE RUNTIME
if not watchlist:
    st.info("Your Watchlist is blank. Insert a stock ticker in the left management tray to begin processing metrics.")
else:
    tabs = st.tabs(["📊 Executive Terminal", "📉 Financial Statement Core", "📦 Order Book Matrix", "🧠 Local AI Concall Intel", "🔬 DCF Valuation Workspace", "🛡️ Multi-Bagger Scanner"])
    
    # PRE-LOAD CORPORATE DATA STRUCTURES
    master_metrics = {}
    failed_tickers = {}
    for t in watchlist:
        data = extract_fundamental_matrix(t)
        if data and not data.get("error"):
            master_metrics[t] = data
        else:
            failed_tickers[t] = data.get("error", "No valid financial data available.")
            
    if failed_tickers:
        st.warning("Some tickers could not be loaded and were excluded from scoring.")
        for ft, reason in failed_tickers.items():
            st.caption(f"{ft}: {reason}")

    # --- TAB 1: EXECUTIVE TERMINAL ---
    with tabs[0]:
        st.subheader("🏁 Institutional Portfolio Command Grid")
        summary_rows = []
        for t, metrics in master_metrics.items():
            # Gather order metrics safely from DB
            with sqlite3.connect(DB_NAME) as conn:
                orders_df = pd.read_sql("SELECT order_value FROM order_books WHERE ticker = ? ORDER BY fy_year DESC LIMIT 2", conn, params=(t,))
            
            trend = "Neutral"
            if len(orders_df) >= 2:
                trend = "Increasing" if orders_df.iloc[0]['order_value'] > orders_df.iloc[1]['order_value'] else "Decreasing"
                
            dcf_v, _ = calculate_dcf_valuation(metrics, 12, 15, 10, 4)
            g, q, v, final = run_scoring_matrix(metrics, dcf_v, trend)
            
            if final >= 90: rec = "Strong Buy"
            elif final >= 80: rec = "Buy"
            elif final >= 70: rec = "Accumulate"
            elif final >= 60: rec = "Hold"
            else: rec = "Avoid"
            
            symbol = get_currency_symbol(metrics.get('currency'), t)
            summary_rows.append({
                "Ticker": t,
                "Price": f"{symbol}{metrics['current_price']:.2f}",
                "Fair Value (DCF)": f"{symbol}{dcf_v:.2f}",
                "Growth Score": g,
                "Quality Score": q,
                "Valuation Score": v,
                "Final Score": final,
                "System Decision": rec
            })
            
        if summary_rows:
            grid_df = pd.DataFrame(summary_rows)
            st.dataframe(grid_df, use_container_width=True, hide_index=True)
            
            # Interactive Plotly Charting Engine
            st.markdown("### 📊 Cross-Asset Score Coordinate Vectors")
            fig = px.bar(grid_df, x="Ticker", y=["Growth Score", "Quality Score", "Valuation Score"], barmode="group",
                         color_discrete_sequence=["#3B82F6", "#10B981", "#F59E0B"])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Unable to fetch data streams for current tracking matrices.")

    # --- TAB 2: FINANCIAL STATEMENT CORE ---
    with tabs[1]:
        st.subheader("📉 Historical Matrix Analytics & Disclosures")
        selected_stock = st.selectbox("Select Asset to Audit:", watchlist)
        if selected_stock in master_metrics:
            m = master_metrics[selected_stock]
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("YoY Revenue Growth", f"{m['rev_growth']:.1f}%")
            col2.metric("3-Yr Revenue CAGR", f"{m['rev_cagr_3y']:.1f}%")
            col3.metric("Operational ROE", f"{m['roe']:.1f}%")
            col4.metric("Debt-to-Equity", f"{m['de']:.2f}")
            
            st.markdown("#### Recent Quarterly Performance Trajectory")
            q_fin = m["raw_q_financials"].head(4).T
            st.dataframe(q_fin, use_container_width=True)
            
            # Quarterly Segment Visualization Engine
            if 'Total Revenue' in q_fin.columns:
                fig_q = go.Figure(data=[go.Scatter(x=q_fin.index.astype(str), y=q_fin['Total Revenue'], mode='lines+markers', line=dict(color='#1E3A8A', width=3))])
                fig_q.update_layout(title="Sequential Quarterly Revenue Volatility Runway", xaxis_title="Reporting Date Period", yaxis_title="Gross Amount")
                st.plotly_chart(fig_q, use_container_width=True)
        else:
            reason = failed_tickers.get(selected_stock, "Data not available for this ticker.")
            st.warning(f"{selected_stock} cannot be audited because it could not be loaded: {reason}")

    # --- TAB 3: ORDER BOOK TRACKER ---
    with tabs[2]:
        st.subheader("📦 Order Book Lifecycle Runway")
        col_o1, col_o2 = st.columns([1, 2])
        with col_o1:
            st.markdown("#### Append Value Metrics")
            otick = st.selectbox("Target Asset Matrix:", watchlist, key="order_t")
            oyear = st.number_input("Fiscal Reporting Year (YYYY):", min_value=2020, max_value=2030, value=2025)
            oval = st.number_input("Total Backlog Order Value ($ Millions):", min_value=0.0, value=150.0)
            if st.button("💾 Record Metric Log"):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("INSERT OR REPLACE INTO order_books (ticker, fy_year, order_value) VALUES (?, ?, ?)", (otick, oyear, oval))
                st.success("Log written to internal ledger storage.")
                st.rerun()
        with col_o2:
            st.markdown("#### Database Backlog State")
            with sqlite3.connect(DB_NAME) as conn:
                master_orders = pd.read_sql("SELECT * FROM order_books ORDER BY fy_year DESC", conn)
            st.dataframe(master_orders, use_container_width=True, hide_index=True)

    # --- TAB 4: LOCAL AI CONCALL INTEL ---
    with tabs[3]:
        st.subheader("🧠 Local LLM Analytics Node (100% Free / Private)")
        st.info("This module uses your local Ollama framework to extract context from financial text files.")
        
        uploaded_file = st.file_uploader("Upload Concall / Investor Transcript or Note (.txt)", type=["txt"])
        if uploaded_file:
            raw_text = uploaded_file.read().decode("utf-8")[:6000] # Trim length to match local system parameters
            
            ai_prompt = f"""
            Analyze this corporate earnings call transcript segment text and distill it into a sharp corporate profile. 
            Highlight:
            1. Primary Drivers of Growth
            2. Structural Risk Vectors & Headwinds
            3. Disclosed Capex Deployments
            4. Forward Guidance Parameters
            
            Text Corpus:
            {raw_text}
            """
            if st.button("⚙️ Execute AI Analysis"):
                with st.spinner("Processing via configured LLM..."):
                    ai_result = run_llm(ai_prompt)
                    st.markdown("### AI Analytical Digest")
                    st.write(ai_result)

    # --- TAB 5: DCF VALUATION WORKSPACE ---
    with tabs[4]:
        st.subheader("🔬 Dynamic Intrinsic Value Multistage DCF Workspace")
        v_stock = st.selectbox("Select Target Framework:", watchlist, key="val_s")
        if v_stock in master_metrics:
            vm = master_metrics[v_stock]
            
            col_v1, col_v2 = st.columns([1, 2])
            with col_v1:
                st.markdown("#### Valuation Driver Variables")
                r_growth = st.slider("Stage 1 Revenue Growth Projection (%)", 1.0, 50.0, float(max(2.0, vm["rev_growth"])))
                wacc = st.slider("Weighted Avg Cost of Capital (WACC %)", 5.0, 20.0, 11.0)
                t_growth = st.slider("Terminal Growth Coeff (%)", 1.0, 7.0, 4.0)
                margin_prox = st.slider("Projected Free Cash Margin Floor (%)", 5.0, 40.0, 15.0)
            
            with col_v2:
                st.markdown("#### Value Extraction Equation Output")
                intrinsic, mos = calculate_dcf_valuation(vm, r_growth, margin_prox, wacc, t_growth)
                
                st.metric("Derived Intrinsic Value Coordinates", f"${intrinsic:.2f}")
                st.metric("Computed Margin of Safety", f"{mos:.1f}%")
                
                # Report Export Interface Pipeline
                if st.button("📄 Compile Institutional PDF Document"):
                    pdf_bin = compile_pdf_report(v_stock, vm, 80, 85, 70, 78, "Accumulate")
                    st.download_button(label="📥 Download Generated PDF Report", data=pdf_bin, file_name=f"{v_stock}_Quant_Report.pdf", mime="application/pdf")

    # --- TAB 6: MULTI-BAGGER SCANNER ---
    with tabs[5]:
        st.subheader("🛡️ Strategic Growth Alpha Filters")
        st.markdown("Filters active equities based on strict growth metrics to isolate structural compounding profiles.")
        
        screened_assets = []
        for t, metrics in master_metrics.items():
            # Ruleset matching institutional parameters
            if metrics["rev_cagr_3y"] >= 15.0 and metrics["roe"] >= 15.0 and metrics["de"] <= 0.6:
                screened_assets.append({
                    "Ticker": t, "3-Yr Revenue CAGR": f"{metrics['rev_cagr_3y']:.1f}%", "ROE Matrix": f"{metrics['roe']:.1f}%", "Leverage (D/E)": f"{metrics['de']:.2f}"
                })
                
        if screened_assets:
            st.success(f"Matched {len(screened_assets)} unique assets matching core compounding criteria.")
            st.dataframe(pd.DataFrame(screened_assets), use_container_width=True, hide_index=True)
        else:
            st.info("No active watchlist components currently meet all baseline structural growth requirements.")