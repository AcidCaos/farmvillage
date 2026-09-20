from items import get_item_by_name, get_item_by_code

# client ref.: src/Classes/storage/StorageItem.as
ITEM_KEY_DELIMITER:str = ":"
METADATA_INDEX_QUANTITY:int = 0
METADATA_INDEX_SENDER_IDS:int = 1
METADATA_INDEX_EXTRADATA:int = 2

# client ref.: src/Classes/FarmGameWorld.as
GIFTBOX_ID:int = -1 
# client ref.: src/Classes/Player.as
HOME_INVENTORY_ID:int = -2
ENGLAND_INVENTORY_ID:int = -8
FISHERMAN_INVENTORY_ID:int = -9
WINTER_WONDERLAND_INVENTORY_ID:int = -10
HAWAII_INVENTORY_ID:int = -11
HALLOW_INVENTORY_ID:int = -14
ASIA_INVENTORY_ID:int = -13
ANGLER_INVENTORY_ID:int = -17
HTOWN_INVENTORY_ID:int = -15
MEADOWS_INVENTORY_ID:int = -16
GLEN_INVENTORY_ID:int = -18
ATLANTIS_INVENTORY_ID:int = -19
GARDEN_INVENTORY_ID:int = -20
AUSTRALIA_INVENTORY_ID:int = -21
SPACE_INVENTORY_ID:int = -22
CANDY_INVENTORY_ID:int = -23
FFOREST_INVENTORY_ID:int = -24
HLIGHTS_INVENTORY_ID:int = -25
RAINFOREST_INVENTORY_ID:int = -26
OZ_INVENTORY_ID:int = -28
VILLAGE_INVENTORY_ID:int = -27
MEDITERRANEAN_INVENTORY_ID:int = -29
OASIS_INVENTORY_ID:int = -31
STORYBOOK_INVENTORY_ID:int = -32
SLEEPYHOLLOW_INVENTORY_ID:int = -33
EASTEROS_INVENTORY_ID:int = -35
TOYLAND_INVENTORY_ID:int = -34
AVALON_INVENTORY_ID:int = -35
WILDWEST_INVENTORY_ID:int = -36
TREASURETIDES_INVENTORY_ID:int = -37
AFRICA_INVENTORY_ID:int = -38
TRANSYLVANIA_INVENTORY_ID:int = -39
WINTER_INVENTORY_ID:int = -40
JAPAN_INVENTORY_ID:int = -42
INDIA_INVENTORY_ID:int = -41
JUNGLE_INVENTORY_ID:int = -43
MOUNT_INVENTORY_ID:int = -44
LIMBO_INVENTORY_ID:int = -45
XMAS_INVENTORY_ID:int = -46
MIDWEST_INVENTORY_ID:int = -47
TURTLEISLAND_INVENTORY_ID:int = -49
UNDERWATER_INVENTORY_ID:int = -48
DREAMWORLD_INVENTORY_ID:int = -50
BRAZIL_INVENTORY_ID:int = -52

_INVENTORY_ID_NAME_MAP = {globals()[name]: name for name in globals().keys() if name.endswith("_INVENTORY_ID") or name == "GIFTBOX_ID"}
def get_inventory_group_name_by_id(inventory_id) -> str:
    n = _INVENTORY_ID_NAME_MAP.get(inventory_id)
    if not n:
        return None
    return n.replace("_ID", "").replace("_", " ")


def _adjust_quantity(entry: list, delta: int, trim_extra_data: bool = True) -> None:
    # client ref.: src/Classes/storage/StorageItem.as (adjustQuantity)
    # extraData holds one entry per unit, so a drop in quantity throws the oldest ones away from the front.
    entry[METADATA_INDEX_QUANTITY] += delta
    if trim_extra_data:
        extra_data = entry[METADATA_INDEX_EXTRADATA]
        while extra_data and len(extra_data) > entry[METADATA_INDEX_QUANTITY]:
            extra_data.pop(0)


def store_deposit_item_by_name(save: dict, item_name: str, amount: int = 1, group: int = HOME_INVENTORY_ID, sender: str = "0") -> bool:
    assert amount > 0

    item_data = get_item_by_name(item_name)
    assert item_data is not None

    item_code = item_data["code"]
    storage = save["userInfo"]["player"]["storageData"]
    group_key = str(group)

    if group_key not in storage:
        storage[group_key] = {}
    if item_code in storage[group_key]:
        storage[group_key][item_code][METADATA_INDEX_QUANTITY] += amount
    else:
        storage[group_key][item_code] = [amount, [], []] # client ref.: src/Classes/Player.as (loadInventoryFromStorageData)

    # client ref.: src/Classes/Player.as (addGift) - one sender id per gift, not per unit, and "0" means
    # "not from a player" (the gift box then shows the generic FarmVille sender).
    if sender != "0":
        storage[group_key][item_code][METADATA_INDEX_SENDER_IDS].append(sender)

    print(" * Stored: {}x {} (code {}) to {}".format(amount, item_name, item_code, get_inventory_group_name_by_id(group)))
    return True


def store_withdraw_item_by_name(save: dict, item_name: str, amount: int = 1, group: int = HOME_INVENTORY_ID) -> bool:
    return store_withdraw_item_by_code(save, get_item_by_name(item_name)["code"], amount, group)


def store_withdraw_item_by_code(save: dict, item_code: str, amount: int = 1, group: int = HOME_INVENTORY_ID, trim_extra_data: bool = True) -> bool:
    storage = save["userInfo"]["player"]["storageData"]
    group_key = str(group)
    entry = storage.get(group_key, {}).get(item_code)
    if entry is None:
        return False

    _adjust_quantity(entry, -amount, trim_extra_data)
    if entry[METADATA_INDEX_QUANTITY] <= 0:
        del storage[group_key][item_code]
    elif entry[METADATA_INDEX_SENDER_IDS]:
        # client ref.: src/Classes/Player.as (removeGiftWithKey -> shiftSenderId): exactly one sender id
        # goes, however many units were taken, and only while the entry survives.
        entry[METADATA_INDEX_SENDER_IDS].pop(0)

    item_data = get_item_by_code(item_code)
    item_name = item_data["name"] if item_data else item_code
    print(" * Storage Withdrawal: {}x {} (code {}) from {}".format(amount, item_name, item_code, get_inventory_group_name_by_id(group)))
    return True


def consume_by_name(save: dict, item_name: str, count, group):
    item = get_item_by_name(item_name)
    if item['type'] == "consumable" or item['className'] == 'CRewardConsumable': # TODO check this properly
        packaged_items = item["rewards"]["reward"]
        if packaged_items["type"] == "item_grant":
            packed_item_name = get_item_by_code(packaged_items["value"])["name"]
            packed_item_quantity = int(packaged_items["quantity"])
            print(f" * Consume {count}x {item_name} -> {count * packaged_items['quantity']}x {packed_item_name}")
            store_deposit_item_by_name(save, item_name=packed_item_name, amount=count * packed_item_quantity, group=group)
            store_withdraw_item_by_name(save, item_name=item_name, amount=count, group=group)
        else:
                raise Exception("Not Implemented reward", packaged_items)
    else:
        raise Exception("Not Implemented consume", item_name)
            

def remove_gift_by_code(save: dict, code: str, amount: int = 1, meta_index=-1) -> bool:
    # client ref.: src/Classes/Player.as (removeGiftWithKey)
    if meta_index < 0:
        return store_withdraw_item_by_code(save, item_code=code, amount=amount, group=GIFTBOX_ID)

    # A meta_index names one exact unit (a bred animal's mutable state, a UGC item's uuid): the client
    # splices that entry out of extraData instead of trimming the front, so trimming stays off here.
    entry = save["userInfo"]["player"]["storageData"].get(str(GIFTBOX_ID), {}).get(code)
    extra_data = entry[METADATA_INDEX_EXTRADATA] if entry else []
    result = store_withdraw_item_by_code(save, item_code=code, amount=amount, group=GIFTBOX_ID,
                                         trim_extra_data=False)
    if result and meta_index < len(extra_data):
        extra_data.pop(meta_index)
    return result
