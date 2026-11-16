# unity2phaser · Unity 转 Phaser 游戏转换 Skill

一个可安装到 AI 编程助手（WorkBuddy、Claude Code、ZCode 等）的 **Skill**：把 Unity 2D 小游戏自动转换为完整、可玩、离线可用的 Phaser 网页游戏，并强制保持与原版 1:1 保真（界面、玩法、关卡、素材）。

> **给 AI Agent 的话**：如果你是被用户要求安装本 skill 的 AI 助手，请直接阅读 [SKILL.md](SKILL.md) 了解触发条件与工作流，并把本仓库全部内容下载/复制到你所在工具的技能目录（见下方「安装」），即可完成安装。

## 安装

### 方式 A：把仓库链接发给你的 AI 助手（推荐）

对 WorkBuddy / ZCode / Claude Code 说：

> 帮我安装这个 skill：https://github.com/AMSnoopy/unity2phaser

AI 会读取本仓库、把 `unity2phaser/` 文件夹复制到它的技能目录并生效。

### 方式 B：手动安装

把 `unity2phaser/` 整个文件夹复制到对应技能目录：

| 工具 | 技能目录 |
|---|---|
| ZCode / 通用（用户级） | `~/.agents/skills/unity2phaser/` |
| ZCode（项目级） | `<项目>/.agents/skills/unity2phaser/` |
| Claude Code | `~/.claude/skills/unity2phaser/` |
| WorkBuddy | 在对话里发仓库链接，WorkBuddy 自行安装 |

也可以用命令行安装（Windows PowerShell / Git Bash）：

```bash
git clone https://github.com/AMSnoopy/unity2phaser.git
mkdir -p ~/.agents/skills
cp -r unity2phaser ~/.agents/skills/
```

安装后新开会话即可触发；或显式调用：`/skill unity2phaser <任务>`。

### 更新已安装的旧版本

Skill 本质就是一个文件夹，**更新 = 用仓库新内容覆盖你技能目录里的同名文件夹**，无需卸载重装、目录名不变。

**方式 A：发给 AI 一句话（推荐）**——对装了旧版本的 AI 助手说：

> 帮我更新这个 skill 到最新版：https://github.com/AMSnoopy/unity2phaser

AI 会重新拉取仓库内容，覆盖它的技能目录（如 `~/.claude/skills/unity2phaser/`、WorkBuddy 技能目录等）。

**方式 B：命令行覆盖**：

```bash
git clone https://github.com/AMSnoopy/unity2phaser.git
cp -rf unity2phaser ~/.agents/skills/   # 换成你实际的技能目录
```

**怎么判断自己是不是旧版**：打开已安装目录里的 `SKILL.md`，第一行有版本号（如 `v1.1 (2026-11-16)`）；或对比 GitHub 上 `SKILL.md` 的同一行。

**更新后请开一个新会话**：已经开着的旧会话里，skill 内容还停留在旧版，新会话才会加载更新后的版本。

## 使用

装好后，把 Unity 游戏交给 AI 并说明意图，例如：

> 这是一个 Unity 小游戏：`蜜蜂填词.unitypackage`。把它转换成 Phaser 网页游戏，界面、玩法、关卡、素材要和原版一致。

**强烈建议：同时附上原版录屏（视频文件）。** 给 AI 本地视频路径（如 `C:\...\原版录屏.mp4`），并在消息里标注关键时间点（开场教学 / 第一次答题 / 答错重试 / 完整结尾）。AI 会用它校准动画与反馈节奏，并在验收阶段与转换结果逐帧对照保真度。没有录屏也能转换，但保真对照只能标注"源码推断"，无法逐帧验证。

AI 会自动：解包 → 盘点出《转换契约》（哪些场景/脚本/图片/音频/关卡必须迁移）→ 分阶段转换 → 自动核销 + 本地试玩验收。你只需要在关键取舍时回答问题，最终拿到一个可直接部署的网页项目：

```
蜜蜂填词-phaser/
├── index.html          # 本地服务器打开即可玩
├── lib/phaser.min.js   # 离线可用（Phaser 4.2.1 固定版本）
├── assets/             # 原版素材
├── src/                # 可继续编辑的 Phaser 源码
├── data/               # 关卡数据
└── conversion/         # 转换档案：契约、进度、核销与验收报告
```

## 它做什么

给定一个 Unity 游戏（`.unitypackage` 导出包 / 项目文件夹 / 项目 ZIP），AI 按八阶段流程自主完成转换：

```
盘点（生成转换契约） → 资产迁移 → 工程骨架 → 场景重建 → 逻辑移植 → 关卡内容 → 自动核销+实机验收 → （可选）增强
```

针对 AI 转换最常见的三类失败，skill 内置了对应机制：

| 常见失败 | skill 的机制 |
|---|---|
| AI 转换"做一半"就停 | 八阶段各设出口条件；`progress.md` 断点恢复；阶段报告制度 |
| 转换"不干净"、丢关卡丢图 | `inventory.py` 生成《转换契约》；`verify_output.py` 自动核销到 0 error 才能交付 |
| AI 重绘美术、偏离原版 | 硬规则禁止替代原素材；验收剧本强制与原版对照 |

## 环境要求

- 运行转换的 AI 助手需能读写文件、执行命令、运行本地浏览器预览
- Python 3.8+（仅标准库，无第三方依赖）
- 可选：Node.js（用于 JS 语法自动检查；没有也能工作）

## 设计原则

1. **保真优先**：先做到和原版一样，再谈更好。玩法、手势、教学节奏、完整结尾时长都不允许被简化。
2. **契约核销**：转换前盘点生成硬约束清单，转换后机器核销 + 人工试玩双层验收，缺一项都不能交付。
3. **对 AI 友好**：skill 是"流程 + 经验 + 工具"的轻量组织（SKILL.md 精简、细节按需加载），不与模型对抗；模型越强，转换质量越高。
4. **自包含**：Phaser 库随 skill 分发，转换产物离线可玩；skill 本身不依赖任何本地路径。

## 目录结构

```
unity2phaser/
├── SKILL.md               # skill 入口：原则 + 八阶段总纲 + 脚本速查
├── references/
│   ├── workflow.md        # 八阶段操作手册（产出格式/出口条件/断点恢复）
│   ├── mapping.md         # Unity→Phaser 概念与 API 映射（坐标/动画/输入/音频/生命周期）
│   ├── pitfalls.md        # 35 个高频坑与自查清单（持续从实战回填）
│   └── acceptance.md      # 验收：自动核销 + 实机试玩剧本 + 诚实记录规范
├── scripts/
│   ├── unpack_unitypackage.py  # 解包 .unitypackage（按 pathname 还原目录）
│   ├── inventory.py            # 盘点：GUID 闭包生成转换契约 + 分层报告
│   ├── verify_output.py        # 核销：素材覆盖/引用扫描/语法检查
│   └── serve.py                # 本地预览服务器
└── assets/
    ├── phaser.min.js           # Phaser 4.2.1（MIT，随 skill 分发）
    └── PHASER-LICENSE.md
```

## 适用范围与边界

- ✅ 适用：2D 小游戏（教育/休闲/益智类），单场景或多场景，UUI 或世界空间，DOTween/Animator 动画，JSON 关卡数据
- ⚠️ 有条件支持：Spine 骨骼动画（需 spine-webgl）、自定义 shader（近似实现）、视频（HTML5 video）
- ❌ 不适用：3D 游戏、重度依赖原生插件的功能（内购、原生 WebView 等）——skill 会如实告知而非硬转

## 实战验证

首个完整实战：蜜蜂填词（BeeLyrics，21 关/105 题）——静态画面与原版视频 10 项对照 9 项一致、1 项修正；逻辑闭环（答题→判定→结算→自动下一题）端到端跑通；实战暴露的 4 个 skill 缺陷已全部回填到坑清单。

## 反馈与迭代

转换结果不满意时，把具体问题（哪个环节、什么现象）反馈给 skill 维护者，或提 Issue；`conversion/` 目录里的契约、核销与验收报告可以帮助定位问题出在哪个阶段。

## 来源与许可

方法论沉淀自真实 Unity→Phaser 迁移实践与《Phaser 游戏创作包-Unity开发者版》的经验总结。

Skill 文档与脚本：[MIT License](LICENSE)。随分发的 `phaser.min.js` 遵循 [Phaser 的 MIT 许可](assets/PHASER-LICENSE.md)。
