"""Top-level plot renderer: ties spec, data, recipes, and exporters together."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from figure_tools.export.exporters import save_figure
from figure_tools.plotting.data import build_data_used, load_source_data
from figure_tools.plotting.recipes import render
from figure_tools.plotting.spec import PlotSpec
from figure_tools.validation.plot_checks import validate_plot_data
from figure_tools.vector.svg_normalize import resolve_export_target


def render_plot(
    spec: PlotSpec,
    output_dir: str | Path,
    base_dir: str | Path | None = None,
    basename: str = "plot",
    export_target: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """端到端渲染一个绘图规格（plot spec）。

    读取 ``spec`` 引用的源数据，构建精确的 ``data_used`` 数据表，绘制图形，
    并把图形文件、``data_used.csv`` 和 ``layout_manifest.json`` 写入 ``output_dir``。

    参数说明：

    - ``spec``：``PlotSpec`` 对象，描述要画的图，包括 ``source_data``（源数据相对路径）、
      ``export``（导出格式、dpi、导出目标等）以及具体的绘图配方。
    - ``output_dir``：产物输出目录，图片、``data_used.csv``、``layout_manifest.json``
      都写到这里。
    - ``base_dir``：解析 ``spec.source_data["path"]`` 的基目录；为 ``None`` 时使用当前
      工作目录（``Path.cwd()``）。
    - ``basename``：输出文件名的主干（不含扩展名），默认 ``"plot"``。
    - ``export_target``：导出目标标识；为 ``None`` 时回退到
      ``spec.export.get("export_target", "general")``，再统一解析成合法目标。
    - ``run_id``：本次运行的标识，用于串起校验报告，便于追溯。

    返回值：``dict``，包含 ``"files"``（键为产物名、值为输出路径字符串的字典）和
    ``"validation_report"``（本次运行的绘图数据校验报告）。

    示例：

    ```python
    from figure_tools.plotting.spec import PlotSpec
    from figure_tools.plotting.renderer import render_plot

    spec = PlotSpec(
        source_data={"path": "data/spectrum.csv"},
        export={"formats": ["png", "svg"], "dpi": 300},
    )
    result = render_plot(
        spec,
        output_dir="outputs/f1",
        base_dir="projects/grating",
        basename="f1_spectrum",
        export_target="journal",
        run_id="run-20260911-001",
    )
    print(result["files"]["png"])          # e.g. outputs/f1/f1_spectrum.png
    print(result["validation_report"])     # 校验报告
    ```
    """
    # 先解析路径并加载数据，再开始绘制，让错误尽早暴露。
    base = Path(base_dir) if base_dir else Path.cwd()
    src_path = base / spec.source_data["path"]
    source = load_source_data(src_path)
    data_used = build_data_used(spec, source)
    export_target = resolve_export_target(
        export_target or spec.export.get("export_target", "general")
    )

    # 绘制图形，随后落盘产物并做校验；无论成功与否都要关闭图形。
    fig = render(spec, data_used)
    try:
        # 源级布局提取（方案第 8 节）：先绘制一次，让每个图元都有真实的像素
        # 包围盒，然后再写出版面清单。
        fig.canvas.draw()
        from figure_tools.validation.extractors.matplotlib import (
            extract_matplotlib_layout,
        )
        from figure_tools.validation.models import write_layout_manifest

        layout = extract_matplotlib_layout(fig=fig, artifact_id=f"plot:{basename}")
        out_dir = Path(output_dir)
        layout_path = write_layout_manifest(out_dir / "layout_manifest.json", layout)

        files = save_figure(
            fig,
            out_dir,
            basename=basename,
            formats=tuple(spec.export["formats"]),
            dpi=spec.export.get("dpi", 300),
            export_target=export_target,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        data_used_path = out_dir / "data_used.csv"
        data_used.to_csv(data_used_path, index=False)
        files["data_used.csv"] = data_used_path
        files["layout_manifest.json"] = layout_path
        validation_report = validate_plot_data(
            spec, source, data_used, source_path=src_path, run_id=run_id,
        )
    finally:
        plt.close(fig)

    return {
        "files": {k: str(v) for k, v in files.items()},
        "validation_report": validation_report,
    }
