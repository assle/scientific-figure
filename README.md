# Scientific Figure Builder

从自然语言需求到可发表的科研论文配图：自动分解任务、路由到正确引擎（Python 数据图 / SVG / Ark 图像模型）、校验、拼装最终 PNG/SVG/PDF。

## 效果

| 折线图 | 热图 | 多面板 |
|---|---|---|
| ![line](assets/example_line_plot.png) | ![heatmap](assets/example_heatmap.png) | ![multipanel](assets/example_multipanel.png) |

## 核心能力

- **数据图**：CSV -> 折线/散点/柱状/热图/误差棒/多面板，跨运行字节级可复现
- **AI 素材**：Ark 图像模型生成隔离的非量化素材（设备示意图等），自动去背景
- **SVG 标签**：箭头、公式、标注，确定性生成
- **自动拼装**：多元素按 z-order 合成，导出 PNG/SVG/PDF
- **两层校验**：确定性几何规则 + 多模态 VLM 审核，错误阻断导出
- **可复现**：版本化 run 目录、缓存、断点恢复

## 安装

```bash
./install.sh
```

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/)、[OpenCode](https://opencode.ai/)。

## 配置

```bash
export ARK_API_KEY="<key>"
export ARK_API_KEY_CODING="<coding key>"
export ARK_IMAGE_GENERATE="<model id>"
export ARK_IMAGE_EDIT="<model id>"
export ARK_VISION_ANALYZE="<model id>"
export ARK_VISION_VALIDATE="<model id>"
```

纯本地绘图无需配置：`./install.sh --without-ark`

## 使用

```text
使用 scientific-figure-builder，根据 data.csv 画一张论文用折线图
```

或用命令：

```bash
/scientific-figure init
/scientific-figure plan 根据 data.csv 生成双面板科研图
/scientific-figure run
/scientific-figure validate
/scientific-figure export
```

## 开发

```bash
cd scientific-figure-builder
uv sync
uv run pytest
```

## License

[MIT](./LICENSE)
