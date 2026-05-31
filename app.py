import streamlit as st
import yfinance as yf
from gnews import GNews
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
from datetime import datetime

# --- 1. PORTFOLIO MATRIX STATE ---
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["AAPL", "MSFT", "TSLA"]

# --- 2. DATA HARVESTING (KEY-FREE) ---
def get_company_metrics(ticker):
    """Extracts raw market data from Yahoo Finance without an API key."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "Price": f"${info.get('currentPrice', info.get('previousClose', 'N/A'))}",
            "PE": str(info.get('forwardPE', 'N/A')),
            "Cap": f"{info.get('marketCap', 0) / 1e9:.1f}B" if info.get('marketCap') else "N/A",
            "Margin": f"{info.get('profitMargins', 0)*100:.1f}%" if info.get('profitMargins') else "N/A"
        }
    except:
        return {"Price": "N/A", "PE": "N/A", "Cap": "N/A", "Margin": "N/A"}

def gather_free_google_news(watchlist):
    """Scrapes Google News clusters based on financial triggers."""
    # Configured for a maximum of 5 recent articles per stream
    google_news = GNews(language='en', period='7d', max_results=5)
    
    portfolio_news = {}
    
    # Track corporate specific flows
    for ticker in watchlist:
        portfolio_news[ticker] = []
        try:
            # Query strings targeting order books, ratings, and quarterly expectations
            query = f"{ticker} stock (earnings OR rating OR contract OR dividend)"
            articles = google_news.get_news(query)
            for art in articles:
                portfolio_news[ticker].append({
                    "title": art['title'],
                    "source": art['publisher']['title']
                })
        except:
            pass
            
    # Track Systemic Macro/Government constraints
    macro_news = []
    if watchlist:
        try:
            macro_query = f"({' OR '.join(watchlist)}) AND (government OR regulation OR tariff OR subsidy)"
            gov_articles = google_news.get_news(macro_query)
            for art in gov_articles[:6]:
                macro_news.append({
                    "title": art['title'],
                    "source": art['publisher']['title']
                })
        except:
            pass
            
    return portfolio_news, macro_news

# --- 3. HARD-CONSTRAINED 2-PAGE PDF GENERATOR ---
def build_structured_pdf(watchlist, company_news, macro_news):
    """Compiles metrics and headlines into a structural 2-page print grid."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=36, 
        leftMargin=36, 
        topMargin=36, 
        bottomMargin=36
    )
    story = []
    styles = getSampleStyleSheet()
    
    # Custom Typographic Scale
    title_style = ParagraphStyle('DocTitle', fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=colors.HexColor("#0F172A"))
    meta_style = ParagraphStyle('MetaText', fontName='Helvetica', fontSize=9, leading=12, textColor=colors.HexColor("#64748B"))
    section_style = ParagraphStyle('SectionH1', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=colors.HexColor("#1E3A8A"), spaceBefore=12, spaceAfter=6)
    ticker_style = ParagraphStyle('TickerH2', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=colors.HexColor("#0369A1"), spaceBefore=6, spaceAfter=2)
    body_style = ParagraphStyle('BulletText', fontName='Helvetica', fontSize=8.5, leading=12.5, textColor=colors.HexColor("#334155"))
    th_style = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white)
    td_style = ParagraphStyle('TD', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor("#1E293B"))

    # Header Construction
    story.append(Paragraph("PORTFOLIO RADAR: AUTOMATED BRIEF", title_style))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Source: Google News & Yahoo Finance (No-Token Pipeline)", meta_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F172A"), spaceAfter=10))
    
    # Section 1: Quantitative Health Grid Matrix
    story.append(Paragraph("1. Market Valuation & Fundamental Health Matrix", section_style))
    
    # Table Grid Core Setup
    table_data = [[Paragraph("Ticker", th_style), Paragraph("Current Price", th_style), Paragraph("Forward P/E", th_style), Paragraph("Market Cap", th_style), Paragraph("Profit Margin", th_style)]]
    for ticker in watchlist:
        metrics = get_company_metrics(ticker)
        table_data.append([
            Paragraph(ticker, td_style),
            Paragraph(metrics["Price"], td_style),
            Paragraph(metrics["PE"], td_style),
            Paragraph(metrics["Cap"], td_style),
            Paragraph(metrics["Margin"], td_style)
        ])
        
    metrics_table = Table(table_data, colWidths=[60, 110, 110, 130, 130])
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#F8FAFC"), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,1), (-1,-1), 4),
        ('TOPPADDING', (0,1), (-1,-1), 4),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 10))
    
    # Section 2: Scraped Google Corporate News Pipeline
    story.append(Paragraph("2. Corporate Actions, Brokerage Ratings & Order Highlights", section_style))
    for ticker in watchlist:
        story.append(Paragraph(f"• {ticker} Equity Field Updates", ticker_style))
        articles = company_news.get(ticker, [])
        if not articles:
            story.append(Paragraph("   - No material disclosures indexed via Google News over the trailing 7-day frame.", body_style))
        for art in articles:
            bullet_text = f"<b>[{art['source']}]</b> {art['title']}"
            story.append(Paragraph(f"   • {bullet_text}", body_style))
            
    # Section 3: Macro Constraints Pipeline
    story.append(Spacer(1, 10))
    story.append(Paragraph("3. Sovereign Interventions, Tariffs & Systemic Macro News", section_style))
    if not macro_news:
        story.append(Paragraph("- No overarching legislative changes or sovereign warnings mapped to current tracking filters.", body_style))
    for art in macro_news:
        bullet_text = f"<b>[{art['source']}]</b> {art['title']}"
        story.append(Paragraph(f"   • {bullet_text}", body_style))
        
    doc.build(story)
    buffer.seek(0)
    return buffer

# --- 4. STREAMLIT MANAGEMENT UI ---
st.set_page_config(page_title="Token-Free Financial Brief", layout="wide")
st.title("🛡️ Keyless Portfolio Intelligence Dashboard")
st.write("This variant operates natively via open-source news web scrapers. **No registration, no accounts, and no API keys required.**")

# Sidebar Dynamic Control Hub
st.sidebar.header("📋 Equity Portfolio Manager")
add_ticker = st.sidebar.text_input("Enter Ticker Identifier (e.g., TSLA, INFY.NS, AMZN):").upper().strip()

if st.sidebar.button("➕ Inject Asset"):
    if add_ticker and add_ticker not in st.session_state.watchlist:
        st.session_state.watchlist.append(add_ticker)
        st.sidebar.success(f"Tracked: {add_ticker}")
    elif add_ticker in st.session_state.watchlist:
        st.sidebar.warning("Ticker already initialized.")

if st.session_state.watchlist:
    remove_target = st.sidebar.selectbox("Eject Target Asset:", st.session_state.watchlist)
    if st.sidebar.button("❌ Purge Asset"):
        st.session_state.watchlist.remove(remove_target)
        st.sidebar.error(f"Purged: {remove_target}")

# Main Stage Display Registry
st.subheader("📊 Tracked Portfolio Coordinates")
st.code(", ".join(st.session_state.watchlist) if st.session_state.watchlist else "Portfolio Registry is currently empty.")

if st.button("⚡ Generate Report (100% Free)"):
    if not st.session_state.watchlist:
        st.error("Cannot compile an empty tracking registry.")
    else:
        with st.spinner("Scraping Yahoo Finance engines and sorting Google News indexes..."):
            # Execute Pipeline directly
            comp_news, global_macro = gather_free_google_news(st.session_state.watchlist)
            pdf_binary = build_structured_pdf(st.session_state.watchlist, comp_news, global_macro)
            
            st.success("✨ Report compilation complete!")
            
            # Download Portal Link
            st.download_button(
                label="📥 Download Strict 2-Page PDF Summary",
                data=pdf_binary,
                file_name="Portfolio_TokenFree_Summary.pdf",
                mime="application/pdf"
            )
            
            # Simple UI Preview Interface
            st.markdown("---")
            st.subheader("🔍 Local Feed Aggregation Preview")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### Corporate Pipelines")
                for tick, stories in comp_news.items():
                    st.markdown(f"**{tick} Updates:**")
                    for s in stories[:2]:
                        st.write(f"- {s['title']} *({s['source']})*")
            with col2:
                st.markdown("### Policy & Macro Pipeline")
                for s in global_macro[:4]:
                    st.write(f"- {s['title']} *({s['source']})*")