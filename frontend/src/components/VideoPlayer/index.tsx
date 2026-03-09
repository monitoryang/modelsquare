/**
 * Video Player with Detection Overlay and Class Filter
 * Uses original video and renders detection boxes on frontend
 * Supports playback control, progress bar, and category filtering
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
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
} from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
} from '@ant-design/icons';
import type { VideoTaskResult, FrameDetectionResult } from '../../services';

const { Text } = Typography;

interface VideoPlayerProps {
  videoFile?: File;
  videoBlob?: Blob;
  result: VideoTaskResult;
  classColors: Record<string, string>;
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
  // Convert hex to RGB
  const hex = bgColor.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16) || 0;
  const g = parseInt(hex.substring(2, 4), 16) || 0;
  const b = parseInt(hex.substring(4, 6), 16) || 0;

  // Calculate relative luminance
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

  // Return black for light backgrounds, white for dark backgrounds
  return luminance > 0.5 ? '#000000' : '#ffffff';
};

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  videoFile,
  videoBlob,
  result,
  classColors,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(result.duration_seconds || 0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [videoUrl, setVideoUrl] = useState<string>('');

  // Class filter state
  const allClasses = React.useMemo(() => {
    const classes = new Set<string>();
    result.frame_results.forEach((frame) => {
      frame.class_names.forEach((name) => classes.add(name));
    });
    return Array.from(classes).sort();
  }, [result.frame_results]);

  const [selectedClasses, setSelectedClasses] = useState<Set<string>>(
    new Set(allClasses)
  );
  const [showAllClasses, setShowAllClasses] = useState(true);

  // Canvas dimensions
  const [canvasSize, setCanvasSize] = useState({ width: 640, height: 480 });

  // Create object URL for video file or blob
  useEffect(() => {
    const source = videoFile || videoBlob;
    if (!source) return;
    const url = URL.createObjectURL(source);
    setVideoUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [videoFile, videoBlob]);

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

  // Draw detection overlay on canvas
  const drawOverlay = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Get filtered detections
    const detections = getFilteredDetections();
    if (detections.length === 0) return;

    // Calculate scale factors
    const scaleX = canvas.width / (video.videoWidth || canvas.width);
    const scaleY = canvas.height / (video.videoHeight || canvas.height);

    // Draw detection boxes
    detections.forEach((det) => {
      const x = det.x1 * scaleX;
      const y = det.y1 * scaleY;
      const w = (det.x2 - det.x1) * scaleX;
      const h = (det.y2 - det.y1) * scaleY;

      // Draw box
      ctx.strokeStyle = det.color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);

      // Draw label background
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

      // Draw label text with contrast color
      ctx.fillStyle = getContrastTextColor(det.color);
      ctx.fillText(label, x + padding, y - padding - 2);
    });

    // Draw detection count
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    ctx.fillRect(10, 10, 120, 30);
    ctx.fillStyle = '#ffffff';
    ctx.font = '14px Arial';
    ctx.fillText(`检测: ${detections.length} 个`, 20, 30);
  }, [getFilteredDetections]);

  // Update canvas size when video metadata loads
  const handleLoadedMetadata = () => {
    const video = videoRef.current;
    if (video) {
      setDuration(video.duration || result.duration_seconds);
      updateCanvasSize();
    }
  };

  // Update canvas size based on container
  const updateCanvasSize = () => {
    const container = containerRef.current;
    const video = videoRef.current;
    if (!container || !video) return;

    const containerWidth = container.clientWidth;
    const videoAspect = video.videoWidth / video.videoHeight || 16 / 9;

    let width = containerWidth;
    let height = width / videoAspect;

    // Limit max height
    const maxHeight = window.innerHeight * 0.6;
    if (height > maxHeight) {
      height = maxHeight;
      width = height * videoAspect;
    }

    setCanvasSize({ width: Math.round(width), height: Math.round(height) });
  };

  // Handle window resize
  useEffect(() => {
    const handleResize = () => {
      updateCanvasSize();
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Redraw overlay when time or selections change
  useEffect(() => {
    drawOverlay();
  }, [currentTime, selectedClasses, drawOverlay]);

  // Video event handlers
  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (video) {
      setCurrentTime(video.currentTime);
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
      video.play();
    }
  };

  const handleSeek = (value: number) => {
    const video = videoRef.current;
    if (video) {
      video.currentTime = value;
      setCurrentTime(value);
    }
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
      video.play();
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

  // Format time display
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

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
              background: '#000',
              borderRadius: 4,
              overflow: 'hidden',
            }}
          >
            <video
              ref={videoRef}
              src={videoUrl}
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
                top: 0,
                left: '50%',
                transform: 'translateX(-50%)',
                pointerEvents: 'none',
              }}
            />
          </div>
        </Col>

        {/* Progress Bar - Single Slider only */}
        <Col span={24}>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Row justify="space-between">
              <Text type="secondary">{formatTime(currentTime)}</Text>
              <Text type="secondary">{formatTime(duration)}</Text>
            </Row>
            <Slider
              min={0}
              max={duration}
              step={0.1}
              value={currentTime}
              onChange={handleSeek}
              tooltip={{ formatter: (value) => formatTime(value || 0) }}
            />
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
                  const textColor = isSelected ? getContrastTextColor(color) : '#666';

                  return (
                    <Tag
                      key={className}
                      color={isSelected ? color : undefined}
                      style={{
                        cursor: 'pointer',
                        opacity: isSelected ? 1 : 0.5,
                        border: `2px solid ${isSelected ? color : '#d9d9d9'}`,
                        backgroundColor: isSelected ? color : '#f5f5f5',
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

        {/* Frame Info */}
        <Col span={24}>
          <Row gutter={16}>
            <Col>
              <Text type="secondary">
                当前帧: {Math.floor(currentTime * result.fps)} / {result.total_frames}
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
    </Card>
  );
};

export default VideoPlayer;
