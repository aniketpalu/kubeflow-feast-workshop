import streamlit as st
import json
import traceback
import requests

st.set_page_config(page_title="Fraud Detection Inference", page_icon="🛡️", layout="wide")

PRESETS = {
    "safe": {
        "label": "🟢 Likely Safe",
        "desc": "Low distance, chip+PIN, in-person",
        "values": {
            "distance_from_home": 3.6,
            "distance_from_last_transaction": 0.69,
            "ratio_to_median_purchase_price": 0.08,
            "repeat_retailer": 1.0,
            "used_chip": 1.0,
            "used_pin_number": 1.0,
            "online_order": 0.0,
        },
    },
    "fraud": {
        "label": "🔴 Likely Fraud",
        "desc": "Far from home, high amount, no chip, no PIN, online",
        "values": {
            "distance_from_home": 113.6,
            "distance_from_last_transaction": 0.53,
            "ratio_to_median_purchase_price": 5.34,
            "repeat_retailer": 1.0,
            "used_chip": 0.0,
            "used_pin_number": 0.0,
            "online_order": 1.0,
        },
    },
    "edge": {
        "label": "🟡 Edge Case",
        "desc": "Moderate distance, new retailer, no chip, online",
        "values": {
            "distance_from_home": 45.0,
            "distance_from_last_transaction": 5.2,
            "ratio_to_median_purchase_price": 2.95,
            "repeat_retailer": 0.0,
            "used_chip": 0.0,
            "used_pin_number": 0.0,
            "online_order": 1.0,
        },
    },
}

FEATURE_ORDER = [
    "distance_from_home",
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "repeat_retailer",
    "used_chip",
    "used_pin_number",
    "online_order",
]

if "feat_vals" not in st.session_state:
    st.session_state["feat_vals"] = PRESETS["safe"]["values"].copy()

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    .pred-fraud { padding: 20px; border-left: 6px solid #ff5252; background-color: #2e1a1a; border-radius: 8px; margin: 16px 0; color: #ffcdd2; font-size: 1.3em; }
    .pred-safe { padding: 20px; border-left: 6px solid #00e676; background-color: #1a2e1a; border-radius: 8px; margin: 16px 0; color: #c8e6c9; font-size: 1.3em; }
    .pred-error { padding: 20px; border-left: 6px solid #ffa726; background-color: #2e2a1a; border-radius: 8px; margin: 16px 0; color: #ffe0b2; }
</style>
""", unsafe_allow_html=True)

st.title("🛡️ Fraud Detection — Live Inference")
st.markdown("Test your KServe InferenceService by sending transaction data and getting predictions.")
st.divider()

inference_url = st.text_input(
    "KServe Inference URL",
    value="http://fraud-detector-predictor.mlops-workshop.svc.cluster.local/v1/models/fraud-detector:predict",
)

st.divider()

st.subheader("Quick Presets")
pcol1, pcol2, pcol3 = st.columns(3)
with pcol1:
    if st.button(PRESETS["safe"]["label"], use_container_width=True, help=PRESETS["safe"]["desc"]):
        st.session_state["feat_vals"] = PRESETS["safe"]["values"].copy()
        st.rerun()
with pcol2:
    if st.button(PRESETS["fraud"]["label"], use_container_width=True, help=PRESETS["fraud"]["desc"]):
        st.session_state["feat_vals"] = PRESETS["fraud"]["values"].copy()
        st.rerun()
with pcol3:
    if st.button(PRESETS["edge"]["label"], use_container_width=True, help=PRESETS["edge"]["desc"]):
        st.session_state["feat_vals"] = PRESETS["edge"]["values"].copy()
        st.rerun()

st.divider()
st.subheader("Transaction Features")

v = st.session_state["feat_vals"]

col1, col2, col3 = st.columns(3)
with col1:
    v["distance_from_home"] = st.number_input(
        "Distance from Home", value=v["distance_from_home"], format="%.2f", step=1.0,
        help="Distance of transaction from cardholder's home")
    v["distance_from_last_transaction"] = st.number_input(
        "Distance from Last Transaction", value=v["distance_from_last_transaction"], format="%.4f", step=0.1,
        help="Distance from the previous transaction location")
    v["ratio_to_median_purchase_price"] = st.number_input(
        "Ratio to Median Purchase Price", value=v["ratio_to_median_purchase_price"], format="%.4f", step=0.1,
        help="Transaction amount relative to cardholder's median")
with col2:
    v["repeat_retailer"] = st.selectbox(
        "Repeat Retailer", [1.0, 0.0],
        index=0 if v["repeat_retailer"] == 1.0 else 1,
        help="1.0 = repeat retailer, 0.0 = new retailer")
    v["used_chip"] = st.selectbox(
        "Used Chip", [1.0, 0.0],
        index=0 if v["used_chip"] == 1.0 else 1,
        help="1.0 = chip used, 0.0 = not used")
with col3:
    v["used_pin_number"] = st.selectbox(
        "Used PIN", [1.0, 0.0],
        index=0 if v["used_pin_number"] == 1.0 else 1,
        help="1.0 = PIN used, 0.0 = not used")
    v["online_order"] = st.selectbox(
        "Online Order", [1.0, 0.0],
        index=0 if v["online_order"] == 1.0 else 1,
        help="1.0 = online, 0.0 = in-person")

st.session_state["feat_vals"] = v

st.divider()

features_list = [v[f] for f in FEATURE_ORDER]

if st.button("🔮 Predict", type="primary", use_container_width=True):

    payload = {"instances": [features_list]}

    st.subheader("Request")
    st.code(json.dumps(payload, indent=2), language="json")

    st.subheader("Result")

    try:
        resp = requests.post(inference_url, json=payload, timeout=15,
                             headers={"Content-Type": "application/json"})

        if resp.status_code == 200:
            result = resp.json()
            predictions = result.get("predictions", [])

            st.markdown("**Raw Response:**")
            st.code(json.dumps(result, indent=2), language="json")

            if len(predictions) > 0:
                pred = predictions[0]
                if pred == 1.0 or pred == 1:
                    st.markdown(
                        '<div class="pred-fraud">🚨 <b>FRAUD DETECTED</b> — This transaction is predicted as fraudulent.</div>',
                        unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div class="pred-safe">✅ <b>LEGITIMATE</b> — This transaction appears safe.</div>',
                        unsafe_allow_html=True)

                st.markdown("**Feature Summary:**")
                summary = {name: [val] for name, val in zip(FEATURE_ORDER, features_list)}
                summary["prediction"] = [pred]
                st.dataframe(summary, use_container_width=True)
        else:
            st.markdown(f'<div class="pred-error">⚠️ <b>HTTP {resp.status_code}</b></div>', unsafe_allow_html=True)
            st.code(resp.text, language="text")

    except Exception as e:
        st.markdown(f'<div class="pred-error">❌ <b>Request Failed</b> — {str(e)[:300]}</div>', unsafe_allow_html=True)
        with st.expander("Full Error Traceback", expanded=True):
            st.code(traceback.format_exc(), language="text")
