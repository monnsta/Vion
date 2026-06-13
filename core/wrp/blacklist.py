import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.lib.file import json_file
from meta import config, file


log = logging.getLogger(__name__)


class Blacklist:
	@staticmethod
	def _now() -> datetime:
		return datetime.now(config.timezone)

	def _parse_duration(self, duration: str) -> Optional[str]:
		try:
			amount = int(duration[:-1])
			unit = duration[-1].lower()

			if unit == "d":
				delta = timedelta(days=amount)
			elif unit == "h":
				delta = timedelta(hours=amount)
			elif unit == "m":
				delta = timedelta(minutes=amount)
			else:
				log.debug(f"Invalid duration unit: {unit}")
				return None

			expiry = (self._now() + delta).isoformat()
			log.debug(f"Parsed duration {duration} to expire at {expiry}")
			return expiry
		except Exception as e:
			log.error(f"Failed to parse duration '{duration}': {e}")
			return None

	async def _get_data(self) -> Tuple[bool, Dict[str, Dict[str, Any]]]:
		success, data = await json_file.load(file.glob.blacklist)

		if "server" not in data: data["server"] = {}
		if "user" not in data: data["user"] = {}

		if not success and not data:
			return False, data

		now = self._now()
		modified = False
		expired_count = 0

		for e_type in ("server", "user"):
			for e_id in list(data[e_type].keys()):
				entry = data[e_type][e_id]
				if entry.get("expires_at"):
					expiry = datetime.fromisoformat(entry["expires_at"])
					if expiry <= now:
						del data[e_type][e_id]
						expired_count += 1
						modified = True

		if modified:
			await json_file.save(file.glob.blacklist, data)

		return True, data


	async def add(self, entity_id: int, entity_type: str, mod_id: int, reason: str, duration: Optional[str] = None) -> Tuple[bool, str]:
		if entity_type not in ("server", "user"):
			log.warning(f"Attempted to blacklist invalid entity type: {entity_type}")
			return False, "Invalid entity type"

		success, data = await self._get_data()
		if not success:
			return False, "Failed to load blacklist database."

		eid = str(entity_id)
		if eid in data[entity_type]:
			log.info(f"Blacklist add failed: {entity_type} {eid} is already blacklisted")
			return False, "Entity is already blacklisted."

		expires_at = self._parse_duration(duration) if duration else None
		if duration and not expires_at:
			return False, "Invalid duration format (use 7d, 12h, 30m)."

		data[entity_type][eid] = {
			"id": entity_id,
			"type": entity_type,
			"mod_id": mod_id,
			"reason": reason,
			"created_at": self._now().isoformat(),
			"expires_at": expires_at,
		}

		await json_file.save(file.glob.blacklist, data)
		log.info(f"Successfully blacklisted {entity_type} {eid} by mod {mod_id}. Reason: {reason}")
		return True, "Blacklisted successfully."

	async def remove(self, entity_id: int, entity_type: str) -> Tuple[bool, str]:
		if entity_type not in ("server", "user"):
			return False, "Invalid entity type"

		success, data = await self._get_data()
		if not success:
			return False, "Failed to load blacklist database."

		eid = str(entity_id)

		if eid in data[entity_type]:
			del data[entity_type][eid]
			await json_file.save(file.glob.blacklist, data)
			log.info(f"Successfully removed {entity_type} {eid} from blacklist")
			return True, "Removed from blacklist."

		log.info(f"Blacklist remove failed: {entity_type} {eid} not found")
		return False, f"{entity_type.capitalize()} was not blacklisted."

	async def get(self, entity_id: int, entity_type: str) -> Tuple[bool, Any]:
		log.debug(f"Fetching blacklist info for {entity_type} {entity_id}")

		if entity_type not in ("server", "user"):
			return False, "Invalid entity type"

		success, data = await self._get_data()
		if not success:
			return False, "OS error"

		eid = str(entity_id)
		if eid in data[entity_type]:
			return True, data[entity_type][eid]

		return False, f"{entity_type.capitalize()} with id '{eid}' was not found."

	async def edit(self, entity_id: int, entity_type: str, mod_id: int, reason: Optional[str] = None, duration: Optional[str] = None) -> Tuple[bool, str]:
		if entity_type not in ("server", "user"):
			return False, "Invalid entity type"

		if not reason and not duration:
			return False, "You must provide either a new reason or a new duration to edit."

		success, data = await self._get_data()
		if not success:
			return False, "Failed to load blacklist database."

		eid = str(entity_id)
		if eid not in data[entity_type]:
			return False, f"{entity_type.capitalize()} is not currently blacklisted."

		entry = data[entity_type][eid]

		if reason:
			entry["reason"] = reason

		if duration is not None:
			if duration == "0":
				entry["expires_at"] = None
			else:
				try:
					amount = int(duration[:-1])
					unit = duration[-1].lower()

					if unit == "d":
						delta = timedelta(days=amount)
					elif unit == "h":
						delta = timedelta(hours=amount)
					elif unit == "m":
						delta = timedelta(minutes=amount)
					else:
						return False, "Invalid duration unit (use d, h, m)."

					created_at = datetime.fromisoformat(entry["created_at"])
					entry["expires_at"] = (created_at + delta).isoformat()
				except Exception as e:
					log.error(f"Failed to parse edit duration '{duration}': {e}")
					return False, "Invalid duration format (use 7d, 12h, 30m). Use 0 for permanent."

		entry["mod_id"] = mod_id

		await json_file.save(file.glob.blacklist, data)
		log.info(f"Successfully edited blacklist entry for {entity_type} {eid} by mod {mod_id}")
		return True, "Blacklist entry updated successfully."

	async def list_all(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
		log.debug(f"Listing all blacklisted entities (filter: {entity_type})")
		success, data = await self._get_data()

		if not success:
			return []

		if entity_type:
			return list(data.get(entity_type, {}).values())

		return list(data["server"].values()) + list(data["user"].values())

	async def is_blacklisted(self, entity_id: int, entity_type: str) -> bool:
		if entity_type not in ("server", "user"):
			return False

		success, data = await self._get_data()
		if not success:
			return False

		result = str(entity_id) in data[entity_type]
		log.debug(f"Check is_blacklisted for {entity_type} {entity_id}: {result}")
		return result


blacklist = Blacklist()


__all__ = ('blacklist',)
