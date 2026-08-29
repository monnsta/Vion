import json
import time
import hashlib
import logging
from typing import Any, Optional

import discord

from infrastructure.converter import convert_message, convert_user
from services.ai.voice import VoiceUtils
from services.ai.summarizer import Summarizer
from config import config

from .base import EntityListStore


log = logging.getLogger("memory")


class STM(EntityListStore):
	def __init__(
		self,
		entity_type: str = "guild",
		guild_ltm: Optional["LTM"] = None,
		user_ltm: Optional["LTM"] = None
	):
		super().__init__("stm", config.max_stm, entity_type)
		self.guild_ltm = guild_ltm
		self.user_ltm = user_ltm

	def _normalize_entry(self, entry: Any) -> str:
		if isinstance(entry, dict):
			return json.dumps(entry, sort_keys=True)
		return str(entry)

	async def add(self, entity_id: int, message) -> bool:
		try:
			entry = await convert_message(message)

			if isinstance(entry, dict):
				entry["author_id"] = message.author.id
				if getattr(message, "reference", None) and message.reference.message_id:
					entry["reply_to_id"] = message.reference.message_id

			transcripts = []
			if hasattr(message, "attachments") and message.attachments:
				for attachment in message.attachments:
					if getattr(attachment, "is_voice_message", lambda: False)():
						success, text = await VoiceUtils.transcribe(attachment.url)
						if success and text:
							transcripts.append(text)

			if transcripts and isinstance(entry, dict):
				entry["_voice_transcript"] = transcripts

			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(entry)
			items = self._trim(items)
			data[self.key] = items

			await self._save(entity_id, data)
			log.debug(f"Added STM entry for {self.entity_type} {entity_id}")

			await self._check_and_summarize(entity_id, items, data)

			return True

		except Exception as e:
			log.error(f"Error adding STM for {self.entity_type} {entity_id}: {e}")
			return False

	async def _check_and_summarize(self, entity_id: int, current_items: list[Any], data: dict) -> None:
		if not current_items or len(current_items) < self.max_items:
			return

		normalized_current = [self._normalize_entry(i) for i in current_items]
		current_hashes = [hashlib.md5(item.encode('utf-8')).hexdigest() for item in normalized_current]
		last_summarized_hashes = data.get("_last_summarized_hashes", [])

		has_overlap = any(h in last_summarized_hashes for h in current_hashes)

		if not has_overlap:
			log.info(f"STM entries for {self.entity_type} {entity_id} are completely unique. Triggering summarizer.")

			stm_text_block = "\n".join(normalized_current)
			summarizer = Summarizer()
			summary_result = await summarizer.summarize(stm_text_block)

			target_ltm = None
			if self.entity_type == "guild":
				target_ltm = self.guild_ltm
			elif self.entity_type == "user":
				target_ltm = self.user_ltm

			if target_ltm and summary_result:
				await target_ltm.add(entity_id, f"[Auto-Summarized] {summary_result}")
				log.info(f"Successfully added auto-summary into LTM for {self.entity_type} {entity_id}")

			data["_last_summarized_hashes"] = current_hashes
			await self._save(entity_id, data)


class LTM(EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("ltm", config.max_ltm, entity_type)

	async def add(self, entity_id: int, note: str) -> bool:
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(note)
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added LTM entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding LTM for {self.entity_type} {entity_id}: {e}")
			return False


class Audit(EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("audit_log", config.max_audit, entity_type)

	async def add(self, entity_id: int, event) -> bool:
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(event)
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added audit entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding audit for {self.entity_type} {entity_id}: {e}")
			return False


class Response(EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("previous_response", config.max_previous_response, entity_type)

	async def add(self, entity_id: int, response_text: str) -> bool:
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(response_text)
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added previous response entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding response for {self.entity_type} {entity_id}: {e}")
			return False


class ChannelSTM:
	def __init__(self):
		self.max_items = config.max_stm

	def _get_store(self, channel: discord.abc.Messageable):
		channel_id = getattr(channel, "id", 0)
		guild = getattr(channel, "guild", None)
		is_private = getattr(channel, "type", None) == discord.ChannelType.private or guild is None

		if is_private:
			recipient = getattr(channel, "recipient", None)
			eid = recipient.id if recipient else 0
			return EntityListStore(f"channel_stm_{channel_id}", self.max_items, "user"), eid
		else:
			return EntityListStore(f"channel_stm_{channel_id}", self.max_items, "guild"), guild.id  # type: ignore

	async def get(self, channel: discord.abc.Messageable):
		store, eid = self._get_store(channel)
		if not eid:
			return False, []
		return await store.get(eid)

	async def add(self, channel: discord.abc.Messageable, message: discord.Message) -> bool:
		store, eid = self._get_store(channel)
		channel_id = getattr(channel, "id", 0)

		if not eid and getattr(channel, "type", None) == discord.ChannelType.private:
			if hasattr(channel, "history"):
				async for msg in channel.history(limit=10):
					if msg.author.id != config.bot.id:
						eid = msg.author.id
						break
			if eid:
				store, eid = EntityListStore(f"channel_stm_{channel_id}", self.max_items, "user"), eid

		if not eid:
			return False

		try:
			entry = await convert_message(message)
			if isinstance(entry, dict):
				entry["author_id"] = message.author.id
				if message.reference and message.reference.message_id:
					entry["reply_to_id"] = message.reference.message_id

			transcripts = []
			if hasattr(message, "attachments") and message.attachments:
				for attachment in message.attachments:
					if getattr(attachment, "is_voice_message", lambda: False)():
						success, text = await VoiceUtils.transcribe(attachment.url)
						if success and text:
							transcripts.append(text)

			if transcripts and isinstance(entry, dict):
				entry["_voice_transcript"] = transcripts

			success, data = await store._load(eid)
			if not success:
				return False

			items = store._get_list(data)
			items.append(entry)
			items = store._trim(items)
			data[store.key] = items

			await store._save(eid, data)
			return True
		except Exception as e:
			log.error(f"Error adding channel STM: {e}")
			return False


class MemoryCluster:
	def __init__(
		self,
		global_stm: STM,
		global_ltm: LTM,
		guild_stm: STM,
		guild_ltm: LTM,
		guild_audit: Audit,
		user_stm: STM,
		user_ltm: LTM,
		channel_stm: ChannelSTM,
		context_linker: "ContextLinker"
	):
		self.global_stm = global_stm
		self.global_ltm = global_ltm
		self.guild_stm = guild_stm
		self.guild_ltm = guild_ltm
		self.guild_audit = guild_audit
		self.user_stm = user_stm
		self.user_ltm = user_ltm
		self.channel_stm = channel_stm
		self.context_linker = context_linker

	async def build(
		self,
		guild: discord.Guild | None,
		user: discord.User | discord.Member | None,
		channel: discord.abc.Messageable | None = None
	) -> dict:
		cluster = {
			"linked_contexts": [],
			"guild_audit": [],
			"global_stm": [],
			"global_ltm": [],
			"guild_stm": [],
			"guild_ltm": [],
			"user_stm": [],
			"user_ltm": [],
			"channel_stm": [],
			"active_users": []
		}

		_, cluster["global_stm"] = await self.global_stm.get(0)
		_, cluster["global_ltm"] = await self.global_ltm.get(0)

		if guild:
			_, cluster["guild_audit"] = await self.guild_audit.get(guild.id)
			_, cluster["guild_stm"] = await self.guild_stm.get(guild.id)
			_, cluster["guild_ltm"] = await self.guild_ltm.get(guild.id)

		if user:
			_, cluster["user_stm"] = await self.user_stm.get(user.id)
			_, cluster["user_ltm"] = await self.user_ltm.get(user.id)

		if channel:
			_, c_stm = await self.channel_stm.get(channel)
			cluster["channel_stm"] = c_stm

			active_ids = set()
			for msg_data in c_stm:
				if isinstance(msg_data, str):
					try:
						msg_data = json.loads(msg_data)
					except Exception:
						pass
				if isinstance(msg_data, dict) and "author_id" in msg_data:
					active_ids.add(msg_data["author_id"])

			active_users_list = []
			for u_id in active_ids:
				member = None
				if guild:
					member = guild.get_member(u_id)
					if not member:
						try:
							member = await guild.fetch_member(u_id)
						except Exception:
							pass
				if not member:
					member = config.bot.get_user(u_id)
					if not member:
						try:
							member = await config.bot.fetch_user(u_id)
						except Exception:
							pass
				if member:
					try:
						u_dict = await convert_user(member)
						active_users_list.append(u_dict)
					except Exception:
						pass
			cluster["active_users"] = active_users_list

		target_id = guild.id if guild else (user.id if user else None)

		if target_id:
			links = self.context_linker.get_links(target_id)

			for link in links:
				s_type = link["type"]
				s_id = link["id"]

				if s_type == "user":
					_, stm = await self.user_stm.get(s_id)
					_, ltm = await self.user_ltm.get(s_id)
					cluster["linked_contexts"].append({
						"type": "user",
						"id": s_id,
						"stm": stm,
						"ltm": ltm
					})

				elif s_type == "guild":
					_, stm = await self.guild_stm.get(s_id)
					_, ltm = await self.guild_ltm.get(s_id)
					cluster["linked_contexts"].append({
						"type": "guild",
						"id": s_id,
						"stm": stm,
						"ltm": ltm
					})

		return cluster


class ContextLinker:
	def __init__(self):
		self._links = {}

	def add_link(self, target_id: int, source_type: str, source_id: int, ttl: int = 3600):
		if target_id not in self._links:
			self._links[target_id] = {}

		key = f"{source_type}_{source_id}"
		self._links[target_id][key] = {
			"type": source_type,
			"id": source_id,
			"expires_at": time.time() + ttl
		}

	def get_links(self, target_id: int) -> list:
		if target_id not in self._links:
			return []

		active_links = []
		expired_keys = []

		for key, link in self._links[target_id].items():
			if time.time() < link["expires_at"]:
				active_links.append(link)
			else:
				expired_keys.append(key)

		for key in expired_keys:
			del self._links[target_id][key]

		return active_links

	def remove_link(self, target_id: int, source_type: str, source_id: int):
		key = f"{source_type}_{source_id}"
		if target_id in self._links and key in self._links[target_id]:
			del self._links[target_id][key]
