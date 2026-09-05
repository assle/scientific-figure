from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from figure_tools.imaging.background_removal import remove_background


def test_background_removal_preserves_light_region_enclosed_by_subject(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 55, 55), fill=(90, 110, 130))
    draw.ellipse((20, 20, 43, 43), fill="white")
    image.save(source)

    assert remove_background(source, output) is True

    alpha = Image.open(output).getchannel("A")
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((32, 32)) == 255
