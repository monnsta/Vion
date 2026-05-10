from core.cog.setting.gemini_key    import GeminiKey
from core.cog.setting.instructions  import Instructions
from core.cog.setting.prefix        import Prefix
from core.cog.setting.root          import Root


async def setup(bot):
	await bot.add_cog(GeminiKey(bot))
	await bot.add_cog(Instructions(bot))
	await bot.add_cog(Prefix(bot))
	await bot.add_cog(Root(bot))
