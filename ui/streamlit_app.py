import requests
import streamlit as st


API_BASE_URL = "http://127.0.0.1:8080"


st.set_page_config(
    page_title="Elastic On-Call Agent",
    page_icon="🚨",
    layout="wide",
)


st.title("Elastic On-Call Agent: Agentic Ops with Google Cloud")

st.markdown(
    """
This demo shows an alert-triggered incident agent.

Flow:
Elastic alert -> Cloud Run / FastAPI -> Gemini / Agent Builder concept -> Elastic evidence -> notification brief
"""
)


def call_api(method: str, path: str, payload: dict | None = None):
    url = f"{API_BASE_URL}{path}"

    if method == "GET":
        response = requests.get(url, timeout=30)
    else:
        response = requests.post(url, json=payload, timeout=60)

    response.raise_for_status()
    return response.json()


col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Health check"):
        try:
            result = call_api("GET", "/health")
            st.success(result)
        except Exception as exc:
            st.error(str(exc))

with col2:
    if st.button("Load demo data to Elastic"):
        try:
            result = call_api("POST", "/seed-demo-data")
            st.success("Demo data seeded")
            st.json(result)
        except Exception as exc:
            st.error(str(exc))

with col3:
    if st.button("Simulate incident"):
        try:
            result = call_api("POST", "/simulate-incident")
            st.success("Incident triaged")
            st.session_state["latest_incident"] = result.get("incident")
            st.json(result)
        except Exception as exc:
            st.error(str(exc))


st.divider()

st.subheader("Latest incident brief")

if st.button("Refresh latest incident"):
    try:
        result = call_api("GET", "/incidents/latest")
        st.session_state["latest_incident"] = result.get("incident")
    except Exception as exc:
        st.error(str(exc))


incident = st.session_state.get("latest_incident")

if incident:
    st.markdown(f"### {incident.get('summary')}")
    st.markdown(f"**Probable root cause:** {incident.get('probable_root_cause')}")
    st.markdown(f"**Confidence:** {incident.get('confidence')}")

    st.markdown("#### Timeline")
    for item in incident.get("timeline", []):
        st.write(f"- {item}")

    st.markdown("#### Evidence")
    for item in incident.get("evidence", []):
        st.write(f"**{item.get('title')}**")
        st.write(item.get("detail"))
        st.caption(f"Source: {item.get('source')} | Confidence: {item.get('confidence')}")

    st.markdown("#### Next actions")
    for item in incident.get("next_actions", []):
        approval = "approval required" if item.get("requires_human_approval") else "no approval required"
        st.write(f"**{item.get('title')}** - {item.get('description')}")
        st.caption(f"Risk: {item.get('risk_level')} | {approval}")
else:
    st.info("No incident brief yet. Load demo data, then simulate an incident.")


st.divider()

st.subheader("Ask follow-up")

question = st.text_input(
    "Question",
    value="Why do you think this is deployment-related?",
)

if st.button("Ask agent"):
    try:
        result = call_api(
            "POST",
            "/ask-followup",
            {
                "question": question,
                "incident_id": incident.get("incident_id") if incident else None,
            },
        )
        st.markdown("### Agent answer")
        st.write(result.get("response", {}).get("answer"))
        st.markdown("#### Evidence used")
        st.write(result.get("response", {}).get("evidence_used"))
    except Exception as exc:
        st.error(str(exc))
