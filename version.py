
version_name = "pre-alpha 0.01a.2024_03_29"
version_code = "0.01a.2024_03_29"
release_date = 'Friday, 30 March 2024'

def migrate_loaded_save(save: dict):
    
    _changed = False

    # 0.01a saves
    if "version" not in save or save["version"] is None:
        _changed = True
        save["version"] = "0.01a"
        print(" [!] Applied version to save")

    return _changed