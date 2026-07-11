def sync_chat_history(storage, item_key, messages, unique_key=None):
    storage.setItem(item_key, messages, key=unique_key or f"{item_key}_set")


def delete_chat_history(storage, item_key, unique_key=None):
    storage.deleteItem(item_key, key=unique_key or f"{item_key}_delete")
