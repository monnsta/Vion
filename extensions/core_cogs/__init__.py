from .events import CoreEvents
from .root import Root


async def setup(bot):
	await bot.add_cog(CoreEvents(bot))
	await bot.add_cog(Root(bot))
