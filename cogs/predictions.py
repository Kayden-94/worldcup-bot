import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import database

PAGE_SIZE = 10


def _build_predictions_embed(username: str, preds: list, page: int, total_pages: int) -> discord.Embed:
    now = datetime.now(timezone.utc)
    embed = discord.Embed(
        title=f'🎯 Tes pronos — {username}',
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f'Page {page + 1}/{total_pages}')

    for p in preds:
        match_label = f"{p['home_team']} vs {p['away_team']}"
        pred_score  = f"{p['home_score']}-{p['away_score']}"

        if p['points_earned'] is not None:
            real = f"{p['real_home']}-{p['real_away']}"
            pen  = p.get('penalty_winner')
            if pen == 'home':
                real += f" a.p. ({p['home_team']})"
            elif pen == 'away':
                real += f" a.p. ({p['away_team']})"
            pts   = p['points_earned']
            icon  = '✅' if pts > 0 else '❌'
            s     = 's' if pts != 1 else ''
            value = f"Prono : **{pred_score}** | Résultat : **{real}** | {icon} +{pts} pt{s}"
        elif p['status'] == 'live':
            value = f"Prono : **{pred_score}** | 🔴 En direct"
        else:
            try:
                dt = datetime.fromisoformat(p['match_date'])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts    = int(dt.timestamp())
                value = f"Prono : **{pred_score}** | Dans <t:{ts}:R>"
            except Exception:
                value = f"Prono : **{pred_score}**"

        embed.add_field(name=match_label, value=value, inline=False)

    return embed


class PredictionsView(discord.ui.View):
    def __init__(self, username: str, preds: list):
        super().__init__(timeout=120)
        self.username = username
        self.preds = preds
        self.page = 0
        self.total_pages = max(1, (len(preds) + PAGE_SIZE - 1) // PAGE_SIZE)
        self._refresh_buttons()

    def _refresh_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    def current_embed(self) -> discord.Embed:
        start = self.page * PAGE_SIZE
        return _build_predictions_embed(
            self.username,
            self.preds[start:start + PAGE_SIZE],
            self.page,
            self.total_pages,
        )

    @discord.ui.button(label='◀ Précédent', style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @discord.ui.button(label='Suivant ▶', style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)


class PredictionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /predict ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name='predict',
        description='Soumettre un prono sur un match à venir (ex: score 2-1)',
    )
    @app_commands.describe(
        match='Choisis un match dans la liste',
        score='Ton pronostic, ex: 2-1 (équipe domicile - équipe extérieure)',
    )
    async def predict_command(
        self,
        interaction: discord.Interaction,
        match: str,
        score: str,
    ):
        # Validation du score
        try:
            parts = score.replace(' ', '').split('-')
            if len(parts) != 2:
                raise ValueError
            home_score = int(parts[0])
            away_score = int(parts[1])
            if home_score < 0 or away_score < 0:
                raise ValueError
        except (ValueError, IndexError):
            return await interaction.response.send_message(
                '❌ Format invalide. Exemples valides : `2-1`, `0-0`, `1-3`',
                ephemeral=True,
            )

        # Récupère le match en base
        db_match = database.get_match(match)
        if not db_match:
            return await interaction.response.send_message(
                '❌ Match introuvable. Utilise bien l\'autocomplétion pour choisir le match.',
                ephemeral=True,
            )

        # Vérifie que le match n'a pas encore commencé
        try:
            dt = datetime.fromisoformat(db_match['match_date'])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None

        now = datetime.now(timezone.utc)
        if db_match['status'] != 'scheduled' or (dt and dt <= now):
            return await interaction.response.send_message(
                '🔒 Ce match a déjà commencé (ou est terminé). Prono impossible.',
                ephemeral=True,
            )

        # Enregistre le prono
        database.upsert_prediction(
            discord_id=str(interaction.user.id),
            username=interaction.user.display_name,
            match_id=db_match['match_id'],
            home_score=home_score,
            away_score=away_score,
        )

        try:
            ts = int(dt.timestamp()) if dt else 0
            date_str = f'<t:{ts}:F>' if ts else db_match['match_date']
        except Exception:
            date_str = db_match['match_date']

        embed = discord.Embed(title='✅ Prono enregistré !', color=discord.Color.green())
        embed.add_field(
            name='Match',
            value=f"**{db_match['home_team']}** vs **{db_match['away_team']}**",
            inline=False,
        )
        embed.add_field(name='Ton score prédit', value=f"**{home_score}-{away_score}**", inline=True)
        embed.add_field(name='Date du match', value=date_str, inline=True)
        embed.set_footer(text='Tu peux modifier ton prono jusqu\'au coup d\'envoi.')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @predict_command.autocomplete('match')
    async def _match_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        matches = database.get_upcoming_matches(limit=25)
        now = datetime.now(timezone.utc)
        choices = []

        for m in matches:
            try:
                dt = datetime.fromisoformat(m['match_date'])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt <= now:
                    continue
                date_fmt = dt.strftime('%d/%m %H:%M')
            except Exception:
                date_fmt = '?'

            label = f"{m['home_team']} vs {m['away_team']} — {date_fmt} UTC"
            if current == '' or current.lower() in label.lower():
                choices.append(
                    app_commands.Choice(name=label[:100], value=m['match_id'])
                )

        return choices[:25]

    # ── /mypredictions ────────────────────────────────────────────────────────

    @app_commands.command(name='mypredictions', description='Voir tous tes pronos')
    async def mypredictions_command(self, interaction: discord.Interaction):
        preds = database.get_user_predictions(str(interaction.user.id))

        if not preds:
            return await interaction.response.send_message(
                '📭 Tu n\'as encore soumis aucun prono. Utilise `/predict` pour commencer !',
                ephemeral=True,
            )

        view = PredictionsView(interaction.user.display_name, preds)
        await interaction.response.send_message(
            embed=view.current_embed(),
            view=view if view.total_pages > 1 else None,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(PredictionsCog(bot))
