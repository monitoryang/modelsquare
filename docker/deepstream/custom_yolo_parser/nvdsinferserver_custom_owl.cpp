/**
 * Custom nvinferserver postprocessor for OWLv2 open-vocabulary detection.
 *
 * OWL image encoder outputs (from Triton):
 *   image_class_embeds: [1, P, D]  — per-patch class embeddings
 *   logit_shift:        [1, P, 1]  — per-patch bias
 *   logit_scale:        [1, P, 1]  — per-patch scale
 *   pred_boxes:         [1, P, 4]  — normalized boxes (x1, y1, x2, y2)
 *
 * This processor:
 *   1. Applies ImageNet normalization in extraInputProcess (nvinferserver
 *      only does /255; per-channel mean/std is done here)
 *   2. Reads pre-computed text embeddings from a binary file
 *   3. Computes cosine similarity between image patches and text embeddings
 *   4. Applies logit shift/scale + sigmoid
 *   5. Runs per-class containment-based NMS
 *   6. Attaches NvDsObjectMeta with per-class colors and text labels
 *   7. Supports hot-reload: checks file mtime each frame
 */

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

#include <cuda_runtime.h>

#include <sys/stat.h>

#include <glib.h>

#include "infer_custom_process.h"
#include "nvbufsurface.h"
#include "nvdsmeta.h"

typedef struct _GstBuffer GstBuffer;

namespace dsis = nvdsinferserver;

// ---- ImageNet constants ------------------------------------------------- //

static constexpr float IMAGENET_MEAN[] = {0.48145466f, 0.4578275f, 0.40821073f};
static constexpr float IMAGENET_STD[]  = {0.26862954f, 0.26130258f, 0.27577711f};

// ---- helpers ------------------------------------------------------------ //

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

struct Detection {
    float x1, y1, x2, y2;
    float score;
    int classId;

    float area() const { return (x2 - x1) * (y2 - y1); }
};

// ---- custom processor --------------------------------------------------- //

class OwlCustomProcess : public dsis::IInferCustomProcessor {
    float conf_threshold_ = 0.1f;
    float nms_threshold_  = 0.3f;

    // Model input dims captured in extraInputProcess
    int model_w_ = 0;
    int model_h_ = 0;
    std::mutex dims_mu_;

    // Text embeddings loaded from binary file (pre-L2-normalized)
    int num_classes_ = 0;
    int embed_dim_   = 0;
    std::vector<float> text_embeds_norm_;  // [num_classes * embed_dim], row-major

    // Per-class labels and colors
    std::vector<std::string> class_names_;
    std::vector<NvOSD_ColorParams> class_colors_;

    // File paths and mtime for hot-reload
    std::string embeds_path_;
    std::string labels_path_;
    time_t embeds_mtime_ = 0;
    time_t labels_mtime_ = 0;

    // CPU staging buffer for GPU→CPU→GPU normalization round-trip
    std::vector<float> host_buf_;

public:
    ~OwlCustomProcess() override = default;

    // ---- Loading -------------------------------------------------------- //

    void loadEmbeddings() {
        const char* envPath = std::getenv("DS_OWL_EMBEDS_FILE");
        if (!envPath || envPath[0] == '\0') {
            fprintf(stderr, "[OwlCustomProcess] DS_OWL_EMBEDS_FILE not set\n");
            return;
        }
        embeds_path_ = envPath;
        reloadEmbeddings();
    }

    void reloadEmbeddings() {
        if (embeds_path_.empty()) return;

        std::ifstream ifs(embeds_path_, std::ios::binary);
        if (!ifs.is_open()) {
            fprintf(stderr, "[OwlCustomProcess] Cannot open embeddings: %s\n",
                    embeds_path_.c_str());
            return;
        }

        int32_t n = 0, d = 0;
        ifs.read(reinterpret_cast<char*>(&n), 4);
        ifs.read(reinterpret_cast<char*>(&d), 4);

        if (n <= 0 || d <= 0 || n > 1000 || d > 2048) {
            fprintf(stderr, "[OwlCustomProcess] Invalid embeddings header: n=%d d=%d\n", n, d);
            return;
        }

        std::vector<float> raw(n * d);
        ifs.read(reinterpret_cast<char*>(raw.data()), n * d * sizeof(float));
        if (!ifs) {
            fprintf(stderr, "[OwlCustomProcess] Truncated embeddings file\n");
            return;
        }

        // Pre-L2-normalize each row for faster per-frame cosine similarity
        for (int i = 0; i < n; ++i) {
            float norm = 0.f;
            for (int j = 0; j < d; ++j)
                norm += raw[i * d + j] * raw[i * d + j];
            norm = std::sqrt(norm) + 1e-6f;
            for (int j = 0; j < d; ++j)
                raw[i * d + j] /= norm;
        }

        num_classes_ = n;
        embed_dim_   = d;
        text_embeds_norm_ = std::move(raw);

        struct stat st;
        if (stat(embeds_path_.c_str(), &st) == 0)
            embeds_mtime_ = st.st_mtime;

        fprintf(stderr, "[OwlCustomProcess] Loaded %d text embeddings (dim=%d) from %s\n",
                n, d, embeds_path_.c_str());
    }

    void loadLabels() {
        const char* envPath = std::getenv("DS_LABELS_FILE");
        if (!envPath || envPath[0] == '\0') {
            fprintf(stderr, "[OwlCustomProcess] DS_LABELS_FILE not set\n");
            return;
        }
        labels_path_ = envPath;
        reloadLabels();
    }

    void reloadLabels() {
        if (labels_path_.empty()) return;

        std::ifstream ifs(labels_path_);
        if (!ifs.is_open()) return;

        std::vector<std::string> names;
        std::vector<NvOSD_ColorParams> colors;

        std::string line;
        while (std::getline(ifs, line)) {
            if (line.empty()) continue;
            auto hashPos = line.rfind('#');
            if (hashPos != std::string::npos && hashPos > 0) {
                std::string name = line.substr(0, hashPos);
                while (!name.empty() && (name.back() == ' ' || name.back() == '\t'))
                    name.pop_back();
                std::string colorStr = line.substr(hashPos);
                while (!colorStr.empty() &&
                       (colorStr.back() == ' ' || colorStr.back() == '\t' || colorStr.back() == '\r'))
                    colorStr.pop_back();
                names.push_back(name);
                colors.push_back(hexToColor(colorStr));
            } else {
                std::string name = line;
                while (!name.empty() &&
                       (name.back() == ' ' || name.back() == '\t' || name.back() == '\r'))
                    name.pop_back();
                names.push_back(name);
                colors.push_back({0.f, 1.f, 0.f, 1.f});
            }
        }

        class_names_  = std::move(names);
        class_colors_ = std::move(colors);

        struct stat st;
        if (stat(labels_path_.c_str(), &st) == 0)
            labels_mtime_ = st.st_mtime;

        fprintf(stderr, "[OwlCustomProcess] Loaded %zu labels from %s\n",
                class_names_.size(), labels_path_.c_str());
    }

    // ---- Hot-reload check ----------------------------------------------- //

    void checkReload() {
        struct stat st;
        if (!embeds_path_.empty() &&
            stat(embeds_path_.c_str(), &st) == 0 &&
            st.st_mtime != embeds_mtime_) {
            fprintf(stderr, "[OwlCustomProcess] Embeddings file changed, reloading\n");
            reloadEmbeddings();
            reloadLabels();  // labels likely changed too
        } else if (!labels_path_.empty() &&
                   stat(labels_path_.c_str(), &st) == 0 &&
                   st.st_mtime != labels_mtime_) {
            reloadLabels();
        }
    }

    // ---- IInferCustomProcessor overrides -------------------------------- //

    bool requireInferLoop() const override { return false; }

    /** Apply ImageNet normalization on top of the /255 done by nvinferserver.
     *
     *  nvinferserver delivers the preprocessed tensor on GPU (memType=kGpuCuda).
     *  We use cudaMemcpy to round-trip the data to CPU for per-channel
     *  (x-mean)/std normalization, then copy back.  ~4ms overhead per frame
     *  which is negligible compared to OWL inference latency.
     */
    NvDsInferStatus extraInputProcess(
        const std::vector<dsis::IBatchBuffer*>& primaryInputs,
        std::vector<dsis::IBatchBuffer*>& /*extraInputs*/,
        const dsis::IOptions* /*options*/) override {

        if (primaryInputs.empty()) return NVDSINFER_SUCCESS;

        auto* buf = primaryInputs[0];
        if (!buf) return NVDSINFER_SUCCESS;

        auto desc = buf->getBufDesc();
        int ndims = desc.dims.numDims;
        if (ndims < 3) return NVDSINFER_SUCCESS;

        int C = desc.dims.d[ndims - 3];
        int H = desc.dims.d[ndims - 2];
        int W = desc.dims.d[ndims - 1];

        {
            std::lock_guard<std::mutex> lk(dims_mu_);
            model_h_ = H;
            model_w_ = W;
        }

        float* devData = reinterpret_cast<float*>(buf->getBufPtr(0));
        if (!devData || C != 3) return NVDSINFER_SUCCESS;

        size_t count = (size_t)C * H * W;
        size_t bytes = count * sizeof(float);

        // Allocate CPU staging buffer (reuse across frames)
        if (host_buf_.size() < count) host_buf_.resize(count);

        // GPU → CPU
        cudaError_t err = cudaMemcpy(host_buf_.data(), devData, bytes, cudaMemcpyDeviceToHost);
        if (err != cudaSuccess) {
            fprintf(stderr, "[OwlCustomProcess] cudaMemcpy D2H failed: %s\n",
                    cudaGetErrorString(err));
            return NVDSINFER_SUCCESS;
        }

        // Per-channel: (x - mean) / std
        for (int c = 0; c < 3; ++c) {
            float m = IMAGENET_MEAN[c];
            float inv_s = 1.0f / IMAGENET_STD[c];
            float* ch = host_buf_.data() + c * H * W;
            for (int i = 0; i < H * W; ++i)
                ch[i] = (ch[i] - m) * inv_s;
        }

        // CPU → GPU
        err = cudaMemcpy(devData, host_buf_.data(), bytes, cudaMemcpyHostToDevice);
        if (err != cudaSuccess) {
            fprintf(stderr, "[OwlCustomProcess] cudaMemcpy H2D failed: %s\n",
                    cudaGetErrorString(err));
        }

        return NVDSINFER_SUCCESS;
    }

    /** Parse OWL outputs, compute cosine similarity, NMS, attach metadata. */
    NvDsInferStatus inferenceDone(
        const dsis::IBatchArray* outputs,
        const dsis::IOptions* inOptions) override {

        fprintf(stderr, "[OwlCustomProcess] >>> inferenceDone called, outputs=%p size=%u\n",
                (void*)outputs, outputs ? outputs->getSize() : 0);

        // Hot-reload check
        checkReload();

        if (!outputs || outputs->getSize() < 4) return NVDSINFER_SUCCESS;
        if (num_classes_ <= 0 || embed_dim_ <= 0) return NVDSINFER_SUCCESS;

        // ---- 1. Retrieve output tensors --------------------------------- //
        // nvinferserver sorts requested outputs alphabetically by name, so the
        // buffer index order is: image_class_embeds(0), logit_scale(1),
        // logit_shift(2), pred_boxes(3).
        const dsis::IBatchBuffer* embedsBuf = outputs->getBuffer(0);  // image_class_embeds
        const dsis::IBatchBuffer* scaleBuf  = outputs->getBuffer(1);  // logit_scale
        const dsis::IBatchBuffer* shiftBuf  = outputs->getBuffer(2);  // logit_shift
        const dsis::IBatchBuffer* boxesBuf  = outputs->getBuffer(3);  // pred_boxes

        if (!embedsBuf || !shiftBuf || !scaleBuf || !boxesBuf)
            return NVDSINFER_SUCCESS;

        // image_class_embeds: [1, P, D]
        auto eDesc = embedsBuf->getBufDesc();

        // Debug: print tensor info on first frame only
        static int dbg_frame = 0;
        if (dbg_frame < 3) {
            auto sDesc = shiftBuf->getBufDesc();
            auto scDesc = scaleBuf->getBufDesc();
            auto bDesc = boxesBuf->getBufDesc();
            fprintf(stderr, "[OwlCustomProcess] embeds: ndims=%d memType=%d dims=",
                    eDesc.dims.numDims, (int)eDesc.memType);
            for (int i = 0; i < eDesc.dims.numDims; i++) fprintf(stderr, "%d ", eDesc.dims.d[i]);
            fprintf(stderr, "\n[OwlCustomProcess] shift:  ndims=%d memType=%d dims=",
                    sDesc.dims.numDims, (int)sDesc.memType);
            for (int i = 0; i < sDesc.dims.numDims; i++) fprintf(stderr, "%d ", sDesc.dims.d[i]);
            fprintf(stderr, "\n[OwlCustomProcess] scale:  ndims=%d memType=%d dims=",
                    scDesc.dims.numDims, (int)scDesc.memType);
            for (int i = 0; i < scDesc.dims.numDims; i++) fprintf(stderr, "%d ", scDesc.dims.d[i]);
            fprintf(stderr, "\n[OwlCustomProcess] boxes:  ndims=%d memType=%d dims=",
                    bDesc.dims.numDims, (int)bDesc.memType);
            for (int i = 0; i < bDesc.dims.numDims; i++) fprintf(stderr, "%d ", bDesc.dims.d[i]);
            fprintf(stderr, "\n");
        }

        int P = 0, D = 0;
        if (eDesc.dims.numDims == 3) {
            P = eDesc.dims.d[1];
            D = eDesc.dims.d[2];
        } else if (eDesc.dims.numDims == 2) {
            P = eDesc.dims.d[0];
            D = eDesc.dims.d[1];
        } else {
            return NVDSINFER_SUCCESS;
        }

        if (D != embed_dim_) {
            fprintf(stderr, "[OwlCustomProcess] embed_dim mismatch: tensor=%d file=%d\n",
                    D, embed_dim_);
            return NVDSINFER_SUCCESS;
        }

        const float* embedsData = reinterpret_cast<const float*>(embedsBuf->getBufPtr(0));
        const float* shiftData  = reinterpret_cast<const float*>(shiftBuf->getBufPtr(0));
        const float* scaleData  = reinterpret_cast<const float*>(scaleBuf->getBufPtr(0));
        const float* boxesData  = reinterpret_cast<const float*>(boxesBuf->getBufPtr(0));
        if (!embedsData || !shiftData || !scaleData || !boxesData)
            return NVDSINFER_SUCCESS;

        // ---- 2. L2-normalize image_class_embeds per patch --------------- //
        std::vector<float> imgEmbedsNorm(P * D);
        for (int p = 0; p < P; ++p) {
            float norm = 0.f;
            for (int d = 0; d < D; ++d) {
                float v = embedsData[p * D + d];
                norm += v * v;
            }
            norm = std::sqrt(norm) + 1e-6f;
            for (int d = 0; d < D; ++d)
                imgEmbedsNorm[p * D + d] = embedsData[p * D + d] / norm;
        }

        // ---- 3. Cosine similarity + logit shift/scale + sigmoid --------- //
        // logits[p][c] = dot(imgEmbedsNorm[p], textEmbedsNorm[c])
        // logits = (logits + shift) * scale
        // scores = sigmoid(logits)
        int NC = num_classes_;
        std::vector<Detection> dets;
        dets.reserve(256);

        float dbg_max_score = 0.f;
        float dbg_max_dot = -1e9f;
        float dbg_sample_shift = 0.f, dbg_sample_scale = 0.f;

        for (int p = 0; p < P; ++p) {
            float shift = shiftData[p];
            float scale = scaleData[p];

            if (p == 0) { dbg_sample_shift = shift; dbg_sample_scale = scale; }

            float bestScore = 0.f;
            int bestClass = 0;

            for (int c = 0; c < NC; ++c) {
                // Dot product
                float dot = 0.f;
                const float* imgRow  = &imgEmbedsNorm[p * D];
                const float* textRow = &text_embeds_norm_[c * D];
                for (int d = 0; d < D; ++d)
                    dot += imgRow[d] * textRow[d];

                if (dot > dbg_max_dot) dbg_max_dot = dot;

                // Apply shift/scale + sigmoid
                float logit = (dot + shift) * scale;
                float score = 1.0f / (1.0f + std::exp(-logit));

                if (score > bestScore) {
                    bestScore = score;
                    bestClass = c;
                }
            }

            if (bestScore > dbg_max_score) dbg_max_score = bestScore;

            if (bestScore < conf_threshold_ || bestScore > 0.999f)
                continue;

            // pred_boxes: [P, 4] normalized (x1, y1, x2, y2)
            Detection det;
            det.x1 = boxesData[p * 4 + 0];
            det.y1 = boxesData[p * 4 + 1];
            det.x2 = boxesData[p * 4 + 2];
            det.y2 = boxesData[p * 4 + 3];
            det.score = bestScore;
            det.classId = bestClass;
            dets.push_back(det);
        }

        // ---- 4. Per-class containment-based NMS ------------------------- //
        // Sort by area ascending (keep smaller inner boxes)
        std::sort(dets.begin(), dets.end(),
                  [](const Detection& a, const Detection& b) {
                      return a.area() < b.area();
                  });

        std::vector<Detection> kept;
        std::vector<bool> suppressed(dets.size(), false);

        for (size_t i = 0; i < dets.size(); ++i) {
            if (suppressed[i]) continue;
            kept.push_back(dets[i]);
            for (size_t j = i + 1; j < dets.size(); ++j) {
                if (suppressed[j]) continue;
                if (dets[i].classId != dets[j].classId) continue;

                // Containment: intersection / min(area_i, area_j)
                float ix1 = std::max(dets[i].x1, dets[j].x1);
                float iy1 = std::max(dets[i].y1, dets[j].y1);
                float ix2 = std::min(dets[i].x2, dets[j].x2);
                float iy2 = std::min(dets[i].y2, dets[j].y2);
                float inter = std::max(0.f, ix2 - ix1) * std::max(0.f, iy2 - iy1);
                float minArea = std::min(dets[i].area(), dets[j].area()) + 1e-6f;
                if (inter / minArea > nms_threshold_)
                    suppressed[j] = true;
            }
        }

        // Debug: print stats for first few frames
        if (dbg_frame < 3) {
            fprintf(stderr, "[OwlCustomProcess] P=%d D=%d NC=%d | "
                    "sample shift=%.4f scale=%.4f | "
                    "max_dot=%.6f max_score=%.6f | "
                    "pre-NMS dets=%zu kept=%zu\n",
                    P, D, NC,
                    dbg_sample_shift, dbg_sample_scale,
                    dbg_max_dot, dbg_max_score,
                    dets.size(), kept.size());

            // Print first few embed values to check if output is CPU-readable
            if (P > 0 && D > 0) {
                fprintf(stderr, "[OwlCustomProcess] embeds[0][0..3]=%.6f %.6f %.6f %.6f\n",
                        embedsData[0], embedsData[1], embedsData[2], embedsData[3]);
                fprintf(stderr, "[OwlCustomProcess] textEmb[0][0..3]=%.6f %.6f %.6f %.6f\n",
                        text_embeds_norm_[0], text_embeds_norm_[1],
                        text_embeds_norm_[2], text_embeds_norm_[3]);
            }
            dbg_frame++;
        }

        // ---- 5. Scale boxes and attach NvDsObjectMeta ------------------- //
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

        float frame_w = 640.f, frame_h = 640.f;
        if (!surfParamsList.empty() && surfParamsList[0]) {
            frame_w = static_cast<float>(surfParamsList[0]->width);
            frame_h = static_cast<float>(surfParamsList[0]->height);
        }

        NvDsFrameMeta* frameMeta = frameMetaList[0];

        for (auto& det : kept) {
            NvDsObjectMeta* objMeta = nvds_acquire_obj_meta_from_pool(batchMeta);
            if (!objMeta) break;

            objMeta->unique_component_id = unique_id;
            objMeta->confidence  = det.score;
            objMeta->object_id   = UNTRACKED_OBJECT_ID;
            objMeta->class_id    = det.classId;

            // Scale from normalized [0,1] to frame pixel coordinates
            float left   = det.x1 * frame_w;
            float top    = det.y1 * frame_h;
            float right  = det.x2 * frame_w;
            float bottom = det.y2 * frame_h;

            left   = std::max(0.f, std::min(left,   frame_w));
            top    = std::max(0.f, std::min(top,    frame_h));
            right  = std::max(0.f, std::min(right,  frame_w));
            bottom = std::max(0.f, std::min(bottom, frame_h));

            // Bounding box
            NvOSD_RectParams& rect = objMeta->rect_params;
            rect.left   = left;
            rect.top    = top;
            rect.width  = right - left;
            rect.height = bottom - top;
            rect.border_width = 3;
            rect.has_bg_color = 0;

            if (det.classId < (int)class_colors_.size()) {
                rect.border_color = class_colors_[det.classId];
            } else {
                rect.border_color = {0.f, 1.f, 0.f, 1.f};
            }

            // Text label
            const char* label = nullptr;
            if (det.classId < (int)class_names_.size()) {
                label = class_names_[det.classId].c_str();
            }
            if (label) {
                NvOSD_TextParams& text = objMeta->text_params;
                text.display_text = (gchar*)g_malloc0(128);
                snprintf(text.display_text, 128, "%s %.0f%%", label, det.score * 100.f);
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
    auto* proc = new OwlCustomProcess();
    proc->loadEmbeddings();
    proc->loadLabels();
    return proc;
}
}
