
version_code = "0.01a.2024_04_07"
version_name = "pre-alpha " + version_code
release_date = 'Sunday, 7 April 2024'

def migrate_loaded_save(save: dict):
    
    _changed = False

    # 0.01a saves
    if "version" not in save or save["version"] is None:
        _changed = True
        save["version"] = "0.01a"
        print(" [!] Applied version to save")

    return _changed