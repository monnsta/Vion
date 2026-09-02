import asyncio
import json
import logging
import discord
from discord.ext import commands

from vion.services.ai import ai
from vion.config import config


log = logging.getLogger("extensions")


class BaseEventsCog(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.pending_message_tasks: dict[tuple[int, int], asyncio.Task] = {}
		self.pending_messages: dict[tuple[int, int], discord.Message] = {}

		self.active_typing_states: dict[tuple[int, int], float] = {}
		self.typing_monitor_tasks: dict[tuple[int, int], asyncio.Task] = {}

		self.synced_contexts: set[str] = set()
		ai.bot = bot

	async def _smart_sync_memory(self, channel, memory_manager, entity_id=None, exclude_id=None):
		is_channel = (entity_id is None)
		sync_key = f"channel_stm_{getattr(channel, 'id', 0)}" if is_channel else f"{memory_manager.entity_type}_{entity_id}"

		if sync_key in self.synced_contexts:
			return

		self.synced_contexts.add(sync_key)

		try:
			if is_channel:
				success, current_mems = await memory_manager.get(channel)
			else:
				success, current_mems = await memory_manager.get(entity_id)

			last_msg_id = None
			if success and current_mems:
				for mem in reversed(current_mems):
					if isinstance(mem, str):
						try:
							mem = json.loads(mem)
						except Exception:
							continue
					if isinstance(mem, dict) and "id" in mem:
						last_msg_id = mem["id"]
						break

			messages_to_add = []
			if last_msg_id:
				try:
					async for msg in channel.history(after=discord.Object(id=last_msg_id), limit=50):
						messages_to_add.append(msg)
				except discord.HTTPException:
					pass
			else:
				try:
					async for msg in channel.history(limit=50):
						messages_to_add.append(msg)
					messages_to_add.reverse()
				except discord.HTTPException:
					pass

			for msg in messages_to_add:
				if exclude_id and msg.id == exclude_id:
					continue

				if is_channel:
					await memory_manager.add(channel, msg)
				else:
					await memory_manager.add(entity_id, msg)

		except Exception as e:
			log.error(f"Error smart syncing {sync_key}: {e}")

	async def do_memory_actions(self, message, manager, memory_manager, context):
		entity = None

		if context == "server" and message.guild:
			entity = message.guild
		elif context == "user":
			entity = message.author
		elif context == "self":
			entity = getattr(message.channel, "recipient", None)

			if not entity and getattr(message.channel, "type", None) == discord.ChannelType.private:
				async for msg in message.channel.history(limit=10):
					if msg.author.id != config.bot.id:
						entity = msg.author
						break

		if not entity:
			log.error("Could not resolve entity.")
			return

		if not await manager.is_setup(entity.id):
			await manager.setup(entity)

		await self._smart_sync_memory(message.channel, memory_manager, entity_id=entity.id, exclude_id=message.id)
		await memory_manager.add(entity.id, message)
