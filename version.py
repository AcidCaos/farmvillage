
version_code = "0.01a"
version_name = "alpha " + version_code

def migrate_loaded_save(save: dict):
    
    _changed = False

    # 0.01a saves
    if "version" not in save or save["version"] is None:
        _changed = True
        save["version"] = "0.01a"
        print("[!] Applied version to save")
    
    # 0.01a.2024_05_04 -> 0.01a.2024_09_16
    if save["version"] == "0.01a":
        if save["userInfo"]["player"]["lonelyAnimalCode"] == 0:
            _changed = True
            save["userInfo"]["player"]["lonelyAnimalCode"] = ""
            print("[!] Fixed lonelyAnimalCode format")

        # client ref.: src/Classes/ExtendedPermissionState.as (hasExtendedPermission)
        # Was stored as a list of permission names, but the client indexes it by name.
        if isinstance(save.get("snExtendedPermissions"), list):
            _changed = True
            save["snExtendedPermissions"] = {perm: True for perm in save["snExtendedPermissions"]}
            print("[!] Fixed snExtendedPermissions format")

        # client ref.: src/Classes/MarketConfigSettings.as (getActiveCarnivalPromotions) - without these,
        # the Carnival Booth's promo grid stays empty (Global.flashHotParams["CARNIVAL_PROMOS_ACTIVE"] is NaN).
        if "CARNIVAL_PROMOS_ACTIVE" not in save["flashHotParams"]:
            _changed = True
            save["flashHotParams"]["CARNIVAL_PROMOS_ACTIVE"] = 6
            save["flashHotParams"]["CARNIVAL_PROMO_DEFAULT"] = "Carnival_Coming_Soon"
            print("[!] Added Carnival Booth flashHotParams")

        # client ref.: src/Widgets/Windows/Pigo/PigoWindow.as - per-token, per-prize win counts.
        if "pigoState" not in save:
            _changed = True
            save["pigoState"] = {}
            print("[!] Added pigoState")

    return _changed