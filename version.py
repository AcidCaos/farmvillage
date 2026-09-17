
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

    return _changed