from PIL import Image, ImageDraw

from figure_tools.imaging.edit_validation import evaluate_local_edit


def _asset(path, color):
    image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((384, 384, 640, 640), fill=color)
    image.save(path)


def test_local_edit_requires_the_target_check_to_improve(tmp_path):
    parent = tmp_path / "parent.png"
    edited = tmp_path / "edited.png"
    _asset(parent, (200, 40, 40, 255))
    _asset(edited, (40, 80, 220, 255))

    outcome = evaluate_local_edit(parent, edited, target_improved=False)

    assert outcome["accepted"] is False
    assert outcome["reason"] == "edited asset did not improve the target check"
