from core.cog.root.events import CoreEvents
from core.cog.root.root import Root


async def setup(bot):
	await bot.add_cog(CoreEvents(bot))
	await bot.add_cog(Root(bot))
