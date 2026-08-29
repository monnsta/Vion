from .root import SettingRoot


async def setup(bot):
	await bot.add_cog(SettingRoot(bot))
