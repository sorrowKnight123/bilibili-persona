# 安装到任何 agent

这个目录（`bilibili-persona/`）是**自包含**的：SKILL.md、全部脚本都在里面。
拷到任何支持 skill 目录约定的 agent 里就能用；不支持约定的，把 SKILL.md 直接给 AI 读也行。

**只需要 python3**。可选依赖按功能降级：`faster-whisper`（本地转写）、`pypdf`（读 PDF 课件）、
`pypinyin`（自动挖术语词表）、`ffmpeg`（解码校验、课件原图提取）。缺哪个，对应功能提示装哪个，
其余功能照常。

## ZCode

设置 → 插件管理 → **发现** → `+` → 添加插件市场，粘贴仓库地址：

```
https://github.com/sorrowKnight123/bilibili-persona
```

装好后 skill 自动启用，命令 `/learn-course <BV号>`。

## Claude Code

`marketplace.json` 与 Claude Code 插件格式兼容，同样支持"添加 marketplace"。
或者手工：把整个 `bilibili-persona/` 目录拷到 `~/.claude/skills/bilibili-persona/`。

## Codex / 其他 agent

1. 把整个 `bilibili-persona/` 目录拷到该 agent 存放 skill/指令的位置
   （没有约定的就放工作目录下）。
2. 对该 agent 说这段话（复制即可）：

```text
读取 <目录>/bilibili-persona/SKILL.md 并按其执行。约定：
- 文中的 $SKILL_DIR 就是 <目录>/bilibili-persona，脚本都在 $SKILL_DIR/scripts/ 下。
- 脚本用 python3 运行；可选依赖（faster-whisper / pypdf / pypinyin / ffmpeg）缺失时，
  按 SKILL.md 对应阶段的说明降级或提示安装，不要静默安装。
- 全程遵守 SKILL.md 的信任边界：不静默安装依赖、不静默上传文件、
  每个需要用户决策的点（读哪些分P、要不要上传、要不要云OCR）先问。
```

## 不装成 skill 也能用

SKILL.md 本质是一份完整的工作流文档。把 `SKILL.md`（和整个目录）直接丢给任何能读文件、
能跑命令的 AI，说「按这个文档操作」即可——这就是上面那段话的最低配版本。

## 验证安装

```bash
# $SKILL_DIR 换成实际目录
python "$SKILL_DIR/scripts/bili_fetch.py" list BV1xxxxxxxxx     # 能列出分P即通
python "$SKILL_DIR/scripts/transcribe.py" --check               # 本地转写自检（可选）
```
