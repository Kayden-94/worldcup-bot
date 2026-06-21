import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import database

load_dotenv()

DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
GUILD_ID = int(os.getenv('GUILD_ID', 0))


class WorldCupBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        database.init_db()
        for cog in ('cogs.matches', 'cogs.predictions', 'cogs.leaderboard'):
            await self.load_extension(cog)
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f'[OK] Commandes slash synchronisees sur le serveur {GUILD_ID}', flush=True)
        else:
            await self.tree.sync()
            print('[OK] Commandes slash synchronisees (global, peut prendre ~1h)', flush=True)

    async def on_ready(self):
        print(f'[OK] Connecte en tant que {self.user} (ID: {self.user.id})', flush=True)
        await self.change_presence(
            activity=discord.Game(name='Coupe du Monde 2026')
        )


bot = WorldCupBot()
bot.run(DISCORD_TOKEN)
