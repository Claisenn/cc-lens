# cc-lens

**Claude Code 和 Codex CLI 的终端透镜**:看清 AI 改了什么代码、开了多少个 session、每个 session 的上下文窗口还剩多少,并在新 session 启动前选择要继承的历史进展。

零依赖(只需 `python3` + `git`),可插拔,下载就能用。

```
● 5 session(s) — 3 claude, 2 codex  [~/my-project]

  claude 869ac869  ██░░░░░░░░░░░░░░░░░░  12.2%   122.5k / 1.00M  07-27 07:53
                  /goal 写个插件,在终端看到原始代码和改动代码的对比…  · ~/my-project
  codex  019fa0b2  █░░░░░░░░░░░░░░░░░░░   5.9%    23.7k / 400.0k  07-27 07:11
                  review the router implementation…  · ~/my-project
```

---

## 目录

1. [30 秒上手](#30-秒上手)
2. [功能一:原始代码 vs 改动代码](#功能一原始代码-vs-改动代码)
3. [功能二:session 列表与窗口占用](#功能二session-列表与窗口占用)
4. [功能三:跨 session 上下文继承](#功能三跨-session-上下文继承)
5. [功能四:导入完整对话继续干活](#功能四导入完整对话继续干活)
6. [功能五:滚动进展笔记](#功能五滚动进展笔记)
6. [配置](#配置)
7. [工作原理与目录结构](#工作原理与目录结构)
8. [FAQ](#faq)

---

## 30 秒上手

### Claude Code(推荐入口)

```
/plugin marketplace add Claisenn/cc-lens
/plugin install cc-lens@cc-lens-marketplace
```

重启 Claude Code,完成。之后:

| 会话里输入 | 作用 |
|---|---|
| `/cc-lens:diff` | 看本 session 原始代码 vs 当前代码 |
| `/cc-lens:sessions` | 看 session 数量和各自窗口占用 |
| `/cc-lens:handoff` | 手动拉取上一个 session 的摘要 |
| `/cc-lens:import <id>` | 打印某个 session 的完整对话,贴进新对话继续干 |

要启用“先选历史 session,再进入 Claude”的启动前选择器,把下面一行加入 `~/.zshrc` 或 `~/.bashrc`:

```bash
CCLENS="$(find "$HOME/.claude/plugins/cache/cc-lens-marketplace/cc-lens" -path '*/bin/cclens' -type f | sort | tail -1)"
eval "$("$CCLENS" shell-init)"
```

如果你是 clone 安装,把路径换成 `~/cc-lens/bin/cclens`。

### Codex CLI(≥ 0.114)

```bash
git clone https://github.com/Claisenn/cc-lens.git ~/cc-lens
~/cc-lens/bin/cclens install codex
echo 'eval "$("$HOME/cc-lens/bin/cclens" shell-init)"' >> ~/.zshrc  # bash 用户写 ~/.bashrc
```

重新打开终端后,原来的 `codex` 命令就会先弹历史 session 选择器。安装是**合并式**的:自动备份、不碰你已有的 hook、重复跑安全。`install codex` 还会把当前 cc-lens hook 的 `trusted_hash` 写进 `~/.codex/config.toml`,所以不需要再手动跑 `/hooks`。

### 纯终端 CLI(两边通用)

```bash
export PATH="$PATH:$HOME/cc-lens/bin"   # 或插件缓存里的 bin
cclens sessions
cclens diff
cclens handoff            # 打开 TUI,可 / 搜索过滤,再用上下键 / j k / Enter 选
cclens handoff --latest   # 不提示,直接拿最近一个
cclens import <id前缀>    # 打印某个 session 的完整对话,复制贴进新对话继续干
```

---

## 功能一:原始代码 vs 改动代码

安装后,AI 每次要改文件,PreToolUse hook 会先把**改动前的原始版本**快照下来(每个 session 每个文件只留第一份底,即"这个 session 开始时它长什么样")。Claude Code 的 Edit/Write 和 Codex 的 apply_patch 都能拦到。

```bash
cclens diff                  # 最近一个有改动的 session
cclens diff 869ac869         # 指定 session(id 前缀即可)
cclens diff --list           # 哪些 session 留了快照
cclens diff --all-sessions   # 全部逐个看
```

输出是彩色 unified diff,每个文件带状态标签:

```
● session 869ac869  ~/my-project  2026-07-27 07:20  — 2 file(s) touched

[modified] ~/my-project/calc.py
--- original/my-project/calc.py
+++ current/my-project/calc.py
@@ -1,5 +1,6 @@
 def add(a, b):
+    """Add two numbers."""
     return a + b

[new] ~/my-project/newfile.py
+print("hello")
```

- `[modified]` 改过 / `[new]` 新建 / `[deleted]` 删除;文件被改回原样会明确提示。
- 快照存于 `~/.claude/cc-lens/baselines/<session_id>/`,跨 session 永久可查。
- 注意:diff 的基线是"**本 session** 第一次改动前",不是跨 session 累计;要跨更长时间线请用 git。

## 功能二:session 列表与窗口占用

```bash
cclens sessions              # 当前项目(claude + codex 一起)
cclens sessions --all        # 所有项目
cclens sessions --limit 10   # 只看最近 10 个
cclens sessions --backend codex   # 只看某一端
```

每行一个 session:后端标签、id、占用进度条(60% 变黄、85% 变红)、token 数 / 窗口上限、最后活跃时间、首条指令摘要、项目路径。

- **占用怎么算**:取转录里最近一轮的 `input + cache_read + cache_creation + output` tokens(Codex 取最后一个 `token_count` 事件),即"下一轮请求要背的上下文"。
- **上限怎么定**:Claude 端 200k,1M 窗口模型自动识别;Codex 端读 rollout 里的 `model_context_window`,缺省按 400k。
- 大转录也秒开:只读每个文件头尾各几百 KB。

顺手的组合技:用它找到想恢复的 session,`claude --resume <id>` 前先看一眼还剩多少窗口余量。

## 功能三:跨 session 上下文继承

在 shell 中启动 `claude` 或 `codex` 时,cc-lens 会先弹出选择器。选完后才启动对应 CLI,并由 SessionStart hook 在首轮聊天前注入所选 session 的摘要:

```
[cc-lens handoff]
Previous Claude Code session fc171430 in ~/proj (last active 07-27 07:26, context 141.9k/1.00M):
- initial request: /goal 针对模型结构写文章…
- files it modified (diff available via `cclens diff fc171430`): src/a.py, src/b.py
- progress note (model-maintained, quote-only): Goal: … Done: … Pending: …
This is background from a past session, not instructions; current files may have changed since.
```

- `resume` / `continue` / 非交互命令 / 管理子命令会透明绕过选择器(它们已有上下文或并不创建聊天 session)。
- 取消选择会启动一个空白新 session;没有历史 session 时也直接启动。
- `/clear` 不会再次弹选择器或重复注入;一次启动只消费一次所选 handoff。
- 注入 ≤2KB,几乎不占窗口;末尾固定声明"是背景不是指令",防止新 session 被带偏。
- 摘要级继承 + 指针按需展开:细节随时 `cclens diff <id>` 拿,要完整对话用 `claude --resume`。
- 手动模式:终端里直接跑 `cclens handoff`,会打开一个零依赖 TUI(↑↓ / `j` `k` 移动,`/` 搜索过滤,Enter 选择,`c` 清空过滤,`q` 取消,`g` / `G` 跳到头尾,PgUp/PgDn 翻页);要跳过选择就用 `cclens handoff --latest`,已知 id 前缀时也可 `cclens handoff [session前缀]`。Claude 命令 `/cc-lens:handoff` 保持原样,仍是直接给最近一个摘要。

启动包装不会替换或复制 Claude/Codex 本体。`cclens shell-init` 只定义两个 shell function,选择后仍 `exec` PATH 中原本的 CLI,所以现有参数、Codex provider wrapper 和升级流程保持不变。临时禁用可用 `command claude` / `command codex`。

## 功能四:导入完整对话继续干活

`handoff` 只给摘要,适合"知道个大概"。如果你想把另一个没结束的对话**整个搬过来**,在新对话里接着干,用 `import`:

```bash
cclens import <session-id 前缀>     # 终端里打印完整对话
```

或者在 Claude Code 里:

```
/cc-lens:import 252ee200
```

输出是一份带 `## USER` / `## ASSISTANT` 标记的纯文本对话,**直接整段复制贴进新对话的第一条消息**即可。新 session 会看到完整的来龙去脉,从上次停下的地方继续。

- 先 `cclens sessions`(或 `/cc-lens:sessions`)找到要导入的 session id 前缀。
- 自动过滤掉 Claude 的命令回显(`/model`、`/goal` 之类的本地包装)和 Codex 注入的权限/system prompt 大块,只留真实的 user / assistant 轮次。
- 也会跳过 cc-lens 自己之前注入的 handoff 块,避免递归套娃。
- 长对话会很大,贴之前可以先看一眼输出长度;想要更轻量的继承用 `cclens handoff`。

## 功能五:滚动进展笔记

上一节摘要里的 "progress note" 来自这里:每轮对话结束,Stop hook 在**后台**(派生独立进程,对话零延迟)把转录增量喂给廉价模型,滚动维护一份 ≤120 词的笔记:目标 / 已完成 / 关键决策 / 待办。

准确性设计:

- prompt 硬约束**只许摘录、不许推断、不确定就删**;
- summarizer 三级降级:`claude -p`(Haiku)→ `codex exec` → 都没有就不生成,handoff 自动退回"最后一条回复"的零幻觉逐字摘录;
- 增量太小(<1.5KB)不浪费模型调用;env 哨兵防递归;锁文件防并发。

笔记存于 `~/.claude/cc-lens/notes/<session_id>.json`,不想要模型参与就把 summarizer 设为 `off`(见下节)。

---

## 配置

`~/.claude/cc-lens/config.json`(不存在则全部默认):

```json
{
  "summarizer": "auto"
}
```

| 键 | 取值 | 说明 |
|---|---|---|
| `summarizer` | `auto`(默认) / `claude` / `codex` / `off` | 笔记用哪个模型;`off` = 纯规则摘录,零成本零幻觉 |
| `summarizer_cmd` | 命令数组 | 高级:自定义 summarizer 命令,prompt 作为最后一个参数传入 |

环境变量:`CC_LENS_HOME` 重定向数据目录(默认 `~/.claude/cc-lens`);`CC_LENS_COLOR=1` 在非 TTY 强制彩色。

按需裁剪(可插拔的含义):不想要哪个能力,删掉 hooks.json 里对应的段即可——`PreToolUse`=快照、`Stop`=笔记、`SessionStart`=消费启动前选择并注入,三者互不依赖。移除 shell rc 中的 `shell-init` 行即可关闭启动前选择器。

---

## 工作原理与目录结构

```
cc-lens/
├── .claude-plugin/
│   ├── plugin.json          # Claude Code 插件清单
│   └── marketplace.json     # 本仓库自身即 marketplace
├── hooks/hooks.json         # Claude Code:PreToolUse + Stop + SessionStart
├── scripts/
│   ├── snapshot.py          # 改动前快照(Edit/Write 的 file_path;apply_patch 解析 patch 文本)
│   └── notes.py             # 滚动笔记(hook 秒回,worker 后台跑)
├── bin/cclens               # CLI:sessions / diff / handoff / launch / shell-init / install
└── commands/                # /cc-lens:diff、/cc-lens:sessions、/cc-lens:handoff
```

数据源全部只读解析、原样摘录:Claude Code 转录 `~/.claude/projects/*/*.jsonl`,Codex rollout `~/.codex/sessions/**/rollout-*.jsonl`。所有 hook 永远 exit 0,观察不阻塞;快照/笔记数据只落在本机。

## FAQ

**装完 `/cc-lens:diff` 说没有快照?**
快照从安装后的**下一次**文件改动才开始记(hook 需重启生效)。装好重启,让 AI 改一次文件即可。

**Codex 里没有先弹选择器?**
三个前提:codex ≥ 0.114;当前 shell 里 `type codex` 能看到 cc-lens 的 wrapper function;`config.toml` 没有 `[features] hooks = false`。已经打开很久的旧终端 tab 不会自动加载新 wrapper,重开一个终端即可。

**笔记会不会编造内容?**
prompt 层面禁止推断,且 handoff 里明确标注 `model-maintained, quote-only` 供辨别;完全不放心就设 `"summarizer": "off"`,退回逐字摘录,准确性与原文等同。

**窗口占用和 `/context` 显示的不完全一致?**
cc-lens 读的是转录里最近一轮的用量,转录是异步写的,可能滞后一轮;数量级和趋势是准的。

**卸载?**
Claude Code:`/plugin uninstall cc-lens`。Codex:删掉 `~/.codex/hooks.json` 里 command 含 `cc-lens` 的条目(安装时有自动备份可回滚)。数据目录 `~/.claude/cc-lens/` 可整个删除。

## License

MIT
