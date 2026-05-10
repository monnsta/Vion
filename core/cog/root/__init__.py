from core.cog.root.events     import Events
from core.cog.root.help       import Help
from core.cog.root.your_data  import Data


async def setup(bot):
	await bot.add_cog(Events(bot))
	await bot.add_cog(Help(bot))
	await bot.add_cog(Data(bot))
