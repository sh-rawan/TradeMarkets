"""DataVisualizer — interactive pages over the shared MarketData store.

    python -m streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="DataVisualizer", page_icon="📈", layout="wide")

st.navigation({
    "Data": [
        st.Page("views/data.py", title="Market data", icon=":material/show_chart:", default=True),
        st.Page("views/financials.py", title="Financials", icon=":material/account_balance:"),
    ],
    "Bank Nifty": [
        st.Page("views/monitor.py", title="Monitor", icon=":material/monitoring:"),
        st.Page("views/accuracy.py", title="Predictions vs actual", icon=":material/fact_check:"),
        st.Page("views/strategy.py", title="Strategy", icon=":material/trending_up:"),
    ],
}).run()
