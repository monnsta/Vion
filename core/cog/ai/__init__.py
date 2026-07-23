from core.cog.ai.events import AIEvents


async def setup(bot):
	await bot.add_cog(AIEvents(bot))
