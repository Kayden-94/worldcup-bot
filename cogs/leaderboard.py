import discord
from discord import app_commands
from discord.ext import commands
import database


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='leaderboard', description='Classement des pronos sur le serveur')
    async def leaderboard_command(self, interaction: discord.Interaction):
        rows = database.get_leaderboard(limit=10)

        if not rows:
            return await interaction.response.send_message(
                '📭 Personne n\'a encore marqué de points. Soyez les premiers avec `/predict` !',
            )

        medals = ['🥇', '🥈', '🥉']
        lines  = []
        for i, row in enumerate(rows):
            icon = medals[i] if i < 3 else f'**#{i + 1}**'
            pts  = row['total_points']
            s    = 's' if pts != 1 else ''
            lines.append(f"{icon} **{row['username']}** — {pts} pt{s}")

        embed = discord.Embed(
            title='🏆 Classement — Coupe du Monde 2026',
            description='\n'.join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text='Mis à jour automatiquement après chaque match')
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
