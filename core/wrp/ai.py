import logging
import io
from typing import Any, Dict, List
from pathlib import Path

import discord
from discord.ext import commands

from core.lib.llm import GenerateContent
from core.lib.code import Code, extract
from core.wrp.memory import MemoryCluster, guild_response, user_response
from core.wrp.profile import server, user
from core.wrp.trackers import activity
from core.wrp.extension import server_cog
from meta import config


log = logging.getLogger(__name__)


class SelfCallAgent:
	def __init__(
		self,
		parent_ai: 'AI',
		guild_obj: discord.Guild | None,
		member_obj: discord.User | discord.Member | None,
		message: discord.Message | None,
		bot_client: commands.Bot
	):
		self.parent_ai = parent_ai
		self.guild_obj = guild_obj
		self.member_obj = member_obj
		self.message = message
		self.bot_client = bot_client

	async def self_call(
		self,
		text: str,
		*files: str | bytes | io.BytesIO | io.IOBase | discord.Attachment,
		request_full_context: bool = False
	) -> None:
		"""
		Allows the AI to recursively call itself with additional text and file inputs.
		File inputs can be Discord Attachments, local file paths (str), raw bytes,
		or file-like objects (BytesIO, IOBase).
		If request_full_context is True, full guild and user profile JSONs will be included.
		"""
		log.info(f"AI self-call initiated by {self.member_obj.id if self.member_obj else 'unknown'}")

		file_inputs_for_llm: List[Any] = []
		file_descs_for_prompt: List[str] = []

		for f_item in files:
			if isinstance(f_item, discord.Attachment):
				file_inputs_for_llm.append(f_item.url)
				file_descs_for_prompt.append(f_item.filename)
			elif isinstance(f_item, (io.BytesIO, io.IOBase)):
				try:
					f_item.seek(0)
					file_inputs_for_llm.append(f_item)
					filename = getattr(f_item, "name", f"file_{len(file_inputs_for_llm)}")
					file_descs_for_prompt.append(filename)
				except Exception as e:
					log.warning(f"Failed to prepare file-like object during self-call: {e}")
			elif isinstance(f_item, str):
				path_obj = Path(f_item)
				if path_obj.is_file():
					file_inputs_for_llm.append(f_item)
					file_descs_for_prompt.append(path_obj.name)
				elif f_item.startswith(("http://", "https://")):
					file_inputs_for_llm.append(f_item)
					file_descs_for_prompt.append(Path(f_item).name if Path(f_item).name else f_item)
				else:
					log.warning(f"Unrecognized string as file input for self-call: {f_item}. Skipping as LLM input.")
			else:
				log.warning(f"Unsupported file type for self-call: {type(f_item)}. Skipping.")

		inputs_summary = f"Includes the following files: {', '.join(file_descs_for_prompt)}" if file_descs_for_prompt else ""
		combined_extra = f"{text}\n\nAdditional Input Summary: {inputs_summary}" if inputs_summary else text

		await self.parent_ai.do_action(
			event="on_self_call",
			guild_obj=self.guild_obj,
			member_obj=self.member_obj,
			extra=combined_extra,
			inputs=file_inputs_for_llm,
			message=self.message,
			bot=self.bot_client,
			request_full_context=request_full_context
		)


class AI:
	def __init__(self) -> None:
		log.info("Initializing AI engine with base modules.")
		self.base_modules = [
			GenerateContent(
				k, m,
				config.system_instructions,
				config.temperature,
				config.top_p, config.top_k
			)
			for m in config.gemini_models
			for k in config.secrets.gemini
		]
		log.debug(f"Loaded {len(self.base_modules)} base modules from configuration.")
		self.custom_modules_cache: Dict[str, List[GenerateContent]] = {}
		self.bot: commands.Bot | None = None

	def _get_custom_modules(self, custom_keys: List[str]) -> List[GenerateContent]:
		cache_signature = ",".join(sorted(custom_keys))
		if cache_signature in self.custom_modules_cache:
			log.debug("Cache hit for custom modules.")
			return self.custom_modules_cache[cache_signature]

		log.info(f"Cache miss. Generating custom modules for signature hash: {hash(cache_signature)}")
		modules = [
			GenerateContent(
				k, m,
				config.system_instructions,
				config.temperature,
				config.top_p, config.top_k
			)
			for m in config.gemini_models
			for k in custom_keys
		]
		self.custom_modules_cache[cache_signature] = modules
		return modules

	async def do_action(
		self,
		event: str,
		guild_obj: discord.Guild | None = None,
		member_obj: discord.User | discord.Member | None = None,
		extra: str | None = None,
		inputs: List[Any] | None = None,
		**kwargs: Any
	) -> bool:
		log.info(f"Processing action for event: '{event}' (Guild: {guild_obj.id if guild_obj else 'None'}, Member: {member_obj.id if member_obj else 'None'})")

		g_obj, u_obj = None, None
		g_ins = None
		g_cog = None
		pipeline = list(self.base_modules)
		custom_keys: List[str] = []

		request_full_context = kwargs.pop('request_full_context', False)
		message = kwargs.get('message')
		channel = kwargs.get('channel') or (message.channel if message else None)

		if guild_obj:
			log.debug(f"Fetching config objects for Guild ID: {guild_obj.id}")
			_, g_full_obj = await server.info.load(guild_obj.id)
			_, g_settings = await server.settings.load(guild_obj.id)
			g_ins = g_settings.get("instructions")

			success_cog, cog_code = await server_cog.read(guild_obj.id)
			if success_cog and cog_code:
				g_cog = cog_code

			if s_keys_raw := g_settings.get("api_keys"):
				log.debug(f"Extracting server-provided API keys for Guild ID: {guild_obj.id}")
				for k in s_keys_raw:
					custom_keys.append(k["key"] if isinstance(k, dict) else k)

			if not g_full_obj:
				await server.info.save(guild_obj)
				_, g_full_obj = await server.info.load(guild_obj.id)

			if request_full_context:
				g_obj = g_full_obj
			else:
				g_obj = f"Guild Name: {guild_obj.name}, ID: {guild_obj.id}\n(Full context omitted. Use self_call with request_full_context=True to retrieve.)"

		if member_obj:
			log.debug(f"Fetching config objects for Member ID: {member_obj.id}")
			_, u_full_obj = await user.info.load(member_obj.id)
			if not u_full_obj:
				await user.info.save(member_obj)
				_, u_full_obj = await user.info.load(member_obj.id)

			_, u_sets = await user.settings.load(member_obj.id)

			if request_full_context:
				u_obj = u_full_obj
			else:
				u_obj = f"User Name: {member_obj.name}, ID: {member_obj.id}\n(Full context omitted. Use self_call with request_full_context=True to retrieve.)"

			if u_keys := u_sets.get("api_keys"):
				log.debug(f"Extracting user-provided API keys for Member ID: {member_obj.id}")
				custom_keys.extend(u_keys)

		if custom_keys:
			unique_keys = list(dict.fromkeys(custom_keys))
			log.info(f"Injecting {len(unique_keys)} custom API keys into pipeline.")
			custom_modules = self._get_custom_modules(unique_keys)
			pipeline = custom_modules + pipeline

		log.debug("Building Memory Cluster...")
		cluster = await MemoryCluster.build(guild_obj, member_obj, channel)

		inputs_summary = ""
		if inputs:
			inputs_summary_list = []
			for item in inputs:
				if isinstance(item, str):
					inputs_summary_list.append(Path(item).name if Path(item).name else item)
				elif isinstance(item, bytes):
					inputs_summary_list.append(f"binary_data_{len(inputs_summary_list)}.bin")
				elif hasattr(item, 'name'):
					inputs_summary_list.append(item.name)
				else:
					inputs_summary_list.append(f"unnamed_input_{len(inputs_summary_list)}")
			inputs_summary = ", ".join(inputs_summary_list)

		active_pipeline = [m for m in pipeline if not m.is_cooling_down]
		log.debug(f"Pipeline status -> Total modules: {len(pipeline)}, Active/Available: {len(active_pipeline)}")

		if not active_pipeline:
			log.warning("No active modules available in the pipeline (all cooling down or none loaded).")

		success, response = False, config.fallback_response
		prompt = config.prompt_template.format(
			guild=g_obj,
			instructions=g_ins,
			guild_cog=g_cog,
			user=u_obj,
			**cluster,
			params=kwargs.keys() | {'self_caller'},
			event=event,
			extra=extra,
			inputs_summary=inputs_summary
		)

		manager = None
		entity_id = None

		if self.bot:
			kwargs['self_caller'] = SelfCallAgent(self, guild_obj, member_obj, kwargs.get('message'), self.bot)
		else:
			log.error("AI instance has no bot client reference, self_caller will not be fully functional.")


		for idx, model in enumerate(active_pipeline):
			log.debug(f"Attempting model generation call (Index: {idx})")
			success, response = await model.call(prompt, inputs=inputs)

			if success:
				log.info(f"Model call succeeded via module index {idx}.")
				if guild_obj:
					manager = guild_response
					entity_id = guild_obj.id
				elif member_obj:
					manager = user_response
					entity_id = member_obj.id
				break
			else:
				log.warning(f"Model call failed at module index {idx}. Retrying next available model if any.")
				response = config.fallback_response

		try:
			log.debug("Extracting and preparing generated code for execution.")
			res_data = extract(response)

			log.info("Executing extracted application code payload.")
			code_instance = Code(res_data.code)

			await code_instance.execute(**kwargs)
			exec_result = await code_instance.wait()

			if exec_result.logs or exec_result.error:
				response += "\n\n---\n### Code Execution Output\n"
				if exec_result.logs:
					response += f"**Logs:**\n```text\n{exec_result.logs}\n```\n"
				if exec_result.error:
					response += f"**Error:**\n```text\n{exec_result.error}\n```\n"

		except Exception as e:
			response += f"\n\n---\n### Code Execution Failure\n```text\n{e}\n```\n"

		if manager and entity_id is not None:
			log.debug(f"Persisting model response for entity ID: {entity_id}")
			await manager.add(entity_id, response)

		if success: await activity.log_activity(
			guild_id=guild_obj.id if guild_obj else None,
			user_id=member_obj.id if member_obj else None
		)

		return success


class Summarizer:
	def __init__(self) -> None:
		log.info("Initializing Summarizer engine.")
		self.modules = [
			GenerateContent(
				k, m,
				config.summary_instructions,
				config.temperature,
				config.top_p, config.top_k
			)
			for m in config.gemini_models
			for k in config.secrets.gemini
		]

	async def summarize(self, text: str) -> str | None:
		if not text.strip():
			return None

		active_pipeline = [m for m in self.modules if not m.is_cooling_down]
		if not active_pipeline:
			log.warning("No active modules available for summarization.")
			return None

		for idx, model in enumerate(active_pipeline):
			log.debug(f"Attempting summarizer call (Index: {idx})")
			success, response = await model.call(text)
			if success and response:
				log.info("Summarization successfully completed.")
				return response.strip()

		log.warning("All summarizer models failed to produce a response.")
		return None


ai = AI()
summarizer = Summarizer()


__all__ = ('ai', 'summarizer', 'SelfCallAgent')
