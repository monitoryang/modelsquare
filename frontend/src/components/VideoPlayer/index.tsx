/**
 * Video Player with Detection Overlay and Class Filter
 * Uses original video and renders detection boxes on frontend
 * Supports playback control, progress bar, category filtering, and HLS streaming
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import Hls from 'hls.js';
import {
  Card,
  Row,
  Col,
  Slider,
  Button,
  Space,
  Checkbox,
  Tag,
  Typography,
  Tooltip,
  Modal,
  message,
  Progress,
} from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  ExportOutlined,
  ExpandOutlined,
} from '@ant-design/icons';
import type { VideoTaskResult, FrameDetectionResult, VideoExportProgressState } from '../../services';
import { modelService } from '../../services';

const { Text } = Typography;

interface VideoPlayerProps {
  videoFile?: File;
  videoBlob?: Blob;
  result: VideoTaskResult;
  classColors: Record<string, string>;
  modelId?: string;
  taskId?: string;
  hlsUrl?: string | null;
  originalHlsUrl?: string | null;
  /** When true, hides export controls and shows a live preview indicator */
  isPreview?: boolean;
}

interface DetectionBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  score: number;
  className: string;
  color: string;
}

// Helper function to determine text color based on background brightness
const getContrastTextColor = (bgColor: string): string => {
  const hex = bgColor.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16) || 0;
  const g = parseInt(hex.substring(2, 4), 16) || 0;
  const b = parseInt(hex.substring(4, 6), 16) || 0;
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.5 ? '#000000' : '#ffffff';
};

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  videoFile,
  videoBlob,
  result,
  classColors,
  modelId,
  taskId,
  hlsUrl,
  originalHlsUrl,
  isPreview = false,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const modalVideoRef = useRef<HTMLVideoElement>(null);
  const modalCanvasRef = useRef<HTMLCanvasElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const modalHlsRef = useRef<Hls | null>(null);
  const videoUrlRef = useRef<string>('');
  const [modalCanvasSize, setModalCanvasSize] = useState({ width: 1280, height: 720 });

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(result.duration_seconds || 0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [videoUrl, setVideoUrl] = useState<string>('');
  // True when video source already has detection boxes rendered (skip canvas overlay)
  const [isRenderedSource, setIsRenderedSource] = useState(false);
  // HLS buffer tracking: the furthest point (in seconds) currently buffered
  const [bufferedEnd, setBufferedEnd] = useState(0);
  // Whether the video source is HLS (used for buffer-aware UI)
  const [isHlsSource, setIsHlsSource] = useState(false);

  // Export state
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [exportStageText, setExportStageText] = useState('准备中');
  const [exportElapsedSeconds, setExportElapsedSeconds] = useState<number | null>(null);
  const [exportEtaSeconds, setExportEtaSeconds] = useState<number | null>(null);
  const [exportAbortController, setExportAbortController] = useState<AbortController | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Keep videoUrlRef in sync
  videoUrlRef.current = videoUrl;

  // Class filter state
  const allClasses = React.useMemo(() => {
    const classes = new Set<string>();
    result.frame_results.forEach((frame) => {
      frame.class_names.forEach((name) => classes.add(name));
    });
    return Array.from(classes).sort();
  }, [result.frame_results]);

  const [selectedClasses, setSelectedClasses] = useState<Set<string>>(new Set());
  const [showAllClasses, setShowAllClasses] = useState(true);

  // Initialize selectedClasses when allClasses changes
  useEffect(() => {
    setSelectedClasses(new Set(allClasses));
    setShowAllClasses(true);
  }, [allClasses]);

  // Canvas dimensions
  const [canvasSize, setCanvasSize] = useState({ width: 640, height: 480 });

  // Attach HLS.js to a <video> element (or fall back to native HLS)
  const attachHls = useCallback(
    (video: HTMLVideoElement, url: string, hlsInstanceRef: React.MutableRefObject<Hls | null>) => {
      // Destroy previous instance if any
      if (hlsInstanceRef.current) {
        hlsInstanceRef.current.destroy();
        hlsInstanceRef.current = null;
      }

      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: true,
          liveSyncDurationCount: 1,
          manifestLoadingTimeOut: 10000,
          manifestLoadingMaxRetry: 6,
          levelLoadingTimeOut: 10000,
          levelLoadingMaxRetry: 6,
        });
        hls.loadSource(url);
        hls.attachMedia(video);

        // Track buffer end position via HLS.js events
        hls.on(Hls.Events.BUFFER_APPENDED, () => {
          if (video.buffered.length > 0) {
            setBufferedEnd(video.buffered.end(video.buffered.length - 1));
          }
        });
        hls.on(Hls.Events.LEVEL_UPDATED, (_event, data) => {
          if (data.details && data.details.totalduration) {
            setDuration(data.details.totalduration);
          }
        });

        hlsInstanceRef.current = hls;
        return hls;
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = url;
      }
      return null;
    },
    [],
  );

  // Create video source: prefer originalHlsUrl (clean) -> blob/file -> hlsUrl (rendered, skip overlay)
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    // Prefer original (clean) HLS for overlay playback
    if (originalHlsUrl) {
      attachHls(video, originalHlsUrl, hlsRef);
      setVideoUrl(originalHlsUrl);
      setIsRenderedSource(false);
      setIsHlsSource(true);
      return () => {
        if (hlsRef.current) {
          hlsRef.current.destroy();
          hlsRef.current = null;
        }
      };
    }

    // Blob/file path (original video uploaded by user — clean, overlay OK)
    const source = videoBlob || videoFile;
    if (source) {
      const url = URL.createObjectURL(source);
      setVideoUrl(url);
      video.src = url;
      setIsRenderedSource(false);
      setIsHlsSource(false);
      return () => {
        URL.revokeObjectURL(url);
      };
    }

    // Fallback: rendered HLS (already has detection boxes — skip canvas overlay)
    if (hlsUrl) {
      attachHls(video, hlsUrl, hlsRef);
      setVideoUrl(hlsUrl);
      setIsRenderedSource(true);
      setIsHlsSource(true);
      return () => {
        if (hlsRef.current) {
          hlsRef.current.destroy();
          hlsRef.current = null;
        }
      };
    }
  }, [videoFile, videoBlob, hlsUrl, originalHlsUrl, attachHls]);

  // Cleanup HLS instances on unmount
  useEffect(() => {
    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      if (modalHlsRef.current) {
        modalHlsRef.current.destroy();
        modalHlsRef.current = null;
      }
    };
  }, []);

  // Get current frame data based on video time
  const getCurrentFrameData = useCallback((): FrameDetectionResult | null => {
    if (!result.frame_results.length) return null;

    const frameIndex = Math.floor(currentTime * result.fps);
    if (frameIndex < 0 || frameIndex >= result.frame_results.length) {
      return null;
    }
    return result.frame_results[frameIndex];
  }, [currentTime, result.fps, result.frame_results]);

  // Filter detection boxes based on selected classes
  const getFilteredDetections = useCallback((): DetectionBox[] => {
    const frameData = getCurrentFrameData();
    if (!frameData) return [];

    const boxes: DetectionBox[] = [];
    frameData.boxes.forEach((box, index) => {
      const className = frameData.class_names[index];
      if (!selectedClasses.has(className)) return;

      boxes.push({
        x1: box[0],
        y1: box[1],
        x2: box[2],
        y2: box[3],
        score: frameData.scores[index],
        className,
        color: classColors[className] || '#FF6B6B',
      });
    });
    return boxes;
  }, [getCurrentFrameData, selectedClasses, classColors]);

  // Core draw logic: draw detections onto any canvas/video pair
  const drawOverlayOnCanvas = useCallback((
    canvas: HTMLCanvasElement,
    video: HTMLVideoElement,
  ) => {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Skip overlay if video source already has detection boxes rendered
    if (isRenderedSource) return;

    const detections = getFilteredDetections();
    if (detections.length === 0) return;

    const scaleX = canvas.width / (video.videoWidth || canvas.width);
    const scaleY = canvas.height / (video.videoHeight || canvas.height);

    detections.forEach((det) => {
      const x = det.x1 * scaleX;
      const y = det.y1 * scaleY;
      const w = (det.x2 - det.x1) * scaleX;
      const h = (det.y2 - det.y1) * scaleY;

      ctx.strokeStyle = det.color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);

      const label = `${det.className}: ${(det.score * 100).toFixed(0)}%`;
      ctx.font = 'bold 14px Arial';
      const textMetrics = ctx.measureText(label);
      const textHeight = 18;
      const padding = 4;

      ctx.fillStyle = det.color;
      ctx.fillRect(
        x,
        y - textHeight - padding,
        textMetrics.width + padding * 2,
        textHeight + padding
      );

      ctx.fillStyle = getContrastTextColor(det.color);
      ctx.fillText(label, x + padding, y - padding - 2);
    });

    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    ctx.fillRect(10, 10, 120, 30);
    ctx.fillStyle = '#ffffff';
    ctx.font = '14px Arial';
    ctx.fillText(`检测: ${detections.length} 个`, 20, 30);
  }, [getFilteredDetections, isRenderedSource]);

  // Draw overlay on main player canvas
  const drawOverlay = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;
    drawOverlayOnCanvas(canvas, video);
  }, [drawOverlayOnCanvas]);

  // Draw overlay on modal canvas
  const drawModalOverlay = useCallback(() => {
    const canvas = modalCanvasRef.current;
    const video = modalVideoRef.current;
    if (!canvas || !video) return;
    drawOverlayOnCanvas(canvas, video);
  }, [drawOverlayOnCanvas]);

  // Update canvas size based on container
  const updateCanvasSize = useCallback(() => {
    const container = containerRef.current;
    const video = videoRef.current;
    if (!container || !video) return;

    const containerWidth = container.clientWidth;
    const videoAspect = video.videoWidth / video.videoHeight || 16 / 9;

    let width = containerWidth;
    let height = width / videoAspect;
    const maxHeight = window.innerHeight * 0.6;
    if (height > maxHeight) {
      height = maxHeight;
      width = height * videoAspect;
    }

    setCanvasSize({ width: Math.round(width), height: Math.round(height) });
  }, []);

  // Update canvas size when video metadata loads
  const handleLoadedMetadata = useCallback(() => {
    const video = videoRef.current;
    if (video) {
      setDuration(video.duration || result.duration_seconds);
      updateCanvasSize();
    }
  }, [result.duration_seconds, updateCanvasSize]);

  // Handle window resize
  useEffect(() => {
    const handleResize = () => updateCanvasSize();
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [updateCanvasSize]);

  // Redraw overlay when time or selections change (main player)
  useEffect(() => {
    drawOverlay();
  }, [currentTime, selectedClasses, drawOverlay]);

  // Redraw overlay on modal canvas when time or selections change
  useEffect(() => {
    if (isModalOpen) {
      drawModalOverlay();
    }
  }, [currentTime, selectedClasses, isModalOpen, drawModalOverlay]);

  // --- Modal video initialization (separate effect, not ref callback) ---
  // NOTE: videoUrl is intentionally excluded from deps to prevent re-runs
  // when the source setup effect sets videoUrl. We use videoUrlRef instead.
  useEffect(() => {
    if (!isModalOpen) {
      // Clean up modal HLS when modal closes
      if (modalHlsRef.current) {
        modalHlsRef.current.destroy();
        modalHlsRef.current = null;
      }
      return;
    }

    // Pause main video to avoid play/load race conditions
    const mainVideo = videoRef.current;
    if (mainVideo && !mainVideo.paused) {
      mainVideo.pause();
    }

    // Capture state before async timer
    const savedTime = mainVideo?.currentTime ?? 0;
    const savedRate = mainVideo?.playbackRate ?? 1;

    // Wait a tick for the modal DOM to render
    const timer = setTimeout(() => {
      const el = modalVideoRef.current;
      if (!el) return;

      const syncAndPlay = () => {
        el.currentTime = savedTime;
        el.playbackRate = savedRate;
        el.play().catch(() => {});
      };

      // Determine which source to use for modal
      if (originalHlsUrl) {
        const hls = attachHls(el, originalHlsUrl, modalHlsRef);
        if (hls) {
          hls.on(Hls.Events.MANIFEST_PARSED, syncAndPlay);
        } else {
          el.addEventListener('canplay', syncAndPlay, { once: true });
        }
      } else if (hlsUrl) {
        const hls = attachHls(el, hlsUrl, modalHlsRef);
        if (hls) {
          hls.on(Hls.Events.MANIFEST_PARSED, syncAndPlay);
        } else {
          el.addEventListener('canplay', syncAndPlay, { once: true });
        }
      } else if (videoUrlRef.current) {
        el.src = videoUrlRef.current;
        el.addEventListener('canplay', syncAndPlay, { once: true });
      }
    }, 100);

    return () => {
      clearTimeout(timer);
      // Destroy modal HLS on effect re-run to prevent stale play() promises
      if (modalHlsRef.current) {
        modalHlsRef.current.destroy();
        modalHlsRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isModalOpen, originalHlsUrl, hlsUrl, attachHls]);

  // Video event handlers
  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (video) {
      setCurrentTime(video.currentTime);
      if (video.buffered.length > 0) {
        setBufferedEnd(video.buffered.end(video.buffered.length - 1));
      }
    }
  };

  const handlePlay = () => setIsPlaying(true);
  const handlePause = () => setIsPlaying(false);
  const handleEnded = () => setIsPlaying(false);

  // Control handlers
  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;

    if (isPlaying) {
      video.pause();
    } else {
      video.play().catch(() => {});
    }
  };

  const handleSeek = (value: number) => {
    const video = videoRef.current;
    if (!video) return;

    let seekTarget = value;
    if (isPreview && isHlsSource && bufferedEnd > 0) {
      seekTarget = Math.min(value, bufferedEnd - 0.5);
      seekTarget = Math.max(0, seekTarget);
    }

    video.currentTime = seekTarget;
    setCurrentTime(seekTarget);
  };

  const handleSkip = (seconds: number) => {
    const video = videoRef.current;
    if (video) {
      const newTime = Math.max(0, Math.min(duration, video.currentTime + seconds));
      video.currentTime = newTime;
      setCurrentTime(newTime);
    }
  };

  const handleRestart = () => {
    const video = videoRef.current;
    if (video) {
      video.currentTime = 0;
      setCurrentTime(0);
      video.play().catch(() => {});
    }
  };

  // Class filter handlers
  const toggleClass = (className: string) => {
    setSelectedClasses((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(className)) {
        newSet.delete(className);
      } else {
        newSet.add(className);
      }
      return newSet;
    });
  };

  const toggleAllClasses = () => {
    if (showAllClasses) {
      setSelectedClasses(new Set());
      setShowAllClasses(false);
    } else {
      setSelectedClasses(new Set(allClasses));
      setShowAllClasses(true);
    }
  };

  const handleCancelExport = () => {
    if (exportAbortController) {
      exportAbortController.abort();
      setExportAbortController(null);
    }
  };

  const formatDuration = (seconds?: number | null): string => {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
      return '--:--';
    }
    const safeSeconds = Math.max(0, Math.round(seconds));
    const mins = Math.floor(safeSeconds / 60);
    const secs = safeSeconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const stageLabelMap: Record<string, string> = {
    pending: '等待开始',
    preparing: '准备资源',
    downloading_assets: '下载源文件',
    decoding: '解析视频帧',
    filtering: '按类别重绘',
    rendering: '合成视频',
    uploading: '上传结果',
    downloading: '下载导出文件',
    completed: '导出完成',
    cancelled: '已取消',
    failed: '导出失败',
  };

  const handleExportProgress = (progress: VideoExportProgressState) => {
    setExportProgress(Math.max(0, Math.min(100, Math.round(progress.percent))));
    setExportStageText(stageLabelMap[progress.current_stage || progress.phase] || '导出中');
    setExportElapsedSeconds(progress.elapsed_seconds ?? null);
    setExportEtaSeconds(progress.eta_seconds ?? null);
  };

  // Export video with detection overlay via backend
  const handleExportVideo = async () => {
    if (!modelId || !taskId) {
      message.error('缺少模型或任务信息，无法导出');
      return;
    }

    if (selectedClasses.size === 0) {
      message.warning('请至少选择一个类别');
      return;
    }

    const controller = new AbortController();
    setExportAbortController(controller);
    setIsExporting(true);
    setExportProgress(0);
    setExportStageText('准备中');
    setExportElapsedSeconds(0);
    setExportEtaSeconds(null);

    try {
      const blob = await modelService.exportVideoWithClasses(
        modelId,
        taskId,
        Array.from(selectedClasses),
        {
          signal: controller.signal,
          onProgress: handleExportProgress,
        },
      );

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `detection_export_${taskId}.mp4`;
      a.click();
      URL.revokeObjectURL(url);
      setExportProgress(100);
      setExportStageText('导出完成');
      setExportEtaSeconds(0);
      message.success('视频导出成功');
    } catch (error: unknown) {
      const customError = error as { code?: string; name?: string; message?: string };
      if (
        customError.code === 'ERR_CANCELED'
        || customError.name === 'CanceledError'
        || customError.message === 'EXPORT_CANCELLED'
      ) {
        setExportStageText('已取消');
        message.info('已取消视频导出');
      } else {
        console.error('Export error:', error);
        setExportStageText('导出失败');
        message.error(customError.message || '视频导出失败');
      }
    } finally {
      setIsExporting(false);
      setExportAbortController(null);
    }
  };

  // Format time display
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Whether the <video> element should use src attribute (only for non-HLS sources)
  const useDirectSrc = !hlsUrl && !originalHlsUrl;

  return (
    <Card>
      <Row gutter={[16, 16]}>
        {/* Video Player */}
        <Col span={24}>
          <div
            ref={containerRef}
            style={{
              position: 'relative',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              background: '#000',
              borderRadius: 4,
              overflow: 'hidden',
            }}
          >
            <video
              ref={videoRef}
              src={useDirectSrc ? videoUrl : undefined}
              style={{
                width: canvasSize.width,
                height: canvasSize.height,
                display: 'block',
              }}
              onTimeUpdate={handleTimeUpdate}
              onPlay={handlePlay}
              onPause={handlePause}
              onEnded={handleEnded}
              onLoadedMetadata={handleLoadedMetadata}
              playsInline
            />
            <canvas
              ref={canvasRef}
              width={canvasSize.width}
              height={canvasSize.height}
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: canvasSize.width,
                height: canvasSize.height,
                pointerEvents: 'none',
              }}
            />
            {/* Expand button */}
            <div
              style={{
                position: 'absolute',
                top: 8,
                right: 8,
                zIndex: 10,
              }}
            >
              <Tooltip title="弹窗放大">
                <Button
                  size="small"
                  icon={<ExpandOutlined />}
                  onClick={() => setIsModalOpen(true)}
                  style={{ background: 'rgba(0,0,0,0.5)', color: '#fff', border: 'none' }}
                />
              </Tooltip>
            </div>
          </div>
        </Col>

        {/* Progress Bar */}
        <Col span={24}>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Row justify="space-between">
              <Text type="secondary">{formatTime(currentTime)}</Text>
              <Col>
                {isPreview && isHlsSource && bufferedEnd > 0 && (
                  <Text type="secondary" style={{ marginRight: 8, fontSize: 12 }}>
                    已缓冲 {formatTime(bufferedEnd)}
                  </Text>
                )}
                <Text type="secondary">{formatTime(duration)}</Text>
              </Col>
            </Row>
            <div>
              <Slider
                min={0}
                max={duration}
                step={0.1}
                value={currentTime}
                onChange={handleSeek}
                tooltip={{ formatter: (value) => formatTime(value || 0) }}
              />
            </div>
          </Space>
        </Col>

        {/* Playback Controls */}
        <Col span={24}>
          <Row justify="space-between" align="middle">
            <Col>
              <Space>
                <Tooltip title="后退 5 秒">
                  <Button
                    icon={<StepBackwardOutlined />}
                    onClick={() => handleSkip(-5)}
                    size="small"
                  />
                </Tooltip>

                <Button
                  type="primary"
                  icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                  onClick={togglePlay}
                  size="large"
                >
                  {isPlaying ? '暂停' : '播放'}
                </Button>

                <Tooltip title="前进 5 秒">
                  <Button
                    icon={<StepForwardOutlined />}
                    onClick={() => handleSkip(5)}
                    size="small"
                  />
                </Tooltip>

                <Tooltip title="重新开始">
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={handleRestart}
                    size="small"
                  />
                </Tooltip>

                <Text type="secondary" style={{ marginLeft: 16 }}>
                  {isPlaying ? '播放中' : '已暂停'}
                </Text>
              </Space>
            </Col>

            <Col>
              <Space size={4}>
                {[0.5, 1, 1.5, 2].map((rate) => (
                  <Button
                    key={rate}
                    size="small"
                    type={playbackRate === rate ? 'primary' : 'default'}
                    onClick={() => {
                      setPlaybackRate(rate);
                      if (videoRef.current) {
                        videoRef.current.playbackRate = rate;
                      }
                    }}
                  >
                    {rate}x
                  </Button>
                ))}
              </Space>
            </Col>
          </Row>
        </Col>

        {/* Class Filter */}
        <Col span={24}>
          <Card size="small" title="类别筛选" style={{ marginTop: 8 }}>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Space>
                <Button
                  size="small"
                  icon={showAllClasses ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                  onClick={toggleAllClasses}
                >
                  {showAllClasses ? '隐藏全部' : '显示全部'}
                </Button>
                <Text type="secondary">
                  已选择 {selectedClasses.size} / {allClasses.length} 个类别
                </Text>
              </Space>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {allClasses.map((className) => {
                  const isSelected = selectedClasses.has(className);
                  const color = classColors[className] || '#666666';
                  const textColor = isSelected ? getContrastTextColor(color) : 'var(--color-text-muted)';

                  return (
                    <Tag
                      key={className}
                      color={isSelected ? color : undefined}
                      style={{
                        cursor: 'pointer',
                        opacity: isSelected ? 1 : 0.5,
                        border: `2px solid ${isSelected ? color : 'var(--color-border-bright)'}`,
                        backgroundColor: isSelected ? color : 'var(--color-bg-elevated)',
                        color: textColor,
                      }}
                      onClick={() => toggleClass(className)}
                    >
                      <Checkbox checked={isSelected} style={{ marginRight: 4 }} />
                      {className}
                    </Tag>
                  );
                })}
              </div>
            </Space>
          </Card>
        </Col>

        {/* Export Video - hidden in preview mode */}
        {!isPreview && (
        <Col span={24}>
          <Card size="small" title="导出视频" style={{ marginTop: 8 }}>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Text type="secondary">
                导出带有选中类别检测框的视频（MP4 格式）
              </Text>
              {isExporting && (
                <Progress
                  percent={exportProgress}
                  status="active"
                  size="small"
                />
              )}
              {isExporting && (
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Text type="secondary">当前阶段：{exportStageText}</Text>
                  <Text type="secondary">
                    导出耗时：{formatDuration(exportElapsedSeconds)} ｜ 预计剩余：{formatDuration(exportEtaSeconds)}
                  </Text>
                </Space>
              )}
              <Space>
                <Button
                  type="primary"
                  icon={<ExportOutlined />}
                  onClick={handleExportVideo}
                  loading={isExporting}
                  disabled={selectedClasses.size === 0}
                >
                  {isExporting ? '导出中...' : '导出视频'}
                </Button>
                {isExporting && (
                  <Button danger onClick={handleCancelExport}>
                    取消导出
                  </Button>
                )}
              </Space>
            </Space>
          </Card>
        </Col>
        )}

        {/* Frame Info */}
        <Col span={24}>
          <Row gutter={16} align="middle">
            {isPreview && (
              <Col>
                <Tag color="green" style={{ margin: 0 }}>
                  <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#52c41a', marginRight: 6, animation: 'pulse 1.5s infinite' }} />
                  实时预览
                </Tag>
              </Col>
            )}
            <Col>
              <Text type="secondary">
                当前帧: {Math.floor(currentTime * result.fps)} / {isPreview ? '~' : ''}{result.total_frames}
              </Text>
            </Col>
            <Col>
              <Text type="secondary">
                当前检测: {getFilteredDetections().length} 个目标
              </Text>
            </Col>
          </Row>
        </Col>
      </Row>

      {/* Enlarged Modal */}
      <Modal
        title="视频预览"
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        footer={null}
        width="90vw"
        centered
        destroyOnClose
        styles={{ body: { padding: 0, background: '#000' } }}
      >
        <div
          style={{ position: 'relative', width: '100%', background: '#000' }}
        >
          <video
            ref={modalVideoRef}
            style={{ width: '100%', display: 'block' }}
            controls
            playsInline
            onTimeUpdate={() => {
              const mv = modalVideoRef.current;
              if (mv) setCurrentTime(mv.currentTime);
            }}
            onLoadedMetadata={() => {
              const mv = modalVideoRef.current;
              if (!mv) return;
              const aspect = mv.videoWidth / mv.videoHeight || 16 / 9;
              const w = Math.round(mv.clientWidth || mv.videoWidth || 1280);
              const h = Math.round(w / aspect);
              setModalCanvasSize({ width: w, height: h });
              drawModalOverlay();
            }}
          />
          <canvas
            ref={modalCanvasRef}
            width={modalCanvasSize.width}
            height={modalCanvasSize.height}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
            }}
          />
        </div>
      </Modal>
    </Card>
  );
};

export default VideoPlayer;
