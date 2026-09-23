from discord import ui

from vion.config import emoji
from .base import TimeoutView


class Generic(TimeoutView):
	def __init__(
		self,
		*messages: str | None,
		accent_color: int | None = 0x00E9FE,
		sep: str = "\n",
		timeout: float = 180.0,
	) -> None:
		super().__init__(timeout=timeout)
		if accent_color:
			container = ui.Container(accent_color=accent_color)
		else:
			container = ui.Container()

		text_buffer = []

		def flush_buffer():
			if text_buffer:
				container.add_item(ui.TextDisplay(sep.join(text_buffer)))
				text_buffer.clear()

		for item in messages:
			if item is None:
				flush_buffer()
				container.add_item(ui.Separator())
			else:
				text_buffer.append(item)

		flush_buffer()
		self.add_item(container)


def Success(title: str, *messages: str | None, sep: str = "\n") -> Generic:
	return Generic(
		f"### {emoji.checkmark} {title}", *messages, accent_color=0x00FEBB, sep=sep
	)


def Fail(title: str, *messages: str | None, sep: str = "\n") -> Generic:
	return Generic(
		f"### {emoji.crossmark} {title}", *messages, accent_color=0xFE0065, sep=sep
	)


UnexpectedError = Fail(
	"Unexpected Error", "An unexpected error occurred. Please report this"
)
