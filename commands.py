from datetime import datetime
import json

from player import get_player

def init_user(UID):
    data = get_player(UID)
    return data
