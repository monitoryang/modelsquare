/**
 * Real-time Stream Test Component
 * Supports RTMP streaming with real-time inference visualization.
 * Detection boxes are burned into the video by DeepStream OSD on the GPU.
 * Browser plays the processed output via HLS from SRS.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Typography,
  Button,
  Space,
  Slider,
  Statistic,
  Select,
  Input,
  Spin,
  Tag,
  Descriptions,
  Tooltip,
  Collapse,
  message,
} from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  CopyOutlined,
  VideoCameraOutlined,
  ExpandOutlined,
} from '@ant-design/icons';
import Hls from 'hls.js';
import { modelService } from '../../services';
import api from '../../services/api';
import type { Model, StreamSession, StreamInferenceResult } from '../../services';

const { Text, Paragraph } = Typography;

interface StreamTestProps {
  model: Model;
}

type StreamType = 'rtmp' | 'webrtc' | 'hls';

const StreamTest: React.FC<StreamTestProps> = ({ model }) => {
  const isOwlModel = model.network_type === 'OWLv2';

  // Stream session state
  const [streamSession, setStreamSession] = useState<StreamSession | null>(null);
  const [streamType, setStreamType] = useState<StreamType>('rtmp');
  const [creating, setCreating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [stopping, setStopping] = useState(false);
  
  // Inference parameters
  const [confThreshold, setConfThreshold] = useState(isOwlModel ? 0.1 : 0.25);
  const [iouThreshold, setIouThreshold] = useState(isOwlModel ? 0.3 : 0.45);

  // OWL-specific: text prompts
  const [owlTextPrompts, setOwlTextPrompts] = useState('');
  const [owlVariant, setOwlVariant] = useState('owlv2-base-patch16');
  const [updatingPrompts, setUpdatingPrompts] = useState(false);
  
  // Real-time stats
  const [latestResult, setLatestResult] = useState<StreamInferenceResult | null>(null);
  const [framesProcessed, setFramesProcessed] = useState(0);
  const [avgLatency, setAvgLatency] = useState(0);
  const [currentFps, setCurrentFps] = useState(0);
  
  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const controlWsRef = useRef<WebSocket | null>(null);
  const thresholdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Video playback state
  const [videoLoading, setVideoLoading] = useState(true);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoPlaying, setVideoPlaying] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Track fullscreen state changes
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);
  
  // Cleanup on unmount - stop session on backend
  useEffect(() => {
    return () => {
      // Stop backend session when component unmounts
      if (streamSession?.session_id) {
        modelService.stopStreamSession(streamSession.session_id).catch(() => {});
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (controlWsRef.current) {
        controlWsRef.current.close();
        controlWsRef.current = null;
      }
      if (thresholdTimerRef.current) {
        clearTimeout(thresholdTimerRef.current);
        thresholdTimerRef.current = null;
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [streamSession?.session_id]);

  // Stop session when page is closed or refreshed
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (streamSession?.session_id) {
        // Use sendBeacon for reliable delivery during page unload
        const baseUrl = (api.defaults.baseURL || '').replace(/\/$/, '');
        const url = `${baseUrl}/stream/${streamSession.session_id}/beacon-stop`;
        navigator.sendBeacon(url);
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [streamSession?.session_id]);

  // Initialize HLS player when session is active
  useEffect(() => {
    if (!streamSession?.playback_url || streamSession.status !== 'active' || !videoRef.current) {
      return;
    }

    setVideoLoading(true);
    setVideoError(null);
    setVideoPlaying(false);

    // Convert playback URL to use nginx proxy (same-origin) for CORS
    let hlsUrl = streamSession.playback_url;
    try {
      const urlObj = new URL(streamSession.playback_url);
      hlsUrl = window.location.origin + urlObj.pathname;
    } catch (e) {
      console.warn('Failed to parse playback URL, using original:', e);
    }

    const video = videoRef.current;
    video.onplaying = () => {
      setVideoPlaying(true);
      setVideoLoading(false);
    };

    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let retryCount = 0;
    const MAX_RETRIES = 30;
    const RETRY_DELAY = 3000;
    let cancelled = false;

    const createHls = () => {
      if (cancelled) return;

      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }

      console.log(`Connecting HLS (attempt ${retryCount + 1}):`, hlsUrl);

      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: true,
          liveSyncDurationCount: 2,
          manifestLoadingTimeOut: 15000,
          manifestLoadingMaxRetry: 6,
          manifestLoadingRetryDelay: 2000,
          levelLoadingTimeOut: 15000,
          levelLoadingMaxRetry: 6,
        });
        hls.loadSource(hlsUrl);
        hls.attachMedia(video);

        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          retryCount = 0;
          video.play().catch(() => {});
        });

        hls.on(Hls.Events.ERROR, (_event, data) => {
          if (data.fatal) {
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                hls.destroy();
                hlsRef.current = null;
                retryCount++;
                if (retryCount < MAX_RETRIES && !cancelled) {
                  console.warn(`HLS network error, retry ${retryCount}/${MAX_RETRIES} in ${RETRY_DELAY}ms...`);
                  retryTimer = setTimeout(createHls, RETRY_DELAY);
                } else if (!cancelled) {
                  setVideoError('无法连接视频流，请检查推流状态');
                  setVideoLoading(false);
                }
                break;
              case Hls.ErrorTypes.MEDIA_ERROR:
                console.warn('HLS media error, recovering...');
                hls.recoverMediaError();
                break;
              default:
                setVideoError('HLS 播放错误，请检查推流状态');
                hls.destroy();
                hlsRef.current = null;
                break;
            }
          }
        });

        hlsRef.current = hls;
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = hlsUrl;
        video.addEventListener('loadedmetadata', () => {
          video.play().catch(() => {});
        });
      } else {
        setVideoError('当前浏览器不支持 HLS 播放');
      }
    };

    createHls();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      setVideoLoading(true);
      setVideoPlaying(false);
    };
  }, [streamSession?.status, streamSession?.playback_url]);

  // Create stream session
  const handleCreateSession = async () => {
    setCreating(true);
    try {
      const session = await modelService.createStreamSession(model.id, streamType);
      setStreamSession(session);
      message.success('推流会话创建成功');
    } catch (error) {
      console.error('Failed to create stream session:', error);
      message.error('创建推流会话失败');
    } finally {
      setCreating(false);
    }
  };

  // Activate inference
  const handleActivateInference = async () => {
    if (!streamSession) return;

    if (isOwlModel && !owlTextPrompts.trim()) {
      message.warning('请先输入检测目标（提示词）');
      return;
    }
    
    setActivating(true);
    try {
      await modelService.activateStreamSession(
        streamSession.session_id,
        confThreshold,
        iouThreshold,
        isOwlModel ? owlTextPrompts : undefined,
        isOwlModel ? owlVariant : undefined,
      );
      
      // Update session status
      setStreamSession(prev => prev ? { ...prev, status: 'active' } : null);
      
      // Connect WebSocket for real-time results
      connectWebSocket();
      
      // Connect control WebSocket for real-time parameter updates
      connectControlWebSocket();
      
      // Start polling for stats
      startPolling();
      
      message.success('推理已激活');
    } catch (error) {
      console.error('Failed to activate inference:', error);
      message.error('激活推理失败');
    } finally {
      setActivating(false);
    }
  };

  // Send threshold updates via control WebSocket (debounced)
  const sendThresholdUpdate = useCallback((conf: number, iou: number) => {
    if (thresholdTimerRef.current) {
      clearTimeout(thresholdTimerRef.current);
    }
    thresholdTimerRef.current = setTimeout(() => {
      if (controlWsRef.current?.readyState === WebSocket.OPEN) {
        controlWsRef.current.send(JSON.stringify({
          command: 'update_threshold',
          conf_threshold: conf,
          iou_threshold: iou,
        }));
      }
    }, 200);
  }, []);

  // Custom slider onChange handlers for real-time updates
  const handleConfThresholdChange = useCallback((value: number) => {
    setConfThreshold(value);
    if (streamSession?.status === 'active') {
      sendThresholdUpdate(value, iouThreshold);
    }
  }, [streamSession, iouThreshold, sendThresholdUpdate]);

  const handleIouThresholdChange = useCallback((value: number) => {
    setIouThreshold(value);
    if (streamSession?.status === 'active') {
      sendThresholdUpdate(confThreshold, value);
    }
  }, [streamSession, confThreshold, sendThresholdUpdate]);

  // Connect control WebSocket for real-time parameter updates
  const connectControlWebSocket = useCallback(() => {
    if (!streamSession) return;
    try {
      const ws = modelService.createStreamControlWebSocket(streamSession.session_id);
      ws.onopen = () => {
        console.log('Control WebSocket connected');
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'threshold_updated') {
            console.log('Threshold updated:', data.conf_threshold, data.iou_threshold);
          } else if (data.type === 'prompts_updated') {
            message.success('提示词已更新，将在下一帧生效');
            setUpdatingPrompts(false);
          } else if (data.type === 'error') {
            message.error(data.message || '参数更新失败');
            setUpdatingPrompts(false);
          }
        } catch (e) {
          console.error('Error parsing control message:', e);
        }
      };
      ws.onerror = (error) => {
        console.error('Control WebSocket error:', error);
      };
      controlWsRef.current = ws;
    } catch (error) {
      console.error('Failed to connect control WebSocket:', error);
    }
  }, [streamSession]);

  // Update OWL text prompts for active session (prefer WebSocket, fallback to REST)
  const handleUpdatePrompts = async () => {
    if (!streamSession?.session_id) return;
    if (!owlTextPrompts.trim()) {
      message.warning('提示词不能为空');
      return;
    }
    if (controlWsRef.current?.readyState === WebSocket.OPEN) {
      setUpdatingPrompts(true);
      controlWsRef.current.send(JSON.stringify({
        command: 'update_prompts',
        text_prompts: owlTextPrompts,
        owl_variant: owlVariant,
      }));
      // Success/error message handled in WebSocket onmessage handler
    } else {
      // Fallback to REST if WebSocket not connected
      setUpdatingPrompts(true);
      try {
        await modelService.updateStreamTextPrompts(
          streamSession.session_id,
          owlTextPrompts,
          owlVariant,
        );
        message.success('提示词已更新，将在下一帧生效');
      } catch (error) {
        console.error('Failed to update prompts:', error);
        message.error('更新提示词失败');
      } finally {
        setUpdatingPrompts(false);
      }
    }
  };

  // Stop session
  const handleStopSession = async () => {
    if (!streamSession?.session_id) {
      // No valid session, just clean up local state
      setStreamSession(null);
      setLatestResult(null);
      setFramesProcessed(0);
      setAvgLatency(0);
      setCurrentFps(0);
      return;
    }
    
    setStopping(true);
    try {
      await modelService.stopStreamSession(streamSession.session_id);
      
      // Cleanup
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (controlWsRef.current) {
        controlWsRef.current.close();
        controlWsRef.current = null;
      }
      if (thresholdTimerRef.current) {
        clearTimeout(thresholdTimerRef.current);
        thresholdTimerRef.current = null;
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      
      setStreamSession(null);
      setLatestResult(null);
      setFramesProcessed(0);
      setAvgLatency(0);
      setCurrentFps(0);
      
      message.success('推流会话已停止');
    } catch (error) {
      console.error('Failed to stop session:', error);
      message.error('停止会话失败');
    } finally {
      setStopping(false);
    }
  };

  // Connect WebSocket for real-time results (stats only, OSD is burned into video)
  // Polling fallback for stats
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }
    
    pollIntervalRef.current = setInterval(async () => {
      if (!streamSession) return;
      
      try {
        const result = await modelService.getStreamLatestResult(streamSession.session_id);
        if (result) {
          setLatestResult(result);
          setFramesProcessed(result.frames_processed || 0);
          setAvgLatency(result.avg_latency_ms || 0);
          if (result.avg_latency_ms > 0) {
            setCurrentFps(1000 / result.avg_latency_ms);
          }
        }
      } catch (error) {
        console.error('Polling error:', error);
      }
    }, 100); // Poll every 100ms
  }, [streamSession]);

  // Connect WebSocket for real-time results (stats only, OSD is burned into video)
  const connectWebSocket = useCallback(() => {
    if (!streamSession) return;
    
    try {
      const ws = modelService.createStreamWebSocket(streamSession.session_id);
      
      ws.onopen = () => {
        console.log('WebSocket connected');
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'inference_result') {
            setLatestResult(data as StreamInferenceResult);
            setFramesProcessed(data.frames_processed || 0);
            setAvgLatency(data.avg_latency_ms || 0);
            if (data.avg_latency_ms > 0) {
              setCurrentFps(1000 / data.avg_latency_ms);
            }
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
      
      ws.onclose = () => {
        console.log('WebSocket disconnected');
      };
      
      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
      // Fallback to polling
      startPolling();
    }
  }, [streamSession, startPolling]);

  // Copy stream URL to clipboard
  const handleCopyUrl = (url: string) => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url)
        .then(() => message.success('已复制到剪贴板'))
        .catch(() => fallbackCopy(url));
    } else {
      fallbackCopy(url);
    }
  };

  // Fallback copy for non-HTTPS environments
  const fallbackCopy = (text: string) => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.top = '0';
    textarea.style.left = '0';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand('copy');
      message.success('已复制到剪贴板');
    } catch {
      message.error('复制失败，请手动复制');
    }
    document.body.removeChild(textarea);
  };

  // Fullscreen: use browser Fullscreen API on the video container
  const handleFullscreen = () => {
    const container = containerRef.current;
    if (!container) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      container.requestFullscreen();
    }
  };

  return (
    <div>
      {/* Configuration Section */}
      <Card size="small" style={{ marginBottom: 16 }}>
        {isOwlModel && (
          <div style={{ marginBottom: 16 }}>
            <Text strong>检测目标（提示词，用英文逗号分隔）：</Text>
            <Input.TextArea
              rows={2}
              placeholder="例如: person, car, dog, cat"
              value={owlTextPrompts}
              onChange={(e) => setOwlTextPrompts(e.target.value)}
              style={{ marginTop: 4 }}
            />
            <Row gutter={16} style={{ marginTop: 8 }}>
              <Col span={12}>
                <Text>模型变体：</Text>
                <Select
                  style={{ width: '100%', marginTop: 4 }}
                  value={owlVariant}
                  onChange={setOwlVariant}
                  disabled={streamSession?.status === 'active'}
                >
                  <Select.Option value="owlv2-base-patch16">owlv2-base-patch16 (960x960)</Select.Option>
                  <Select.Option value="owlv2-large-patch14">owlv2-large-patch14 (1008x1008)</Select.Option>
                </Select>
              </Col>
              {streamSession?.status === 'active' && (
                <Col span={12} style={{ display: 'flex', alignItems: 'flex-end' }}>
                  <Button
                    type="primary"
                    onClick={handleUpdatePrompts}
                    loading={updatingPrompts}
                    style={{ marginTop: 24 }}
                  >
                    实时更新提示词
                  </Button>
                </Col>
              )}
            </Row>
          </div>
        )}
        <Row gutter={24} align="middle">
          <Col span={6}>
            <Text>推流协议:</Text>
            <Select
              value={streamType}
              onChange={setStreamType}
              style={{ width: '100%', marginTop: 4 }}
              disabled={!!streamSession}
            >
              <Select.Option value="rtmp">RTMP</Select.Option>
              <Select.Option value="hls">HLS</Select.Option>
              <Select.Option value="webrtc">WebRTC</Select.Option>
            </Select>
          </Col>
          <Col span={8}>
            <Text>置信度阈值: {confThreshold.toFixed(2)}</Text>
            <Slider
              min={0}
              max={1}
              step={0.05}
              value={confThreshold}
              onChange={handleConfThresholdChange}
            />
          </Col>
          <Col span={8}>
            <Text>IoU 阈值: {iouThreshold.toFixed(2)}</Text>
            <Slider
              min={0}
              max={1}
              step={0.05}
              value={iouThreshold}
              onChange={handleIouThresholdChange}
            />
          </Col>
        </Row>
      </Card>

      {/* Session Control */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          {!streamSession ? (
            <Button
              type="primary"
              icon={<VideoCameraOutlined />}
              onClick={handleCreateSession}
              loading={creating}
            >
              创建推流会话
            </Button>
          ) : (
            <>
              <Tag color={streamSession.status === 'active' ? 'green' : 'orange'}>
                {streamSession.status === 'active' ? '推理中' : '等待推流'}
              </Tag>
              
              {streamSession.status === 'pending' && (
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={handleActivateInference}
                  loading={activating}
                >
                  开始推理
                </Button>
              )}
              
              <Button
                danger
                icon={<PauseCircleOutlined />}
                onClick={handleStopSession}
                loading={stopping}
              >
                停止会话
              </Button>
            </>
          )}
        </Space>
      </Card>

      {/* Stream URLs */}
      {streamSession && (
        <Card 
          size="small" 
          title="推流地址" 
          style={{ marginBottom: 16 }}
        >
          <Descriptions column={1} size="small">
            <Descriptions.Item label="推流地址 (OBS/FFmpeg)">
              <Space>
                <Input 
                  value={streamSession.stream_url} 
                  readOnly 
                  style={{ width: 400 }}
                />
                <Button 
                  icon={<CopyOutlined />} 
                  onClick={() => handleCopyUrl(streamSession.stream_url)}
                >
                  复制
                </Button>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="播放地址 (HLS)">
              <Space>
                <Input 
                  value={streamSession.playback_url} 
                  readOnly 
                  style={{ width: 400 }}
                />
                <Button 
                  icon={<CopyOutlined />} 
                  onClick={() => handleCopyUrl(streamSession.playback_url)}
                >
                  复制
                </Button>
              </Space>
            </Descriptions.Item>
          </Descriptions>
          
          <Collapse
            size="small"
            style={{ marginTop: 16 }}
            items={[{
              key: 'stream-instructions',
              label: '推流说明',
              children: (
                <div>
                  <Paragraph style={{ marginBottom: 8 }}>
                    <strong>1. 推流方式：</strong>
                  </Paragraph>
                  <Paragraph style={{ marginBottom: 4, marginLeft: 16 }}>
                    • 使用 OBS 或 FFmpeg 将视频推送到上方的 RTMP 推流地址
                  </Paragraph>
                  <Paragraph style={{ marginBottom: 12, marginLeft: 16 }}>
                    • DeepStream 自动拉取视频、GPU 推理、烧录检测框后输出
                  </Paragraph>
                  
                  <Paragraph style={{ marginBottom: 8 }}>
                    <strong>2. 播放方式：</strong>
                  </Paragraph>
                  <Paragraph style={{ marginBottom: 4, marginLeft: 16 }}>
                    • 浏览器通过 HLS 自动播放处理后的视频（含检测框）
                  </Paragraph>
                  <Paragraph style={{ marginBottom: 12, marginLeft: 16 }}>
                    • 检测框由 DeepStream OSD 在 GPU 上直接烧录到画面中
                  </Paragraph>
                  
                  <Paragraph style={{ marginBottom: 8 }}>
                    <strong>3. FFmpeg 推流命令示例：</strong>
                  </Paragraph>
                  <Paragraph style={{ marginBottom: 4, marginLeft: 16 }}>
                    • 推送视频文件: <Text code>ffmpeg -re -i input.mp4 -c:v libx264 -f flv {streamSession.stream_url}</Text>
                  </Paragraph>
                  <Paragraph style={{ marginBottom: 12, marginLeft: 16 }}>
                    • 推送摄像头: <Text code>ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -f flv {streamSession.stream_url}</Text>
                  </Paragraph>
                  
                  <Paragraph style={{ marginBottom: 0 }}>
                    <strong>4.</strong> 推流开始后，点击"开始推理"按钮激活实时检测
                  </Paragraph>
                </div>
              ),
            }]}
          />
        </Card>
      )}

      {/* Main Content: Video Preview + Stats */}
      <Row gutter={16}>
        <Col span={16}>
          <Card 
            title="实时推理预览" 
            size="small"
            extra={
              streamSession?.status === 'active' && (
                <Tag color="processing">
                  <Spin size="small" /> 推理中
                </Tag>
              )
            }
          >
            <div 
              ref={containerRef}
              style={{ 
                position: 'relative', 
                width: '100%', 
                minHeight: 400,
                background: '#1a1a1a',
                borderRadius: 4,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {!streamSession ? (
                <Text type="secondary">创建推流会话后开始</Text>
              ) : streamSession.status !== 'active' ? (
                <Text type="secondary">等待推流并激活推理...</Text>
              ) : (
                <div style={{ position: 'relative', width: '100%', height: '100%' }}>
                  {/* Video element for HLS playback (OSD already burned in) */}
                  <video
                    ref={videoRef}
                    style={{ 
                      width: '100%',
                      maxHeight: isFullscreen ? undefined : 480,
                      display: 'block',
                      background: '#000',
                    }}
                    controls
                    autoPlay
                    muted
                    playsInline
                  />

                  {/* Fullscreen button */}
                  <Tooltip title="全屏">
                    <Button
                      size="small"
                      icon={<ExpandOutlined />}
                      onClick={handleFullscreen}
                      style={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        zIndex: 10,
                        background: 'rgba(0,0,0,0.5)',
                        color: '#fff',
                        border: 'none',
                      }}
                    />
                  </Tooltip>
                  
                  {/* Video loading overlay */}
                  {videoLoading && !videoError && (
                    <div style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: 'rgba(0,0,0,0.7)',
                    }}>
                      <Space direction="vertical" align="center">
                        <Spin size="large" />
                        <Text style={{ color: '#fff' }}>正在连接视频流...</Text>
                        <Text style={{ color: '#999', fontSize: 12 }}>请确保已开始向推流地址推送视频</Text>
                      </Space>
                    </div>
                  )}
                  
                  {/* Video error overlay */}
                  {videoError && (
                    <div style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: 'rgba(0,0,0,0.8)',
                    }}>
                      <Space direction="vertical" align="center">
                        <Text style={{ color: '#ff4d4f' }}>{videoError}</Text>
                      </Space>
                    </div>
                  )}
                  
                  {/* Status indicator */}
                  <div style={{
                    position: 'absolute',
                    top: 8,
                    left: 8,
                    display: 'flex',
                    gap: 8,
                  }}>
                    <Tag color={videoPlaying ? 'green' : 'orange'}>
                      {videoPlaying ? '视频播放中' : '视频等待中'}
                    </Tag>
                    {latestResult && (
                      <Tag color="blue">推理中</Tag>
                    )}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </Col>
        
        <Col span={8}>
          {/* Real-time Statistics */}
          <Card title="实时统计" size="small" style={{ marginBottom: 16 }}>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic
                  title="处理帧数"
                  value={framesProcessed}
                  suffix="帧"
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="平均延迟"
                  value={avgLatency.toFixed(1)}
                  suffix="ms"
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="推理帧率"
                  value={currentFps.toFixed(1)}
                  suffix="FPS"
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="检测数量"
                  value={latestResult?.detection_count || 0}
                  suffix="个"
                />
              </Col>
            </Row>
          </Card>
          
          {/* Detection Results */}
          {latestResult && latestResult.detection_count > 0 && (
            <Card title="检测结果" size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                {Object.entries(latestResult.class_counts).map(([name, count]) => (
                  <div key={name} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Space>
                      <div style={{
                        width: 12,
                        height: 12,
                        borderRadius: 2,
                        backgroundColor: latestResult.class_colors[name] || '#666',
                      }} />
                      <Text>{name}</Text>
                    </Space>
                    <Tag color="blue">{count}</Tag>
                  </div>
                ))}
              </Space>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  );
};

export default StreamTest;
