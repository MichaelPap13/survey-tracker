# file: survey_tracker.py

import os
import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px

# Load secrets from Streamlit config
AIRTABLE_TOKEN = st.secrets["AIRTABLE_TOKEN"]
BASE_ID = st.secrets["AIRTABLE_BASE_ID"]
TABLE_NAME = st.secrets["AIRTABLE_TABLE_NAME"]

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}"
}

@st.cache_data(ttl=3600)
def fetch_airtable_data():
    records = []
    offset = None
    fields = [
        "mv_company_id",
        "Relevant Company",
        "Survey Completed",
        "Region",
        "Industry of Relevant Company",
        "FTEs of Relevant Company",
        "Ownership of Former Relevant Company",
        "Expert Id",
        "First Name [Extracted]",
        "Last Name [Extracted]"
    ]
    while True:
        params = {"fields[]": fields}
        if offset:
            params["offset"] = offset
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

def parse_records(records):
    rows = []
    for r in records:
        f = r.get("fields", {})
        company_id = f.get("mv_company_id")
        company_name = f.get("Relevant Company", "Unknown")
        company_display = company_name if not company_id else f"{company_name} ({company_id})"

        industry = f.get("Industry of Relevant Company", "Unknown")
        if isinstance(industry, list):
            industry = ", ".join(industry)
        elif not isinstance(industry, str):
            industry = str(industry)

        expert_ids = f.get("Expert Id", [])
        first_names = f.get("First Name [Extracted]", [])
        last_names = f.get("Last Name [Extracted]", [])

        if isinstance(expert_ids, str): expert_ids = [expert_ids]
        if isinstance(first_names, str): first_names = [first_names]
        if isinstance(last_names, str): last_names = [last_names]

        expert_info = [
            (f"{fn} {ln}".strip(), eid)
            for fn, ln, eid in zip(first_names, last_names, expert_ids)
        ]

        rows.append({
            "company_id": company_id,
            "company_name": company_name,
            "company_display": company_display,
            "Survey Completed": f.get("Survey Completed", "No"),
            "Region": f.get("Region", "Unknown"),
            "Industry": industry,
            "FTEs": f.get("FTEs of Relevant Company", "Unknown"),
            "Ownership": f.get("Ownership of Former Relevant Company", "Unknown"),
            "Expert Info": expert_info
        })
    return pd.DataFrame(rows)

# Dashboard Setup
st.set_page_config(page_title="Survey Completion Dashboard", layout="wide")
st.title("📊 Expert Survey Engagement Dashboard")

with st.spinner("Fetching latest data from Airtable..."):
    records = fetch_airtable_data()
    df = parse_records(records)

if df.empty:
    st.warning("No valid records with required fields")
    st.stop()

# Completed only
df_completed = df[df["Survey Completed"] == "Yes"]

unique_sent = df["company_display"].nunique()
unique_completed = df_completed["company_display"].nunique()

col1, col2 = st.columns(2)
col1.metric("📨 Unique Companies Sent Survey", unique_sent)
col2.metric("✅ Unique Companies with Completed Survey", unique_completed)

show_ids = st.checkbox("Show Company IDs", value=False)
page_size = st.selectbox("Rows per page", options=[10, 20, 50], index=1)
search_query = st.text_input("🔍 Search Company or Expert Name")

summary_df = df_completed.groupby(["company_name", "company_id"]).agg(
    Completed_Count=("Survey Completed", "count"),
    Expert_Info=("Expert Info", lambda x: sum(x, []))
).reset_index()

summary_df["Display"] = summary_df.apply(
    lambda x: f"{x['company_name']} ({x['company_id']})" if show_ids and pd.notna(x["company_id"]) else x["company_name"],
    axis=1
)

summary_df["Expert_Links"] = summary_df["Expert_Info"].apply(lambda infos: ", ".join(
    f"[{name}](https://maven2.dialecticanet.com/experts/view/{eid})" for name, eid in infos if eid
))

if search_query:
    summary_df = summary_df[
        summary_df["Display"].str.contains(search_query, case=False) |
        summary_df["Expert_Links"].str.contains(search_query, case=False)
    ]

st.markdown("### 💼 Company Survey Summary")

with st.expander("Expand to view company survey table"):
    total_pages = (len(summary_df) - 1) // page_size + 1
    page = st.number_input("Page", min_value=1, max_value=total_pages, step=1)
    start = (page - 1) * page_size
    end = start + page_size
    page_df = summary_df.iloc[start:end]
    st.write(
        page_df[["Display", "Completed_Count", "Expert_Links"]]
        .rename(columns={"Display": "Company", "Expert_Links": "Expert Profiles"})
        .to_markdown(index=False),
        unsafe_allow_html=True
    )

st.download_button("Download CSV", summary_df.to_csv(index=False), file_name="completed_surveys_by_company.csv")

st.subheader("📍 Completed Surveys by Region")
st.bar_chart(df_completed["Region"].value_counts())

st.subheader("🏭 Completed Surveys by Industry")
st.bar_chart(df_completed["Industry"].value_counts())

st.subheader("🧹 Interactive Pie Chart: Distribution by Region")
fig1 = px.pie(df_completed, names="Region", title="Survey Completion by Region", hole=0.4)
st.plotly_chart(fig1, use_container_width=True)

st.subheader("🧹 Interactive Pie Chart: Distribution by Industry")
fig2 = px.pie(df_completed, names="Industry", title="Survey Completion by Industry", hole=0.4)
st.plotly_chart(fig2, use_container_width=True)

missing_fte = df_completed["FTEs"].eq("Unknown").sum()
st.caption(f"ℹ️ Missing FTE values: {missing_fte}")

st.subheader("📊 Bar Chart: Company Size (FTEs)")
df_fte = df_completed[df_completed["FTEs"] != "Unknown"].copy()
df_fte["FTEs"] = pd.to_numeric(df_fte["FTEs"], errors="coerce")
df_fte.dropna(subset=["FTEs"], inplace=True)
df_fte["FTE Bucket"] = pd.cut(df_fte["FTEs"], bins=[0, 10, 50, 100, 250, 1000, float("inf")], labels=["0-10", "11-50", "51-100", "101-250", "251-1000", "1000+"])
st.bar_chart(df_fte["FTE Bucket"].value_counts().sort_index())

missing_own = df_completed["Ownership"].eq("Unknown").sum()
st.caption(f"ℹ️ Missing Ownership values: {missing_own}")

st.subheader("🏢 Distribution by Company Ownership")
fig4 = px.pie(df_completed, names="Ownership", title="Ownership of Former Relevant Company", hole=0.4)
st.plotly_chart(fig4, use_container_width=True)
