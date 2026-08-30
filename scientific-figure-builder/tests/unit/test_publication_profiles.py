from figure_tools.publication_profiles import get_publication_profile


def test_nature_research_profile_preserves_official_publication_constraints():
    profile = get_publication_profile("nature_research")

    assert profile["widths_mm"] == [89, 183]
    assert profile["maximum_height_mm"] == 170
    assert profile["ordinary_text_pt"] == [5, 7]
    assert profile["panel_label_pt"] == 8
    assert profile["font_families"] == ["Arial", "Helvetica"]
    assert profile["editable_vectors"] is True
    assert "drop_shadows" in profile["forbidden_elements"]


def test_general_profile_remains_available():
    assert get_publication_profile("general")["profile_id"] == "general"
