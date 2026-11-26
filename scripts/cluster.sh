#!/usr/bin/env bash
# make cluster (openspec add-lab4-cluster, design Decision 10; add-lab4-monitoring, Decision 10): Minikube, the images
# of HEAD, the manifests with the monitoring stack, a seeded registry, a smoke request, the drift reference and the
# labels, from a clean clone. Every step is a no-op when its result is already in place.
# Run through make, which exports .env, PYTHONPATH and MINIKUBE_MEMORY / MINIKUBE_CPUS.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "no .env: run cp .env.example .env first" >&2; exit 1; }
git diff --quiet HEAD || { echo "uncommitted changes to tracked files; commit them first" >&2; exit 1; }
commit=$(git rev-parse HEAD)

# The client that matches the server's 1.30; the installed kubectl may be outside the supported skew.
k() { minikube kubectl -- "$@"; }
step() { echo "== $* (at ${SECONDS} s)"; }

# minikube kubectl runs kubectl as a child, so stop the children of each background job too.
trap 'for p in $(jobs -p); do pkill -P "$p"; kill "$p"; done 2>/dev/null || true' EXIT
forward() {  # service, local port, service port; waits for an HTTP answer (a TCP connection for PostgreSQL)
    local log
    log=$(mktemp)
    # Not through k(): a function runs in a subshell, and kubectl would outlive the trap as a grandchild.
    minikube kubectl -- port-forward "svc/$1" "$2:$3" --address 127.0.0.1 >"$log" 2>&1 &
    for _ in $(seq 60); do
        if [ "$1" = postgres ]; then
            (exec 3<>"/dev/tcp/127.0.0.1/$2") 2>/dev/null && return
        else
            curl -s -o /dev/null "http://127.0.0.1:$2/" && return
        fi
        sleep 1
    done
    echo "port-forward to $1 did not open:" >&2
    cat "$log" >&2
    exit 1
}

step "minikube"
# Only when it is not running: minikube start on a running cluster restarts the node's Docker and every pod.
minikube status >/dev/null 2>&1 || minikube start --driver=docker --container-runtime=docker \
    --kubernetes-version=v1.30.0 --memory="${MINIKUBE_MEMORY:-6144}" --cpus="${MINIKUBE_CPUS:-4}"

step "images, built by Minikube's Docker daemon"
eval "$(minikube docker-env)"
make images
docker build -q -t landcover-mlflow:3.16.1 docker/mlflow

step "data sample"
make sample

step "manifests"
k create secret generic landcover --dry-run=client -o yaml \
    --from-literal=POSTGRES_USER="$POSTGRES_USER" --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    --from-literal=WAREHOUSE_DSN="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres/landcover" \
    | k apply -f -
k create configmap postgres-init --from-file=sql/warehouse.sql --dry-run=client -o yaml | k apply -f -
k create configmap prometheus --from-file=k8s/prometheus.yml --dry-run=client -o yaml | k apply -f -
k create configmap grafana-provisioning --from-file=k8s/grafana/datasource.yml \
    --from-file=k8s/grafana/dashboards.yml --dry-run=client -o yaml | k apply -f -
k create configmap grafana-dashboards --from-file=k8s/grafana/landcover.json --dry-run=client -o yaml | k apply -f -
manifest=$(sed "s/COMMIT/$commit/g" k8s/landcover.yaml)
# PostgreSQL first: MLflow and the index Job need its databases from the first start on.
echo "$manifest" | k apply -l app=postgres -f -
k rollout status deploy/postgres --timeout=5m
echo "$manifest" | k apply -f -
k rollout status deploy/mlflow --timeout=5m
k wait --for=condition=Ready pod -l app=mlflow --timeout=5m

step "registry"
forward mlflow 5002 5000
MLFLOW_TRACKING_URI=http://127.0.0.1:5002 uv run --locked python -m landcover.tracking seed

step "retrieval index"
k wait --for=condition=complete "job/retrieval-index-$commit" --timeout=10m

step "ML service"
k rollout status deploy/ml --timeout=5m
forward ml 8000 8000
uv run --locked python scripts/smoke.py predict --ml http://127.0.0.1:8000 --mlflow http://127.0.0.1:5002 \
    --commit "$commit"

step "drift reference and labels"
forward postgres 5433 5432
dsn="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:5433/landcover"
uv run --locked python -m landcover.monitor reference --ml http://127.0.0.1:8000 --mlflow http://127.0.0.1:5002 \
    --dsn "$dsn"
uv run --locked python -m landcover.monitor labels --dsn "$dsn"

step "monitoring"
for deploy in pushgateway prometheus grafana; do k rollout status "deploy/$deploy" --timeout=10m; done

step "LLM service"
if curl -sf -o /dev/null http://127.0.0.1:8081/v1/models; then
    k rollout status deploy/llm --timeout=3m
    forward llm 8002 8000
    uv run --locked python scripts/smoke.py ask --llm http://127.0.0.1:8002
else
    echo "llm not ready: no text model server on 127.0.0.1:8081 (make llm-server)"
fi

echo "dashboard: minikube kubectl -- port-forward svc/grafana 3000:3000, then http://127.0.0.1:3000/d/landcover"
echo "metrics:   minikube kubectl -- port-forward svc/prometheus 9090:9090, then http://127.0.0.1:9090"
k get pods,svc
echo "took ${SECONDS} s"
