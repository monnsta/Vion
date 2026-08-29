from .base import Convert


COMMON_FILTERS = [
	'BASE', 'key', 'DEFAULT_VALUE', 'VALID_FLAGS', 'jump_url', 'colour',
	'accent_colour', 'accent_color', 'avatar_decoration_sku_id', 'client_status',
	'desktop_status', 'web_status', 'mobile_status', 'mutual_guilds', 'flags',
	'public_flags', 'raw_mentions', 'raw_role_mentions', 'clean_content', 'interaction',
	'voice_states', 'threads', 'available_tags'
]

convert_message = Convert(
	filter_attrs=COMMON_FILTERS + [
		'call', 'role_subscription', 'value', 'nonce', 'guild', 'channel',
		'author', 'reference', 'mentions', 'role_mentions', 'reactions',
		'stickers', 'flags', 'system_content', 'webhook_id', 'application', 'activity'
	],
	max_depth=3,
	attr_depths={"components": 8, "embeds": 6, "message_snapshots": 6},
	output_format="json"
)

convert_guild = Convert(
	filter_attrs=COMMON_FILTERS + ['me'],
	max_depth=5,
	output_format="json"
)

convert_user = Convert(
	filter_attrs=COMMON_FILTERS + ['status', 'default_avatar', 'discriminator'],
	max_depth=3,
	output_format="json"
)

convert_bot = Convert(
	filter_attrs=COMMON_FILTERS + ['cached_messages', 'cogs', 'extra_events', 'token'],
	max_depth=4,
	output_format="json"
)
