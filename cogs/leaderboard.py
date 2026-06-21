import discord
from discord import app_commands
from discord.ext import commands
import os
import database

OWNER_ID = int(os.getenv('OWNER_ID', 0))


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


    @app_commands.command(name='setpoints', description='[OWNER] Corriger manuellement les points d\'un joueur')
    @app_commands.describe(
        membre='Le membre Discord a modifier',
        points='Nouveau total de points',
    )
    async def setpoints_command(self, interaction: discord.Interaction, membre: discord.Member, points: int):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                'Seul le proprietaire du bot peut utiliser cette commande.',
                ephemeral=True,
            )
        if points < 0:
            return await interaction.response.send_message('Les points ne peuvent pas etre negatifs.', ephemeral=True)

        database.set_user_points(str(membre.id), points)

        embed = discord.Embed(
            title='Points corriges',
            description=f'**{membre.display_name}** : {points} pt{"s" if points != 1 else ""}',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
