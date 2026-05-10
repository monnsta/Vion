from core.cog.dev.blacklist   import Blacklist
from core.cog.dev.extension   import Extension
from core.cog.dev.misc        import Root


dev_only = True


async def setup(bot):
	await bot.add_cog(Blacklist(bot))
	await bot.add_cog(Extension(bot))
	await bot.add_cog(Root(bot))