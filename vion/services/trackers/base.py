from infrastructure.file import json_file


class BaseTracker:
    def __init__(self, file_path):
        self.file_path = file_path

    async def get_all(self) -> dict:
        success, data = await json_file.load(self.file_path)
        return data if success and isinstance(data, dict) else {}
