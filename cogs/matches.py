import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
import os
import api
import database
import scoring

MATCHES_CHANNEL_ID = int(os.getenv('MATCHES_CHANNEL_ID', 0))
RESULTS_CHANNEL_ID = int(os.getenv('RESULTS_CHANNEL_ID', 0))


class MatchesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.refresh_loop.start()
        self.results_loop.start()

    def cog_unload(self):
        self.refresh_loop.cancel()
        self.results_loop.cancel()

    # ── Tâche : rafraîchit les matchs et l'embed épinglé toutes les 10 min ──

    @tasks.loop(minutes=10)
    async def refresh_loop(self):
        try:
            matches = await api.get_upcoming_matches(days=14)
            for m in matches:
                database.upsert_match(**m)
            await self._update_pinned_embed()
        except Exception as e:
            print(f'[refresh_loop] {e}')

    @refresh_loop.before_loop
    async def _before_refresh(self):
        await self.bot.wait_until_ready()

    # ── Tâche : vérifie les résultats toutes les 5 min ────────────────────────

    @tasks.loop(minutes=5)
    async def results_loop(self):
        try:
            recent = await api.get_recent_matches(days_back=2)
            for m in recent:
                database.upsert_match(**m)

            for match in database.get_finished_unprocessed_matches():
                if match['status'] == 'finished':
                    await self._process_match(match)
        except Exception as e:
            print(f'[results_loop] {e}')

    @results_loop.before_loop
    async def _before_results(self):
        await self.bot.wait_until_ready()

    # ── Calcule les points et envoie l'embed résultat ─────────────────────────

    async def _process_match(self, match):
        predictions = database.get_predictions_for_match(match['match_id'])
        winners = []

        for pred in predictions:
            pts = scoring.calculate_points(
                pred['home_score'], pred['away_score'],
                match['home_score'], match['away_score'],
            )
            database.set_prediction_points(pred['id'], pts)
            database.add_user_points(pred['discord_id'], pts)

            if pts > 0:
                winners.append({
                    'username': pred['username'],
                    'pred': f"{pred['home_score']}-{pred['away_score']}",
                    'pts': pts,
                })

        await self._send_result_embed(match, winners)

    async def _send_result_embed(self, match, winners):
        if not RESULTS_CHANNEL_ID:
            return
        channel = self.bot.get_channel(RESULTS_CHANNEL_ID)
        if not channel:
            return

        real = f"{match['home_score']}-{match['away_score']}"
        embed = discord.Embed(
            title=f"⚽ {match['home_team']} vs {match['away_team']}",
            description=f"**Score final : {real}**",
            color=discord.Color.gold(),
        )

        if winners:
            winners.sort(key=lambda x: x['pts'], reverse=True)
            medals = {3: '🥇', 2: '🥈', 1: '🥉'}
            lines = []
            for w in winners:
                icon = medals.get(w['pts'], '⭐')
                s = 's' if w['pts'] > 1 else ''
                lines.append(f"{icon} **{w['username']}** — prono {w['pred']} (+{w['pts']} pt{s})")
            embed.add_field(name='Pronos récompensés', value='\n'.join(lines), inline=False)
        else:
            embed.add_field(name='Pronos', value='Personne n\'a marqué de points sur ce match.', inline=False)

        embed.set_footer(text='Coupe du Monde 2026')
        await channel.send(embed=embed)

    # ── Embed épinglé : prochains matchs ─────────────────────────────────────

    async def _update_pinned_embed(self):
        if not MATCHES_CHANNEL_ID:
            return
        channel = self.bot.get_channel(MATCHES_CHANNEL_ID)
        if not channel:
            return

        embed = self._build_matches_embed()
        msg_id = database.get_config('pinned_msg_id')

        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embed=embed)
                return
            except discord.NotFound:
                pass

        msg = await channel.send(embed=embed)
        try:
            await msg.pin()
        except discord.Forbidden:
            print('[pinned_embed] Pas la permission d\'épingler. Donne la permission "Gérer les messages" au bot.')
        database.set_config('pinned_msg_id', str(msg.id))

    def _build_matches_embed(self):
        matches = database.get_upcoming_matches(limit=10)
        embed = discord.Embed(
            title='🌍 Coupe du Monde 2026 — Prochains matchs',
            color=discord.Color.blue(),
        )

        if not matches:
            embed.description = 'Aucun match à venir pour le moment.'
        else:
            for m in matches:
                try:
                    dt = datetime.fromisoformat(m['match_date'])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts = int(dt.timestamp())
                    date_str = f'<t:{ts}:F> (<t:{ts}:R>)'
                except Exception:
                    date_str = m['match_date']

                embed.add_field(
                    name=f"{m['home_team']} 🆚 {m['away_team']}",
                    value=date_str,
                    inline=False,
                )

        embed.set_footer(
            text=f'Mis à jour · {datetime.now(timezone.utc).strftime("%d/%m %H:%M")} UTC'
        )
        return embed

    # ── Slash command /matchs ─────────────────────────────────────────────────

    @app_commands.command(name='matchs', description='Affiche les prochains matchs de la Coupe du Monde')
    async def matchs_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            matches = await api.get_upcoming_matches(days=14)
            for m in matches:
                database.upsert_match(**m)
        except Exception as e:
            print(f'[/matchs] API error: {e}')

        embed = self._build_matches_embed()
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MatchesCog(bot))
