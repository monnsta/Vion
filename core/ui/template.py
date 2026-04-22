from discord  import ui

from meta     import emoji


class Generic(ui.LayoutView):
	def __init__(self, *messages: str, accent_color: int = 0x00E9FE, sep: str = "\n") -> None:
		super().__init__()
		self.add_item(ui.Container(
			ui.TextDisplay(
				sep.join(messages)
			),
			accent_color=accent_color
		))


def Success(*messages: str, sep: str = "\n") -> Generic:
	return Generic(
		f"### {emoji.checkmark} {sep.join(messages)}",
		accent_color=0x00FEBB
	)

def Fail(*messages: str, sep: str = "\n") -> Generic:
	return Generic(
		f"### {emoji.crossmark} {sep.join(messages)}",
		accent_color=0xFE0065
	)
