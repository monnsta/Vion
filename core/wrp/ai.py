from typing import Any, Dict, List
import logging

import discord

from core.lib.llm import GenerateContent
from core.lib.code import Code, extract
from core.wrp.memory import guild_memory, user_memory, guild_response, user_response
from core.wrp.profile import server, user
from meta import config



log = logging.getLogger(__name__)


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
		**kwargs: Any
	) -> None:
		log.info(f"Processing action for event: '{event}' (Guild: {guild.id if guild else 'None'}, Member: {member.id if member else 'None'})")
		
		g_msg, u_msg = None, None
		g_obj, u_obj = None, None
		pipeline = list(self.base_modules)

		if event == "on_message":
			if guild:
				log.debug(f"Fetching context for Guild ID: {guild.id}")
				_, g_msg = await guild_memory.get(guild.id)
				_, g_obj = await server.info.load(guild.id)
				if not g_obj:
					await server.info.save(guild)
					_, g_obj = await server.info.load(guild.id)
			if member:
				log.debug(f"Fetching context for Member ID: {member.id}")
				_, u_msg = await user_memory.get(member.id)
				_, u_obj = await user.info.load(member.id)
				if not u_obj:
					await user.info.save(member)
					_, u_obj = await user.info.load(member.id)

				_, u_sets = await user.settings.load(member.id)

				if user_keys := u_sets.get("api_keys"):
					log.info(f"Injecting user-provided API keys into pipeline for Member ID: {member.id}")
					user_modules = self._get_user_modules(user_keys)
					pipeline = user_modules + pipeline

		active_pipeline = [m for m in pipeline if not m.is_cooling_down]
		log.debug(f"Pipeline status -> Total modules: {len(pipeline)}, Active/Available: {len(active_pipeline)}")

		if not active_pipeline:
			log.warning("No active modules available in the pipeline (all cooling down or none loaded).")

		success, response = False, config.fallback_response
		prompt = config.prompt_template.format(
			guild=g_obj,
			user=u_obj,
			guild_messages=g_msg,
			user_messages=u_msg,
			params=kwargs.keys(),
			event=event,
			extra=extra
		)

		manager = None
		entity_id = None

		for idx, model in enumerate(active_pipeline):
			log.debug(f"Attempting model generation call (Index: {idx})")
			success, response = await model.call(prompt)

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
			log.error("Failed to execute generated code.", exc_info=True)
			response += f"\n\n---\n### Code Execution Failure\n```text\n{e}\n```\n"

		if manager and entity_id is not None:
			log.debug(f"Persisting model response for entity ID: {entity_id}")
			await manager.add(entity_id, response)

ai = AI()
