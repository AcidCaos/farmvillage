#!/usr/bin/env python3
"""Run the isolated server-mechanics regressions, excluding Deco and UI tests.

From the FarmVillage directory:
    LocalData/venv/bin/python -B macOS/Scripts/run-other-mechanics-regressions.py

The persistence fixture must load before product modules so every save and
catalog cache is written under its temporary data directory.
"""

from pathlib import Path
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "macOS" / "Tests"))

import test_persistence  # noqa: E402,F401 -- establishes isolation first


MODULES = (
    "test_persistence",
    "test_october_village",
    "test_october_creation",
    "test_october_actions",
    "test_october_presentation",
    "test_october_presentation_routes",
    "test_native_launcher_presets",
    "test_minion_backups",
    "test_barn_actions",
    "test_breeding",
    "test_breeding_wire",
    "test_client_catalog",
    "test_construction",
    "test_construction_wire",
    "test_core_actions",
    "test_action_ledger",
    "test_crafting",
    "test_cottage_lifecycle",
    "test_cottage_recipes",
    "test_feature_availability",
    "test_level_progression_1_100",
    "test_market_availability",
    "test_equipment_wire",
    "test_gifts_storage",
    "test_levels",
    "test_market",
    "test_market_dates",
    "test_minion_commands_equipment",
    "test_minion_commands_pricing",
    "test_minion_player_storage_options",
    "test_minion_round3_commands",
    "test_minion_round3_quests",
    "test_peaceful",
    "test_progression",
    "test_quest_actions",
    "test_motd_wire",
    "test_world_travel",
    "test_world_travel_review",
    "test_creative_worlds",
    "test_cove_rules",
    "test_cove_travel",
    "test_cove_cellar",
    "test_themed_worlds",
    "test_hallow_rules",
    "test_hallow_world_rules",
    "test_hawaii_rules",
    "test_world_currency_conversion",
    "test_instantgrow_worlds",
    "test_shared_farming_loop",
    "test_inventory_capacity",
    "test_enabled_farms_regression",
    "test_additional_farms_http",
    "test_client_england",
    "test_england_progression",
    "test_pets",
    "test_minigames",
)


def main():
    started = time.monotonic()
    print("Interpreter:", sys.executable, flush=True)
    print("Isolation: test_persistence loaded before product modules", flush=True)
    print("Modules (%d): %s" % (len(MODULES), ", ".join(MODULES)), flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    print("Collected:", suite.countTestCases(), flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(
        "FINAL_RESULT tests=%d failures=%d errors=%d skipped=%d elapsed=%.3fs"
        % (
            result.testsRun,
            len(result.failures),
            len(result.errors),
            len(result.skipped),
            time.monotonic() - started,
        ),
        flush=True,
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
