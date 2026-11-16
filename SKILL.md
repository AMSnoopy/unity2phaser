---
name: unity2phaser
description: 将 Unity 2D 小游戏（.unitypackage 导出包、项目文件夹或 ZIP）转换为完整可运行、离线可玩的 Phaser 网页游戏。当用户提到 Unity 转 Phaser/Web/H5、游戏迁移、unitypackage 转换、"把这个 Unity 游戏做成网页版"、游戏移植时使用——即使用户没有说出"转换"二字。覆盖资源迁移、场景重建、C# 逻辑移植、关卡数据迁移、自动核销与实机验收的完整流程。
---

# Unity → Phaser 转换

> **版本**：v1.2（2026-11-16）。更新方式见仓库 README 的「更新」一节：把仓库链接发给 AI 说"更新 skill"即可，目录名不变，覆盖安装。

把一个 Unity 2D 小游戏转换为 **1:1 保真的 Phaser 网页游戏**：界面一致、玩法一致、关卡一致、素材一致。用户上传 Unity 项目后，你按八阶段流程自主完成整个转换，中途不需要用户逐步确认。

设计分辨率参考：目标游戏复杂度 ≈ 单场景、10~20 个游戏脚本、JSON 关卡数据、prefab UI、DOTween 动画、音效/音乐、双语文本。更简单的游戏按同一流程走；明显更复杂的游戏同样按流程走，只是每阶段工作量更大。

## 不可违反的原则

1. **保真**：以还原原版为唯一标准。不简化玩法、不剪短教学与庆祝节奏、不换手势类型、不删关卡。可以更好，但先做到一样。
2. **原素材**：图片/音频/字体一律从原项目复制并保持可用。**禁止重绘或 AI 生成替代已有素材**；缺失才允许生成替代，且必须登记。
3. **完整**：禁止做一半交付。八阶段逐段推进，每阶段有出口条件；停下前必须更新 `progress.md`（断点恢复的唯一依据）。第一版可玩 ≠ 转换完成。
4. **可运行**：交付物必须本地 serve 即玩、离线可用。Phaser 用本 skill 自带的 `assets/phaser.min.js`，禁止 CDN。
5. **诚实**：静态推断 ≠ 实机验证。没有对照证据的写 inferred；修了代码不等于验证通过；差异全部列出，不隐瞒。
6. **范围**：只转"游戏本体"。引擎包源码（Packages/com.unity.*）、平台壳、第三方插件不移植，但游戏代码调用到的插件行为（如 TouchScript 手势、Spine 动画）需用 web 等价实现。3D/重度 shader 依赖无法等价转换时如实说明，不硬转。
7. **增强需授权**：默认转换到验收通过为止。体验增强只在验收全过且用户同意后进行，且不得改动核心玩法。

## 工作区与输出结构

```
<workspace>/
├── unity-source/          # 解包后的 Unity 项目（只读）
└── <game-name>-phaser/    # 输出项目（用户拿走的就是这个目录）
    ├── index.html
    ├── lib/phaser.min.js  # 从本 skill 的 assets/ 复制
    ├── assets/            # 原素材，保持相对目录结构
    ├── src/               # main.js + scenes/*.js (+prefabs/*.js)
    ├── data/              # 关卡/文案 JSON
    └── conversion/        # 过程档案：契约/计划/进度/报告（细节见 references/workflow.md）
```

## 八阶段流程（总纲）

> 详细操作、产出格式、出口条件全部在 **references/workflow.md**；开工先读它。

| # | 阶段 | 核心动作 | 出口条件（简） |
|---|---|---|---|
| 0 | 接收与盘点 | 解包 → `inventory.py` 两次运行（建议→正式 scope）→ 读本体脚本 → 写 `plan.md` | 契约已声明 scope，plan 完成 |
| 1 | 资产迁移 | 按契约复制素材（保持目录结构），登记缺失 | verify 无 asset 缺失 |
| 2 | 工程骨架 | index.html + 本地 phaser + main.js（分辨率/缩放/音频解锁）+ Boot 场景 | serve 打开无报错 |
| 3 | 场景重建 | 逐场景还原布局（坐标/层级/Prefab 覆盖，读 mapping.md §3） | 全场景有文件 + 对照记录 |
| 4 | 逻辑移植 | 逐脚本移植（inventory"游戏本体"清单是硬清单），读 mapping.md §5-7 + pitfalls | 全流程可玩通，脚本状态全记录 |
| 5 | 关卡与内容 | data 迁移 + 数量对账 + 动态加载路径展开 | 关卡数 = 契约数，抽查可玩 |
| 6 | 验收 | `verify_output.py` 核销到 0 error + serve 试玩剧本 A/B/C/D（读 acceptance.md） | 验收门槛全勾 |
| 7 | 增强（可选） | 仅用户同意后；登记前后对照 | 无回归 |

## 脚本速查

```bash
S=<本skill目录>

# 解包 .unitypackage → unity-source/（tar.gz 结构按 pathname 还原）
python "$S/scripts/unpack_unitypackage.py <file.unitypackage> unity-source"

# 盘点（两次：无 scope 看建议 → 带 scope 出正式契约）
python "$S/scripts/inventory.py" --source unity-source --out game-phaser/conversion
python "$S/scripts/inventory.py" --source unity-source \
  --entry Assets/Scenes/X.unity --folder Assets/<游戏目录> --out game-phaser/conversion

# 核销（阶段1/6 运行；exit 0 = 无 error）
python "$S/scripts/verify_output.py" --project game-phaser \
  --inventory game-phaser/conversion/inventory.json \
  [--asset-map game-phaser/conversion/asset-map.json]

# 本地试玩（阶段2/6）
python "$S/scripts/serve.py" --project game-phaser [--port 8768]
```

脚本只依赖 Python 3 标准库（Windows/macOS/Linux 通用）；盘点/核销只读原项目。

## 何时读哪个参考

| 时机 | 读 |
|---|---|
| 开工（阶段 0 前） | references/workflow.md（全文） |
| 阶段 1（素材） | workflow.md 阶段1；遇到改名/转格式再看 asset-map 格式 |
| 阶段 3（布局） | mapping.md §2 §3（两套坐标模型，最高频出错点） |
| 阶段 4（逻辑） | mapping.md §4-§8；**pitfalls.md 全文**（高频坑清单） |
| 阶段 6（验收） | acceptance.md（剧本与门槛） |
| 任何时候不确定"该怎么做对" | pitfalls.md 对应条目 |

## 即死行为（出现即算转换失败）

- 素材缺失但 verify 通过了——不可能；如果你试图改契约让它通过，即失败。
- 用 AI 生成图替代原项目里已有的素材。
- index.html 引用 CDN 的 phaser。
- "转换完成"但 progress.md 没有阶段 6 验收记录。
- 声称"与原版一致"却没有对照证据。
- 玩法被简化（滑动变点选、教学被剪短、关卡被删）且未登记为差异。

## 开场白（对用户）

收到 Unity 项目后，简短确认三件事（用户不知道就自己从盘点推断，不要卡住等待）：
1. 入口场景/游戏目录（inventory 报告可推断）
2. 是否有原版视频/截图可作对照（没有就按源码推断）
3. 输出目录名

然后直接开工。过程中只在**需要取舍**（如：素材缺失怎么补、平台钩子怎么处理）时集中问一次，其余自主推进。
