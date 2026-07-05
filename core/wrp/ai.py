from typing import Any
import logging

import discord

from core.lib.llm import GenerateContent
from core.lib.code import Code, extract
from core.wrp.memory import guild_memory, user_memory
from core.wrp.profile import server, user
from meta import config


log = logging.getLogger(__name__)


class AI:
	def __init__(self) -> None:
		self.base_modules = [
			GenerateContent(
				k, m,
				config.system_instructions,
				config.temperature,
				config.top_p, config.top_k
			)
			for m in config.gemini_models
			for k in config.secret.gemini_api_key
		]

	async def do_action(
		self,
		event: str,
		guild: discord.Guild | None = None,
		member: discord.User | discord.Member | None = None,
		extra: str | None = None,
		**kwargs: Any
	) -> None:
		g_msg, u_msg = None, None
		g_obj, u_obj = None, None
		pipeline = list(self.base_modules)

		if event == "on_message":
			if guild:
				_, g_msg = await guild_memory.get(guild.id)
				_, g_obj = await server.info.load(guild.id)
			if member:
				_, u_msg = await user_memory.get(member.id)
				_, u_obj = await user.info.load(member.id)
				_, u_sets = await user.settings.load(member.id)

				if user_keys := u_sets.get("api_keys"):
					user_modules = [
						GenerateContent(
							k, m,
							config.system_instructions,
							config.temperature,
							config.top_p, config.top_k
						)
						for m in config.gemini_models
						for k in user_keys
					]
					pipeline = user_modules + pipeline

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

		for model in pipeline:
			success, response = await model.call(prompt)
			if success:
				break

		if success:
			res_data = extract(response)
			await Code(res_data.code).execute(**kwargs)
