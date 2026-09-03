import asyncio
import discord
from discord import ui

from vion.config import emoji
from .base import TimeoutView, global_interaction_check
from .feedback import Fail, Generic, Success
from .modal import TextInputModal


class Confirmation(TimeoutView):
    def __init__(
        self,
        question: str,
        confirm: str,
        cancel: str,
        user: discord.Member | discord.User,
        accent_color: int = 0x00E9FE,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.confirm_text = confirm
        self.cancel_text = cancel
        self.user = user
        self.value = None
        self._view_finished = asyncio.Future()

        container = ui.Container(ui.TextDisplay(f"### {question}"), accent_color=accent_color)

        confirm_btn = ui.Button(emoji=emoji.checkmark, style=discord.ButtonStyle.success)
        confirm_btn.callback = self.confirm

        cancel_btn = ui.Button(emoji=emoji.crossmark, style=discord.ButtonStyle.secondary)
        cancel_btn.callback = self.cancel

        container.add_item(ui.ActionRow(confirm_btn, cancel_btn))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await global_interaction_check(interaction, self.user)

    async def on_timeout(self) -> None:
        if not self._view_finished.done():
            self._view_finished.set_result(None)
        await super().on_timeout()

    async def confirm(self, interaction: discord.Interaction):
        self.value = True
        self._view_finished.set_result(True)
        self.stop()
        await interaction.response.edit_message(view=Success(self.confirm_text))

    async def cancel(self, interaction: discord.Interaction):
        self.value = False
        self._view_finished.set_result(False)
        self.stop()
        await interaction.response.edit_message(view=Fail(self.cancel_text))

    async def wait_for_answer(self) -> bool | None:
        return await self._view_finished


class TextForm(Generic):
    def __init__(
        self,
        message_content: str,
        button_label: str,
        modal_title: str,
        field_label: str,
        default_field_value: str | None = None,
        user: discord.Member | discord.User | None = None,
        accent_color: int = 0x00E9FE,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(message_content, accent_color=accent_color, timeout=timeout)
        self.user = user
        self.modal_title = modal_title
        self.field_label = field_label
        self.default_field_value = default_field_value

        self.result_future = asyncio.Future()

        container = self.children[0]
        btn = ui.Button(label=button_label, style=discord.ButtonStyle.primary)
        btn.callback = self.open_modal
        getattr(container, "add_item")(ui.ActionRow(btn))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user:
            return await global_interaction_check(interaction, self.user)
        return True

    async def on_timeout(self) -> None:
        if not self.result_future.done():
            self.result_future.set_result(None)
        await super().on_timeout()

    async def open_modal(self, interaction: discord.Interaction):
        modal = TextInputModal(
            title=self.modal_title,
            field_label=self.field_label,
            default_value=self.default_field_value,
            future=self.result_future,
        )
        await interaction.response.send_modal(modal)

    async def wait_for_input(self) -> str | None:
        try:
            return await self.result_future
        except asyncio.CancelledError:
            return None
