import discord
import asyncio
import yt_dlp
from typing import cast, Optional, Any


ytdl_format_options: dict[str, Any] = {
	'format': 'bestaudio/best',
	'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
	'restrictfilenames': True,
	'noplaylist': True,
	'nocheckcertificate': True,
	'ignoreerrors': False,
	'logtostderr': False,
	'quiet': True,
	'no_warnings': True,
	'default_search': 'auto',
	'source_address': '0.0.0.0',
}

ytdl = yt_dlp.YoutubeDL(cast(Any, ytdl_format_options))


class VoiceUtils:
	@staticmethod
	async def join(channel: discord.VoiceChannel) -> discord.VoiceClient | None:
		if channel.guild.voice_client:
			vc = cast(discord.VoiceClient, channel.guild.voice_client)
			if vc.channel and vc.channel.id != channel.id:
				await vc.move_to(channel)
			return vc
		
		connection = await channel.connect()
		return cast(discord.VoiceClient, connection)

	@staticmethod
	async def leave(guild: discord.Guild, force: bool = False) -> bool:
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			await vc.disconnect(force=force)
			return True
		return False

	@staticmethod
	async def play(guild: discord.Guild, source: str | discord.AudioSource, volume: float = 1.0) -> bool:
		if not guild.voice_client:
			return False
		
		vc = cast(discord.VoiceClient, guild.voice_client)
		if not vc.is_connected():
			return False

		if vc.is_playing():
			vc.stop()

		if isinstance(source, str):
			if source.startswith(('http://', 'https://')):
				loop = asyncio.get_event_loop()
				data = cast(Optional[dict[str, Any]], await loop.run_in_executor(None, lambda: ytdl.extract_info(source, download=False)))
				
				if not data:
					return False
					
				if 'entries' in data and data['entries']:
					data = data['entries'][0]
					
				stream_url = data.get('url')
				if not isinstance(stream_url, str):
					return False
					
				audio_source: discord.AudioSource = discord.PCMVolumeTransformer(
					discord.FFmpegPCMAudio(
						stream_url,
						before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
						options='-vn'
					), 
					volume=volume
				)
			else:
				audio_source: discord.AudioSource = discord.PCMVolumeTransformer(
					discord.FFmpegPCMAudio(source), volume=volume
				)
		else:
			audio_source = source

		vc.play(audio_source)
		return True

	@staticmethod
	def pause(guild: discord.Guild) -> bool:
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.is_playing():
				vc.pause()
				return True
		return False

	@staticmethod
	def resume(guild: discord.Guild) -> bool:
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.is_paused():
				vc.resume()
				return True
		return False

	@staticmethod
	def stop(guild: discord.Guild) -> bool:
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.is_playing():
				vc.stop()
				return True
		return False

	@staticmethod
	def change_volume(guild: discord.Guild, volume: float) -> bool:
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
				vc.source.volume = volume
				return True
		return False

	@staticmethod
	def is_playing(guild: discord.Guild) -> bool:
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			return vc.is_playing()
		return False

	@staticmethod
	async def set_bot_status(guild: discord.Guild, mute: Optional[bool] = None, deafen: Optional[bool] = None) -> bool:
		if guild.me.voice:
			kwargs = {}
			if mute is not None:
				kwargs["mute"] = mute
			if deafen is not None:
				kwargs["deafen"] = deafen
			if kwargs:
				await guild.me.edit(**kwargs)
			return True
		return False

	@staticmethod
	async def move_member(member: discord.Member, channel: discord.VoiceChannel | None) -> bool:
		if member.voice:
			await member.edit(voice_channel=channel)
			return True
		return False

	@staticmethod
	async def mute_member(member: discord.Member, mute: bool) -> bool:
		if member.voice:
			await member.edit(mute=mute)
			return True
		return False

	@staticmethod
	async def deafen_member(member: discord.Member, deafen: bool) -> bool:
		if member.voice:
			await member.edit(deafen=deafen)
			return True
		return False


voice = VoiceUtils()
