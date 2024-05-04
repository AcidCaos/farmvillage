from datetime import datetime
import constants

def timestamp_now():
    return int(datetime.now().timestamp())

def world_object_id_is_temporary(world_object_id: int) -> bool:
    return constants.TEMP_ID_START <= world_object_id <= constants.TEMP_ID_END

def world_objects_equal(a: dict, b: dict) -> bool: # , check_temp_id: bool = False) -> bool:
    if a["id"] == b["id"]:
        return True
    # Temp ID system already handles this. Should not be needed.
    # if check_temp_id and ( \
    #     ("tempId" in a and a["tempId"] is not None and a["tempId"] == b["id"]) \
    #     or ("tempId" in b and b["tempId"] is not None and a["id"] == b["tempId"]) \
    #     or ("tempId" in a and "tempId" in b and a["tempId"] is not None and b["tempId"] is not None and a["tempId"] == b["tempId"])
    # ):
    #     return True
    return False

def get_new_world_object_id(world_objects: list) -> int:
    object_ids = [obj["id"] for obj in world_objects]
    next_id = max(object_ids) + 1
    if world_object_id_is_temporary(next_id): # skip temporary ids
            next_id = constants.TEMP_ID_END + 1
    assert not world_object_id_is_temporary(next_id)
    assert not next_id in object_ids
    return next_id
