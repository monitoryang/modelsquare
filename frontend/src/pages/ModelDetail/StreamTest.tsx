/**
 * Real-time Stream Test Component
 * Supports RTMP streaming with real-time inference visualization
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import mpegts from 'mpegts.js';
import {
  Card,
  Row,
  Col,
  Typography,
  Button,
  Space,
  Alert,
  Slider,
  Statistic,
  Select,
  Input,
  Spin,
  Tag,
  Descriptions,
  message,
} from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  CopyOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import { modelService } from '../../services';
import type { Model, StreamSession, StreamInferenceResult } from '../../services';

const { Text, Paragraph } = Typography;

interface StreamTestProps {
  model: Model;
}

type StreamType = 'rtmp' | 'webrtc' | 'hls';

const StreamTest: React.FC<StreamTestProps> = ({ model }) => {
  // Stream session state
  const [streamSession, setStreamSession] = useState<StreamSession | null>(null);
  const [streamType, setStreamType] = useState<StreamType>('rtmp');
  const [creating, setCreating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [stopping, setStopping] = useState(false);
  
  // Inference parameters
  const [confThreshold, setConfThreshold] = useState(0.25);
  const [iouThreshold, setIouThreshold] = useState(0.45);
  
  // Real-time stats
  const [latestResult, setLatestResult] = useState<StreamInferenceResult | null>(null);
  const [framesProcessed, setFramesProcessed] = useState(0);
  const [avgLatency, setAvgLatency] = useState(0);
  const [currentFps, setCurrentFps] = useState(0);
  
  // WebSocket connection
  const wsRef = useRef<WebSocket | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flvPlayerRef = useRef<mpegts.Player | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Video playback state
  const [videoLoading, setVideoLoading] = useState(true);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [videoPlaying, setVideoPlaying] = useState(false);
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      if (flvPlayerRef.current) {
        flvPlayerRef.current.destroy();
        flvPlayerRef.current = null;
      }
    };
  }, []);

  // Initialize FLV player when session is active
  useEffect(() => {
    if (streamSession?.status === 'active' && videoRef.current && mpegts.getFeatureList().mseLivePlayback) {
      // Reset states
      setVideoLoading(true);
      setVideoError(null);
      setVideoPlaying(false);
      
      // Destroy existing player
      if (flvPlayerRef.current) {
        flvPlayerRef.current.destroy();
      }

      console.log('Initializing MPEGTS player with URL:', streamSession.playback_url);

      // Convert playback URL to use nginx proxy for CORS support
      // Original: http://localhost:8090/live/{stream_key}.flv
      // Proxied: http://localhost:3010/live/{stream_key}.flv (through nginx proxy)
      let flvUrl = streamSession.playback_url;
      try {
        const urlObj = new URL(streamSession.playback_url);
        // Use current origin + path through nginx proxy
        flvUrl = window.location.origin + urlObj.pathname; // e.g., http://localhost:3010/live/xxx.flv
        console.log('Using proxied FLV URL:', flvUrl);
      } catch (e) {
        console.warn('Failed to parse playback URL, using original:', e);
      }

      // Create MPEGTS player with playback URL
      const flvPlayer = mpegts.createPlayer({
        type: 'flv',
        url: flvUrl,
        isLive: true,
      }, {
        enableWorker: false,  // Disable worker to avoid compatibility issues
        enableStashBuffer: false,
        stashInitialSize: 128,
        lazyLoad: false,
        liveBufferLatencyChasing: true,
        liveBufferLatencyMaxLatency: 1.5,
        liveBufferLatencyMinRemain: 0.5,
      });

      const video = videoRef.current;

      // Video event listeners
      video.onloadeddata = () => {
        console.log('Video data loaded');
        setVideoLoading(false);
      };
      
      video.onplaying = () => {
        console.log('Video is playing');
        setVideoPlaying(true);
        setVideoLoading(false);
      };
      
      video.onwaiting = () => {
        console.log('Video is waiting for data...');
        setVideoLoading(true);
      };
      
      video.onerror = (e) => {
        console.error('Video element error:', e);
        setVideoError('视频加载失败');
        setVideoLoading(false);
      };

      flvPlayer.attachMediaElement(video);
      flvPlayer.load();
      const playPromise = flvPlayer.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch((e: Error) => {
          console.log('Autoplay blocked:', e);
          // Try to play on user interaction
        });
      }

      flvPlayerRef.current = flvPlayer;

      // Handle MPEGTS player errors
      flvPlayer.on(mpegts.Events.ERROR, (type, detail) => {
        console.error('FLV Player error:', type, detail);
        if (type === mpegts.ErrorTypes.NETWORK_ERROR) {
          setVideoError('网络错误：无法连接到视频流。请确保正在推流到正确的地址。');
        } else if (type === mpegts.ErrorTypes.MEDIA_ERROR) {
          setVideoError('媒体错误：视频格式不支持');
        } else {
          setVideoError(`播放错误: ${detail}`);
        }
        setVideoLoading(false);
      });
      
      // Handle loading state changes
      flvPlayer.on(mpegts.Events.LOADING_COMPLETE, () => {
        console.log('FLV loading complete');
        setVideoLoading(false);
      });
    } else if (!mpegts.getFeatureList().mseLivePlayback) {
      setVideoError('您的浏览器不支持 FLV 播放');
    }

    return () => {
      if (flvPlayerRef.current) {
        flvPlayerRef.current.destroy();
        flvPlayerRef.current = null;
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
    
    setActivating(true);
    try {
      await modelService.activateStreamSession(
        streamSession.session_id,
        confThreshold,
        iouThreshold
      );
      
      // Update session status
      setStreamSession(prev => prev ? { ...prev, status: 'active' } : null);
      
      // Connect WebSocket for real-time results
      connectWebSocket();
      
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
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
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

  // Connect WebSocket for real-time results
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
            
            // Draw detection boxes on canvas
            drawDetections(data as StreamInferenceResult);
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
  }, [streamSession]);

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
          drawDetections(result);
        }
      } catch (error) {
        console.error('Polling error:', error);
      }
    }, 100); // Poll every 100ms
  }, [streamSession]);

  // Draw detections on canvas overlay
  const drawDetections = (result: StreamInferenceResult) => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Get video dimensions or use result image size
    let width = result.image_size.width;
    let height = result.image_size.height;
    
    // If video is playing, use its dimensions
    if (video && video.videoWidth > 0) {
      width = video.videoWidth;
      height = video.videoHeight;
    }
    
    // Update canvas size
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    
    // Clear previous drawings
    ctx.clearRect(0, 0, width, height);
    
    // Calculate scale factors for detection boxes
    const scaleX = width / result.image_size.width;
    const scaleY = height / result.image_size.height;
    
    const { boxes, scores, class_names } = result.detections;
    const classColors = result.class_colors || {};
    
    // Draw each detection
    boxes.forEach((box, index) => {
      const [x1, y1, x2, y2] = box;
      const score = scores[index];
      const className = class_names[index];
      const color = classColors[className] || '#FF6B6B';
      
      // Scale box coordinates
      const scaledX1 = x1 * scaleX;
      const scaledY1 = y1 * scaleY;
      const scaledX2 = x2 * scaleX;
      const scaledY2 = y2 * scaleY;
      
      // Draw bounding box
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.strokeRect(scaledX1, scaledY1, scaledX2 - scaledX1, scaledY2 - scaledY1);
      
      // Draw label background
      const label = `${className} ${(score * 100).toFixed(0)}%`;
      ctx.font = 'bold 14px Arial';
      const textWidth = ctx.measureText(label).width;
      const textHeight = 20;
      
      ctx.fillStyle = color;
      ctx.fillRect(scaledX1, scaledY1 - textHeight, textWidth + 8, textHeight);
      
      // Draw label text
      ctx.fillStyle = '#FFFFFF';
      ctx.fillText(label, scaledX1 + 4, scaledY1 - 5);
    });
  };

  // Copy stream URL to clipboard
  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url);
    message.success('已复制到剪贴板');
  };

  return (
    <div>
      {/* Configuration Section */}
      <Card size="small" style={{ marginBottom: 16 }}>
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
              onChange={setConfThreshold}
              disabled={streamSession?.status === 'active'}
            />
          </Col>
          <Col span={8}>
            <Text>IoU 阈值: {iouThreshold.toFixed(2)}</Text>
            <Slider
              min={0}
              max={1}
              step={0.05}
              value={iouThreshold}
              onChange={setIouThreshold}
              disabled={streamSession?.status === 'active'}
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
            <Descriptions.Item label="播放地址">
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
          
          <Alert
            type="info"
            message="推流说明"
            description={
              <div>
                <Paragraph style={{ marginBottom: 8 }}>
                  <strong>1. 推流地址示例：</strong>
                </Paragraph>
                <Paragraph style={{ marginBottom: 4, marginLeft: 16 }}>
                  • RTMP: <Text code copyable>rtmp://localhost:1945/live/{'<stream_key>'}</Text>
                </Paragraph>
                <Paragraph style={{ marginBottom: 12, marginLeft: 16 }}>
                  • 将 {'<stream_key>'} 替换为上方推流地址中的实际 key
                </Paragraph>
                
                <Paragraph style={{ marginBottom: 8 }}>
                  <strong>2. 播放地址示例：</strong>
                </Paragraph>
                <Paragraph style={{ marginBottom: 4, marginLeft: 16 }}>
                  • HLS: <Text code>http://localhost:8090/live/{'<stream_key>'}.m3u8</Text> (延迟较高)
                </Paragraph>
                <Paragraph style={{ marginBottom: 4, marginLeft: 16 }}>
                  • HTTP-FLV: <Text code>http://localhost:8090/live/{'<stream_key>'}.flv</Text> (低延迟)
                </Paragraph>
                <Paragraph style={{ marginBottom: 12, marginLeft: 16 }}>
                  • WebRTC: <Text code>webrtc://localhost:8090/live/{'<stream_key>'}</Text> (最低延迟)
                </Paragraph>
                
                <Paragraph style={{ marginBottom: 8 }}>
                  <strong>3. FFmpeg 推流命令：</strong>
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
            }
            style={{ marginTop: 16 }}
          />
        </Card>
      )}

      {/* Main Content: Video + Canvas Overlay */}
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
                  {/* Video element for FLV playback */}
                  <video
                    ref={videoRef}
                    style={{ 
                      width: '100%',
                      maxHeight: 480,
                      display: 'block',
                      background: '#000',
                    }}
                    autoPlay
                    muted
                    playsInline
                  />
                  
                  {/* Canvas overlay for detection boxes - positioned over video */}
                  <canvas
                    ref={canvasRef}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      pointerEvents: 'none',
                    }}
                  />
                  
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
                        <Text style={{ color: '#999', fontSize: 12 }}>检测框仍可独立显示（基于服务端推理）</Text>
                      </Space>
                    </div>
                  )}
                  
                  {/* Status indicator */}
                  <div style={{
                    position: 'absolute',
                    top: 8,
                    right: 8,
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
                  value={latestResult?.detections?.boxes?.length || 0}
                  suffix="个"
                />
              </Col>
            </Row>
          </Card>
          
          {/* Detection Results */}
          {latestResult && latestResult.detections.boxes.length > 0 && (
            <Card title="检测结果" size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                {(() => {
                  // Group by class
                  const countMap: Record<string, number> = {};
                  latestResult.detections.class_names.forEach(name => {
                    countMap[name] = (countMap[name] || 0) + 1;
                  });
                  
                  return Object.entries(countMap).map(([name, count]) => (
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
                  ));
                })()}
              </Space>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  );
};

export default StreamTest;
