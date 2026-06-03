# LanCaster 架构与设计文档

## 1. 项目概述

LanCaster（LAN + Caster）是一款基于 DLNA/UPnP 协议的全功能视频投屏工具。它允许用户在同一 WiFi 局域网下，将 Windows PC 上的视频文件、在线视频 URL、甚至桌面画面投送到智能电视上播放。

### 1.1 名称由来

- **LAN** — Local Area Network（局域网）
- **Caster** — 投屏器
- **Lancaster** — 英文实词（兰开斯特），好记好拼

### 1.2 核心场景

| 场景 | 说明 | 状态 |
|------|------|------|
| 本地文件投屏 | 选择 PC 上的视频文件推送到电视播放 | Phase 1 已实现 |
| 在线 URL 投屏 | 将网络视频 URL 直接投送到电视 | Phase 2 |
| 媒体库共享 | PC 作为 DLNA Media Server，电视主动浏览 | Phase 3 |
| 桌面镜像 | PC 桌面实时画面串流到电视 | Phase 3 |

---

## 2. 技术架构

### 2.1 分层设计

```
┌─────────────────────────────────────────────────┐
│           Presentation Layer                    │
│  ┌───────────────┐  ┌────────────────────────┐  │
│  │  lancaster-cli│  │  GUI (未来)            │  │
│  │  (Click+Rich) │  │  PyQt6 / Tauri / Web   │  │
│  └───────┬───────┘  └──────────┬─────────────┘  │
├──────────┼─────────────────────┼────────────────┤
│          │    lancaster-core   │                 │
│  ┌───────▼─────────────────────▼──────────────┐ │
│  │  DeviceDiscovery  │  MediaController       │ │
│  │  MediaServer      │  Transcoder            │ │
│  │  DesktopMirror    │  URLProxy              │ │
│  │  HTTPFileServer   │  DIDLBuilder           │ │
│  └───────────────────┴────────────────────────┘ │
├─────────────────────────────────────────────────┤
│           External Dependencies                 │
│  async_upnp_client  │  aiohttp  │  FFmpeg      │
└─────────────────────────────────────────────────┘
```

### 2.2 设计原则

1. **核心库与 UI 分离** — `lancaster/` 是纯 Python 库，不依赖任何 GUI 框架。CLI、Web UI、桌面 GUI 都是独立的消费者。
2. **异步优先** — 所有 I/O 操作基于 `asyncio`，与 `async_upnp_client` 的事件循环统一。
3. **渐进式功能** — 每个模块独立可用，用户可以只用设备发现，也可以只用文件服务器。
4. **容错优先** — 网络设备不可靠，所有设备交互都有超时和异常处理。

---

## 3. DLNA/UPnP 协议基础

### 3.1 三角色模型

LanCaster 的 DLNA 实现基于 UPnP AV 架构的三角色模型：

```
      ┌──────────────────────┐
      │  DMC (Controller)    │
      │  LanCaster 软件      │
      └──────┬───────┬───────┘
             │       │
    SOAP     │       │  SOAP
  控制命令   │       │  浏览请求
             │       │
      ┌──────▼──┐ ┌──▼─────────┐
      │  DMR    │ │  DMS       │
      │  电视   │ │  PC/NAS    │
      │(播放端) │ │(媒体源)    │
      └────┬────┘ └──────┬─────┘
           │              │
           │   HTTP GET   │
           │◄─────────────┘
           │  (拉取媒体流)
```

| 角色 | UPnP 设备类型 | LanCaster 中的体现 |
|------|--------------|-------------------|
| DMS (Digital Media Server) | MediaServer | `HTTPFileServer` — 提供本地文件的 HTTP 访问 |
| DMR (Digital Media Renderer) | MediaRenderer | 电视 — 接收并播放媒体 |
| DMC (Digital Media Controller) | Control Point | `MediaController` — 发现设备、控制播放 |

### 3.2 协议栈

```
┌─────────────────────────────────┐
│  DLNA Guidelines                │  ← 格式/Profile 规范
├─────────────────────────────────┤
│  UPnP AV                       │
│  ├─ ContentDirectory (Browse)   │  ← 媒体库浏览
│  ├─ AVTransport (Play/Pause...) │  ← 播放控制
│  ├─ RenderingControl (Volume)   │  ← 音量/亮度
│  └─ ConnectionManager           │  ← 格式协商
├─────────────────────────────────┤
│  UPnP Device Architecture      │
│  ├─ SSDP (发现)                 │  ← UDP 239.255.255.250:1900
│  ├─ SOAP (控制)                 │  ← HTTP POST + XML
│  ├─ GENA (事件)                 │  ← HTTP SUBSCRIBE/NOTIFY
│  └─ Device Description (XML)    │  ← HTTP GET
├─────────────────────────────────┤
│  HTTP / TCP / UDP / IP          │
└─────────────────────────────────┘
```

### 3.3 投屏工作流

```
时间线 →

PC (LanCaster)                              电视 (DMR)
     │                                          │
     │── SSDP M-SEARCH (UDP 多播) ──────────────>│
     │<── SSDP Response (Location URL) ─────────│
     │                                          │
     │── HTTP GET description.xml ──────────────>│
     │<── Device Description XML ───────────────│
     │                                          │
     │  [启动本地 HTTP 服务器 :8200]              │
     │                                          │
     │── SOAP SetAVTransportURI ────────────────>│
     │   (告诉电视：播放 http://pc:8200/file/xx) │
     │<── 200 OK ──────────────────────────────│
     │                                          │
     │── SOAP Play ─────────────────────────────>│
     │<── 200 OK ──────────────────────────────│
     │                                          │
     │                    │<── HTTP GET /file/xx │
     │                    │── 206 Partial ──────>│
     │                    │    (视频数据)         │
     │                    │                      │
     │── SOAP GetPositionInfo ──────────────────>│
     │<── 当前播放位置 ────────────────────────│
```

---

## 4. 模块详细设计

### 4.1 DeviceDiscovery (`lancaster/discovery.py`)

**职责**：在局域网中发现 DLNA 设备（电视、音箱、NAS 等）。

**实现**：
- 使用 `async_upnp_client.ssdp_listener.SsdpListener` 监听 SSDP 多播
- 发送 M-SEARCH 请求后等待指定超时时间
- 收到响应后通过 `UpnpFactory` 获取设备描述 XML
- 根据设备/服务类型分类为 Renderer 或 Server
- 内部缓存已发现设备，支持按名称/IP 查找

**API**：

```python
class DeviceDiscovery:
    async def scan(timeout=5.0) -> list[DLNADevice]     # 一次性扫描
    async def watch(callback) -> SsdpListener            # 持续监听
    async def stop_watch() -> None                       # 停止监听
    def find_by_name(name) -> DLNADevice | None          # 按名称模糊匹配
    def find_by_ip(ip) -> DLNADevice | None              # 按 IP 精确匹配
    @property renderers -> list[DLNADevice]               # 所有渲染器
    @property servers -> list[DLNADevice]                 # 所有服务器
```

**边界条件**：
- 多网卡环境：`SsdpListener` 自动绑定，或可指定 `source` IP
- 设备描述获取失败时静默跳过（网络不稳定场景）
- 相同 UDN 的设备不会重复注册

### 4.2 HTTPFileServer (`lancaster/http_server.py`)

**职责**：提供本地文件和实时流的 HTTP 访问，供电视拉取。

**实现**：
- 基于 `aiohttp.web` 异步 HTTP 服务器
- 两类端点：`/file/{id}` 静态文件、`/stream/{id}` 实时流
- 每个文件/流注册后返回唯一 URL

**HTTP Range 支持**（电视 seek 必需）：
- 解析 `Range: bytes=start-end` 请求头
- 有 Range 时返回 `206 Partial Content` + `Content-Range`
- 无 Range 时返回 `200 OK` + 完整文件
- 256KB 分块传输，大文件友好

**DLNA 专属响应头**：
- `TransferMode.DLNA.ORG: Streaming` — 表明传输模式
- `ContentFeatures.DLNA.ORG: DLNA.ORG_OP=01;DLNA.ORG_FLAGS=...` — 支持 seek
- `Accept-Ranges: bytes` — 声明支持 Range 请求

**安全考虑**：
- 文件通过随机 UUID 映射，外部无法猜测路径
- 仅在局域网 IP 上监听

### 4.3 MediaController (`lancaster/controller.py`)

**职责**：封装对电视的所有播放控制操作。

**实现**：
- 通过 `UpnpFactory` 创建 `UpnpDevice`，再包装为 `DmrDevice`
- `DmrDevice` 提供 AVTransport 和 RenderingControl 的高层 API
- 缓存已创建的 `DmrDevice` 实例，避免重复建连

**支持的操作**：

| 操作 | UPnP Action | 方法 |
|------|------------|------|
| 播放 URL | SetAVTransportURI + Play | `play_url()` |
| 播放本地文件 | 启动 HTTP 服务 + SetURI + Play | `play_file()` |
| 暂停 | AVT:Pause | `pause()` |
| 继续 | AVT:Play | `resume()` |
| 停止 | AVT:Stop | `stop()` |
| 跳转 | AVT:Seek (ABS_TIME) | `seek()` |
| 设置音量 | RC:SetVolume | `set_volume()` |
| 获取音量 | RC:GetVolume | `get_volume()` |
| 获取状态 | AVT:GetTransportInfo + GetPositionInfo | `get_position()` |

**自动字幕发现**：
- `play_file()` 自动查找同名 `.srt` 文件
- 字幕通过 HTTP 服务器提供，在 DIDL-Lite 元数据中通过 `sec:CaptionInfoEx` 引用

### 4.4 DIDLBuilder (`lancaster/didl.py`)

**职责**：构建 UPnP 标准的 DIDL-Lite XML 元数据。

DIDL-Lite（Digital Item Declaration Language - Lite）是 UPnP 用于描述媒体元数据的 XML 格式。电视需要这些元数据来正确显示媒体标题、时长、格式等信息。

**示例输出**：

```xml
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
           xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
           xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
           xmlns:sec="http://www.sec.co.kr/">
  <item id="0" parentID="-1" restricted="1">
    <dc:title>My Movie</dc:title>
    <upnp:class>object.item.videoItem</upnp:class>
    <res protocolInfo="http-get:*:video/mp4:*"
         duration="01:30:00">
      http://192.168.1.5:8200/file/abc123
    </res>
    <sec:CaptionInfoEx sec:type="srt">
      http://192.168.1.5:8200/file/def456
    </sec:CaptionInfoEx>
  </item>
</DIDL-Lite>
```

### 4.5 Transcoder (`lancaster/transcoder.py`) — Phase 2

**职责**：通过 FFmpeg 检测媒体格式并按需转码，解决电视不支持的编解码器问题。

**设计决策**：
- 使用 `subprocess` 调用 FFmpeg CLI，而非 FFI 绑定（如 ffmpeg-python），原因：
  - 进程隔离更安全，FFmpeg 崩溃不影响主进程
  - 无需编译 C 扩展，安装更简单
  - FFmpeg CLI 功能最完整，文档最丰富

**API**：

```python
class Transcoder:
    @staticmethod
    async def probe(filepath: Path) -> MediaInfo
        """用 ffprobe 提取媒体元数据（编码、分辨率、时长、字幕轨等）。"""

    @staticmethod
    def needs_transcode(media_info: MediaInfo, safe_codecs=None) -> bool
        """判断是否需要转码。默认安全集: H.264+AAC+MP4。"""

    async def transcode_to_file(
        self, input_path: Path, output_path: Path, **opts
    ) -> Path
        """离线转码：将文件转为兼容格式并写入新文件。"""

    async def transcode_stream(
        self, input_path: Path, **opts
    ) -> AsyncIterator[bytes]
        """实时流式转码：输出 MPEG-TS 管道流，配合 HTTPFileServer 使用。"""

    @staticmethod
    async def detect_hw_accel() -> list[str]
        """检测可用的硬件加速器（nvenc/qsv/amf）。"""
```

**转码策略**：

```
输入文件
  │
  ├─ ffprobe 分析编码信息
  │
  ├─ 视频: H.264 + 音频: AAC + 容器: MP4?
  │    ├─ 是 → 直传（不转码）
  │    └─ 否 → 需要转码
  │         │
  │         ├─ 检测硬件加速
  │         │   ├─ NVIDIA → -vcodec h264_nvenc
  │         │   ├─ Intel  → -vcodec h264_qsv
  │         │   ├─ AMD    → -vcodec h264_amf
  │         │   └─ 无     → -vcodec libx264
  │         │
  │         ├─ 实时流模式: -f mpegts pipe:1
  │         └─ 文件模式:   -f mp4 output.mp4
```

**ffprobe 输出解析示例**：

```bash
ffprobe -v quiet -print_format json -show_format -show_streams input.mkv
```

```json
{
  "streams": [
    {
      "codec_type": "video",
      "codec_name": "hevc",
      "width": 1920, "height": 1080,
      "bit_rate": "5000000"
    },
    {
      "codec_type": "audio",
      "codec_name": "dts",
      "channels": 6
    },
    {
      "codec_type": "subtitle",
      "codec_name": "subrip"
    }
  ],
  "format": {
    "format_name": "matroska",
    "duration": "7200.000"
  }
}
```

**TDD 测试计划**：

```python
# test_transcoder.py — 在实现 transcoder.py 之前先写
class TestProbe:
    async def test_probe_mp4_returns_media_info(self, sample_mp4):
        """ffprobe 应正确解析 H.264+AAC MP4 文件。"""
    async def test_probe_nonexistent_raises(self):
        """不存在的文件应抛出 TranscodeError。"""
    async def test_probe_without_ffmpeg_raises(self, monkeypatch):
        """ffprobe 不存在时应给出友好错误信息。"""

class TestNeedsTranscode:
    def test_h264_aac_mp4_no_transcode(self):
        """H.264+AAC+MP4 不需要转码。"""
    def test_hevc_needs_transcode(self):
        """HEVC 视频需要转码。"""
    def test_dts_audio_needs_transcode(self):
        """DTS 音频需要转码。"""
    def test_mkv_container_needs_transcode(self):
        """MKV 容器需要转码（部分电视不支持）。"""

class TestTranscodeStream:
    async def test_stream_produces_bytes(self, sample_mp4):
        """流式转码应产生 MPEG-TS 字节流。"""
    async def test_stream_cancellation(self, sample_mp4):
        """取消转码任务应终止 FFmpeg 进程。"""
```

### 4.6 URLProxy (`lancaster/url_proxy.py`) — Phase 2

**职责**：处理在线 URL 投屏的三种模式。

**三种投屏模式**：

```
模式 1: 直投（电视直接拉取）
  PC ──SetURI(url)──> 电视 ──HTTP GET──> 互联网
  适用: 公网 HTTP MP4/M3U8，电视可直达

模式 2: 代理中继（PC 中转）
  互联网 ──HTTP──> PC(代理) ──HTTP──> 电视
  适用: HTTPS URL（多数电视不支持）、需认证的 URL、PC 有 VPN

模式 3: 代理 + 转码
  互联网 ──HTTP──> PC ──FFmpeg──> PC(HTTP) ──> 电视
  适用: 格式不兼容的在线视频
```

**API**：

```python
class URLProxy:
    def __init__(self, http_server: HTTPFileServer, controller: MediaController):
        ...

    async def cast_direct(self, device: DLNADevice, url: str) -> None
        """直投: 将 URL 直接发送给电视。"""

    async def cast_proxied(self, device: DLNADevice, url: str) -> None
        """代理: PC 下载并通过本地 HTTP 服务器中继。"""

    async def cast_with_transcode(
        self, device: DLNADevice, url: str, **transcode_opts
    ) -> None
        """代理+转码: 下载 → FFmpeg 转码 → HTTP 流 → 电视。"""

    @staticmethod
    def detect_mode(url: str) -> str
        """根据 URL 特征自动判断最佳模式。
        - http:// + .mp4/.m3u8 → direct
        - https:// → proxied
        - 其他 → proxied
        """
```

**TDD 测试计划**：

```python
# test_url_proxy.py
class TestDetectMode:
    def test_http_mp4_direct(self):
        assert URLProxy.detect_mode("http://example.com/video.mp4") == "direct"
    def test_https_proxied(self):
        assert URLProxy.detect_mode("https://example.com/video.mp4") == "proxied"
    def test_m3u8_direct(self):
        assert URLProxy.detect_mode("http://example.com/live.m3u8") == "direct"
```

### 4.7 MediaServer (`lancaster/server.py`) — Phase 3

**职责**：将 PC 的指定目录作为 DLNA Media Server 广播，电视可主动浏览和播放。

**与 HTTPFileServer 的区别**：

| 维度 | HTTPFileServer (Phase 1) | MediaServer (Phase 3) |
|------|--------------------------|----------------------|
| 角色 | 被动提供单个文件的 HTTP 访问 | 完整的 UPnP DMS 设备 |
| 发现 | 不在 SSDP 中广播 | 通过 SSDP 广播自己为 MediaServer |
| 浏览 | 无 | 实现 ContentDirectory 的 Browse action |
| 电视端体验 | 电视无法主动发现 | 电视可在"媒体来源"中看到 PC |

**实现要点**：

```
MediaServer
  │
  ├─ SSDP 广播 (urn:schemas-upnp-org:device:MediaServer:1)
  │   └─ async_upnp_client.server 搭建 UPnP 设备宿主
  │
  ├─ ContentDirectory 服务
  │   ├─ Browse action: 返回目录/文件的 DIDL-Lite XML
  │   ├─ GetSearchCapabilities: 返回可搜索字段
  │   ├─ GetSortCapabilities: 返回可排序字段
  │   └─ GetSystemUpdateID: 内容变更标识
  │
  ├─ ConnectionManager 服务
  │   └─ GetProtocolInfo: 返回支持的 MIME 类型列表
  │
  ├─ HTTP 文件服务 (复用 HTTPFileServer)
  │   └─ Range 支持 + DLNA 头
  │
  └─ 媒体扫描引擎
      ├─ 递归扫描指定目录
      ├─ ffprobe 提取元数据
      ├─ 构建内存中的虚拟目录树
      └─ objectID 映射表（路径 ↔ 数字 ID）
```

**目录树模型**：

```python
@dataclass
class MediaNode:
    """虚拟目录树中的节点。"""
    object_id: str
    parent_id: str
    title: str
    is_container: bool
    path: Path | None = None
    media_info: MediaInfo | None = None
    children: list["MediaNode"] = field(default_factory=list)
```

**Browse 请求处理流程**：

```
电视发送 SOAP Browse(ObjectID="0")
  │
  ├─ ObjectID=0 → 返回根容器 "LanCaster Media"
  │
  ├─ ObjectID=1 → 返回 dirs[0] 下的子目录和文件
  │
  └─ ObjectID=文件ID → 返回文件的 DIDL-Lite 元数据
      包含: title, duration, resolution, codec, HTTP URL
```

### 4.8 DesktopMirror (`lancaster/mirror.py`) — Phase 3

**职责**：将 PC 桌面画面实时串流到电视。

**工作原理**：

```
FFmpeg 屏幕采集 ──pipe──> HTTPFileServer ──HTTP──> 电视
     │                        │
     │ -f gdigrab/dxgi        │ /stream/{id}
     │ -vcodec libx264        │ Content-Type: video/mp2t
     │ -preset ultrafast      │
     │ -tune zerolatency      │
     │ -f mpegts pipe:1       │
```

**API**：

```python
class DesktopMirror:
    def __init__(
        self,
        http_server: HTTPFileServer,
        controller: MediaController,
    ):
        ...

    async def start(
        self,
        device: DLNADevice,
        fps: int = 30,
        quality: str = "medium",    # low/medium/high
        audio: bool = True,         # 是否采集系统音频
    ) -> None
        """开始桌面镜像。"""

    async def stop(self) -> None
        """停止镜像，终止 FFmpeg 进程。"""

    @property
    def is_running(self) -> bool
        """是否正在镜像中。"""
```

**质量预设**：

| 预设 | 分辨率 | 码率 | 延迟 |
|------|--------|------|------|
| low | 原始/2 | 2 Mbps | ~1s |
| medium | 原始 | 5 Mbps | ~2s |
| high | 原始 | 10 Mbps | ~3s |

**FFmpeg 命令模板**（Windows）：

```bash
ffmpeg -f gdigrab -framerate 30 -i desktop \
  -vcodec libx264 -preset ultrafast -tune zerolatency \
  -pix_fmt yuv420p -g 60 \
  -b:v 5000k -maxrate 5000k -bufsize 10000k \
  -f mpegts pipe:1
```

**限制说明**：
- DLNA 协议不支持低延迟实时流，最低延迟约 1 秒
- 不适合游戏、视频会议等低延迟场景
- 适合演示文稿、图片浏览等容忍延迟的场景
- 音频采集在 Windows 上需要额外配置（DirectShow 设备）

---

## 5. 数据模型

### 5.1 DLNADevice

表示一个已发现的 DLNA 设备。

| 字段 | 类型 | 说明 |
|------|------|------|
| name | str | 设备友好名称（如 "Living Room TV"） |
| ip | str | IP 地址 |
| location | str | UPnP description.xml 的 URL |
| device_type | DeviceType | renderer（电视）或 server（NAS） |
| manufacturer | str | 制造商 |
| model | str | 型号 |
| udn | str | 唯一设备标识（UUID） |

### 5.2 PlaybackInfo

当前播放状态快照。

| 字段 | 类型 | 说明 |
|------|------|------|
| state | TransportState | PLAYING / PAUSED / STOPPED / TRANSITIONING |
| position | timedelta | 当前播放位置 |
| duration | timedelta | 总时长 |
| volume | int | 音量 (0-100) |
| title | str | 当前播放的资源 URL |

---

## 6. CLI 设计

CLI 使用 Click 框架，每个功能对应一个子命令：

```
lancaster
├── discover          扫描设备，输出 Rich 表格
├── cast <target>     投屏（自动判断文件 vs URL）
│   ├── -d <device>   指定目标设备（模糊匹配）
│   └── -t <timeout>  设备扫描超时
├── pause             暂停
├── resume            继续
├── stop              停止
├── seek <time>       跳转（支持 HH:MM:SS / MM:SS / SS）
├── volume <level>    音量 (0-100)
└── status            显示播放状态
```

所有命令支持 `-d` 参数指定设备，未指定时使用配置的默认设备或第一个发现的 Renderer。

---

## 7. 依赖关系

### 7.1 运行时依赖

| 包 | 版本 | 用途 |
|----|------|------|
| async-upnp-client | >=0.46.0 | UPnP/DLNA 核心：SSDP 发现、SOAP 控制、GENA 事件 |
| aiohttp | >=3.9.0 | HTTP 服务器（文件服务）+ HTTP 客户端 |
| python-didl-lite | >=1.5.0 | DIDL-Lite XML 处理 |
| click | >=8.0 | CLI 框架 |
| rich | >=13.0 | 终端美化输出 |

### 7.2 外部工具

| 工具 | 用途 | 必需性 |
|------|------|--------|
| FFmpeg | 视频转码、桌面采集 | Phase 2+ 需要 |

### 7.3 为什么选这些依赖

- **async_upnp_client**：唯一在 2026 年仍活跃维护的 Python UPnP 库，Home Assistant 月下载 10 万+，AVTransport 全部 Action 封装完整。
- **aiohttp**：async_upnp_client 已依赖 aiohttp，复用不引入新依赖。
- **click**：比 argparse 更适合多子命令 CLI，比 typer 更成熟稳定。
- **rich**：一行代码实现表格/进度条/彩色输出。

---

## 8. 路线图

| Phase | 内容 | 周期 | 状态 |
|-------|------|------|------|
| 1 | 核心投屏 MVP | 1-2 周 | 已完成 |
| 2 | FFmpeg 转码 + URL 代理 + 增强控制 | 2 周 | 计划中 |
| 3 | 媒体库共享 (DMS) + 桌面镜像 | 3 周 | 计划中 |
| 4 | GUI（PyQt6 / Tauri / Web） | 开放 | 计划中 |

---

## 9. 已知限制

| 限制 | 说明 | 缓解方案 |
|------|------|---------|
| 格式兼容性 | 电视只能播放它支持的编解码器 | Phase 2 FFmpeg 实时转码 |
| DRM 内容 | DLNA 不支持加密内容 | 无法绕过，仅支持未加密媒体 |
| 字幕 | 仅支持 SRT 外挂，依赖电视端渲染 | Phase 2 FFmpeg 硬字幕烧录 |
| 桌面镜像延迟 | DLNA 协议本身导致 1-3 秒延迟 | 协议限制，无法根本解决 |
| 防火墙 | Windows 防火墙可能阻断 SSDP/HTTP | 首次运行提示用户放行 |
| 跨子网 | SSDP 多播不跨子网 | 需路由器配置多播转发 |

---

## 10. 测试策略

### 10.1 单元测试

覆盖所有不依赖网络的模块：
- `test_models.py` — 数据模型构造与默认值
- `test_utils.py` — IP 检测、MIME 推断、时间格式化
- `test_didl.py` — DIDL-Lite XML 构建与转义
- `test_config.py` — 配置文件读写
- `test_http_server.py` — HTTP Range、DLNA 头、404 处理

### 10.2 集成测试（手动）

在实际电视或 VLC（配置为 DLNA Renderer）上验证：
1. `lancaster discover` 能发现设备
2. `lancaster cast video.mp4` 能投屏播放
3. `lancaster pause / resume / stop` 能控制播放
4. `lancaster seek 00:05:00` 能跳转
5. `lancaster volume 30` 能调节音量

### 10.3 用 VLC 作为测试 DMR

```bash
# 启动 VLC 的 UPnP Renderer 模式
vlc --intf dummy --extraintf http --http-port 8080
# 在 VLC 偏好设置 > 全部 > 流输出 > UPnP > 启用 UPnP Renderer
```

---

## 11. TDD 开发流程

LanCaster 采用 TDD（Test-Driven Development）模式开发。每个模块遵循 Red-Green-Refactor 循环。

### 11.1 TDD 三步循环

```
┌─────────────────────────────────────────────┐
│                                             │
│   1. RED: 写一个失败的测试                    │
│      │                                      │
│      ▼                                      │
│   2. GREEN: 写最少的代码让测试通过            │
│      │                                      │
│      ▼                                      │
│   3. REFACTOR: 重构代码，保持测试通过         │
│      │                                      │
│      └──────── 回到 1 ──────────────────────┘
│
```

### 11.2 每个模块的 TDD 步骤

以 Phase 2 的 `Transcoder` 为例：

**Step 1: 先写测试文件 `tests/test_transcoder.py`**

```python
import pytest
from lancaster.transcoder import Transcoder
from lancaster.models import MediaInfo
from lancaster.exceptions import TranscodeError

class TestProbe:
    @pytest.mark.asyncio
    async def test_probe_returns_media_info(self, tmp_path):
        # 创建一个最小的测试视频文件（用 FFmpeg 生成）
        test_file = tmp_path / "test.mp4"
        # ... 生成测试文件 ...
        info = await Transcoder.probe(test_file)
        assert isinstance(info, MediaInfo)
        assert info.video_codec != ""

    @pytest.mark.asyncio
    async def test_probe_nonexistent_raises(self):
        with pytest.raises(TranscodeError):
            await Transcoder.probe("/nonexistent/file.mp4")

class TestNeedsTranscode:
    def test_h264_aac_mp4_no_transcode(self):
        info = MediaInfo(
            path="test.mp4",
            video_codec="h264", audio_codec="aac", container="mp4"
        )
        assert not Transcoder.needs_transcode(info)

    def test_hevc_needs_transcode(self):
        info = MediaInfo(
            path="test.mkv",
            video_codec="hevc", audio_codec="aac", container="matroska"
        )
        assert Transcoder.needs_transcode(info)
```

**Step 2: 运行测试，确认全部失败（RED）**

```bash
pytest tests/test_transcoder.py -v
# 预期: 全部 FAILED（模块尚未实现）
```

**Step 3: 实现 `lancaster/transcoder.py` 使测试通过（GREEN）**

**Step 4: 重构代码，保持测试通过（REFACTOR）**

**Step 5: 添加更多边界条件测试，重复循环**

### 11.3 测试分层策略

```
┌──────────────────────────────────────────┐
│  Level 3: 端到端测试 (E2E)               │
│  - 需要真实设备或 VLC DMR                 │
│  - 手动执行或 CI 中跳过                   │
│  - 测试完整投屏流程                       │
├──────────────────────────────────────────┤
│  Level 2: 集成测试                        │
│  - 启动真实 HTTP 服务器                   │
│  - 测试 HTTP Range、DLNA 头              │
│  - 测试 FFmpeg 子进程调用                 │
├──────────────────────────────────────────┤
│  Level 1: 单元测试                        │
│  - Mock 所有外部依赖                      │
│  - 测试数据模型、XML 构建、工具函数       │
│  - 毫秒级执行                             │
└──────────────────────────────────────────┘
```

### 11.4 测试覆盖率目标

| 模块 | 目标覆盖率 | 测试类型 |
|------|-----------|---------|
| models.py | 100% | 单元 |
| utils.py | 100% | 单元 |
| didl.py | 95%+ | 单元 |
| config.py | 95%+ | 单元 |
| http_server.py | 90%+ | 集成（真实 HTTP） |
| transcoder.py | 85%+ | 单元（Mock subprocess）+ 集成 |
| discovery.py | 70%+ | 单元（Mock SSDP）|
| controller.py | 70%+ | 单元（Mock DmrDevice）|
| url_proxy.py | 85%+ | 单元 + 集成 |
| server.py | 75%+ | 集成 |
| mirror.py | 70%+ | 单元（Mock FFmpeg）|

### 11.5 Mock 策略

对于依赖网络设备的模块，测试中使用 Mock：

```python
# 示例: Mock DmrDevice 进行 Controller 单元测试
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_dmr():
    dmr = MagicMock(spec=DmrDevice)
    dmr.async_set_transport_uri = AsyncMock()
    dmr.async_play = AsyncMock()
    dmr.async_pause = AsyncMock()
    dmr.async_stop = AsyncMock()
    dmr.async_wait_for_can_play = AsyncMock()
    return dmr

async def test_play_url_calls_set_uri_and_play(mock_dmr, sample_renderer):
    with patch.object(MediaController, '_get_dmr', return_value=mock_dmr):
        ctrl = MediaController()
        await ctrl.play_url(sample_renderer, "http://example.com/video.mp4")
        mock_dmr.async_set_transport_uri.assert_called_once()
        mock_dmr.async_play.assert_called_once()
```

---

## 12. GUI 设计与选型

### 12.1 GUI 需求分析

LanCaster 的 GUI 需要支持以下交互：

| 功能区域 | 需求 |
|----------|------|
| 设备管理 | 自动发现设备列表，显示在线/离线状态，选择默认设备 |
| 文件选择 | 拖拽文件投屏、文件浏览器选择、最近投屏历史 |
| 播放控制 | 播放/暂停/停止按钮、进度条拖拽、音量滑块 |
| 状态显示 | 当前播放媒体信息、进度、设备状态 |
| 媒体库 | 配置共享文件夹、启停 MediaServer |
| 桌面镜像 | 一键开始/停止、帧率/质量选择 |
| 系统托盘 | 最小化到托盘、快捷控制 |
| 设置 | 默认设备、网卡选择、转码偏好 |

### 12.2 GUI 框架对比

#### 方案 A: PyQt6

```
优势:
  + 与核心库同语言 (Python)，集成最简单
  + 成熟稳定，15+ 年历史
  + 原生 Windows 外观
  + 丰富的控件库（表格、树、滑块、进度条）
  + 系统托盘支持完善
  + asyncio 集成: qasync 库

劣势:
  - 打包体积大 (~50MB with PyInstaller)
  - 许可证限制 (GPL，商用需 Qt 商业许可)
  - UI 设计较传统，不够"现代感"

技术栈: Python + PyQt6 + qasync + PyInstaller
打包大小: 50-80 MB
```

#### 方案 B: Tauri 2.0 + Web 前端

```
优势:
  + 打包极小 (3-15 MB)
  + UI 最现代化（React/Vue 前端生态）
  + 跨平台（Windows/macOS/Linux/移动端）
  + 安全的 Capability 权限模型
  + 系统托盘、自动更新内置

劣势:
  - 需要 Rust 后端 + Python 核心库 IPC
  - 架构复杂度高（Rust ↔ Python 跨进程通信）
  - 各平台 WebView 渲染差异
  - 开发者需掌握 Rust + Web + Python 三栈

技术栈: Rust (Tauri) + React/Vue + Python (subprocess/socket)
打包大小: 10-20 MB
IPC 方案: Tauri sidecar 启动 Python 进程，通过 stdin/stdout JSON-RPC 通信
```

#### 方案 C: Web UI (aiohttp)

```
优势:
  + 最简单，复用已有 aiohttp 服务器
  + 无需额外依赖
  + 可远程访问（手机当遥控器）
  + 跨平台无障碍

劣势:
  - 非桌面原生体验
  - 无系统托盘
  - 需要手动打开浏览器
  - 性能较桌面 GUI 差

技术栈: aiohttp + Jinja2/HTMX + Alpine.js
打包大小: 0 MB（额外）
```

#### 方案 D: Textual (TUI)

```
优势:
  + 纯 Python，与核心库完美集成
  + 零额外依赖（rich 生态）
  + 终端中运行，极轻量
  + SSH 远程可用

劣势:
  - 非图形化，学习曲线
  - 不支持拖拽
  - 普通用户不习惯

技术栈: Python + Textual (rich 出品)
打包大小: 0 MB（额外）
```

### 12.3 推荐方案与分阶段策略

鉴于 LanCaster 的核心价值是"简单好用的投屏工具"，推荐分阶段递进：

```
Phase 4a: Web UI（最快落地，2-3 天）
  ├─ 复用 aiohttp，添加 HTML 页面
  ├─ 设备选择 + 文件上传 + 播放控制
  ├─ 手机浏览器也能当遥控器
  └─ 作为 MVP 验证 GUI 交互

Phase 4b: PyQt6 桌面版（2-3 周）
  ├─ 适合做正式产品
  ├─ 系统托盘常驻
  ├─ 拖拽投屏
  └─ 如果 GPL 许可可接受

Phase 4c: Tauri + React（备选，4-6 周）
  ├─ 打包最小、UI 最美
  ├─ 适合开源社区推广
  └─ 如果团队有 Rust + Web 经验
```

### 12.4 Web UI 初步设计

由于 Web UI 实现最快且可复用现有技术栈，这里给出初步设计：

**页面布局**：

```
┌─────────────────────────────────────────────┐
│  LanCaster                        [设置] ⚙  │
├─────────────────────────────────────────────┤
│                                             │
│  设备列表                                    │
│  ┌─────────────────────────────────────┐    │
│  │ ● Living Room TV    Samsung  [选择] │    │
│  │ ○ Bedroom TV        LG       [选择] │    │
│  │ ○ Kitchen Speaker   Sonos    [选择] │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  投屏                                        │
│  ┌─────────────────────────────────────┐    │
│  │  [选择文件...]  或 [输入URL...]       │    │
│  │                                     │    │
│  │  ┌──────────────────────────┐       │    │
│  │  │   拖拽文件到此处投屏      │       │    │
│  │  └──────────────────────────┘       │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  播放控制                                    │
│  ┌─────────────────────────────────────┐    │
│  │  ◄◄  ▶/❚❚  ■   00:15:30 / 01:30:00 │    │
│  │  ════════════●══════════════════     │    │
│  │  🔊 ════════●══  50%                │    │
│  └─────────────────────────────────────┘    │
│                                             │
└─────────────────────────────────────────────┘
```

**Web UI 后端路由**（添加到 HTTPFileServer）：

```python
# 新增路由
GET  /                       → 主页面 HTML
GET  /api/devices            → JSON 设备列表
POST /api/cast               → 投屏操作
POST /api/control/{action}   → 播放控制
GET  /api/status             → 当前播放状态 (SSE 或轮询)
POST /api/upload             → 文件上传投屏
```

**前端技术选择**：
- **HTMX + Alpine.js**：无构建步骤、无 node_modules，单个 HTML 文件即可
- 适合嵌入 Python 项目，无前端工具链负担
- 通过 SSE (Server-Sent Events) 实现设备状态实时更新

### 12.5 PyQt6 桌面版设计

**主窗口布局**：

```python
class MainWindow(QMainWindow):
    """
    ┌─────────────────────────────────────┐
    │ 菜单栏: 文件 | 设备 | 帮助          │
    ├─────────┬───────────────────────────┤
    │ 设备列表 │  投屏区域                 │
    │ (QList) │  ┌─────────────────────┐  │
    │         │  │ 当前播放信息         │  │
    │ ● TV1   │  │ 标题: video.mp4     │  │
    │ ○ TV2   │  │ 时长: 01:30:00      │  │
    │         │  └─────────────────────┘  │
    │         │                           │
    │         │  进度条 + 控制按钮         │
    │         │  ◄◄ ▶ ■  00:15/01:30     │
    │         │  音量: ═══●═══ 50%        │
    ├─────────┴───────────────────────────┤
    │ 状态栏: 已连接 Living Room TV       │
    └─────────────────────────────────────┘
    """
```

**核心类设计**：

```python
class DeviceListWidget(QWidget):
    """设备列表面板，实时更新设备在线状态。"""
    device_selected = Signal(DLNADevice)

class PlaybackPanel(QWidget):
    """播放控制面板，含进度条、音量、按钮。"""
    # 使用 QTimer 每秒轮询播放状态
    # 或使用 GENA 事件订阅实时更新

class CastDropZone(QWidget):
    """文件拖拽区域，支持拖拽文件直接投屏。"""
    def dragEnterEvent(self, event): ...
    def dropEvent(self, event): ...

class SystemTrayIcon(QSystemTrayIcon):
    """系统托盘图标，最小化时驻留。"""
    # 右键菜单: 打开 | 暂停 | 停止 | 退出
```

**asyncio 与 Qt 事件循环集成**：

```python
# 使用 qasync 桥接 asyncio 和 Qt 事件循环
import qasync

app = QApplication(sys.argv)
loop = qasync.QEventLoop(app)
asyncio.set_event_loop(loop)

with loop:
    loop.run_until_complete(main())
```

---

## 13. 部署与分发

### 13.1 PyInstaller 打包

```bash
# 单文件 exe（含 Python 运行时）
pyinstaller --onefile --name lancaster \
  --add-data "lancaster_web/templates:templates" \
  lancaster_cli/app.py
```

### 13.2 未来考虑

| 分发方式 | 适用场景 |
|----------|---------|
| PyPI (`pip install lancaster`) | 开发者/高级用户 |
| GitHub Releases (exe) | Windows 普通用户 |
| Microsoft Store (MSIX) | 如果做 WinUI 3 版本 |
| Docker | NAS/服务器用户 |
