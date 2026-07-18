import logging
import io
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

import discord
from discord.ext import commands

from core.lib.llm import GenerateContent
from core.lib.code import Code, extract
from core.wrp.memory import MemoryCluster, guild_response, user_response
from core.wrp.profile import server, user
from meta import config


log = logging.getLogger(__name__)


class SelfCallAgent:
	def __init__(
		self,
		parent_ai: 'AI',
		guild: Optional[discord.Guild],
		member: Optional[Union[discord.User, discord.Member]],
		message: Optional[discord.Message],
		bot_client: commands.Bot
	):
		self.parent_ai = parent_ai
		self.guild = guild
		self.member = member
		self.message = message
		self.bot_client = bot_client

	async def self_call(self, text: str, *files: Union[str, bytes, io.BytesIO, io.IOBase, discord.Attachment]) -> None:
		"""
		Allows the AI to recursively call itself with additional text and file inputs.
		File inputs can be Discord Attachments, local file paths (str), raw bytes,
		or file-like objects (BytesIO, IOBase).
		"""
		log.info(f"AI self-call initiated by {self.member.id if self.member else 'unknown'}")

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

		await self.parent_ai.do_action(event="on_self_call", guild=self.guild, member=self.member, extra=combined_extra, inputs=file_inputs_for_llm, message=self.message, bot=self.bot_client)


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
			for k in config.secrets.gemini_api_key
		]
		log.debug(f"Loaded {len(self.base_modules)} base modules from configuration.")
		self.user_modules_cache: Dict[str, List[GenerateContent]] = {}
		self.bot: Optional[commands.Bot] = None

	def _get_user_modules(self, user_keys: List[str]) -> List[GenerateContent]:
		cache_signature = ",".join(sorted(user_keys))
		if cache_signature in self.user_modules_cache:
			log.debug("Cache hit for user modules.")
			return self.user_modules_cache[cache_signature]

		log.info(f"Cache miss. Generating user modules for signature hash: {hash(cache_signature)}")
		modules = [
			GenerateContent(
				k, m,
				config.system_instructions,
				config.temperature,
				config.top_p, config.top_k
			)
			for m in config.gemini_models
			for k in user_keys
		]
		self.user_modules_cache[cache_signature] = modules
		return modules

	async def do_action(
		self,
		event: str,
		guild: discord.Guild | None = None,
		member: discord.User | discord.Member | None = None,
		extra: str | None = None,
		inputs: Optional[List[Any]] = None,
		**kwargs: Any
	) -> None:
		log.info(f"Processing action for event: '{event}' (Guild: {guild.id if guild else 'None'}, Member: {member.id if member else 'None'})")

		g_obj, u_obj = None, None
		g_ins = None
		pipeline = list(self.base_modules)

		if event == "on_message" or event == "on_self_call":
			if guild:
				log.debug(f"Fetching config objects for Guild ID: {guild.id}")
				_, g_obj = await server.info.load(guild.id)
				_, g_settings = await server.settings.load(guild.id)
				g_ins = g_settings.get("instructions")
				if not g_obj:
					await server.info.save(guild)
					_, g_obj = await server.info.load(guild.id)
			if member:
				log.debug(f"Fetching config objects for Member ID: {member.id}")
				_, u_obj = await user.info.load(member.id)
				if not u_obj:
					await user.info.save(member)
					_, u_obj = await user.info.load(member.id)

				_, u_sets = await user.settings.load(member.id)

				if user_keys := u_sets.get("api_keys"):
					log.info(f"Injecting user-provided API keys into pipeline for Member ID: {member.id}")
					user_modules = self._get_user_modules(user_keys)
					pipeline = user_modules + pipeline

		log.debug("Building Memory Cluster...")
		cluster = await MemoryCluster.build(guild, member)

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
			kwargs['self_caller'] = SelfCallAgent(self, guild, member, kwargs.get('message'), self.bot) # Pass the bot instance
		else:
			log.error("AI instance has no bot client reference, self_caller will not be fully functional.")


		for idx, model in enumerate(active_pipeline):
			log.debug(f"Attempting model generation call (Index: {idx})")
			success, response = await model.call(prompt, inputs=inputs)

			if success:
				log.info(f"Model call succeeded via module index {idx}.")
				if guild:
					manager = guild_response
					entity_id = guild.id
				elif member:
					manager = user_response
					entity_id = member.id
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

			if exec_result.stdout or exec_result.stderr or exec_result.error:
				response += "\n\n---\n### Code Execution Output\n"
				if exec_result.stdout:
					response += f"**Stdout:**\n```text\n{exec_result.stdout}\n```\n"
				if exec_result.stderr:
					response += f"**Stderr:**\n```text\n{exec_result.stderr}\n```\n"
				if exec_result.error:
					response += f"**Error:**\n```text\n{exec_result.error}\n```\n"

		except Exception as e:
			response += f"\n\n---\n### Code Execution Failure\n```text\n{e}\n```\n"

		if manager and entity_id is not None:
			log.debug(f"Persisting model response for entity ID: {entity_id}")
			await manager.add(entity_id, response)


ai = AI()
