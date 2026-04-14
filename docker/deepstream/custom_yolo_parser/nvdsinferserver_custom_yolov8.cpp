/**
 * Custom nvinferserver postprocessor for YOLOv8 / YOLO11 output format.
 *
 * YOLOv8 single-tensor output layout:
 *   output0: [batch, 4 + num_classes, num_boxes]
 *            channels 0-3 = cx, cy, w, h  (in model input pixel space)
 *            channels 4+  = per-class confidence scores
 *
 * This processor:
 *   1. Reads the raw output tensor from Triton
 *   2. Applies confidence threshold filtering
 *   3. Runs per-class greedy NMS
 *   4. Scales bounding boxes from model-input resolution to muxer-frame resolution
 *   5. Attaches NvDsObjectMeta to each frame for nvdsosd rendering
 *      with per-class colors and text labels
 */

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

#include <glib.h>

#include "infer_custom_process.h"
#include "nvbufsurface.h"
#include "nvdsmeta.h"

typedef struct _GstBuffer GstBuffer;

namespace dsis = nvdsinferserver;

// ---- helpers ------------------------------------------------------------ //

struct Detection {
    float x1, y1, x2, y2;
    float score;
    int classId;
};

static float iou(const Detection& a, const Detection& b) {
    float ix1 = std::max(a.x1, b.x1);
    float iy1 = std::max(a.y1, b.y1);
    float ix2 = std::min(a.x2, b.x2);
    float iy2 = std::min(a.y2, b.y2);
    float inter = std::max(0.f, ix2 - ix1) * std::max(0.f, iy2 - iy1);
    float area_a = (a.x2 - a.x1) * (a.y2 - a.y1);
    float area_b = (b.x2 - b.x1) * (b.y2 - b.y1);
    return inter / (area_a + area_b - inter + 1e-6f);
}

/** Parse "#RRGGBB" hex string into NvOSD_ColorParams (RGBA 0-1 floats). */
static NvOSD_ColorParams hexToColor(const std::string& hex) {
    NvOSD_ColorParams c = {0.f, 1.f, 0.f, 1.f};  // fallback green
    std::string h = hex;
    if (!h.empty() && h[0] == '#') h = h.substr(1);
    if (h.size() != 6) return c;
    unsigned int r = 0, g = 0, b = 0;
    r = std::stoul(h.substr(0, 2), nullptr, 16);
    g = std::stoul(h.substr(2, 2), nullptr, 16);
    b = std::stoul(h.substr(4, 2), nullptr, 16);
    c.red   = r / 255.f;
    c.green = g / 255.f;
    c.blue  = b / 255.f;
    c.alpha = 1.f;
    return c;
}

// ---- custom processor --------------------------------------------------- //

class YoloV8CustomProcess : public dsis::IInferCustomProcessor {
    float conf_threshold_ = 0.25f;
    float nms_threshold_  = 0.45f;

    // Model input dims captured in extraInputProcess for scaling in inferenceDone
    int model_w_ = 0;
    int model_h_ = 0;
    std::mutex dims_mu_;

    // Per-class labels and colors loaded from the labels file
    std::vector<std::string> class_names_;
    std::vector<NvOSD_ColorParams> class_colors_;

public:
    ~YoloV8CustomProcess() override = default;

    /**
     * Load class names and per-class colors from a labels file.
     * File format: one line per class — "name #RRGGBB"
     * The file path is read from the DS_LABELS_FILE environment variable,
     * which is set by the Python pipeline manager before pipeline creation.
     */
    void loadLabels() {
        const char* envPath = std::getenv("DS_LABELS_FILE");
        if (!envPath || envPath[0] == '\0') {
            fprintf(stderr, "[YoloV8CustomProcess] DS_LABELS_FILE env not set, "
                            "skipping label loading\n");
            return;
        }
        std::string path(envPath);

        fprintf(stderr, "[YoloV8CustomProcess] Loading labels from: %s\n",
                path.c_str());

        if (path.empty()) return;

        std::ifstream ifs(path);
        if (!ifs.is_open()) return;

        std::string line;
        while (std::getline(ifs, line)) {
            if (line.empty()) continue;
            // Format: "class_name #RRGGBB"
            // Find the last space-separated token starting with '#'
            auto hashPos = line.rfind('#');
            if (hashPos != std::string::npos && hashPos > 0) {
                std::string name = line.substr(0, hashPos);
                // Trim trailing whitespace from name
                while (!name.empty() && (name.back() == ' ' || name.back() == '\t'))
                    name.pop_back();
                std::string colorStr = line.substr(hashPos);
                // Trim trailing whitespace from color
                while (!colorStr.empty() && (colorStr.back() == ' ' || colorStr.back() == '\t' || colorStr.back() == '\r'))
                    colorStr.pop_back();
                class_names_.push_back(name);
                class_colors_.push_back(hexToColor(colorStr));
            } else {
                // No color specified — use fallback green
                std::string name = line;
                while (!name.empty() && (name.back() == ' ' || name.back() == '\t' || name.back() == '\r'))
                    name.pop_back();
                class_names_.push_back(name);
                class_colors_.push_back({0.f, 1.f, 0.f, 1.f});
            }
        }
    }

    void supportInputMemType(dsis::InferMemType& type) override {
        type = dsis::InferMemType::kCpu;
    }

    bool requireInferLoop() const override { return false; }

    /* Capture model input resolution from the primary tensor */
    NvDsInferStatus extraInputProcess(
        const std::vector<dsis::IBatchBuffer*>& primaryInputs,
        std::vector<dsis::IBatchBuffer*>& /*extraInputs*/,
        const dsis::IOptions* /*options*/) override {

        if (!primaryInputs.empty()) {
            auto desc = primaryInputs[0]->getBufDesc();
            // desc.dims for image: [batch, C, H, W] or [C, H, W]
            if (desc.dims.numDims >= 3) {
                std::lock_guard<std::mutex> lk(dims_mu_);
                model_h_ = desc.dims.d[desc.dims.numDims - 2];
                model_w_ = desc.dims.d[desc.dims.numDims - 1];
            }
        }
        return NVDSINFER_SUCCESS;
    }

    /* Parse YOLO output, run NMS, attach NvDsObjectMeta */
    NvDsInferStatus inferenceDone(
        const dsis::IBatchArray* outputs,
        const dsis::IOptions* inOptions) override {

        if (!outputs || outputs->getSize() == 0) return NVDSINFER_SUCCESS;

        // ---- 1. Retrieve output tensor --------------------------------- //
        const dsis::IBatchBuffer* outBuf = outputs->getBuffer(0);
        if (!outBuf) return NVDSINFER_SUCCESS;

        auto desc = outBuf->getBufDesc();
        // Expected shape: [batch, channels, num_boxes]  or [channels, num_boxes]
        int channels, numBoxes;
        if (desc.dims.numDims == 3) {
            channels = desc.dims.d[1];
            numBoxes = desc.dims.d[2];
        } else if (desc.dims.numDims == 2) {
            channels = desc.dims.d[0];
            numBoxes = desc.dims.d[1];
        } else {
            return NVDSINFER_SUCCESS;
        }

        int numClasses = channels - 4;
        if (numClasses <= 0 || numBoxes <= 0) return NVDSINFER_SUCCESS;

        const float* data = reinterpret_cast<const float*>(outBuf->getBufPtr(0));
        if (!data) return NVDSINFER_SUCCESS;

        // ---- 2. Parse detections --------------------------------------- //
        std::vector<Detection> dets;
        dets.reserve(256);

        for (int i = 0; i < numBoxes; ++i) {
            float cx = data[0 * numBoxes + i];
            float cy = data[1 * numBoxes + i];
            float w  = data[2 * numBoxes + i];
            float h  = data[3 * numBoxes + i];

            float maxScore = 0.f;
            int   maxClass = 0;
            for (int c = 0; c < numClasses; ++c) {
                float s = data[(4 + c) * numBoxes + i];
                if (s > maxScore) { maxScore = s; maxClass = c; }
            }
            if (maxScore < conf_threshold_) continue;

            Detection d;
            d.x1 = cx - w * 0.5f;
            d.y1 = cy - h * 0.5f;
            d.x2 = cx + w * 0.5f;
            d.y2 = cy + h * 0.5f;
            d.score = maxScore;
            d.classId = maxClass;
            dets.push_back(d);
        }

        // ---- 3. Per-class greedy NMS ----------------------------------- //
        std::sort(dets.begin(), dets.end(),
                  [](const Detection& a, const Detection& b) { return a.score > b.score; });

        std::vector<Detection> kept;
        std::vector<bool> suppressed(dets.size(), false);

        for (size_t i = 0; i < dets.size(); ++i) {
            if (suppressed[i]) continue;
            kept.push_back(dets[i]);
            for (size_t j = i + 1; j < dets.size(); ++j) {
                if (suppressed[j]) continue;
                if (dets[i].classId != dets[j].classId) continue;
                if (iou(dets[i], dets[j]) > nms_threshold_)
                    suppressed[j] = true;
            }
        }

        // ---- 4. Scale bboxes from model space to muxer-frame space ----- //
        NvDsBatchMeta* batchMeta = nullptr;
        std::vector<NvDsFrameMeta*> frameMetaList;
        std::vector<NvBufSurfaceParams*> surfParamsList;
        int64_t unique_id = 0;

        if (!inOptions) return NVDSINFER_SUCCESS;

        inOptions->getObj(OPTION_NVDS_BATCH_META, batchMeta);
        inOptions->getValueArray(OPTION_NVDS_FRAME_META_LIST, frameMetaList);
        inOptions->getInt(OPTION_NVDS_UNIQUE_ID, unique_id);
        inOptions->getValueArray(OPTION_NVDS_BUF_SURFACE_PARAMS_LIST, surfParamsList);

        if (!batchMeta || frameMetaList.empty()) return NVDSINFER_SUCCESS;

        // Frame dimensions from surfaceParams (the muxer output resolution)
        float frame_w = 640.f, frame_h = 640.f;
        if (!surfParamsList.empty() && surfParamsList[0]) {
            frame_w = static_cast<float>(surfParamsList[0]->width);
            frame_h = static_cast<float>(surfParamsList[0]->height);
        }

        // Model input dimensions (captured from the primary input tensor)
        float mw, mh;
        {
            std::lock_guard<std::mutex> lk(dims_mu_);
            mw = model_w_ > 0 ? static_cast<float>(model_w_) : frame_w;
            mh = model_h_ > 0 ? static_cast<float>(model_h_) : frame_h;
        }

        float sx = frame_w / mw;
        float sy = frame_h / mh;

        // ---- 5. Attach NvDsObjectMeta ---------------------------------- //
        NvDsFrameMeta* frameMeta = frameMetaList[0];

        for (auto& det : kept) {
            NvDsObjectMeta* objMeta = nvds_acquire_obj_meta_from_pool(batchMeta);
            if (!objMeta) break;

            objMeta->unique_component_id = unique_id;
            objMeta->confidence  = det.score;
            objMeta->object_id   = UNTRACKED_OBJECT_ID;
            objMeta->class_id    = det.classId;

            // Scale from model input resolution -> muxer-frame resolution
            float left   = det.x1 * sx;
            float top    = det.y1 * sy;
            float right  = det.x2 * sx;
            float bottom = det.y2 * sy;

            // Clamp to frame bounds
            left   = std::max(0.f, std::min(left,   frame_w));
            top    = std::max(0.f, std::min(top,    frame_h));
            right  = std::max(0.f, std::min(right,  frame_w));
            bottom = std::max(0.f, std::min(bottom, frame_h));

            // ---- Bounding box ----
            NvOSD_RectParams& rect = objMeta->rect_params;
            rect.left   = left;
            rect.top    = top;
            rect.width  = right - left;
            rect.height = bottom - top;
            rect.border_width = 3;
            rect.has_bg_color = 0;

            // Per-class border color (fallback: green)
            if (det.classId < (int)class_colors_.size()) {
                rect.border_color = class_colors_[det.classId];
            } else {
                rect.border_color = {0.f, 1.f, 0.f, 1.f};
            }

            // ---- Text label: "class_name 95%" ----
            const char* label = nullptr;
            if (det.classId < (int)class_names_.size()) {
                label = class_names_[det.classId].c_str();
            }
            if (label) {
                NvOSD_TextParams& text = objMeta->text_params;
                // nvdsosd frees display_text with g_free(), so allocate with g_malloc0
                text.display_text = (gchar*)g_malloc0(64);
                snprintf(text.display_text, 64, "%s %.0f%%", label, det.score * 100.f);
                text.x_offset = (int)left;
                text.y_offset = std::max(0, (int)top - 12);
                text.font_params.font_name  = (gchar*)"WenQuanYi Zen Hei";
                text.font_params.font_size  = 14;
                text.font_params.font_color = {1.f, 1.f, 1.f, 1.f};
                text.set_bg_clr = 1;
                text.text_bg_clr = rect.border_color;
                text.text_bg_clr.alpha = 0.6f;
            }

            nvds_acquire_meta_lock(batchMeta);
            nvds_add_obj_meta_to_frame(frameMeta, objMeta, NULL);
            frameMeta->bInferDone = TRUE;
            nvds_release_meta_lock(batchMeta);
        }

        return NVDSINFER_SUCCESS;
    }

    void notifyError(NvDsInferStatus /*s*/) override {}
};

// ---- factory function --------------------------------------------------- //

extern "C" {
dsis::IInferCustomProcessor*
CreateInferServerCustomProcess(const char* config, uint32_t configLen) {
    (void)config;
    (void)configLen;
    auto* proc = new YoloV8CustomProcess();
    proc->loadLabels();
    return proc;
}
}
