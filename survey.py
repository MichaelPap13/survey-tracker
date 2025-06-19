import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px

# Load secrets from .env
AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
TABLE_NAME = st.secrets["AIRTABLE_TABLE_NAME"]

# Show token status for debug
st.sidebar.code(f"TOKEN loaded? {'Yes' if AIRTABLE_TOKEN else 'No'}")
st.sidebar.code(f"TOKEN starts with: {AIRTABLE_TOKEN[:5] if AIRTABLE_TOKEN else 'None'}")

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}"
}

# Function to fetch all Airtable records with pagination
def fetch_airtable_data():
    records = []
    offset = None
    while True:
        params = {
            "offset": offset,
            "fields[]": [
                "mv_company_id",
                "Survey Completed",
                "Region",
                "Industry of Relevant Company",
                "FTEs of Relevant Company",
                "Ownership of Former Relevant Company"
            ]
        } if offset else {
            "fields[]": [
                "mv_company_id",
                "Survey Completed",
                "Region",
                "Industry of Relevant Company",
                "FTEs of Relevant Company",
                "Ownership of Former Relevant Company"
            ]
        }
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code != 200:
            st.error("Failed to fetch data from Airtable")
            st.code(response.text, language="json")
            st.stop()
        data = response.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records

# Parse Airtable records into DataFrame
def parse_records(records):
    rows = []
    for r in records:
        fields = r.get("fields", {})
        company_id = fields.get("mv_company_id")
        if "Survey Completed" in fields:
            industry = fields.get("Industry of Relevant Company", "Unknown")
            if isinstance(industry, list):
                industry = ", ".join(industry)
            elif not isinstance(industry, str):
                industry = str(industry)

            rows.append({
                "company": company_id if company_id else "(blank)",
                "Survey Completed": fields["Survey Completed"],
                "Region": fields.get("Region", "Unknown"),
                "Industry": industry,
                "FTEs": fields.get("FTEs of Relevant Company", "Unknown"),
                "Ownership": fields.get("Ownership of Former Relevant Company", "Unknown")
            })
    return pd.DataFrame(rows)

# Streamlit App
st.set_page_config(page_title="Survey Completion Dashboard", layout="wide")
st.title("📈 Expert Survey Engagement Dashboard")

with st.spinner("Fetching latest data from Airtable..."):
    records = fetch_airtable_data()
    df = parse_records(records)

if df.empty:
    st.warning("No valid records with required fields")
else:
    df_completed = df[df["Survey Completed"] == "Yes"]

    unique_companies_sent = df[df["company"] != "(blank)"]["company"].nunique()
    unique_companies_completed = df_completed[df_completed["company"] != "(blank)"]["company"].nunique()

    col1, col2 = st.columns(2)
    col1.metric(label="📨 Unique Companies Sent Survey", value=unique_companies_sent)
    col2.metric(label="✅ Unique Companies with Completed Survey", value=unique_companies_completed)

    summary_df = df_completed.groupby("company").size().reset_index(name="Completed Count")
    st.dataframe(summary_df, use_container_width=True)

    st.download_button("Download CSV", summary_df.to_csv(index=False), file_name="completed_surveys_by_company.csv")

    st.subheader("📍 Completed Surveys by Region")
    region_counts = df_completed["Region"].value_counts()
    st.bar_chart(region_counts)

    st.subheader("🏭 Completed Surveys by Industry")
    industry_counts = df_completed["Industry"].value_counts()
    st.bar_chart(industry_counts)

    st.subheader("🧩 Interactive Pie Chart: Distribution by Region")
    fig1 = px.pie(df_completed, names="Region", title="Survey Completion by Region", hole=0.4)
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("🧩 Interactive Pie Chart: Distribution by Industry")
    fig2 = px.pie(df_completed, names="Industry", title="Survey Completion by Industry", hole=0.4)
    st.plotly_chart(fig2, use_container_width=True)

    missing_fte = df_completed["FTEs"].eq("Unknown").sum()
    st.caption(f"ℹ️ Missing FTE values: {missing_fte}")

    st.subheader("📊 Bar Chart: Company Size (FTEs)")
    df_fte_grouped = df_completed.copy()
    df_fte_grouped = df_fte_grouped[df_fte_grouped["FTEs"] != "Unknown"]
    df_fte_grouped["FTEs"] = pd.to_numeric(df_fte_grouped["FTEs"], errors="coerce")
    df_fte_grouped = df_fte_grouped.dropna(subset=["FTEs"])
    df_fte_grouped["FTE Bucket"] = pd.cut(df_fte_grouped["FTEs"], bins=[0, 10, 50, 100, 250, 1000, float("inf")], labels=["0-10", "11-50", "51-100", "101-250", "251-1000", "1000+"])
    fte_bar = df_fte_grouped["FTE Bucket"].value_counts().sort_index()
    st.bar_chart(fte_bar)

    missing_own = df_completed["Ownership"].eq("Unknown").sum()
    st.caption(f"ℹ️ Missing Ownership values: {missing_own}")

    st.subheader("🏢 Distribution by Company Ownership")
    ownership_counts = df_completed["Ownership"].value_counts()
    fig4 = px.pie(df_completed, names="Ownership", title="Ownership of Former Relevant Company", hole=0.4)
    st.plotly_chart(fig4, use_container_width=True)
