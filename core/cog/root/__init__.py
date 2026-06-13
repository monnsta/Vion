from core.cog.root.events import Events
from core.cog.root.root import Root


async def setup(bot):
	await bot.add_cog(Events(bot))
	await bot.add_cog(Root(bot))
