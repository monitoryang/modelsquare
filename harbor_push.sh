#!/bin/bash
# =============================================================================
# ModelSquare Docker镜像构建与推送脚本
# 将所有自建服务打包为Harbor镜像并推送至 harbor.jouav.com/modelsquare
# =============================================================================

set -euo pipefail

HARBOR_REGISTRY="harbor.jouav.com"
HARBOR_PROJECT="modelsquare"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

# --------------- 镜像版本配置 ---------------
API_VERSION="v0.0.17"
WEB_VERSION="v0.0.26"
DEEPSTREAM_VERSION="v0.0.5"
FFMPEG_VERSION="v0.0.8"
VLLM_VERSION="v0.0.4"
VLLM_V013_VERSION="v0.13.0"
VLLM_OMNI_VERSION="qwen3-omni"

# --------------- 镜像全名 ---------------
API_IMAGE="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/modelsquare-api:${API_VERSION}"
WEB_IMAGE="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/modelsquare-web:${WEB_VERSION}"
DEEPSTREAM_IMAGE="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/modelsquare-deepstream:${DEEPSTREAM_VERSION}"
FFMPEG_IMAGE="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/modelsquare-ffmpeg:${FFMPEG_VERSION}"
VLLM_IMAGE="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/modelsquare-vllm:${VLLM_VERSION}"
VLLM_V013_IMAGE="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/modelsquare-vllm:${VLLM_V013_VERSION}"
VLLM_OMNI_IMAGE="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/modelsquare-vllm:${VLLM_OMNI_VERSION}"

# --------------- 颜色输出 ---------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# --------------- 构建函数 ---------------
build_image() {
    local image_name="$1"
    local dockerfile="$2"
    local context="$3"
    shift 3
    local extra_args=("$@")

    log_step "构建镜像: ${image_name}"
    log_info "  Dockerfile: ${dockerfile}"
    log_info "  构建上下文: ${context}"

    if docker build \
        -t "${image_name}" \
        -f "${dockerfile}" \
        "${extra_args[@]+"${extra_args[@]}"}" \
        "${context}"; then
        log_info "✅ 构建成功: ${image_name}"
    else
        log_error "❌ 构建失败: ${image_name}"
        return 1
    fi
}

# --------------- 推送函数 ---------------
push_image() {
    local image_name="$1"
    local max_retries=3
    local retry_delay=10

    log_step "推送镜像: ${image_name}"

    for ((attempt=1; attempt<=max_retries; attempt++)); do
        if docker push "${image_name}"; then
            log_info "推送成功: ${image_name}"
            return 0
        fi
        if [[ $attempt -lt $max_retries ]]; then
            log_warn "推送失败，${retry_delay}秒后重试 (${attempt}/${max_retries})..."
            sleep $retry_delay
            retry_delay=$((retry_delay * 2))
        fi
    done

    log_error "推送失败: ${image_name} (已重试${max_retries}次)"
    return 1
}

# --------------- 使用说明 ---------------
usage() {
    echo "用法: $0 [选项] [服务名...]"
    echo ""
    echo "服务名 (不指定则构建全部):"
    echo "  api          FastAPI 后端服务"
    echo "  web          React 前端服务"
    echo "  deepstream   DeepStream GPU Pipeline 服务"
    echo "  ffmpeg       FFmpeg Worker 服务"
    echo "  vllm         vLLM 推理服务 (v0.0.1)"
    echo "  vllm-v013    vLLM 推理服务 (v0.13.0)"
    echo "  vllm-omni    vLLM Qwen3-Omni 推理服务"
    echo ""
    echo "选项:"
    echo "  --build-only   仅构建，不推送"
    echo "  --push-only    仅推送，不构建"
    echo "  --no-cache     构建时不使用缓存"
    echo "  -h, --help     显示帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                        # 构建并推送所有镜像"
    echo "  $0 api web                # 仅构建并推送 api 和 web"
    echo "  $0 --build-only deepstream # 仅构建 deepstream 镜像"
    echo "  $0 --no-cache ffmpeg       # 不使用缓存构建 ffmpeg"
}

# --------------- 参数解析 ---------------
BUILD=true
PUSH=true
NO_CACHE=""
SERVICES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-only) PUSH=false; shift ;;
        --push-only)  BUILD=false; shift ;;
        --no-cache)   NO_CACHE="--no-cache"; shift ;;
        -h|--help)    usage; exit 0 ;;
        *)            SERVICES+=("$1"); shift ;;
    esac
done

# 默认构建全部服务
if [[ ${#SERVICES[@]} -eq 0 ]]; then
    SERVICES=(api web deepstream ffmpeg vllm vllm-v013 vllm-omni)
fi

# --------------- 前置检查 ---------------
log_info "=========================================="
log_info " ModelSquare 镜像构建与推送"
log_info "=========================================="
log_info "项目根目录: ${PROJECT_ROOT}"
log_info "目标仓库:   ${HARBOR_REGISTRY}/${HARBOR_PROJECT}"
log_info "构建服务:   ${SERVICES[*]}"
echo ""

if ! command -v docker &>/dev/null; then
    log_error "Docker 未安装，请先安装 Docker"
    exit 1
fi

if [[ "${PUSH}" == true ]]; then
    log_step "检查 Harbor 登录状态..."
    if ! docker login "${HARBOR_REGISTRY}" --username "" --password "" 2>/dev/null; then
        log_warn "请先登录 Harbor: docker login ${HARBOR_REGISTRY}"
        read -rp "是否现在登录? (y/N): " login_choice
        if [[ "${login_choice}" =~ ^[Yy]$ ]]; then
            docker login "${HARBOR_REGISTRY}"
        else
            log_error "未登录 Harbor，无法推送镜像"
            exit 1
        fi
    fi
fi

# --------------- 记录结果 ---------------
SUCCESS_LIST=()
FAIL_LIST=()

process_service() {
    local service="$1"

    case "${service}" in
        api)
            # Backend API - 构建上下文为项目根目录(需要 package/ 和 backend/)
            if [[ "${BUILD}" == true ]]; then
                build_image "${API_IMAGE}" \
                    "${PROJECT_ROOT}/backend/Dockerfile" \
                    "${PROJECT_ROOT}" \
                    ${NO_CACHE} || { FAIL_LIST+=("${API_IMAGE}"); return; }
            fi
            if [[ "${PUSH}" == true ]]; then
                push_image "${API_IMAGE}" || { FAIL_LIST+=("${API_IMAGE}"); return; }
            fi
            SUCCESS_LIST+=("${API_IMAGE}")
            ;;

        web)
            # Frontend - 构建上下文为 frontend/
            local vite_api_url="${VITE_API_URL:-http://lp.jouavcloud.com:8020}"
            if [[ "${BUILD}" == true ]]; then
                build_image "${WEB_IMAGE}" \
                    "${PROJECT_ROOT}/frontend/Dockerfile" \
                    "${PROJECT_ROOT}/frontend" \
                    --build-arg "VITE_API_URL=${vite_api_url}" \
                    ${NO_CACHE} || { FAIL_LIST+=("${WEB_IMAGE}"); return; }
            fi
            if [[ "${PUSH}" == true ]]; then
                push_image "${WEB_IMAGE}" || { FAIL_LIST+=("${WEB_IMAGE}"); return; }
            fi
            SUCCESS_LIST+=("${WEB_IMAGE}")
            ;;

        deepstream)
            # DeepStream - 构建上下文为 docker/deepstream/
            if [[ "${BUILD}" == true ]]; then
                build_image "${DEEPSTREAM_IMAGE}" \
                    "${PROJECT_ROOT}/docker/deepstream/Dockerfile" \
                    "${PROJECT_ROOT}/docker/deepstream" \
                    ${NO_CACHE} || { FAIL_LIST+=("${DEEPSTREAM_IMAGE}"); return; }
            fi
            if [[ "${PUSH}" == true ]]; then
                push_image "${DEEPSTREAM_IMAGE}" || { FAIL_LIST+=("${DEEPSTREAM_IMAGE}"); return; }
            fi
            SUCCESS_LIST+=("${DEEPSTREAM_IMAGE}")
            ;;

        ffmpeg)
            # FFmpeg Worker - 复用 backend Dockerfile (内含 FFmpeg GPU 编译)
            if [[ "${BUILD}" == true ]]; then
                build_image "${FFMPEG_IMAGE}" \
                    "${PROJECT_ROOT}/backend/Dockerfile" \
                    "${PROJECT_ROOT}" \
                    ${NO_CACHE} || { FAIL_LIST+=("${FFMPEG_IMAGE}"); return; }
            fi
            if [[ "${PUSH}" == true ]]; then
                push_image "${FFMPEG_IMAGE}" || { FAIL_LIST+=("${FFMPEG_IMAGE}"); return; }
            fi
            SUCCESS_LIST+=("${FFMPEG_IMAGE}")
            ;;

        vllm)
            # vLLM v0.0.1 (Qwen3-VL-32B)
            if [[ "${BUILD}" == true ]]; then
                build_image "${VLLM_IMAGE}" \
                    "${PROJECT_ROOT}/vllm/Dockerfile" \
                    "${PROJECT_ROOT}/vllm" \
                    ${NO_CACHE} || { FAIL_LIST+=("${VLLM_IMAGE}"); return; }
            fi
            if [[ "${PUSH}" == true ]]; then
                push_image "${VLLM_IMAGE}" || { FAIL_LIST+=("${VLLM_IMAGE}"); return; }
            fi
            SUCCESS_LIST+=("${VLLM_IMAGE}")
            ;;

        vllm-v013)
            # vLLM v0.13.0 (8B/4B 使用同一镜像)
            if [[ "${BUILD}" == true ]]; then
                build_image "${VLLM_V013_IMAGE}" \
                    "${PROJECT_ROOT}/vllm/Dockerfile" \
                    "${PROJECT_ROOT}/vllm" \
                    ${NO_CACHE} || { FAIL_LIST+=("${VLLM_V013_IMAGE}"); return; }
            fi
            if [[ "${PUSH}" == true ]]; then
                push_image "${VLLM_V013_IMAGE}" || { FAIL_LIST+=("${VLLM_V013_IMAGE}"); return; }
            fi
            SUCCESS_LIST+=("${VLLM_V013_IMAGE}")
            ;;

        vllm-omni)
            # vLLM Qwen3-Omni
            if [[ "${BUILD}" == true ]]; then
                build_image "${VLLM_OMNI_IMAGE}" \
                    "${PROJECT_ROOT}/vllm/Dockerfile" \
                    "${PROJECT_ROOT}/vllm" \
                    ${NO_CACHE} || { FAIL_LIST+=("${VLLM_OMNI_IMAGE}"); return; }
            fi
            if [[ "${PUSH}" == true ]]; then
                push_image "${VLLM_OMNI_IMAGE}" || { FAIL_LIST+=("${VLLM_OMNI_IMAGE}"); return; }
            fi
            SUCCESS_LIST+=("${VLLM_OMNI_IMAGE}")
            ;;

        *)
            log_warn "未知服务: ${service}，跳过"
            ;;
    esac
}

# --------------- 执行构建与推送 ---------------
for svc in "${SERVICES[@]}"; do
    echo ""
    log_info "------------------------------------------"
    process_service "${svc}"
done

# --------------- 输出总结 ---------------
echo ""
log_info "=========================================="
log_info " 构建推送总结"
log_info "=========================================="

if [[ ${#SUCCESS_LIST[@]} -gt 0 ]]; then
    log_info "✅ 成功 (${#SUCCESS_LIST[@]}):"
    for img in "${SUCCESS_LIST[@]}"; do
        echo "   - ${img}"
    done
fi

if [[ ${#FAIL_LIST[@]} -gt 0 ]]; then
    log_error "❌ 失败 (${#FAIL_LIST[@]}):"
    for img in "${FAIL_LIST[@]}"; do
        echo "   - ${img}"
    done
    exit 1
fi

log_info "🎉 全部完成!"