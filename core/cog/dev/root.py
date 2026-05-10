import traceback

from discord                import app_commands as app
from discord.ext            import commands

from core.lib.code          import Code, status
from core.cog.dev._group    import dev
from core.cog.ui_template   import Fail, Success
from meta                   import load_config, config, emoji


class Root(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot


	@dev.command(
		name='code',
		aliases=['c'],
		description='Execute python code'
	)
	@app.describe(code='The code to execute')
	async def code(self, ctx: commands.Context, *, code: str):
		"""
		Execute python code. you are required to define an asynchronios main function as entry point, accepting message and bot object.
		Example: /dev execute async def main(message, bot): await message.channel.send("Hello there.")
		"""
		await ctx.defer(ephemeral=False)

		runner = Code(code)

		try:
			await runner.execute(timeout=30.0, message=ctx.message, bot=self.bot)

			data = await runner.wait()

			output_parts = []

			if data.stdout:
				output_parts.append(f"**Stdout:**\n```py\n{data.stdout}\n```")
			if data.stderr:
				output_parts.append(f"**Stderr:**\n```py\n{data.stderr}\n```")
			if data.error:
				output_parts.append(f"**Error:**\n```py\n{data.error}\n```")
			if data.result is not None:
				output_parts.append(f"**Result:** `{data.result}`")

			final_content = "\n".join(output_parts) if output_parts else "Code executed with no output."

			if data.status == status.COMPLETED:
				await ctx.reply(view=Success(f"**Execution {runner.execution_id} Successful**\n\n{final_content}"))
			else:
				await ctx.reply(view=Fail(f"**Execution {runner.execution_id} {data.status}**\n\n{final_content}"))

		except Exception as e:
			await ctx.reply(view=Fail(f"An unexpected error occurred during execution setup: {str(e)}"))


	@dev.command(
		name='reload_config',
		aliases=['r'],
		description='Reload the config file'
	)
	async def reload_config(self, ctx: commands.Context):
		"""Reloads the internal config file, usefull when you've edited the config file but can't restart the bot."""
		original_config = config.to_dict()
		original_emoji = emoji.to_dict()
		try:
			config.clear()
			emoji.clear()
			load_config()
			await ctx.reply(view=Success("Successfully reloaded config"))
		except Exception:
			config.load(original_config)
			emoji.load(original_emoji)

			error_traceback = traceback.format_exc()

			await ctx.reply(view=Fail(
				"Failed to Reload Config",
				None,
				"```python",
				error_traceback,
				"```"
			))
