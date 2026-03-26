import streamlit as st
import pandas as pd
import json
import time
import traceback
import requests

st.set_page_config(page_title="Feast Remote Tester", page_icon="🔍", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    .test-pass { padding: 12px 16px; border-left: 5px solid #00e676; background-color: #1a2e1a; border-radius: 5px; margin: 10px 0; color: #c8e6c9; }
    .test-fail { padding: 12px 16px; border-left: 5px solid #ff5252; background-color: #2e1a1a; border-radius: 5px; margin: 10px 0; color: #ffcdd2; }
    .test-header { font-size: 1.2em; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("🔍 Feast Remote Access Tester")
st.markdown("Validate that your Feast servers are reachable from this pod.")
st.divider()

col1, col2 = st.columns(2)
with col1:
    registry_url = st.text_input(
        "Registry Service (gRPC)",
        value="feast-registry-service.mlops-workshop.svc.cluster.local:6567",
        help="Format: host:port (no http://)"
    )
with col2:
    offline_host = st.text_input(
        "Offline Service Host (Arrow Flight)",
        value="feast-offline-service.mlops-workshop.svc.cluster.local",
    )
    offline_port = st.number_input("Offline Service Port", value=8815, min_value=1, max_value=65535)

online_url_parts = registry_url.replace("feast-registry-service", "feast-service").replace(":6567", "")
online_url = st.text_input(
    "Online Service (REST)",
    value=f"http://{online_url_parts}:6566",
)

st.divider()

if st.button("🚀 Run Feast Tests", type="primary", use_container_width=True):

    results = []

    # ---- Test 1: Registry ----
    st.subheader("Test 1: Registry Connection (gRPC)")
    t1_start = time.time()
    store = None
    try:
        from feast import FeatureStore, RepoConfig

        config = RepoConfig(
            project="fraud_detection",
            provider="local",
            registry={"registry_type": "remote", "path": registry_url},
            offline_store={"type": "remote", "host": offline_host, "port": int(offline_port)},
            online_store={"type": "sqlite", "path": "/tmp/feast_test_online.db"},
            entity_key_serialization_version=3,
        )
        store = FeatureStore(config=config)
        feature_views = store.list_feature_views()
        t1_dur = time.time() - t1_start

        if len(feature_views) > 0:
            st.markdown(f'<div class="test-pass"><span class="test-header">✅ PASS</span> — Found {len(feature_views)} feature view(s) in {t1_dur:.2f}s</div>', unsafe_allow_html=True)
            for fv in feature_views:
                st.markdown(f"**{fv.name}**: {[f.name for f in fv.features]}")
            results.append(("Registry", True))
        else:
            st.markdown(f'<div class="test-fail"><span class="test-header">⚠️ WARNING</span> — Connected but no feature views found ({t1_dur:.2f}s)</div>', unsafe_allow_html=True)
            results.append(("Registry", False))
    except Exception as e:
        t1_dur = time.time() - t1_start
        err_msg = str(e)
        hint = ""
        if "Connection refused" in err_msg:
            hint = "\n\n**Hint:** The registry server (feast serve_registry) may not be running. Check that port 6567 is listening on the Jupyter pod."
        elif "No module named" in err_msg:
            hint = "\n\n**Hint:** Missing Python dependency. Ensure feast[grpc] is installed."
        st.markdown(f'<div class="test-fail"><span class="test-header">❌ FAIL</span> — {err_msg[:300]} ({t1_dur:.2f}s){hint}</div>', unsafe_allow_html=True)
        with st.expander("Full Error Traceback"):
            st.code(traceback.format_exc(), language="text")
        results.append(("Registry", False))

    st.divider()

    # ---- Test 2: Historical Features ----
    st.subheader("Test 2: Historical Feature Fetch (Arrow Flight)")
    t2_start = time.time()
    if store is None:
        st.markdown('<div class="test-fail"><span class="test-header">⏭️ SKIPPED</span> — Registry connection failed, cannot proceed.</div>', unsafe_allow_html=True)
        results.append(("Historical Features", False))
    else:
        try:
            from datetime import datetime
            features = store.get_historical_features(
                entity_df=None,
                features=[
                    "fraud_features:distance_from_home",
                    "fraud_features:distance_from_last_transaction",
                    "fraud_features:ratio_to_median_purchase_price",
                    "fraud_features:repeat_retailer",
                    "fraud_features:used_chip",
                    "fraud_features:used_pin_number",
                    "fraud_features:online_order",
                ],
                start_date=datetime(2025, 1, 1),
                end_date=datetime(2025, 1, 15),
            )
            result_df = features.to_df()
            t2_dur = time.time() - t2_start

            non_null = result_df.drop(columns=["entity_id", "event_timestamp"], errors="ignore").notna().sum().sum()

            if result_df.shape[0] > 0 and non_null > 0:
                st.markdown(f'<div class="test-pass"><span class="test-header">✅ PASS</span> — {result_df.shape[0]:,} rows, {result_df.shape[1]} columns ({t2_dur:.2f}s)</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="test-fail"><span class="test-header">⚠️ WARNING</span> — {result_df.shape[0]} rows returned but values are null ({t2_dur:.2f}s)</div>', unsafe_allow_html=True)

            st.dataframe(result_df.head(10), use_container_width=True)
            if result_df.shape[0] > 10:
                st.caption(f"Showing first 10 of {result_df.shape[0]:,} rows")
            results.append(("Historical Features", result_df.shape[0] > 0 and non_null > 0))
        except Exception as e:
            t2_dur = time.time() - t2_start
            err_msg = str(e)
            hint = ""
            if "Connection refused" in err_msg:
                hint = "\n\n**Hint:** The offline server (feast serve_offline) may not be running. Check port 8815."
            st.markdown(f'<div class="test-fail"><span class="test-header">❌ FAIL</span> — {err_msg[:300]} ({t2_dur:.2f}s){hint}</div>', unsafe_allow_html=True)
            with st.expander("Full Error Traceback"):
                st.code(traceback.format_exc(), language="text")
            results.append(("Historical Features", False))

    st.divider()

    # ---- Test 3: Online Features ----
    st.subheader("Test 3: Online Feature Fetch (REST)")
    t3_start = time.time()
    try:
        payload = {
            "features": [
                "fraud_features:distance_from_home",
                "fraud_features:distance_from_last_transaction",
                "fraud_features:ratio_to_median_purchase_price",
            ],
            "entities": {"entity_id": [57618]},
        }
        resp = requests.post(f"{online_url}/get-online-features", json=payload, timeout=10)
        t3_dur = time.time() - t3_start

        if resp.status_code == 200:
            st.markdown(f'<div class="test-pass"><span class="test-header">✅ PASS</span> — HTTP {resp.status_code} ({t3_dur:.2f}s)</div>', unsafe_allow_html=True)
            st.json(resp.json())
        else:
            st.markdown(f'<div class="test-fail"><span class="test-header">❌ FAIL</span> — HTTP {resp.status_code} ({t3_dur:.2f}s)</div>', unsafe_allow_html=True)
            st.code(resp.text)
        results.append(("Online Features", resp.status_code == 200))
    except Exception as e:
        t3_dur = time.time() - t3_start
        err_msg = str(e)
        hint = ""
        if "Connection refused" in err_msg or "Max retries exceeded" in err_msg:
            hint = "\n\n**Hint:** The online server (feast serve) may not be running. Check port 6566."
        st.markdown(f'<div class="test-fail"><span class="test-header">❌ FAIL</span> — {err_msg[:300]} ({t3_dur:.2f}s){hint}</div>', unsafe_allow_html=True)
        with st.expander("Full Error Traceback"):
            st.code(traceback.format_exc(), language="text")
        results.append(("Online Features", False))

    # ---- Summary ----
    st.divider()
    st.subheader("Summary")
    passed = sum(1 for _, ok in results if ok)
    total_tests = len(results)

    if passed == total_tests:
        st.success(f"🎉 All {total_tests} tests passed! Your Feast remote access is working.")
    elif passed > 0:
        st.warning(f"⚠️ {passed}/{total_tests} tests passed. Check failed tests above.")
    else:
        st.error(f"❌ All {total_tests} tests failed. Are the Feast servers running?")

    for name, ok in results:
        st.write(f"{'✅' if ok else '❌'} {name}")
