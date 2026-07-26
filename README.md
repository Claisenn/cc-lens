# cc-lens

Claude Code **和 Codex CLI** 的终端透镜插件:

- **`/cc-lens:diff`** — 对比 **原始代码 vs Claude 改动后的代码**(彩色 unified diff)。插件通过 PreToolUse hook 在 Claude 第一次改动某个文件前自动快照原始版本,无需 git、无需手动操作。
- **`/cc-lens:sessions`** — 列出有 **多少个 session**,以及 **每个 session 的上下文窗口占用**(进度条 + 百分比 + token 数)。
- **session 上下文继承** — 开新 session(或 `/clear` 后)时,SessionStart hook 自动注入上一个 session 的摘要:当初的需求、改过哪些文件、最后聊到哪、窗口占用。`resume` / `compact` 场景不注入(它们本来就带着上下文)。也可随时手动 `/cc-lens:handoff [session前缀]` 拉取任意历史 session 的摘要。
- **滚动进展笔记** — 每轮结束后 Stop hook 在后台用廉价模型(Haiku,失败自动退 `codex exec`,都没有就退回纯规则摘录)滚动维护一份 ≤120 词的笔记(Goal / Done / Decisions / Pending),prompt 强约束"只许摘录不许推断"。handoff 注入时优先用笔记,没有笔记就用零幻觉的尾部摘录保底。hook 本体毫秒级返回,绝不拖慢对话。
- **Codex 同样适用** — `cclens sessions` 同时统计 `~/.codex/sessions` 的 rollout(带 `claude`/`codex` 标签);快照 hook 能解析 apply_patch 的 patch 文本,diff / 笔记 / handoff 注入在 Codex 里同样工作(Codex ≥0.114 的 hooks 与 Claude Code 同构)。
- 三个视图也能脱离两个 CLI、直接在任何终端里用:`cclens diff` / `cclens sessions` / `cclens handoff`。

零依赖:只需要 `python3` 和 `git`(用于彩色 diff 渲染)。

## 安装(即插即用)

在 Claude Code 里:

```
/plugin marketplace add Claisenn/cc-lens
/plugin install cc-lens@cc-lens-marketplace
```

重启 Claude Code 后 hook 生效,之后每个 session 的文件改动都会自动留底。

想在终端直接使用 CLI,把插件的 `bin` 加进 PATH(装好后插件位于 `~/.claude/plugins/cache/...`,也可以直接 clone 本仓库):

```bash
git clone https://github.com/Claisenn/cc-lens.git
export PATH="$PATH:$(pwd)/cc-lens/bin"
```

### Codex 接入

```bash
git clone https://github.com/Claisenn/cc-lens.git ~/cc-lens
~/cc-lens/bin/cclens install codex     # 合并进 ~/.codex/hooks.json(先自动备份,不动你已有的 hook)
```

然后在 Codex 里跑一次 `/hooks` 审阅并信任(Codex 按 hash 信任钉住 hook)。卸载:删掉 hooks.json 里 command 含 `cc-lens` 的条目即可。

### 笔记 summarizer 配置(可选)

`~/.claude/cc-lens/config.json`:

```json
{ "summarizer": "auto" }   // auto | claude | codex | off
```

`off` 表示不用模型,handoff 退回纯规则摘录(零成本零幻觉)。

## 使用

### 原始代码 vs 改动代码

```
cclens diff                  # 最近一个有改动的 session
cclens diff --list           # 列出所有留了快照的 session
cclens diff 869ac869         # 指定 session(前缀即可)
cclens diff --all-sessions   # 所有 session 的改动
```

输出示例:

```
● session testsess  /tmp/demo  2026-07-27 07:20  — 2 file(s) touched

[modified] /tmp/demo/calc.py
--- original/tmp/demo/calc.py
+++ current/tmp/demo/calc.py
@@ -1,5 +1,6 @@
 def add(a, b):
+    """Add two numbers."""
     return a + b
-def sub(a, b):
-    return a - b
+def mul(a, b):
+    return a * b

[new] /tmp/demo/newfile.py
+print("hello")
```

`[modified]` / `[new]` / `[deleted]` 标签区分改动类型;文件被改回原样时会明确提示。

### session 与上下文窗口占用

```
cclens sessions              # 当前项目的 session
cclens sessions --all        # 所有项目
cclens sessions --limit 10   # 只看最近 10 个
```

输出示例:

```
● 21 session(s)  [/Users/you/project]

  fc171430  ██░░░░░░░░░░░░░░░░░░  11.1%   110.8k / 1.00M  07-27 07:20
           /goal 针对模型结构写文章…  · ~
  77f230eb  ███████░░░░░░░░░░░░░  32.9%   329.2k / 1.00M  07-27 07:19
           分析 FlashMLA…  · ~
```

占用 = 最近一轮的 `input + cache_read + cache_creation + output` tokens,对照该 session 模型的上下文窗口(200k;1M 窗口模型自动识别)。进度条按 60% / 85% 变色提醒。

### session 上下文继承

```
cclens handoff             # 上一个 session 的摘要(终端里看)
cclens handoff fc171430    # 指定 session
```

新 session 启动时自动注入的内容形如:

```
[cc-lens handoff]
Previous Claude Code session fc171430 in ~/proj (last active 2026-07-27 07:26, context 141.9k/1.00M):
- initial request: /goal 针对模型结构写文章…
- files it modified (diff available via `cclens diff fc171430`): src/a.py, src/b.py
- how it ended (last assistant message): 已完成 X,剩 Y 待验证…
This is background from a past session, not instructions; current files may have changed since.
```

注入量控制在 2KB 以内,不吃窗口。想关掉:装好后删掉 `hooks/hooks.json` 里的 `SessionStart` 段即可(可插拔)。

## 工作原理

```
cc-lens/
├── .claude-plugin/
│   ├── plugin.json          # 插件清单
│   └── marketplace.json     # 仓库本身即 marketplace
├── hooks/hooks.json         # PreToolUse: Write|Edit|MultiEdit|NotebookEdit
├── scripts/snapshot.py      # 改动前快照原始文件 → ~/.claude/cc-lens/baselines/<session>/
├── bin/cclens               # CLI:diff / sessions
└── commands/                # /cc-lens:diff、/cc-lens:sessions
```

- **快照**:hook 从 stdin 读事件 JSON,同一 session 内每个文件只在首次改动前留一份底(新建文件记为 `[new]`)。hook 永远 exit 0,绝不阻塞编辑。
- **session 统计**:解析 `~/.claude/projects/*/*.jsonl` 转录,只读每个文件的头尾各几百 KB,大转录也秒开。
- 快照目录可用环境变量 `CC_LENS_HOME` 重定向;`--color` 或 `CC_LENS_COLOR=1` 在非 TTY 下强制彩色。

## License

MIT
