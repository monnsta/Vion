from .root import DevRoot


async def setup(bot):
	await bot.add_cog(DevRoot(bot))
