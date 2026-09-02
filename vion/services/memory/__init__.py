from .service import (
	ContextLinker,
	MemoryCluster,
	STM,
	LTM,
	Audit,
	Response,
	ChannelSTM
)


context_linker = ContextLinker()

global_ltm = LTM(entity_type="global")
guild_ltm = LTM(entity_type="guild")
user_ltm = LTM(entity_type="user")

global_stm = STM(entity_type="global")
guild_stm = STM(entity_type="guild", guild_ltm=guild_ltm)
user_stm = STM(entity_type="user", user_ltm=user_ltm)

guild_audit = Audit(entity_type="guild")
guild_response = Response(entity_type="guild")
user_response = Response(entity_type="user")
channel_stm = ChannelSTM()

memory_cluster = MemoryCluster(
	global_stm=global_stm,
	global_ltm=global_ltm,
	guild_stm=guild_stm,
	guild_ltm=guild_ltm,
	guild_audit=guild_audit,
	user_stm=user_stm,
	user_ltm=user_ltm,
	channel_stm=channel_stm,
	context_linker=context_linker
)


__all__ = (
	'global_stm', 'global_ltm',
	'guild_stm', 'guild_ltm', 'guild_audit', 'guild_response',
	'user_stm', 'user_ltm', 'user_response', 'channel_stm',
	'MemoryCluster', 'memory_cluster', 'context_linker'
)
