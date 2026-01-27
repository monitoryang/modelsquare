#!/bin/bash

set -euo pipefail  # 严格模式：出错即停

BASE_URL="http://localhost:8000"
EMAIL="155_@modelsquare.com"
USERNAME="owenYoung_"
PASSWORD="Abc@123456"

echo "🚀 开始集成测试..."

# ==============================
# 3.1 健康检查接口
# ==============================
echo "🧪 3.1 健康检查..."
HEALTH_RESP=$(curl -s "$BASE_URL/api/v1/health")
STATUS=$(echo "$HEALTH_RESP" | jq -r '.status // empty')
if [[ "$STATUS" != "healthy" ]]; then
  echo "❌ 健康检查失败：$HEALTH_RESP"
  exit 1
fi
echo "✅ 健康检查通过"

# ==============================
# 3.2 用户注册接口
# ==============================
echo "🧪 3.2 用户注册..."
REGISTER_RESP=$(curl -s -w "%{http_code}" -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}")

HTTP_CODE="${REGISTER_RESP: -3}"
RESP_BODY="${REGISTER_RESP%???}"

if [[ "$HTTP_CODE" == "201" ]]; then
  echo "✅ 用户注册成功"
elif [[ "$HTTP_CODE" == "400" ]] && echo "$RESP_BODY" | jq -e '.detail == "Email already registered"' > /dev/null; then
  echo "ℹ️ 用户已存在，跳过注册"
else
  echo "❌ 注册失败 (HTTP $HTTP_CODE): $RESP_BODY"
  exit 1
fi

# ==============================
# 3.3 用户登录接口
# ==============================
echo "🧪 3.3 用户登录..."
LOGIN_RESP=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$EMAIL&password=$PASSWORD")

ACCESS_TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token // empty')
if [[ -z "$ACCESS_TOKEN" || "$ACCESS_TOKEN" == "null" ]]; then
  echo "❌ 登录失败：$LOGIN_RESP"
  exit 1
fi
export TOKEN="$ACCESS_TOKEN"
echo "✅ 登录成功，Token 已保存"

# ==============================
# 3.4 模型创建接口
# ==============================
echo "🧪 3.4 创建模型..."
CREATE_MODEL_RESP=$(curl -s -w "%{http_code}" -X POST "$BASE_URL/api/v1/models" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "YOLOv8-Detection",
    "description": "目标检测模型，支持80类物体识别",
    "task_type": "detection",
    "framework": "onnx",
    "version": "1.0.0",
    "is_public": true,
    "tags": ["detection", "yolo", "coco"],
    "input_spec": {"image": "HWC", "shape": [640, 640, 3]},
    "output_spec": {"boxes": "Nx4", "scores": "N", "labels": "N"}
  }')

HTTP_CODE="${CREATE_MODEL_RESP: -3}"
RESP_BODY="${CREATE_MODEL_RESP%???}"

if [[ "$HTTP_CODE" != "201" ]]; then
  echo "❌ 模型创建失败 (HTTP $HTTP_CODE): $RESP_BODY"
  exit 1
fi

MODEL_ID=$(echo "$RESP_BODY" | jq -r '.id // empty')
if [[ -z "$MODEL_ID" || "$MODEL_ID" == "null" ]]; then
  echo "❌ 未返回模型 ID"
  exit 1
fi
export MODEL_ID="$MODEL_ID"
echo "✅ 模型创建成功，ID: $MODEL_ID"

# ==============================
# 3.5 模型列表查询接口
# ==============================
echo "🧪 3.5 模型列表查询..."
LIST_RESP=$(curl -s "$BASE_URL/api/v1/models?page=1&page_size=10")
TOTAL=$(echo "$LIST_RESP" | jq -r '.total // empty')
ITEMS_COUNT=$(echo "$LIST_RESP" | jq '.items | length')

if [[ "$TOTAL" -lt 1 ]] || [[ "$ITEMS_COUNT" -lt 1 ]]; then
  echo "❌ 模型列表为空或 total 不正确"
  exit 1
fi
echo "✅ 模型列表查询通过"

# ==============================
# 3.6 模型详情查询接口
# ==============================
echo "🧪 3.6 模型详情查询..."
DETAIL_RESP=$(curl -s "$BASE_URL/api/v1/models/$MODEL_ID")
DETAIL_ID=$(echo "$DETAIL_RESP" | jq -r '.id // empty')
if [[ "$DETAIL_ID" != "$MODEL_ID" ]]; then
  echo "❌ 模型详情不匹配"
  exit 1
fi
echo "✅ 模型详情查询通过"

# ==============================
# 3.7 模型更新接口
# ==============================
echo "🧪 3.7 模型更新..."
UPDATE_RESP=$(curl -s -w "%{http_code}" -X PATCH "$BASE_URL/api/v1/models/$MODEL_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"description": "更新后的模型描述", "version": "1.0.1"}')

HTTP_CODE="${UPDATE_RESP: -3}"
RESP_BODY="${UPDATE_RESP%???}"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "❌ 模型更新失败 (HTTP $HTTP_CODE): $RESP_BODY"
  exit 1
fi

UPDATED_DESC=$(echo "$RESP_BODY" | jq -r '.description // empty')
if [[ "$UPDATED_DESC" != "更新后的模型描述" ]]; then
  echo "❌ 描述未更新"
  exit 1
fi
echo "✅ 模型更新成功"

# ==============================
# 3.8 图片推理接口
# ==============================
echo "🧪 3.8 图片推理..."
# 下载测试图片
cp /mnt/14TB/yangwen/code/AIcoder/ModelSquare/tests/images/R-C.jpg /tmp/test.jpg

INFER_RESP=$(curl -s -w "%{http_code}" -X POST "$BASE_URL/api/v1/models/$MODEL_ID/infer/image" \
  -H "Authorization: Bearer $TOKEN" \
  -F "image=@/tmp/test.jpg")

HTTP_CODE="${INFER_RESP: -3}"
RESP_BODY="${INFER_RESP%???}"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "❌ 推理失败 (HTTP $HTTP_CODE): $RESP_BODY"
  exit 1
fi

LATENCY=$(echo "$RESP_BODY" | jq '.latency_ms // empty')
if [[ -z "$LATENCY" ]] || (( $(echo "$LATENCY < 0" | bc -l) )); then
  echo "❌ latency_ms 异常: $LATENCY"
  exit 1
fi
echo "✅ 图片推理成功，延迟: ${LATENCY}ms"

# ==============================
# 3.9 模型删除接口
# ==============================
echo "🧪 3.9 模型删除测试..."

# 创建临时模型
TEMP_MODEL_RESP=$(curl -s -X POST "$BASE_URL/api/v1/models" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"TempModel","task_type":"classification","framework":"pytorch"}')
TEMP_MODEL_ID=$(echo "$TEMP_MODEL_RESP" | jq -r '.id')

# 删除模型
DELETE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/api/v1/models/$TEMP_MODEL_ID" \
  -H "Authorization: Bearer $TOKEN")

if [[ "$DELETE_STATUS" != "204" ]]; then
  echo "❌ 删除模型失败 (HTTP $DELETE_STATUS)"
  exit 1
fi

# 验证是否真的删除
VERIFY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/models/$TEMP_MODEL_ID")
if [[ "$VERIFY_STATUS" != "404" ]]; then
  echo "❌ 模型删除后仍可访问 (HTTP $VERIFY_STATUS)"
  exit 1
fi

echo "✅ 模型删除成功"

# ==============================
echo "🎉 所有集成测试通过！"