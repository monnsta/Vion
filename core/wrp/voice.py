import discord
import asyncio
import io
import wave
import yt_dlp
import logging
from typing import cast, Any, Tuple, Dict
from discord.ext import voice_recv

from core.lib.llm import AssemblyAITranscriber
from meta import config


log = logging.getLogger(__name__)


class YTDLPLogger:
	def debug(self, msg: str):
		if msg.lower().startswith("[debug] "):
			log.debug(msg)
		else:
			log.info(msg)

	def info(self, msg: str):
		log.info(msg)

	def warning(self, msg: str):
		log.warning(msg)

	def error(self, msg: str):
		log.error(msg)


ytdl_format_options: dict[str, Any] = {
	'format': 'bestaudio/best',
	'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
	'restrictfilenames': True,
	'noplaylist': True,
	'nocheckcertificate': True,
	'ignoreerrors': False,
	'quiet': False,
	'no_warnings': False,
	'logger': YTDLPLogger(),
	'default_search': 'auto',
	'source_address': '0.0.0.0',
}

ytdl = yt_dlp.YoutubeDL(cast(Any, ytdl_format_options))


class MemoryAudioSink(voice_recv.AudioSink):
	def __init__(self):
		super().__init__()
		self.user_buffers: Dict[int, io.BytesIO] = {}
		self.user_wavs: Dict[int, wave.Wave_write] = {}

	def wants_opus(self) -> bool:
		return False

	def write(self, user: discord.Member | discord.User | None, data: voice_recv.VoiceData):
		if not data.pcm:
			return

		user_id = user.id if user else 0

		if user_id not in self.user_buffers:
			buffer = io.BytesIO()
			wav_writer = wave.open(buffer, 'wb')
			wav_writer.setnchannels(2)
			wav_writer.setsampwidth(2)
			wav_writer.setframerate(48000)

			self.user_buffers[user_id] = buffer
			self.user_wavs[user_id] = wav_writer

		self.user_wavs[user_id].writeframes(data.pcm)

	def cleanup(self):
		for wav_writer in self.user_wavs.values():
			wav_writer.close()
		for buffer in self.user_buffers.values():
			buffer.seek(0)


class VoiceUtils:
	@staticmethod
	async def join(channel: discord.VoiceChannel) -> discord.VoiceClient | None:
		if channel.guild.voice_client:
			vc = cast(discord.VoiceClient, channel.guild.voice_client)
			if vc.channel and vc.channel.id != channel.id:
				await vc.move_to(channel)
			return vc

		connection = await channel.connect(cls=voice_recv.VoiceRecvClient)
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
				data = cast(dict[str, Any] | None, await loop.run_in_executor(None, lambda: ytdl.extract_info(source, download=False)))

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
	async def set_bot_status(guild: discord.Guild, mute: bool | None = None, deafen: bool | None = None) -> bool:
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

	@staticmethod
	async def transcribe(item: Any, **config_kwargs: Any) -> Tuple[bool, str]:
		transcriber = AssemblyAITranscriber(
			api_key=config.secrets.assemblyai,
			**config_kwargs
		)
		return await transcriber.call(item)

	@staticmethod
	def start_record(guild: discord.Guild) -> bool:
		if not guild.voice_client:
			return False

		vc = cast(voice_recv.VoiceRecvClient, guild.voice_client)
		if not vc.is_connected() or vc.is_listening():
			return False

		vc.listen(MemoryAudioSink())
		return True

	@staticmethod
	def stop_record(guild: discord.Guild) -> Dict[int, io.BytesIO] | None:
		if not guild.voice_client:
			return None

		vc = cast(voice_recv.VoiceRecvClient, guild.voice_client)
		if not vc.is_listening():
			return None

		sink = cast(MemoryAudioSink, vc.sink)

		vc.stop_listening()

		return sink.user_buffers


voice = VoiceUtils()
