import asyncio
import logging
from collections.abc import Sequence
from enum import Enum
import os
from pathlib import Path
from threading import Thread

import discord
from discord import Member, Role, UserFlags
from discord.ext import commands
from flask import (
    Blueprint,
    Flask,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from flask.sessions import SessionMixin

from definitions import SECRETS_PATH

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = False
bp = Blueprint("app", __name__, template_folder="templates")
bot = commands.Bot(command_prefix="!", intents=intents)
bot.shard_id = os.getpid()
logging.basicConfig(level=logging.INFO)
guilds = []

loop = asyncio.new_event_loop()


flag_to_badge_dict = {
    UserFlags.hypesquad_balance: "https://discordresources.com/img/hypesquadbalance.svg",
    UserFlags.verified_bot: "https://discordresources.com/img/special/VerifiedBot.svg",
}


class ExceptionType(Enum):
    NoGuild = "Guild not provided"
    BadGuild = "Guild not found"
    NoMember = "Member not provided"
    BadMember = "Member not found"


class BotException(Exception):
    def __init__(self, type: ExceptionType, *args: object) -> None:
        self.type: ExceptionType = type
        super().__init__(*args)

    def value(self) -> str:
        return self.type.value


HTML_TEMPLATE = """
{% include 'template.html' %}
"""


@bp.route("/")
def home():
    guilds = bot.guilds
    session["url"] = request.url
    return render_template_string(
        HTML_TEMPLATE,
        guilds=guilds,
    )


@bp.route("/team", methods=["GET"])
def team_page():
    guilds = bot.guilds
    members: list[dict[str, str | bool | int | Sequence[Role | str] | None]] = []
    guild_id = request.args.get("guild_id")
    search_query = request.args.get("search_query")
    if search_query is not None and len(search_query) < 1:
        return redirect(url_for("app.team_page", guild_id=guild_id))
    if not guild_id:
        session["error"] = ExceptionType.NoGuild.value
        return fail_route(session, 404)
    guild = bot.get_guild(int(guild_id))
    if not guild:
        session["error"] = ExceptionType.BadGuild.value
        return fail_route(session, 404)
    for member in guild.members:
        if search_query:
            if search_query.lower() not in member.name.lower():
                continue
        banner_url = None
        bio = None
        try:
            banner_url = str(member.banner.url) if member.banner else None

        except Exception as e:
            print(f"Error fetching banner or bio: {e}")

        members.append(
            {
                "name": str(member),
                "is_bot": member.bot,
                "is_admin": member.guild_permissions.administrator,
                "avatar_url": str(member.display_avatar.url),
                "status": str(member.status).capitalize(),
                "banner_url": banner_url,
                "bio": str(bio),
                "id": member.id,
                "roles": member.roles[1:],
                "badges": [
                    str(flag_to_badge_dict.get(badge))
                    for badge in member.public_flags.all()
                ],
            }
        )

    session["url"] = request.url

    return render_template_string(
        HTML_TEMPLATE,
        members=members,
        guilds=guilds,
        guild_name=guild.name,
        guild_id=guild.id,
    )


@bp.route("/ban", methods=["POST"])
@bp.route("/kick", methods=["POST"])
def manage_member():
    guild_id = request.form.get("guild_id")
    member_id = request.form.get("member_id")
    print(request.url_rule)
    rule = "/kick"
    if request.url_rule:
        rule = str(request.url_rule)
    action_dict = {
        "/kick": kick_member_async,
        "/ban": ban_member_async,
    }

    try:
        member = get_member(guild_id, member_id)
        future = asyncio.run_coroutine_threadsafe(action_dict[rule](member), loop)
        user_action = future.result(10)
        if session.get("url"):
            return redirect(session.pop("url", None))
        else:
            return f"Successfully {user_action} user..."

    except discord.Forbidden as e:
        session["error"] = f"Failed to {e.text}"
        return fail_route(session, 403)

    except BotException as e:
        session["error"] = e.value()
        return fail_route(session, 404)

    except ValueError:
        return "Invalid Guild ID format.", 400


@bp.route("/leave/<int:guild_id>")
def leave_server(guild_id: int):
    guild = bot.get_guild(guild_id)
    if not guild:
        session["error"] = ExceptionType.BadGuild.value
        return fail_route(session, 404)
    try:
        guild_leave = asyncio.run_coroutine_threadsafe(guild.leave(), loop)
        guild_leave.result(10)
        return redirect(url_for("app.home"))
    except discord.Forbidden as e:
        session["error"] = f"I don't have permission to leave this server, {e}"
        return fail_route(session, 403)


async def kick_member_async(member: Member):
    try:
        await member.kick(reason="Requested by bot.")
        return "Kicked"
    except discord.Forbidden as e:
        raise discord.Forbidden(e.response, f"Kick: {e.text}")    


async def ban_member_async(member: Member):
    try:
        await member.ban(reason="Requested by bot.")
        return "Banned"
    except discord.Forbidden as e:
        raise discord.Forbidden(e.response, f"Ban: {e.text}")


@bot.event
async def on_ready():
    if bot.user:
        print(f"Bot logged in as {bot.user.name}")


def get_member(guild_id: str | None, member_id: str | None):
    if not guild_id:
        raise BotException(ExceptionType.NoGuild)

    if not member_id:
        raise BotException(ExceptionType.NoMember)

    try:
        guild = bot.get_guild(int(guild_id))
        if not guild:
            raise BotException(ExceptionType.BadGuild)
        member = guild.get_member(int(member_id))
        if not member:
            raise BotException(ExceptionType.BadMember)
        else:
            return member
    except ValueError:
        raise


def fail_route(session: SessionMixin, code: int):
    if session.get("url"):
        return redirect(session.pop("url"))
    else:
        return session["error"], code


def run_flask(app: Flask):
    return app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)


def run_bot_loop():
    asyncio.set_event_loop(loop)
    token = read_token_from_file(SECRETS_PATH / "discord_token")
    _ = loop.create_task(bot.start(token))
    _ = loop.run_forever()


def read_token_from_file(path: Path):
    with open(path, "r") as file:
        return file.readline()


def create_app():
    global guilds
    app = Flask(__name__)
    app.secret_key = read_token_from_file(SECRETS_PATH / "flask_token")
    app.register_blueprint(bp)
    loop_thread = Thread(target=run_bot_loop, daemon=True)
    loop_thread.start()
    return app


if __name__ == "__main__":
    print("Prefer flask run instead!")
    run_flask(create_app())
