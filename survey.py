# file: survey.py

import os
import requests
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import plotly.express as px

# Load secrets directly (Streamlit Cloud handles these securely)
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
        params = {"offset": offset, "fields[]": fields} if offset else {"fields[]": fields}
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code != 200:
            st.error("Failed to fetch data from Airtable")
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
        fields = r.get("fields", {})
        company_id = fields.get("mv_company_id")
        company_name = fields.get("Relevant Company", "Unknown")
        company_display = company_name if not company_id else f"{company_name} ({company_id})"

        industry = fields.get("Industry of Relevant Company", "Unknown")
        if isinstance(industry, list):
            industry = ", ".join(industry)
        elif not isinstance(industry, str):
            industry = str(industry)

        expert_ids = fields.get("Expert Id", [])
        first_names = fields.get("First Name [Extracted]", [])
        last_names = fields.get("Last Name [Extracted]", [])

        if isinstance(expert_ids, str):
            expert_ids = [expert_ids]
        if isinstance(first_names, str):
            first_names = [first_names]
        if isinstance(last_names, str):
            last_names = [last_names]

        expert_info = [
            (f"{fn} {ln}".strip(), eid)
            for fn, ln, eid in zip(first_names, last_names, expert_ids)
        ]

        rows.append({
            "company_id": company_id,
            "company_name": company_name,
            "company_display": company_display,
            "Survey Completed": fields.get("Survey Completed", "No"),
            "Region": fields.get("Region", "Unknown"),
            "Industry": industry,
            "FTEs": fields.get("FTEs of Relevant Company", "Unknown"),
            "Ownership": fields.get("Ownership of Former Relevant Company", "Unknown"),
            "Expert Info": expert_info
        })
    return pd.DataFrame(rows)

# Streamlit UI
st.set_page_config(page_title="Survey Completion Dashboard", layout="wide")
st.title("📈 Expert Survey Engagement Dashboard")

with st.spinner("Fetching data..."):
    records = fetch_airtable_data()
    df = parse_records(records)

if df.empty:
    st.warning("No valid records with required fields.")
    st.stop()

df_completed = df[df["Survey Completed"] == "Yes"]
unique_sent = df["company_display"].nunique()
unique_completed = df_completed["company_display"].nunique()

search_query = st.text_input("🔍 Search Company or Expert Name")
show_ids = st.checkbox("Show Company IDs", value=False)
page_size = st.selectbox("Rows per page", [10, 20, 50], index=1)

summary_df = df_completed.groupby(["company_name", "company_id"]).agg(
    Completed_Count=("Survey Completed", "count"),
    Expert_Info=("Expert Info", lambda x: sum(x, []))
).reset_index()

if show_ids:
    summary_df["Display"] = summary_df.apply(lambda x: f"{x['company_name']} ({x['company_id']})" if pd.notna(x["company_id"]) else x["company_name"], axis=1)
else:
    summary_df["Display"] = summary_df["company_name"]

def format_expert_links(expert_info):
    return ", ".join([
        f"[{name}](https://maven2.dialecticanet.com/experts/view/{eid})"
        for name, eid in expert_info if eid
    ])

summary_df["Expert_Links"] = summary_df["Expert_Info"].apply(format_expert_links)

if search_query:
    summary_df = summary_df[
        summary_df["Display"].str.contains(search_query, case=False) |
        summary_df["Expert_Links"].str.contains(search_query, case=False)
    ]

st.subheader("📊 Completed Surveys by Company")
page_total = (len(summary_df) - 1) // page_size + 1
page = st.number_input("Page", 1, page_total, step=1)
start = (page - 1) * page_size
end = start + page_size

display_df = summary_df.iloc[start:end]
st.write(display_df[["Display", "Completed_Count", "Expert_Links"]].rename(columns={
    "Display": "Company", "Expert_Links": "Expert Profiles"
}).to_html(index=False, escape=False), unsafe_allow_html=True)

st.download_button("📥 Download CSV", summary_df.to_csv(index=False), file_name="completed_surveys_by_company.csv")

with st.expander("📌 Summary Metrics", expanded=True):
    col1, col2 = st.columns(2)
    col1.metric("📨 Unique Companies Sent Survey", unique_sent)
    col2.metric("✅ Companies with Completed Survey", unique_completed)

st.subheader("📍 Completed Surveys by Region")
st.bar_chart(df_completed["Region"].value_counts())

st.subheader("🏭 Completed Surveys by Industry")
st.bar_chart(df_completed["Industry"].value_counts())

fig1 = px.pie(df_completed, names="Region", title="Survey Completion by Region", hole=0.4)
st.plotly_chart(fig1, use_container_width=True)

fig2 = px.pie(df_completed, names="Industry", title="Survey Completion by Industry", hole=0.4)
st.plotly_chart(fig2, use_container_width=True)

st.caption(f"ℹ️ Missing FTE values: {df_completed['FTEs'].eq('Unknown').sum()}")

st.subheader("📊 Company Size (FTEs)")
df_fte = df_completed[df_completed["FTEs"] != "Unknown"].copy()
df_fte["FTEs"] = pd.to_numeric(df_fte["FTEs"], errors="coerce")
df_fte.dropna(subset=["FTEs"], inplace=True)
df_fte["FTE Bucket"] = pd.cut(df_fte["FTEs"], bins=[0, 10, 50, 100, 250, 1000, float("inf")], labels=["0-10", "11-50", "51-100", "101-250", "251-1000", "1000+"])
st.bar_chart(df_fte["FTE Bucket"].value_counts().sort_index())

st.caption(f"ℹ️ Missing Ownership values: {df_completed['Ownership'].eq('Unknown').sum()}")

st.subheader("🏢 Distribution by Ownership")
fig3 = px.pie(df_completed, names="Ownership", title="Ownership of Former Relevant Company", hole=0.4)
st.plotly_chart(fig3, use_container_width=True)
