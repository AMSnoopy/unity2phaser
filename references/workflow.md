# 转换工作流：八阶段操作手册

SKILL.md 给出流程总纲；本文是每个阶段的详细操作、产出格式与出口条件。**严格按阶段推进，每阶段结束必须满足出口条件并写阶段报告**——这是防止"转换做一半"的核心机制。

## 工作区布局（约定）

```
<workspace>/                      # 本次转换的工作目录
├── unity-source/                 # 解包后的 Unity 项目（只读参考，永不修改）
├── <game-name>-phaser/           # 输出的 Phaser 项目
│   ├── index.html
│   ├── lib/phaser.min.js         # 从 skill assets/ 复制，禁止 CDN
│   ├── assets/                   # 原素材（保持相对目录结构，见阶段1）
│   ├── src/
│   │   ├── main.js               # Phaser.Game 配置与启动
│   │   ├── scenes/*.js           # 每个 Unity 场景一个 Scene 文件
│   │   └── prefabs/*.js          # 复杂 Prefab 的工厂函数（可选）
│   ├── data/                     # 关卡/文案/配置 JSON
│   └── conversion/               # 过程档案（本次转换的"记忆"）
│       ├── inventory.json        # 契约（inventory.py 产出）
│       ├── inventory-report.md
│       ├── plan.md               # 转换计划（阶段0产出）
│       ├── progress.md           # 进度与缺口（唯一断点恢复依据）
│       ├── asset-map.json        # 改名/转换映射（仅需要时）
│       ├── verify-report.md      # 核销报告（verify_output.py 产出）
│       └── acceptance.md         # 试玩验收记录
└── （.unitypackage 原包保留在 workspace 外，不改动）
```

## 断点恢复规则（所有阶段通用）

- `progress.md` 是唯一进度事实源。格式：每阶段一节，状态 ∈ `未开始/进行中/完成`，后跟要点与未决问题。
- **任何时刻停下（会话结束/上下文不足/等待用户），必须先更新 progress.md**：当前阶段、已完成项、下一步、卡点。
- 新会话恢复时：读 `conversion/progress.md` + `inventory.json` + `plan.md` → 从记录的位置继续，**不重新盘点、不推翻已有决定**（除非发现事实错误）。
- 每完成一个阶段：在 progress.md 把该阶段置为"完成"，附阶段报告（见各阶段模板）。

---

## 阶段 0：接收与盘点

**目的**：搞清楚"这是个什么游戏、有什么、转什么"。

1. 确认输入形态：
   - `.unitypackage` → 先解包：`python <skill>/scripts/unpack_unitypackage.py <文件> <workspace>/unity-source`
   - 项目文件夹 / ZIP → 直接（ZIP 先解压）放入 `unity-source/`
2. 运行盘点（先不带 scope，看建议；再带 scope 得到正式契约）：
   ```bash
   # 第一次：了解全貌与建议
   python <skill>/scripts/inventory.py --source unity-source --out game-phaser/conversion
   # 阅读 inventory-report.md，确定游戏本体目录与入口场景
   # 第二次：正式契约
   python <skill>/scripts/inventory.py --source unity-source \
     --entry Assets/.../MainScene.unity --folder Assets/<游戏目录> \
     --out game-phaser/conversion
   ```
3. 读游戏本体脚本（报告"游戏本体"层的全部脚本）+ 入口场景 YAML，理解玩法闭环：**入口 → 教学 → 核心操作 → 判定反馈 → 关卡推进 → 结束 → 重开**。
4. 有原版视频/截图参照时记下关键画面，作为保真对照。

**产出 `conversion/plan.md`**（一页以内）：

```markdown
# 转换计划
## 游戏概述
<一段话：这是什么游戏，核心玩法，目标用户>
## 范围
- 入口场景：…
- 游戏目录：…
- 场景 → Phaser Scene 映射：| Unity 场景 | Scene key | 文件 |
- 需要 reimplement 的插件行为（TouchScript/Spine 等被游戏用到的部分）：…
- 明确不转换的：引擎包、平台壳、…（说明理由）
## 风险与限制
<inventory 的 risks + 你阅读源码发现的：3D/shader/视频/动态路径…>
## 关键行为清单
<从脚本归纳的核心行为：状态机、计分、音效触发点、动画序列——各一条>
## 开放问题
<源码无法确定、需要用户回答的；没有就写"无">
```

**出口条件**：契约 json 存在且 scope 已声明；plan.md 完成；progress.md 初始化（阶段 0 = 完成）。

---

## 阶段 1：资产迁移

**目的**：原素材 100% 进入网页项目，一个不丢，一个不改。

1. 按 `inventory.json` 的 `assets` 清单复制：**保持相对目录结构**复制进 `assets/`（`Assets/AllGame/.../Textures/Main/背景.png` → `assets/.../Main/背景.png`，去掉 Assets 根路径即可）。目录结构一致可以让同名文件天然不冲突，也不需要 asset-map。
2. 不得不改名/转格式时（如去空格、PSD→PNG），**必须**写 `conversion/asset-map.json`：
   ```json
   { "Assets/.../已插入图像.png": { "target": "assets/Player/bee0/bee0.png", "operation": "改名去中文以兼容 URL" } }
   ```
3. 确实缺失/损坏的素材：登记 progress.md 缺口段（原因 + 影响 + 处置），**不许用 AI 生成图静默替代**。
4. 记录每个图片在游戏中的用途推断（读场景 YAML 的 m_Sprite guid 引用），写进 progress.md 素材段（一两行即可，不用全量表格）。

**出口条件**：`python <skill>/scripts/verify_output.py --project game-phaser --inventory game-phaser/conversion/inventory.json`（阶段 1 只看 coverage 部分）无 asset 缺失错误；asset-map（如有）每条都有 operation。

---

## 阶段 2：工程骨架

**目的**：空游戏能跑起来，分辨率/缩放/音频解锁等基建正确。

1. `lib/phaser.min.js` 从 skill `assets/` 复制（版本固定，勿换 CDN）。
2. `index.html`：最小 HTML + canvas 容器 + 引入脚本；`touch-action: none` 防滚动。
3. `src/main.js`：Phaser.Game 配置。
   - **设计分辨率**：优先用场景 Canvas 的参考分辨率（inventory 场景段有 `uiReferenceResolution`）；世界空间游戏用 `orthoSize×2×PPU` 推算（见 mapping.md §3）。
   - **缩放**：`scale: { mode: Phaser.Scale.FIT, autoCenter: CENTER_BOTH }`；朝向按 inventory 的 `defaultOrientation`（横屏游戏可加旋转提示）。
   - 物理（如原游戏有 2D 物理）：`physics: { default: 'arcade' }`。
4. Boot/Preload Scene：加载清单从契约生成（阶段 1 的 assets）；显示加载进度；音频解锁钩子（首个 pointerdown 调 `this.sound.unlock()`，之前入队的声音在解锁后补播——队列实现见 pitfalls #15）。
5. 全局服务：AudioManager（通道队列）、简单 i18n（原游戏多语言时）、存档工具（原游戏用 PlayerPrefs 时）。

**出口条件**：`python <skill>/scripts/serve.py --project game-phaser` 后浏览器打开无报错、能看到加载画面；`node --check` 全绿（无 node 则人工检查）。

**骨架模板要点（防两个真实翻车点）：**
1. **场景方法挂载先于 Game 创建**：`new Phaser.Game({scene:[...]})` 若在场景方法赋值前执行，场景会以空方法启动并永久卡死。标准写法——main.js 只创建 `Phaser.Scene` 实例挂到全局，把 `new Phaser.Game(...)` 延迟到 `window load` 事件（此时全部脚本已执行完）：
   ```js
   if (document.readyState === 'complete') start();
   else window.addEventListener('load', start);
   ```
2. **index.html 的 script 标签必须逐一核对**：lib/phaser.min.js、main.js、每一个 scenes/*.js、audio.js——漏引一个就是"无报错黑屏"。出口检查用 `document.scripts` 对比 src 目录清单。

---

## 阶段 3：场景重建

**目的**：每个 Unity 场景 → 一个 Phaser Scene，布局与原版可对照。

按 plan.md 的映射表逐场景进行；细节规则全部按 mapping.md §2/§3（坐标两套模型、Prefab 覆盖合并、y 轴翻转、pivot→origin）。

1. 从场景 YAML 提取对象树（inventory 已给出挂载脚本清单；对象层级用 YAML 缩进/GameObject 父子链读）。
2. Prefab 实例：打开对应 .prefab 文件，把实例 override 合并到模板值，得到"最终值"，再换算。
3. 静态 UI 布局逐对象还原：位置/尺寸/贴图/文字/层级（sortingOrder → depth）。
4. 每完成一个 Scene，浏览器截图与原版参照（视频帧/原理解截图）目测对照，差异记录。
5. 动态创建的 UI（代码 `new GameObject`/`AddComponent`）此时不建，阶段 4 随逻辑一起实现。

**出口条件**：plan.md 里全部场景都有对应 Scene 文件；静态布局对照差异已记录；progress.md 更新。

---

## 阶段 4：逻辑移植

**目的**：游戏"动起来"，行为与原版一致。

1. 逐个移植 inventory 报告"游戏本体"层脚本（这是硬清单）。每个脚本：
   - 读源码，理解职责与被调用关系（平台层脚本只在被调用处实现等价行为）；
   - 按 mapping.md §5/§6/§7 重写为 JS（合并进 Scene 或 prefabs 工厂；不机械一行对一行）；
   - 在 progress.md 记一行状态：`<脚本> → <JS 位置>：完成/部分/不适用（原因）`。
2. 重点核对（对应 pitfalls 高频项）：
   - DOTween 序列：Append/Join/Insert 的重叠关系 + 秒→毫秒
   - .anim：数值曲线 vs 逐帧换图分开处理
   - 协程 → 状态机/delayedCall 链，重开时要可取消
   - 单例/PlayerPrefs：重开重置
   - 音效触发点与队列优先级：按源码调用点还原
   - 输入：抓取偏移、可交互状态、连续滑动不被简化
3. 平台钩子（原游戏调用 App 层的：计分上报、退出确认、计时器）：实现成占位接口（console/内部实现），在 plan.md 开放问题列出，**不虚构平台功能**。

**出口条件**：游戏从入口玩到结尾全流程可走通（可能有粗糙处）；硬清单每个脚本都有状态记录；无 `setScale(1)` 裸写、无未清理的 window/document 监听。

---

## 阶段 5：关卡与内容

**目的**：内容数量与原版一致。

1. `inventory.json` 的 data 清单（关卡 JSON/文本/配置）迁到 `data/`；**数量必须与契约一致**（如 42 个关卡文件 → 42 关）。原格式基本可直用；有 Unity 特有字段（如 hideFlags）剔除并注明。
2. 动态加载路径（inventory 的 dynamicLoads）：展开成静态清单/索引文件，确认每个 Load 调用在新工程有对应数据。
3. 文本/多语言：按原游戏的字符串表迁移；`WordScriptable` 这类 ScriptableObject 数据（含中文释义/读音）必须完整迁移。
4. 关卡选择/推进逻辑：与原版规则一致（顺序、解锁条件、循环），不自创。

**出口条件**：`data/` 数量对账 = 契约数量；每关可进入可完成（抽查首/中/尾各一关）；progress.md 更新。

---

## 阶段 6：验收

**目的**：证明"转换完整且可玩"。两层验收，标准见 `references/acceptance.md`。

1. 契约核销：`python <skill>/scripts/verify_output.py --project game-phaser --inventory game-phaser/conversion/inventory.json [--asset-map conversion/asset-map.json]` → 修复到 0 error，warning 逐条确认。
2. 实机试玩：`python <skill>/scripts/serve.py` → 按验收剧本 A（完整通关）/ B（错误恢复）/ C（生命周期压力：重开×2）/ D（保真对照）执行，结果写 `conversion/acceptance.md`。
3. 发现问题 → 回对应阶段修复 → 重跑验收。**不允许降标准交付**；客观阻碍如实写明。

**出口条件**：acceptance.md 出口门槛全勾；progress.md 状态"转换完成"。

---

## 阶段 7：增强（可选，默认不进入）

**目的**：在 1:1 基线之上提升体验。**仅在阶段 6 全部通过、且用户明确同意增强时进行。**

- 增强方向参考：引导清晰度、操作响应、帮助与反馈、完整结尾的满足感、动画/声音质感。**不加新玩法、不改学习目标、不动已认可的核心体验。**
- 每项增强登记 `conversion/acceptance.md` 的"有意增强"段：问题 → 改动 → 同条件前后对照。
- 保留基线版本（转换完成时的 acceptance.md + verify-report.md 即为基线证据），增强后重跑阶段 6 核销确认无回归。

**出口条件**：增强清单全部登记且对照完成；verify 仍为 0 error。

---

## 阶段报告模板（每阶段结束贴入 progress.md）

```markdown
### 阶段 N 报告（<阶段名>）- <日期>
- 状态：完成
- 本阶段做了什么：<2-5 条要点>
- 与计划的偏差：<无 / 有+原因>
- 遗留问题：<无 / 列表，每条含影响与下一步>
- 下一步：阶段 N+1 的第一件事
```
