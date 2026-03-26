#!/bin/bash
# KServe installation on OpenShift (MLOps workshop).
# Prerequisites: oc logged in with cluster-admin (or sufficient rights for CRDs, webhooks, and namespaces).
#
# NOTE: On clusters with Docker Hub rate limits, KServe controller images must be
# mirrored to an accessible registry (e.g., quay.io). See the image patching steps below.

set -e

# -----------------------------------------------------------------------------
# Step 1: Install cert-manager (KServe dependency for TLS / webhook certificates)
# -----------------------------------------------------------------------------
echo "Applying cert-manager v1.16.3..."
oc apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.3/cert-manager.yaml

# -----------------------------------------------------------------------------
# Step 2: Wait until cert-manager core components are Available
# -----------------------------------------------------------------------------
echo "Waiting for cert-manager deployments..."
oc wait --for=condition=Available deployment/cert-manager -n cert-manager --timeout=300s
oc wait --for=condition=Available deployment/cert-manager-webhook -n cert-manager --timeout=300s

# -----------------------------------------------------------------------------
# Step 3: Install KServe CRDs and controller (server-side apply to handle large CRDs)
# -----------------------------------------------------------------------------
echo "Applying KServe v0.14.1 (CRDs + controller)..."
oc apply --server-side --force-conflicts -f https://github.com/kserve/kserve/releases/download/v0.14.1/kserve.yaml

# -----------------------------------------------------------------------------
# Step 4: Patch controller images for Docker Hub rate-limited clusters
# If your cluster can pull from Docker Hub, you can skip this step.
# -----------------------------------------------------------------------------
echo "Patching KServe images to use quay.io mirrors..."
oc set image deployment/kserve-controller-manager \
  manager=quay.io/aniket-redhat/kserve-controller:v0.14.1 -n kserve
oc set image deployment/kserve-localmodel-controller-manager \
  manager=quay.io/aniket-redhat/kserve-localmodel-controller:v0.14.1 -n kserve

# -----------------------------------------------------------------------------
# Step 5: Wait until the KServe controller manager is ready
# -----------------------------------------------------------------------------
echo "Waiting for kserve-controller-manager..."
oc wait --for=condition=Available deployment/kserve-controller-manager -n kserve --timeout=300s

# -----------------------------------------------------------------------------
# Step 6: Install built-in ClusterServingRuntimes (sklearn, etc.)
# -----------------------------------------------------------------------------
echo "Applying KServe cluster resources (serving runtimes)..."
oc apply --server-side --force-conflicts -f https://github.com/kserve/kserve/releases/download/v0.14.1/kserve-cluster-resources.yaml

# -----------------------------------------------------------------------------
# Step 7: Verification
# -----------------------------------------------------------------------------
echo ""
echo "Verification — pods in kserve namespace:"
oc get pods -n kserve

echo ""
echo "Verification — ClusterServingRuntimes:"
oc get clusterservingruntimes

echo ""
echo "KServe install completed successfully."
