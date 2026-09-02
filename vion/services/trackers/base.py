"""
Base tracker class implementation.

Provides shared JSON loading routines for underlying metrics and event storage files.
"""

from infrastructure.file import json_file


class BaseTracker:
	"""
	Base class for managing file-backed tracking data.

	Attributes:
		file_path: Path to the target JSON backing storage file.
	"""

	def __init__(self, file_path):
		"""
		Initialize BaseTracker with a target file path.

		Args:
			file_path: Path to storage JSON file.
		"""
		self.file_path = file_path

	async def get_all(self) -> dict:
		"""
		Load and return all stored tracking data.

		Returns:
			Loaded data dictionary, or empty dict if missing or invalid.
		"""
		success, data = await json_file.load(self.file_path)
		return data if success and isinstance(data, dict) else {}
