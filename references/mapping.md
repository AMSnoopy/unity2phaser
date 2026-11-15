# Unity → Phaser 概念映射

转换不是逐行翻译 C#，而是"理解原游戏在做什么，再用 Phaser 的惯用方式重写"。本文是概念与 API 对应表；先理解意图，再查表落实细节。所有建议以 Phaser 3/4 通用 API 为准。

## 1. 工程概念对应

| Unity | Phaser | 说明 |
|---|---|---|
| 项目 (Project) | 输出目录 `index.html + src/ + assets/ + data/` | 独立可运行网页项目，见 SKILL.md 输出结构 |
| Build Settings 场景列表 | `scene: [...]` 数组（main.js） | 数组顺序 = 启动顺序，第一个是入口场景 |
| Scene (.unity) | `Phaser.Scene` 子类 | 一个 Unity 场景 → 一个 Phaser Scene 类 |
| GameObject | `Phaser.GameObjects.*`（Sprite/Image/Text/Container…） | Unity 的空节点+组件 → Phaser 直接创建具体对象 |
| Prefab | 工厂函数 / 类（`src/prefabs/*.js`） | 没有直接等价物；把 Prefab 结构写成返回配置好的对象组的工厂函数。嵌套 Prefab 的属性覆盖必须合并后再用 |
| Prefab 变体 / override | 工厂函数参数 | 覆盖值是"最终生效值"，序列化文件里的嵌套覆盖要递归合并 |
| Component (MonoBehaviour) | Scene 内的更新逻辑 / 独立类 | 多个组件共享一个对象时，合并进对象工厂或 Scene；不要机械一对一 |
| ScriptableObject | `data/*.json` 常量 | 配置数据用 JSON；带行为的 SO 把行为并入使用它的系统 |
| Resources.Load("path") | 预加载进 `this.load` + key 引用 | Phaser 需要在 preload 阶段显式加载；动态路径要在转换时展开成静态清单 |
| AssetBundle / Addressables | 预加载清单 | 全部改为 preload；运行时远程下载一律摊平 |
| PlayerPrefs | `localStorage`（包一层工具函数） | 注意隐私模式可能抛异常 |
| Time.deltaTime | Scene `update(time, delta)` 的 `delta` | Unity 秒 → Phaser 毫秒；`delta` 已是毫秒 |
| Time.timeScale | `this.time.timeScale` / tween timeScale | |
| Camera.main（正交） | 主 Camera | 见 §3 坐标换算 |
| Sorting Layer / Order in Layer | `setDepth(z)` | Phaser 无分层概念，用 depth 数值；按原 SortingOrder 造出同序数值 |
| Mask (RectMask2D / Sprite Mask) | `setGeometryMask` / `setBitmapMask` | |
| Canvas (Screen Space - Overlay) | DOM/固定层 UI 或 setScrollFactor(0) 的容器 | UI 不随摄像机滚动 |
| World Space Canvas | 世界坐标容器 | 与 UI 坐标模型不同，勿混用公式 |
| Coroutine (IEnumerator) | `time.delayedCall` / tween 链 / async 状态标志 | 见 §5 |
| UnityEvent / C# event | 回调函数 / `events`（Phaser.Events.EventEmitter） | |
| [SerializeField] 字段 | 场景 YAML 里的同名属性 → 常量或 JSON 配置 | 序列化值就是"Inspector 里填的值"，从场景/Prefab YAML 读出 |
| DontDestroyOnLoad 单例 | 全局 registry / `game.registry` 或模块级单例 | 注意重开时要重置状态 |

## 2. 渲染与显示

| Unity | Phaser |
|---|---|
| SpriteRenderer | `this.add.sprite/image` |
| Sprite Editor 切图（图集单图） | atlas：`this.load.atlas(key, png, json)` + 帧名；或在 preload 用 `addSpriteSheet` |
| SpriteAtlas (.spriteatlas) | 打包后的图集 png + atlas JSON；没有打包数据时按 meta 里的 sprite 矩形手工切分 |
| Sprite pivot | `setOrigin(x, y)`（Unity pivot (px,py) 归一化后同值；注意 Phaser origin 也是 0~1） |
| Pixels Per Unit (PPU) | 无对应；决定"世界单位→像素"换算比例，见 §3 |
| SpriteRenderer.color / material tint | `setTint(0xRRGGBB)` |
| CanvasGroup.alpha | `setAlpha()` |
| Line/Trail/粒子 (ParticleSystem) | Graphics 手绘 / `this.add.particles`；复杂粒子可降级为简化版并登记 |
| Shaders / URP 特效 | 无直接等价；常见效果用 tint、blendMode、mask、Camera flash/shake 近似；做不到的登记为差异 |
| 分辨率 / CanvasScaler | `scale: { mode: Phaser.Scale.FIT, width, height }`，设计分辨率取原参考分辨率 |

## 3. 坐标与布局（最高频出错点）

**两套坐标模型，绝不混用公式：**

- **世界空间（正交摄像机）**：视野高 = `orthographicSize × 2`（单位），宽 = 高 × aspect。像素换算：`像素 = 单位 × PPU`（如 PPU=100，orthographicSize=5 → 逻辑高度 1000px）。取场景 Camera 的 `orthographic size` 与实际宽高比算出视野，再放对象。
- **UI 空间（RectTransform）**：由 CanvasScaler 的 ReferenceResolution 决定逻辑画布；子元素位置由 **anchors + pivot + anchoredPosition + sizeDelta** 共同决定，先解析父容器，再算子元素局部坐标。stretch 锚点（anchorMin≠anchorMax）的 sizeDelta 是边距不是尺寸。

**换算步骤（每次布局都按此顺序）：**
1. 找到父链：场景对象 → Prefab 实例（合并 override）→ 根 Canvas / 摄像机。
2. 算父容器的实际矩形（位置+尺寸）。
3. 子元素：`局部位置 = anchoredPosition + (锚点在父矩形中的位置) − pivot×自身尺寸`；y 轴翻转（见下）。
4. 拿一个**带旋转或非中心 pivot** 的真实对象当对照组，验证公式只翻转一次，防止翻转两次又翻回来。

**y 轴**：Unity UI/世界坐标 y 向上，Phaser y 向下。序列化数据里的 `m_LocalPosition.y`、`m_AnchoredPosition.y` 在换算后要取反（旋转角度同理：Unity 逆时针为正，Phaser `angle` 顺时针为正，取反）。

**缩放基准**：`setDisplaySize(w,h)` 会改 `scaleX/scaleY`。定尺寸后立即保存 `sprite.baseScaleX/scaleY`，之后呼吸/点击/成功动画一律 `baseScaleX × k`，**永远不要写回 `setScale(1)`**，否则纹理原始尺寸会突然撑爆画面。

## 4. 资源：图、字体、音频

| Unity | Phaser |
|---|---|
| Texture (png/jpg) | 直接复制，`this.load.image(key, url)`；**文件名即 key 的建议来源，保持原文件名** |
| Texture meta: spriteMode=Multiple + spriteID/spriteBorder | 需要 atlas JSON（frames 矩形 + pivot + 9-slice border）；按 .meta 数据生成 |
| PSD/PSB 源文件 | 跳过（那是编辑源）；用项目里已有的 png 导出 |
| 字体 (.ttf/.otf) | 复制后 CSS `@font-face` + `document.fonts.ready` 等待；Text 用 `fontFamily` 引用 |
| TextMeshPro 资产 | 找到其引用的底层 ttf/otf；TMP 的材质/描边/间距参数换算成 Phaser Text style 或 DOM；缺字要登记 |
| AudioClip (wav/mp3/ogg) | 直接复制；浏览器兼容优先 ogg/mp3，wav 体积大可保留但注意加载时间 |
| AudioSource: playOnAwake/loop/volume/pitch | `this.sound.play(key, {loop, volume, rate})`；BGM 用专门管理器 |
| AudioMixer 分组/淡入淡出 | 简化为按通道的音量控制 + tween 音量；复杂混音登记差异 |
| 视频 (VideoClip) | HTML5 `<video>`；格式不兼容时登记 |

**铁律：已有素材一律复制原文件，禁止重绘、AI 生成替代或"找张相似的图"。** 只有素材在原项目里确实缺失时才允许生成替代，且必须在 progress.md 登记为缺口。

## 5. C# 惯用法 → JS 模式

| C# | JS/Phaser |
|---|---|
| `void Update()` | Scene `update(time, delta)`；多个组件的 Update 合并进一个 Scene update，注意原执行顺序（组件在 Inspector 里的顺序） |
| `Invoke("Fn", 2f)` | `this.time.delayedCall(2000, fn)` |
| `StartCoroutine(Fn())` + `yield return new WaitForSeconds(1f)` | 拆成 delayedCall 链，或写一个带 `elapsed` 状态的小状态机；**嵌套 yield/while 循环**优先改写成显式状态机，避免 setTimeout 传染 |
| `yield return null`（等一帧） | `update` 里下一帧处理，或 `time.delayedCall(0,…)` |
| `AsyncOperation` / `await` | 原生 Promise；注意取消（见 lifecycle） |
| DOTween `Append` / `Join` / `Insert` / `SetDelay` / `SetEase` / `OnComplete` | `tweens.timeline({ tweens: [...] })`（顺序）/ 同一 start 并行 / `tween.stop()`；**秒→毫秒 ×1000**；ease 对照：OutQuad≈`'Quad.easeOut'` 等 |
| `.anim` 数值曲线（位置/缩放/透明度） | 关键帧 → `tweens.timeline` 逐段近似；保留关键帧节奏，别拉直成匀速 |
| `.anim` 的 PPtrCurves（逐帧换图） | `this.load.spritesheet` 或 atlas + `sprite.play('anim')`；按 `m_Time`/sampleRate 还原帧率 |
| Animator 状态机 | 简单的：一个状态枚举 + 切换函数；复杂的：每个状态一段动画代码 + events 触发；AnimatorEvent → tween onComplete / 自定义事件 |
| Rigidbody2D + Collider2D | Arcade Physics：`this.physics.add.sprite` + `body.setSize/setOffset`（对齐原碰撞盒大小/偏移）；isTrigger → `overlap` 而非 `collider` |
| Rigidbody2D 重力/常数 | `physics.gravity` / `body.setGravityY`；Unity 重力标量 −9.81×scale 按实际效果校准 |
| OnPointerClick / IBeginDrag… | `setInteractive()` + `on('pointerdown/up/move/out')`；拖动用 `setDraggable` 或手写 pointer 跟踪（保留抓取偏移，见 pitfalls） |
| Button.onClick | `on('pointerdown')` + 点击态贴图切换 |
| SceneManager.LoadScene("X") | `this.scene.start('X')`；Additive → `this.scene.launch` |
| Instantiate(prefab) | 工厂函数调用 |
| Destroy(obj, delay) | `obj.destroy()` + delayedCall；对象池（原游戏有复用逻辑时）用数组回收 |
| JsonUtility.FromJson | `JSON.parse` + 手工字段对齐 |
| `#if UNITY_EDITOR` / 平台宏 | 删除分支，按目标平台行为 |
| 单例 `Instance` | 模块级导出对象；**重开游戏时必须重置全部状态** |

## 6. 生命周期与清理

Unity 的对象销毁由引擎 GC 完成，Phaser/浏览器里**监听器、计时器、补间、音频不会自动清理**。每个 Scene 的对应关系：

| Unity | Phaser + 必须做的清理 |
|---|---|
| OnEnable/OnDisable | `scene.start` 的 `create` / `scene.shutdown` 事件；shutdown 里移除本 Scene 之外的全局监听 |
| OnDestroy | `events.on('shutdown'/'destroy')`：停 tween、停 delayedCall、解绑 window/document 级监听、停声音 |
| Awake 单例初始化 | Scene `init()`/`create()` 开头；重开不叠加 BGM——启动前先 stop 旧的 |
| DontDestroyOnLoad 音乐 | 一个独立 Audio 管理器（game 级，非 scene 级），换 Scene 不重启 BGM，游戏完全退出才销毁 |

**重开（Restart/Replay）是最高危场景**：旧 tween、旧 delayedCall、旧监听器、旧 BGM 叠加、旧 async 回调落在新一局对象上。规则：重开前先完整销毁再重建，或逐项登记清理；测试必测"玩到一半重开两次"。

## 7. 输入

| Unity | Phaser |
|---|---|
| Input.GetMouseButton(0) / OnMouse* | `this.input.on('pointerdown'/'pointerup'/'pointermove')` |
| EventSystem 射线检测 UI | Phaser 交互对象自动命中；注意 `input.topOnly` 与 depth 的关系 |
| 拖动（IDragHandler） | `setInteractive({draggable:true})` + `on('drag')`；**保留手指与对象中心的抓取偏移**：`dragX = pointer.x − dragOffsetX` |
| Input.GetAxis（键盘） | `this.input.keyboard.addKeys(...)`；儿童游戏多为触屏，键盘操控若原版没有就不加 |
| 触摸多点 | `pointer.id` 区分；一次只允许一个活动手势时锁 `activePointer` |
| 手势（滑动判定） | pointerdown 记录起点，pointerup 算位移/速度/方向阈值 |

浏览器前置：**音频必须等首次真实用户手势后解锁**（`this.sound.unlock()` 或首个 pointerdown 后再播）；本地静音调试不破坏队列时序。

## 8. 文本与本地化

| Unity | Phaser |
|---|---|
| UI.Text / TMP 文本 | `this.add.text(x, y, str, style)`；中文注意字体字形覆盖与 fallback 链 |
| 富文本/描边/阴影 | style：`stroke`/`strokeThickness`/`shadow`；复杂排版（自动换行规则不同）对照原版截图校准 |
| 本地化表 | `data/i18n/*.json`，启动时按语言载入 |
