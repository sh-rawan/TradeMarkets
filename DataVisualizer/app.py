"""DataVisualizer — interactive pages over the shared MarketData store.

    python -m streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="DataVisualizer", page_icon="📈", layout="wide")

st.navigation([
    st.Page("views/data.py", title="Data", icon=":material/table_view:", default=True),
    st.Page("views/monitor.py", title="Bank Nifty monitor", icon=":material/monitoring:"),
    st.Page("views/accuracy.py", title="Predictions vs actual", icon=":material/fact_check:"),
]).run()
