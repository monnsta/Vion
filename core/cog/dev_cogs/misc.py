import discord
from discord             import app_commands as app
from discord.ext         import commands

from ._dev_cog           import dev
from core.lib.code       import Code, status
from core.ui.template    import Fail, Success


dev_only = True


class Misc(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@dev.command(
		name='execute',
		aliases=['e'],
		description='Execute code like the AI does'
	)
	@app.describe(code='The code to execute')
	async def execute(self, ctx: commands.Context, *, code: str):
		"""
		Execute code like the AI does.
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


async def setup(bot: commands.Bot):
	await bot.add_cog(Misc(bot))
