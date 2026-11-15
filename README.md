# bilibili-persona

把一门 B 站网课变成**两样东西**：一份能查的课程知识库，和一个能按老师口吻答疑的虚拟讲师。
给自学网课、却没法向老师提问的人。

> EN: Turn a bilibili course series into a queryable course knowledge base plus an optional
> "teacher persona" — transcribed locally, terminology auto-corrected, slides illustrated,
> provenance clickable. One self-contained skill directory, works in any agent.

**自学网课的真实困境**：一门课几十个分P、总长几十小时；字幕缺失或干脆没有；语音识别把
「薛定谔」写成「薛定恶」还一错五六种；看到一半有疑问，只能去评论区碰运气。

本插件把这些压成一次对话：给它一个 BV 号，它逐分P 转写、自动纠正术语、解析课件和配套资料、
生成结构化讲义，最后蒸馏出两个 skill。在一门 24 分P / 31 小时的大学网课上实测：
**4 小时 08 分的音频转写用了 18 分钟**（13.6 倍实时），术语纠错 **4618 处**，24 讲讲义全部落盘。

## 它的形态：一个拷走就能用的目录

```
bilibili-persona/
├── SKILL.md      给 AI 读的完整工作流 + 写作规范（本插件的大脑）
├── INSTALL.md    装到任何 agent 的说明
└── scripts/      七个命令行脚本，纯 Python
```

安装三选一（详见 [`INSTALL.md`](skills/bilibili-persona/INSTALL.md)）：

- **ZCode**：设置 → 插件管理 → 发现 → `+` → 粘贴本仓库地址
- **Claude Code / Codex / 其他**：拷目录 + 对 AI 说一段现成的话
- **兜底**：不装也行——SKILL.md 本质是份工作流文档，直接丢给任何能读文件、能跑命令的 AI

脚本只需 python3。可选依赖缺失时自动降级：`faster-whisper`（本地转写）、`pypdf`（PDF 课件）、
`pypinyin`（挖词表）、`ffmpeg`（切分/校验）。

## 两份产物，各管各的

| 产物 | 给谁用 | 默认 |
|---|---|---|
| **知识库** `skills/<课程名>/` | 只想学这门课的人：大纲、讲义、术语表、课件笔记、复习页 | 生成并**启用** |
| **讲师人格** `personas/<讲师名>/` | 想按老师的口吻听课、答疑、押考点的人 | 生成但**不启用** |

分开是刻意的：多数人只需要知识。想要"老师"，一条命令：

```bash
cp -r personas/<讲师名> skills/
```

人格分两层写——**语言风格**（口头禅原句，按出现讲次标注可信度）和**判断与教学法**
（他先看什么、怎么框定问题、怎么纠错、他亲口说的考点判定规则）。每条都能引回原话和时间点，
引不回的不写。

## 工作流程

```
BV 号
 └→ 列分P → 停下来问你：读全部还是指定哪几门
     └→ 找文字（三级降级）：① 视频原生字幕 → ② 云 ASR → ③ 本地 faster-whisper
     └→ 找资料：扫简介/置顶/热评里的网盘和直链，列成清单问你要不要下
     └→ 读课件：PDF/PPTX/DOCX 解析成带页码锚点的笔记，原图进知识库
     └→ 纠术语：从转录自动挖同音错字（拼音聚类 + 频次对比），你确认后确定性替换
     └→ 写讲义：每讲六栏（概念/公式/推导/例题/易混与坑/考点），条目带时间戳、配课件原图
     └→ 产出：知识库 + 讲师人格 + 单页复习笔记 + 交付报告（缺什么、置信度、AI 使用说明）
```

每个需要决策的点（读哪些分P、要不要上传音频、要不要云 OCR）都**先问你**；
不静默安装依赖，不静默上传文件。

## 七个脚本

| 脚本 | 干什么 | 备注 |
|---|---|---|
| `bili_fetch.py` | 列分P / 下音频 / 存原生字幕 / **找配套资料** | 直连公开 API；下载串行 + 解码校验；坏 CDN 节点自动换备用 |
| `transcribe.py` | 转写（云/本地）+ 术语纠错 | `--engine auto\|cloud\|local`；`--check` 自检；断点续跑 |
| `glossary.py` | **自动挖术语纠错词表**，无需任何 API | 拼音同音聚类 + 频次对比，附证据报告；人工确认后并入 |
| `materials.py` | 课件解析（本地优先，扫描件可走云 OCR） | 输出带页码锚点 |
| `illustrate.py` | 课件原图进笔记 | 只取课件里已有的图，**绝不用模型画图** |
| `stamp.py` | 时间戳链接化 + 两道检查 + 单页复习笔记 | 点 `00:12:34` 跳回原视频那一秒 |
| `mock_asr.py` | 本地假 ASR 服务 | 无密钥即可验证云转写全链路 |

## 命令速查

```bash
# $SKILL_DIR 指 skills/bilibili-persona/

# 列分P；--json 生成 course.json 供 stamp.py 使用
python "$SKILL_DIR/scripts/bili_fetch.py" list BV1xxxxxxxxx
python "$SKILL_DIR/scripts/bili_fetch.py" list BV1xxxxxxxxx --json -o course.json

# 找配套资料：扫简介+置顶+热评，网盘只列链接和提取码，绝不自动下载
python "$SKILL_DIR/scripts/bili_fetch.py" resources BV1xxxxxxxxx --pages 2

# 下音频（串行 + 解码校验；并发会损坏文件，别开）
python "$SKILL_DIR/scripts/bili_fetch.py" audio BV1xxxxxxxxx -I 1-5 -o downloads
python "$SKILL_DIR/scripts/bili_fetch.py" verify BV1xxxxxxxxx -o downloads      # 自查完整性

# 转写（本地 GPU；--check 先自检）
python "$SKILL_DIR/scripts/transcribe.py" --check
python "$SKILL_DIR/scripts/transcribe.py" downloads/ -o transcripts

# 术语纠错：自动挖掘 → 人工确认 → 确定性替换（先 dry-run）
python "$SKILL_DIR/scripts/glossary.py" transcripts/ --reference 课件笔记/ -o 术语表.auto.json
python "$SKILL_DIR/scripts/transcribe.py" --apply-glossary 术语表.auto.json transcripts/ --dry-run

# 讲义收尾三连：时间戳链接化 → 强绑检查 → 公式残留检查 → 复习页
python "$SKILL_DIR/scripts/stamp.py" link    讲义/ --course course.json
python "$SKILL_DIR/scripts/stamp.py" lint    讲义/
python "$SKILL_DIR/scripts/stamp.py" fxcheck 讲义/
python "$SKILL_DIR/scripts/stamp.py" html    讲义/ -o 复习页.html --course course.json --overview 大纲.md
```

## 笔记为什么不像 AI 写的

「图文并茂、没有 AI 味」不是靠一句提示词，而是靠一套**可检查的规范**：

- **条目化，不逐句转录**：口语填充语（"这个这个"、"啊"、重复、半句）不进讲义
- **正文零防御性描述**：「转录未读出」「按课件补全」「存疑」这类话不出现在正文——
  缺的公式用课件原图补，补不上的写一行「注：」放章末
- **简洁是硬要求**：一条 bullet 一个事实；引用原话每条最多一句；啰嗦是另一种 AI 味
- **公式记法契约**：源文件用 ASCII 记法（`L̂_z`、`e^{ikx}`），渲染层排版成真上下标
- **强制时间戳**：每个条目必须带 `mm:ss` 且只能取自转录里真实存在的行——`stamp.py lint`
  逐条检查（实测 2012 条、缺失 0）；`fxcheck` 检查公式渲染残留

## 常见问题

**yt-dlp 报 HTTP 412，但接口明明是通的？**
B 站有两种 412：① yt-dlp 走的**网页端点**被风控（同一时刻公开 API 正常）——用 `bili_fetch.py`；
② **Python 的 TLS 指纹**被 WAF 拒绝（同一请求 `urllib`/`requests` 412 而 `curl` 200）——
脚本会自动改用 curl 重试。第二种与登录无关，cookie 解决不了。连 curl 都 412 才是 IP 限流：等几分钟，
`--delay` 调大。

**下载的音频大小正常，却解不开？**
并发下载会静默产生损坏文件（实测 21 个里坏 12 个，字节数接近正确，ffprobe 也报完整时长——
分片 DASH 的 init 段会撒谎）。所以本项目**默认串行 + 下载后解码校验**，坏就重下而不是按字节续传。
别开 `--workers`，随时 `verify` 自查。

**第一次转写卡在下载模型？**
HuggingFace 国内连不上，且其 Xet 后端没有镜像，两件事都要做：
`export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`（PowerShell 用 `$env:`）。
权重 1.6G，建议 `HF_HOME` 指到大盘。脚本失败时会把这两行打给你。

**GPU 用不起来？**
Windows 上只需保证 `cublas64_12.dll` 在 PATH 里。CTranslate2 4.5+ 的 Windows 轮子默认**不链 cuDNN**，
网上"必须装 cuDNN 9"的说法对当前版本已不成立。8G 显存用 `int8_float16`。没 GPU 自动退回 CPU（换小模型）。

**云转写报 404 或返回 HTML？**
`ASR_BASE_URL` 指向的是对话模型网关，它没有 `/audio/transcriptions`。换真正的语音转写服务
（如硅基流动 `https://api.siliconflow.cn/v1` + `FunAudioLLM/SenseVoiceSmall`），或用 `--engine local`。
无密钥验证链路：`python "$SKILL_DIR/scripts/mock_asr.py"`。

**需要登录态的内容取不到？**
`bili_fetch.py` 加 `--cookie "SESSDATA=..."`。yt-dlp 侧的 cookie 三坑（浏览器运行锁库、
Chrome 应用绑定加密、firefox 空 profile）见 SKILL.md。**cookie 是账号凭据，别写进仓库、别贴进对话。**

## 依赖

| 依赖 | 什么时候需要 |
|---|---|
| python3 | 必须 |
| `yt-dlp` | 可选（`bili_fetch.py` 是主路径） |
| `faster-whisper` | 本地转写（**不需要 torch**） |
| `pypdf` | PDF 课件 |
| `pypinyin` | 自动挖词表（约 2MB 纯 Python，缺失时跳过拼音信号） |
| `ffmpeg` | 云转写切分、解码校验 |
| `MINERU_API_TOKEN` | 扫描件课件走云 OCR 时 |

skill 只报告缺什么、给出安装命令，**不会静默安装**，也不会静默上传你的任何文件。

## 设计取舍：为什么功能这么少

**小而美是原则，不是缺陷。** 本插件只做"别的工具从下游补不出来的东西"——
知识库和人格必须从原始音视频里蒸馏，这是它们的护城河；至于下游能力：

- **思维导图 / 知识图谱**：已经商品化（25+ 同类项目标配），用本插件产出的结构化笔记喂给
  专门的工具，效果一样甚至更好
- **云 ASR 不是默认引擎**：本地转写免费、隐私、够快；云端点留给没有 GPU 的人
- **网盘资料永不自动下载**：只列链接和提取码——要登录、有风控，做成自动下载只会被当成爬虫
- **抽帧插图 ≠ 视觉理解**：把画面截图嵌进笔记不需要 LLM 读它，所以"图文并茂"与"不烧钱"不冲突
- **不做**：MCP server、GUI、配置文件（用 CLI 参数）、向量库 RAG、学习进度跟踪、
  其他视频平台（等真有第二个需求）

## 许可与免责

**GPL-3.0**（见 `LICENSE`）。复用的第三方代码归属见 `NOTICE`——衍生作品必须同样开源。

只做**个人学习用途**的本地文字化：不重新分发视频、音频、字幕、课件，不绕过付费墙或 DRM，
不批量爬取，需要登录态的课程请使用你自己已购买的账号。`downloads/`、`transcripts/`、
课件原件已在 `.gitignore` 排除，**不要提交或上传**；生成的知识库与人格可以自由分发。
请遵守 B 站用户协议与你所在地区的法律，使用产生的后果由使用者自负。
