from pathlib import Path

import streamlit as st

from backend.errors import DashboardError
from ui.errors import dashboard_action

st.set_page_config(
    page_title="AI Smart Energy Management",
    page_icon=":material/bolt:",
    layout="wide",
    initial_sidebar_state="expanded",
)

dashboard_dir = Path(__file__).parent / "ui" / "dashboard"
static_dir = dashboard_dir / "static"
css_file = static_dir / "style.css"
logo_file = static_dir / "Capstone_Logo.png"

if css_file.exists():
    st.html(f"<style>{css_file.read_text(encoding='utf-8')}</style>")

if logo_file.exists():
    st.logo(str(logo_file), size="large")


def overview_page():
    st.title("Overview")
    st.write("Monitor and analyze electricity consumption across German properties.")


def buildings_page():
    st.title("Buildings")
    st.write("Overview of individual facilities and meter metadata.")


pages = st.navigation(
    [
        st.Page(overview_page, title="Overview", icon=":material/overview:"),
        st.Page(buildings_page, title="Buildings", icon=":material/apartment:"),
        st.Page(
            "ui/dashboard/EnergyAnalytics.py",
            title="Energy Analytics",
            icon=":material/energy_program_time_used:",
        ),
        st.Page(
            "ui/dashboard/Forecasting.py",
            title="Forecasting",
            icon=":material/robot_2:",
        ),
        st.Page(
            "ui/dashboard/Advisor.py",
            title="AI Advisor",
            icon=":material/support_agent:",
        ),
        st.Page(
            "ui/dashboard/Reports.py",
            title="Reports",
            icon=":material/description:",
        ),
        st.Page(
            "ui/dashboard/Properties.py",
            title="Properties",
            icon=":material/business_center:",
        ),
    ]
)

try:
    dashboard_action(pages.run)
except DashboardError as error:
    st.error(str(error))
