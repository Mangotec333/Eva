"""Baseline offline tests for drive_organizer match_folder (google libs stubbed)."""

import sys
import types

# The module imports the Google Drive client stack at import time; those packages
# are not installed in the offline test env, so provide lightweight stubs. No
# stubbed function is exercised — only pure match_folder logic is tested.
for name in (
    "google", "google.oauth2", "google.oauth2.credentials",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "google_auth_oauthlib", "google_auth_oauthlib.flow",
    "googleapiclient", "googleapiclient.discovery",
):
    sys.modules.setdefault(name, types.ModuleType(name))

sys.modules["google.oauth2.credentials"].Credentials = object
sys.modules["google_auth_oauthlib.flow"].InstalledAppFlow = object
sys.modules["google.auth.transport.requests"].Request = object
sys.modules["googleapiclient.discovery"].build = lambda *a, **k: None

import drive_organizer  # noqa: E402


def test_match_folder_maps_known_patterns():
    assert drive_organizer.match_folder("empire_flippers_marketplace.xlsx") == "EVA/Deal Intelligence"
    assert drive_organizer.match_folder("EVA_STATUS.md") == "EVA/Architecture"
    assert drive_organizer.match_folder("linkedin_post_templates.md") == "EVA/Personal Brand"


def test_match_folder_unmatched_goes_to_misc():
    assert drive_organizer.match_folder("random_unrelated_file.txt") == "EVA/Misc"


def test_folder_map_has_expected_categories():
    assert "EVA/Financial" in drive_organizer.FOLDER_MAP
    assert "EVA/Operations" in drive_organizer.FOLDER_MAP
