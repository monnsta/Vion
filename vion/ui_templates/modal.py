import asyncio
import discord
from discord import ui


class GotoModal(ui.Modal):
    def __init__(self, view: "Paginated"):  # type: ignore # noqa: F821
        super().__init__(title="Jump to Page")
        from ui_templates.feedback import Fail

        self._Fail = Fail
        self.view_ref = view
        self.page_input = ui.TextInput(
            label=f"Page Number (1-{view.total_pages})",
            style=discord.TextStyle.short,
            default=str(view.current_page + 1),
            required=True,
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_input.value) - 1
            if 0 <= page < self.view_ref.total_pages:
                self.view_ref.current_page = page
                self.view_ref.create_layout()
                await interaction.response.edit_message(view=self.view_ref)
            else:
                await interaction.response.send_message(
                    view=self._Fail("Error", "Invalid page number."), ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                view=self._Fail("Error", "Please enter a valid number."), ephemeral=True
            )


class TextInputModal(ui.Modal):
    def __init__(
        self,
        title: str,
        field_label: str,
        default_value: str | None,
        future: asyncio.Future,
    ):
        super().__init__(title=title)
        self.future = future
        self.input_field = ui.TextInput(
            label=field_label,
            style=discord.TextStyle.paragraph,
            default=default_value,
            required=True,
        )
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.future.done():
            self.future.set_result(self.input_field.value)
        await interaction.response.defer()
