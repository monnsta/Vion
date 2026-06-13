from core.cog.dev.root import DevRoot


dev_only = True


async def setup(bot):
	await bot.add_cog(DevRoot(bot))
