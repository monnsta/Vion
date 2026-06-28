from core.cog.fun.root import FunRoot


async def setup(bot):
	await bot.add_cog(FunRoot(bot))
