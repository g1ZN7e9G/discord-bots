import discord
from flask import Flask, render_template_string, request, redirect, url_for
from discord.ext import commands
from discord import UserFlags
from threading import Thread
import asyncio
import logging

intents = discord.Intents.default()
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)
loop = asyncio.new_event_loop()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

members = []
guilds = []

flag_to_badge_dict = {
    UserFlags.hypesquad_balance:"https://discordresources.com/img/hypesquadbalance.svg",
    UserFlags.verified_bot: "https://discordresources.com/img/special/VerifiedBot.svg",
}

HTML_TEMPLATE = '''
{% include 'template.html' %}
'''

@app.route('/')
def home():
    global guilds
    guilds = bot.guilds
    return render_template_string(HTML_TEMPLATE, guilds=guilds)

@app.route('/team', methods=['POST'])
def team_page():
    global members
    guild_id = request.form.get('guild_id')
    
    if guild_id:
        guild = bot.get_guild(int(guild_id))
        
        if guild:
            members = []
            for member in guild.members:
                banner_url = None
                bio = None
                try:
                    banner_url = str(member.banner.url) if member.banner else None
                except Exception as e:
                    print(f"Error fetching banner or bio: {e}")

                print(member.public_flags.all())
                members.append({
                    "name": member.name,
                    "discriminator": member.discriminator,
                    "is_bot": member.bot,
                    "is_admin": member.guild_permissions.administrator,
                    "avatar_url": str(member.avatar.url) if member.avatar else None,
                    "status": str(member.status).capitalize(),
                    "banner_url": banner_url,
                    "bio": bio,
                    "id": member.id,
                    "roles": member.roles[1:],
                    "badges": [flag_to_badge_dict.get(badge) for badge in member.public_flags.all()]
                })
            return render_template_string(HTML_TEMPLATE, members=members, guilds=guilds, guild_name=guild.name, guild_id=guild.id)
        else:
            return render_template_string(HTML_TEMPLATE, error="Guild not found.", guilds=guilds)
    else:
        return render_template_string(HTML_TEMPLATE, error="No guild selected.", guilds=guilds)

@app.route('/kick/<int:member_id>', methods=['POST'])
def kick_member(member_id):
    guild_id = request.form.get('guild_id')
    
    if guild_id is None:
        return "Guild ID is missing.", 400
    
    try:
        guild = bot.get_guild(int(guild_id))
        if guild:
            member = guild.get_member(member_id)
            if member:
                future = asyncio.run_coroutine_threadsafe(kick_member_async(member), loop)
                try:
                    future.result(10)
                    return redirect(url_for('home', guild_id=guild_id))
                except discord.Forbidden as e:
                    return f"This was not allowed, {e}", 401
            return "Member not found.", 404
        return "Guild not found.", 404
    except ValueError:
        return "Invalid Guild ID format.", 400


@app.route('/ban/<int:member_id>', methods=['POST'])
def ban_member(member_id):
    guild_id = request.form.get('guild_id')
    
    if guild_id is None:
        return "Guild ID is missing.", 400
    
    try:
        guild = bot.get_guild(int(guild_id))
        if guild:
            member = guild.get_member(member_id)
            if member:
                future = asyncio.run_coroutine_threadsafe(ban_member_async(member), loop)
                try:
                    future.result(10)
                    return redirect(url_for('home', guild_id=guild_id))
                except discord.Forbidden as e:
                    return f"This was not allowed, {e}", 401
            return "Member not found.", 404
        return "Guild not found.", 404
    except ValueError:
        return "Invalid Guild ID format.", 400

@app.route('/leave/<int:guild_id>')
def leave_server(guild_id):
    guild = bot.get_guild(guild_id)
    if guild:
        try:
            guild_leave = asyncio.run_coroutine_threadsafe(guild.leave(), loop)
            guild_leave.result(10)
            return redirect(url_for('home'))
        except discord.Forbidden:
            return "I don't have permission to leave this server.", 403
    return "Guild not found.", 404

async def kick_member_async(member):
    try:
        await member.kick(reason="Requested by bot.")
    except discord.Forbidden:
        raise 

async def ban_member_async(member):
    try:
        await member.ban(reason="Requested by bot.")
    except discord.Forbidden as e:
        raise discord.Forbidden(e.response, "I don't have permission to ban this member.")

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user.name}')

def run_flask():
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)

def read_token_from_file(path):
    with open(path, 'r') as file:
        return file.readline()

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    token = read_token_from_file(".token")
    loop.create_task(bot.start(token))
    loop.run_forever()
