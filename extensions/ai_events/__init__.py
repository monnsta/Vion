from .tasks import EventTasksCog
from .guild import GuildEventsCog
from .message import MessageEventsCog
from .user import UserEventsCog


async def setup(bot):
	await bot.add_cog(EventTasksCog(bot))
	await bot.add_cog(MessageEventsCog(bot))
	await bot.add_cog(GuildEventsCog(bot))
	await bot.add_cog(UserEventsCog(bot))
