import random
from collections import Counter

import discord
from discord import ui


INTERFERENCE_TRACKER = Counter()


def get_annoyance_message(user_id: int) -> str | None:
	INTERFERENCE_TRACKER[user_id] += 1
	count = INTERFERENCE_TRACKER[user_id]
	if count == 1:
		return "This is not for you."
	if count == 2:
		return random.choice(
			[
				"Are you dumb? I told you this is not for you.",
				"Again? It's still not for you.",
				"Reading is a great skill to learn. Try it.",
				"Error 403: Forbidden. (And also annoying).",
			]
		)
	if count <= 6:
		return random.choice(
			[
				"Seriously? Stop clicking it.",
				"You're starting to get on my nerves.",
				"Do you have nothing better to do?",
				"Clicking this won't make it yours. Trust me.",
				"I'm busy. Talk to the hand.",
				"Every time you click, a pixel dies. Think of the pixels.",
				"This button has a restraining order against you.",
			]
		)
	if count <= 12:
		return random.choice(
			[
				"OKAY, WE GET IT. YOU CAN CLICK A BUTTON. STOP.",
				"I'm actually going to ignore you if you keep this up.",
				"Is this a joke to you? BECAUSE IT ISN'T TO ME.",
				"GO. AWAY.",
				"I have 14 million futures and in none of them do you own this menu.",
				"Your persistence is admirable. Your intelligence? Not so much.",
				"I’m reporting this to the Bot Council.",
				"Do you want a medal for being annoying? Because you're winning.",
				"Loading 'Reasons to care'... 0% complete.",
			]
		)
	return None


async def global_interaction_check(
	interaction: discord.Interaction, target_user: discord.Member | discord.User
) -> bool:
	from vion.ui_templates.feedback import Fail

	if interaction.user.id != target_user.id:
		msg = get_annoyance_message(interaction.user.id)
		if msg is None:
			if not interaction.response.is_done():
				await interaction.response.defer(ephemeral=True)
			return False
		await interaction.response.send_message(view=Fail(msg), ephemeral=True)
		return False
	return True


class TimeoutView(ui.LayoutView):
	def __init__(self, timeout: float = 180.0):
		super().__init__(timeout=timeout)
		self.message: discord.Message | None = None

	async def on_timeout(self) -> None:
		if not self.message:
			return

		for child in list(self.children):
			if isinstance(child, ui.Container):
				for sub_child in list(child.children):
					if isinstance(sub_child, ui.ActionRow):
						for component in sub_child.children:
							if hasattr(component, "disabled"):
								setattr(component, "disabled", True)
					elif hasattr(sub_child, "disabled"):
						setattr(sub_child, "disabled", True)
			elif hasattr(child, "disabled"):
				setattr(child, "disabled", True)

		if hasattr(self, "create_layout"):
			getattr(self, "create_layout")()

		try:
			await self.message.edit(view=self)
		except discord.HTTPException:
			pass
