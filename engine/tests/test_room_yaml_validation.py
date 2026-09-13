"""Room YAML writes are refused unless the loader could actually use them."""

import pytest

from sage.admin.content_browser import validate_room_yaml_text

GOOD = "id: z:hall\nzone: z\nname: Hall\ntype: chamber\ndescription:\n  base: A hall.\n"


def test_valid_room_passes():
    validate_room_yaml_text("z", "hall", GOOD)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("id: [broken", "invalid_yaml"),
        ("- just\n- a list\n", "invalid_yaml"),
        ("id: z:hall\nzone: z\ntype: chamber\nexits: 5\n", "invalid_room"),
        (GOOD.replace("z:hall", "z:elsewhere"), "id_mismatch"),
    ],
)
def test_bad_rooms_refused(text, reason):
    with pytest.raises(ValueError, match=reason):
        validate_room_yaml_text("z", "hall", text)
