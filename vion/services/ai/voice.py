"""
Voice operations, playback handling, audio recording, transcription, and TTS module.
"""

import asyncio
import io
import wave
import yt_dlp
import logging
from typing import cast, Any, Tuple, Dict

import discord
import discord.opus
from discord.ext import voice_recv

from vion.infrastructure.llm import (
	AssemblyAITranscriber,
	GeminiTTS,
	GeminiVoice
)
from vion.config import config


log = logging.getLogger("ai")

original_opus_decode = discord.opus.Decoder.decode

def patched_opus_decode(self, *args, **kwargs):
	"""Patched Opus decoder preventing error raises on minor audio frame corruptions."""
	try:
		return original_opus_decode(self, *args, **kwargs)
	except discord.opus.OpusError:
		return b''

discord.opus.Decoder.decode = patched_opus_decode


class YTDLPLogger:
	"""Custom logger redirecting yt-dlp logging output into module logger."""

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
	"""In-memory audio sink storing incoming PCM audio per user as WAV files."""

	def __init__(self):
		"""Initialize internal memory buffers and WAV writers."""
		super().__init__()
		self.user_buffers: Dict[int, io.BytesIO] = {}
		self.user_wavs: Dict[int, wave.Wave_write] = {}

	def wants_opus(self) -> bool:
		"""Return False to request decoded PCM audio data."""
		return False

	def write(self, user: discord.Member | discord.User | None, data: voice_recv.VoiceData):
		"""
		Write incoming PCM audio frames into the targeted user's WAV memory buffer.

		Args:
			user: The user transmitting audio.
			data: Received voice data frame containing PCM bytes.
		"""
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
		"""Close active WAV writers and reset memory buffer offsets to zero."""
		for wav_writer in self.user_wavs.values():
			wav_writer.close()
		for buffer in self.user_buffers.values():
			buffer.seek(0)


class VoiceUtils:
	"""Utility class managing voice client operations, audio streaming, recording, speech-to-text, and TTS."""

	def __init__(self):
		"""Initialize Gemini TTS engine modules."""
		log.info("Initializing VoiceUtils.")

		self.tts_modules = [
			GeminiTTS(
				api_key=key,
				model_name="gemini-2.5-flash-preview-tts"
			)
			for key in config.secrets.gemini
		]

		log.info(f"Loaded {len(self.tts_modules)} Gemini TTS module(s).")

	@staticmethod
	async def join(channel: discord.VoiceChannel) -> discord.VoiceClient | None:
		"""
		Connect or move to the designated voice channel.

		Args:
			channel: Target Discord voice channel.

		Returns:
			Active VoiceClient instance or None.
		"""
		if channel.guild.voice_client:
			vc = cast(discord.VoiceClient, channel.guild.voice_client)
			if vc.channel and vc.channel.id != channel.id:
				await vc.move_to(channel)
			return vc

		connection = await channel.connect(cls=voice_recv.VoiceRecvClient)
		return cast(discord.VoiceClient, connection)

	@staticmethod
	async def leave(guild: discord.Guild, force: bool = False) -> bool:
		"""
		Disconnect the bot from the guild's voice channel.

		Args:
			guild: Target Discord guild.
			force: Force disconnect regardless of state.

		Returns:
			True if disconnected, False if not connected.
		"""
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			await vc.disconnect(force=force)
			return True
		return False

	@staticmethod
	async def play(guild: discord.Guild, source: str | discord.AudioSource, volume: float = 1.0) -> bool:
		"""
		Play audio in a voice channel from a URL, local path, or AudioSource object.

		Args:
			guild: Target Discord guild.
			source: URL string, local file path, or discord.AudioSource.
			volume: Playback volume scale factor.

		Returns:
			True if playback initiated, False otherwise.
		"""
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
		"""Pause active audio playback in a guild."""
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.is_playing():
				vc.pause()
				return True
		return False

	@staticmethod
	def resume(guild: discord.Guild) -> bool:
		"""Resume paused audio playback in a guild."""
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.is_paused():
				vc.resume()
				return True
		return False

	@staticmethod
	def stop(guild: discord.Guild) -> bool:
		"""Stop audio playback in a guild."""
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.is_playing():
				vc.stop()
				return True
		return False

	@staticmethod
	def change_volume(guild: discord.Guild, volume: float) -> bool:
		"""
		Modify playback volume on an active PCMVolumeTransformer source.

		Args:
			guild: Target Discord guild.
			volume: Target volume multiplier float.

		Returns:
			True if volume changed, False otherwise.
		"""
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			if vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
				vc.source.volume = volume
				return True
		return False

	@staticmethod
	def is_playing(guild: discord.Guild) -> bool:
		"""Check if audio is currently playing in the guild's voice channel."""
		if guild.voice_client:
			vc = cast(discord.VoiceClient, guild.voice_client)
			return vc.is_playing()
		return False

	@staticmethod
	async def set_bot_status(guild: discord.Guild, mute: bool | None = None, deafen: bool | None = None) -> bool:
		"""
		Update server mute and deafen status for the bot itself.

		Args:
			guild: Target Discord guild.
			mute: Server mute state.
			deafen: Server deafen state.

		Returns:
			True if state updated, False if bot not in voice.
		"""
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
		"""Move a guild member to another voice channel or disconnect them."""
		if member.voice:
			await member.edit(voice_channel=channel)
			return True
		return False

	@staticmethod
	async def mute_member(member: discord.Member, mute: bool) -> bool:
		"""Mute or unmute a guild member in voice."""
		if member.voice:
			await member.edit(mute=mute)
			return True
		return False

	@staticmethod
	async def deafen_member(member: discord.Member, deafen: bool) -> bool:
		"""Deafen or undeafen a guild member in voice."""
		if member.voice:
			await member.edit(deafen=deafen)
			return True
		return False

	@staticmethod
	def start_record(guild: discord.Guild) -> bool:
		"""
		Begin listening and recording audio from voice channel participants.

		Args:
			guild: Target Discord guild.

		Returns:
			True if recording started, False if client is not connected/already listening.
		"""
		if not guild.voice_client:
			return False

		vc = cast(voice_recv.VoiceRecvClient, guild.voice_client)
		if not vc.is_connected() or vc.is_listening():
			return False

		vc.listen(MemoryAudioSink())
		return True

	@staticmethod
	def stop_record(guild: discord.Guild) -> Dict[int, io.BytesIO] | None:
		"""
		Stop audio recording and return captured PCM audio streams by user ID.

		Args:
			guild: Target Discord guild.

		Returns:
			Dictionary mapping user ID keys to BytesIO WAV buffers, or None.
		"""
		if not guild.voice_client:
			return None

		vc = cast(voice_recv.VoiceRecvClient, guild.voice_client)
		if not vc.is_listening():
			return None

		sink = cast(MemoryAudioSink, vc.sink)

		vc.stop_listening()

		return sink.user_buffers

	@staticmethod
	async def transcribe(item: Any, **config_kwargs: Any) -> Tuple[bool, str]:
		"""
		Transcribe audio data using AssemblyAI service.

		Args:
			item: Audio input object (file path, URL, or buffer).
			**config_kwargs: Configuration parameters passed to AssemblyAITranscriber.

		Returns:
			Tuple of (success_boolean, transcript_string).
		"""
		transcriber = AssemblyAITranscriber(
			api_key=config.secrets.assemblyai,
			**config_kwargs
		)
		return await transcriber.call(item)

	async def tts(self, text: str, voice: GeminiVoice = GeminiVoice.CHARON) -> io.BytesIO | None:
		"""
		Synthesize speech from text using Gemini TTS models.

		Args:
			text: Text string to generate audio for.
			voice: Selected voice model enum.

		Returns:
			BytesIO object containing WAV audio data, or None on failure.
		"""
		if not text or not text.strip():
			log.warning("VoiceUtils.tts() received empty text.")
			return None

		active_modules = [
			module
			for module in self.tts_modules
			if not module.is_cooling_down
		]

		if not active_modules:
			log.warning("No active Gemini TTS modules available.")
			return None

		for idx, module in enumerate(active_modules):
			log.debug(f"Attempting Gemini TTS call (Index: {idx}, Voice: {voice.value})")

			success, audio = await module.call(
				text=text,
				voice=voice
			)

			if success and audio:
				log.info(f"Gemini TTS succeeded via module index {idx}.")

				file = io.BytesIO(audio)
				file.name = "tts.wav"
				file.seek(0)

				return file

			log.warning(f"Gemini TTS module index {idx} failed. Trying next available module.")

		log.warning("All Gemini TTS modules failed.")
		return None


__all__ = ('VoiceUtils', 'GeminiVoice')
