#!/bin/bash
# ============================================================
# Pepper AI ROS2 Pipeline — Docker helper script
# Usage:
#   ./docker_run.sh build          Build the image
#   ./docker_run.sh run            Run full pipeline
#   ./docker_run.sh shell          Open a bash shell inside container
#   ./docker_run.sh launch <args>  Run with custom ros2 launch args
# ============================================================

IMAGE_NAME="pepper-ai-ros2:latest"
CONTAINER_NAME="pepper_ai_pipeline"

# Load .env if it exists
if [ -f .env ]; then
    export "$(grep -v '^#' .env | xargs)"
fi

build() {
    echo "[Docker] Building image: $IMAGE_NAME"
    docker build -t "$IMAGE_NAME" .
    echo "[Docker] Build complete."
}

run() {
    echo "[Docker] Starting container: $CONTAINER_NAME"
    docker run --rm -it \
        --name "$CONTAINER_NAME" \
        --network host \
        -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
        -e PEPPER_IP="${PEPPER_IP:-192.168.100.20}" \
        -e PEPPER_USER="${PEPPER_USER:-nao}" \
        -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" \
        -e DISPLAY="${DISPLAY}" \
        -v "${HOME}/.ssh:/root/.ssh:ro" \
        -v "pepper_model_cache:/root/.cache" \
        --device /dev/input \
        --device /dev/snd \
        -p 5000:5000 \
        "$IMAGE_NAME" \
        ros2 launch pepper_bringup pepper_full_system.launch.py "$@"
}

shell() {
    echo "[Docker] Opening bash shell in: $IMAGE_NAME"
    docker run --rm -it \
        --name "${CONTAINER_NAME}_shell" \
        --network host \
        -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
        -e PEPPER_IP="${PEPPER_IP:-192.168.100.20}" \
        -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" \
        -v "${HOME}/.ssh:/root/.ssh:ro" \
        -v "pepper_model_cache:/root/.cache" \
        -p 5000:5000 \
        "$IMAGE_NAME" \
        bash
}

case "${1:-}" in
    build)   build ;;
    run)     shift; run "$@" ;;
    shell)   shell ;;
    launch)  shift; run "$@" ;;
    *)
        echo "Usage: $0 {build|run|shell|launch <args>}"
        exit 1
        ;;
esac
