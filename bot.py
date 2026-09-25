import asyncio
import os
import subprocess
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from rcon.source import Client

# ============================================================
# 設定
# ============================================================
# Discord Bot Token
DISCORD_TOKEN = ""

# Botを使用するDiscordサーバーのID
# テスト中は設定推奨。0の場合は全サーバーに同期。
DISCORD_GUILD_ID = 0

# ASA Server
ASA_DIRECTORY = Path(r"")
ASA_EXECUTABLE = ASA_DIRECTORY / "ArkAscendedServer.exe"

# ASA起動コマンド
# Port / QueryPort / RCONPort は後から変更してください。
ASA_MAP = ""
ASA_PORT = 7777
ASA_QUERY_PORT = 27015
ASA_RCON_PORT = 27020

ASA_MODS = ""
ASA_MAX_PLAYERS = 6


# RCON接続先
# BotとASAが同じPCなら127.0.0.1
RCON_HOST = "127.0.0.1"

# GameUserSettings.ini の ServerAdminPassword
RCON_PASSWORD = ""

# /shutdown関連定数
SHUTDOWN_ALLOWED_USER_ID = 0
SHUTDOWN_WAIT_TIME = 600

# ============================================================
# 起動コマンド作成
# ============================================================

def create_asa_command():
    """
    ASA Server Managerが生成する起動コマンド。
    ポート番号などを変更した場合もここだけ確認すればOK。
    """

    return [
        str(ASA_EXECUTABLE),

        f"{ASA_MAP}"
        f"?Port={ASA_PORT}"
        f"?QueryPort={ASA_QUERY_PORT}"
        f"?RCONPort={ASA_RCON_PORT}",
        f"-mods={ASA_MODS}",
        f"-WinLiveMaxPlayers={ASA_MAX_PLAYERS}",
        "-culture=ja",
        "-ServerPlatform=ALL",
    ]

# ============================================================
# プロセス確認
# ============================================================

def get_asa_process():
    """
    ArkAscendedServer.exe が起動しているか確認。
    """

    try:
        result = subprocess.run(
            [
                "tasklist",
                "/FI",
                "IMAGENAME eq ArkAscendedServer.exe",
                "/NH",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        return "ArkAscendedServer.exe" in result.stdout

    except Exception as e:
        print(f"[PROCESS ERROR] {e}")
        return False


# ============================================================
# RCON接続
# ============================================================

def rcon_command(command: str):
    """
    ASAへRCONコマンドを送信。
    """

    with Client(
        RCON_HOST,
        ASA_RCON_PORT,
        passwd=RCON_PASSWORD,
        timeout=5,
    ) as client:

        response = client.run(command)

        return response


# ============================================================
# RCON接続確認
# ============================================================

def check_rcon():
    try:
        response = rcon_command("ListPlayers")
        return True, response

    except Exception as e:
        print(f"[RCON ERROR] {type(e).__name__}: {e}")
        return False, str(e)



# ============================================================
# ASA起動
# ============================================================

def start_asa():

    if get_asa_process():

        return False, "ASAサーバーは既に起動しています。"

    if not ASA_EXECUTABLE.exists():

        return False, (
            "ArkAscendedServer.exe が見つかりません。\n"
            f"{ASA_EXECUTABLE}"
        )

    command = create_asa_command()

    print("[START]")
    print(" ".join(command))

    try:

        subprocess.Popen(
            command,
            cwd=str(ASA_DIRECTORY),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

        return True, "ASAサーバーを起動しました。"

    except Exception as e:

        return False, (
            "ASAサーバーの起動に失敗しました。\n"
            f"{e}"
        )


# ============================================================
# ASA正常終了
# ============================================================

def stop_asa():

    if not get_asa_process():

        return False, "ASAサーバーは起動していません。"

    try:

        # ----------------------------------------
        # 1. ワールドを保存
        # ----------------------------------------

        print("[RCON] SaveWorld")

        rcon_command("SaveWorld")

        # 保存完了待ち
        import time
        time.sleep(10)

        # ----------------------------------------
        # 2. ASA終了
        # ----------------------------------------

        print("[RCON] DoExit")

        rcon_command("DoExit")

        # ----------------------------------------
        # 3. 終了待ち
        # ----------------------------------------

        timeout = 60

        for _ in range(timeout):

            time.sleep(1)

            if not get_asa_process():

                return True, (
                    "ASAサーバーを正常終了しました。"
                )

        # ----------------------------------------
        # 4. RCONで終了できなかった場合
        # ----------------------------------------

        return False, (
            "DoExitを送信しましたが、"
            "60秒以内にASAが終了しませんでした。\n"
            "プロセスは強制終了していません。"
        )

    except Exception as e:

        return False, (
            "RCONによるASA終了に失敗しました。\n"
            f"{e}"
        )

# ============================================================
# シャットダウン確認ボタン
# ============================================================

class ShutdownConfirmView(discord.ui.View):

    def __init__(self, allowed_user_id: int, timeout_seconds=60):
        super().__init__(timeout=timeout_seconds)

        self.allowed_user_id = allowed_user_id
        self.shutdown_confirmed = False
        self.shutdown_cancelled = False

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:

        # 許可されたユーザー以外
        if interaction.user.id != self.allowed_user_id:

            await interaction.response.send_message(
                "⚠️ この操作を実行する権限がありません。",
                ephemeral=True,
            )

            return False

        return True

    # ----------------------------------------
    # シャットダウン許可
    # ----------------------------------------

    @discord.ui.button(
        label="シャットダウン許可",
        style=discord.ButtonStyle.danger,
        emoji="🔴",
    )
    async def confirm_shutdown(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        self.shutdown_confirmed = True

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=(
                "🔴 シャットダウンが許可されました。\n"
                "PCをシャットダウンします。"
            ),
            view=self,
        )

        self.stop()

    # ----------------------------------------
    # シャットダウン拒否
    # ----------------------------------------

    @discord.ui.button(
        label="シャットダウン拒否",
        style=discord.ButtonStyle.secondary,
        emoji="🟢",
    )
    async def cancel_shutdown(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        self.shutdown_cancelled = True

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="🟢 シャットダウンはキャンセルされました。",
            view=self,
        )

        self.stop()


# ============================================================
# Windowsシャットダウン
# ============================================================

def shutdown_windows():

    try:

        print("[SYSTEM] Windows shutdown")

        subprocess.run(
            [
                "shutdown",
                "/s",
                "/t",
                "0",
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        return True, "Windowsをシャットダウンします。"

    except Exception as e:

        print(f"[SHUTDOWN ERROR] {e}")

        return False, (
            "Windowsのシャットダウンに失敗しました。\n"
            f"{e}"
        )


# ============================================================
# プレイヤー情報
# ============================================================

def get_players():

    try:

        response = rcon_command("ListPlayers")

        if not response:
            return []

        players = []

        for line in response.splitlines():

            line = line.strip()

            if not line:
                continue

            players.append(line)

        return players

    except Exception:

        return None


# ============================================================
# Discord Bot
# ============================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)


# ============================================================
# /start
# ============================================================

@bot.tree.command(
    name="start",
    description="ASAサーバーを起動します。",
)
async def start(
    interaction: discord.Interaction,
):

    await interaction.response.defer()

    success, message = await asyncio.to_thread(
        start_asa
    )

    if success:

        embed = discord.Embed(
            title="🚀 ASA Server Start",
            description=message,
            color=discord.Color.green(),
        )

    else:

        embed = discord.Embed(
            title="⚠️ ASA Server Start",
            description=message,
            color=discord.Color.orange(),
        )

    await interaction.followup.send(
        embed=embed
    )


# ============================================================
# /stop
# ============================================================

@bot.tree.command(
    name="stop",
    description="ASAサーバーを安全に終了します。",
)
async def stop(
    interaction: discord.Interaction,
):

    await interaction.response.defer()

    success, message = await asyncio.to_thread(
        stop_asa
    )

    if success:

        embed = discord.Embed(
            title="🛑 ASA Server Stop",
            description=message,
            color=discord.Color.red(),
        )

    else:

        embed = discord.Embed(
            title="⚠️ ASA Server Stop",
            description=message,
            color=discord.Color.orange(),
        )

    await interaction.followup.send(
        embed=embed
    )

# ============================================================
# /shutdown
# ============================================================

@bot.tree.command(
    name="shutdown",
    description="ASAサーバーを停止してからPCをシャットダウンします。",
)
async def shutdown(
    interaction: discord.Interaction,
):

    await interaction.response.defer()

    # ----------------------------------------
    # ASAサーバー停止
    # ----------------------------------------

    process_running = await asyncio.to_thread(
        get_asa_process
    )

    if process_running:

        print("[SHUTDOWN] ASA is running.")

        success, message = await asyncio.to_thread(
            stop_asa
        )

        # ASAを正常終了できなかった場合
        # PCはシャットダウンしない
        if not success:

            embed = discord.Embed(
                title="⚠️ Shutdown Cancelled",
                description=(
                    "ASAサーバーを正常に終了できなかったため、"
                    "PCのシャットダウンを中止しました。\n\n"
                    f"{message}"
                ),
                color=discord.Color.orange(),
            )

            await interaction.followup.send(
                embed=embed
            )

            return

        # ----------------------------------------
        # ASA終了確認
        # ----------------------------------------

        shutdown_wait = SHUTDOWN_WAIT_TIME

        print(
            f"[SHUTDOWN] Waiting for confirmation "
            f"({shutdown_wait} seconds)..."
        )

    else:

        print(
            "[SHUTDOWN] ASA is already stopped."
        )

        shutdown_wait = SHUTDOWN_WAIT_TIME

    # ----------------------------------------
    # シャットダウン確認ボタン
    # ----------------------------------------

    view = ShutdownConfirmView(
        allowed_user_id=SHUTDOWN_ALLOWED_USER_ID,
        timeout_seconds=shutdown_wait,
    )


    embed = discord.Embed(
        title="⚠️ PC Shutdown Confirmation",
        description=(
            "ASAサーバーの停止処理が完了しました。\n\n"
            f"**{shutdown_wait}秒後にPCを自動的にシャットダウンします。**\n\n"
            "今すぐシャットダウンする場合は"
            " **「シャットダウン許可」** を押してください。\n"
            "シャットダウンを中止する場合は"
            " **「シャットダウン拒否」** を押してください。"
        ),
        color=discord.Color.orange(),
    )

    await interaction.followup.send(
        content=f"<@{SHUTDOWN_ALLOWED_USER_ID}>",
        embed=embed,
        view=view,
    )


    # ----------------------------------------
    # ボタン操作またはタイムアウト待ち
    # ----------------------------------------

    await view.wait()

    # ----------------------------------------
    # シャットダウン拒否
    # ----------------------------------------

    if view.shutdown_cancelled:

        print(
            "[SHUTDOWN] Shutdown cancelled by user."
        )

        return

    # ----------------------------------------
    # シャットダウン許可
    # ----------------------------------------

    if view.shutdown_confirmed:

        print(
            "[SHUTDOWN] Shutdown confirmed."
        )

    # ----------------------------------------
    # タイムアウト
    # ----------------------------------------

    else:

        print(
            "[SHUTDOWN] Confirmation timeout."
        )

    # ----------------------------------------
    # Windowsシャットダウン
    # ----------------------------------------

    success, message = await asyncio.to_thread(
        shutdown_windows
    )

    if success:

        print(
            "[SHUTDOWN] Windows shutdown started."
        )

    else:

        embed = discord.Embed(
            title="⚠️ System Shutdown Failed",
            description=message,
            color=discord.Color.orange(),
        )

        await interaction.followup.send(
            embed=embed
        )


# ============================================================
# /status
# ============================================================

@bot.tree.command(
    name="status",
    description="ASAサーバーの状態を確認します。",
)
async def status(
    interaction: discord.Interaction,
):

    await interaction.response.defer()

    process_running = await asyncio.to_thread(
        get_asa_process
    )

    # ----------------------------------------
    # サーバー停止中
    # ----------------------------------------

    if not process_running:

        embed = discord.Embed(
            title="🔴 ASA Server",
            description="サーバーは **停止中** です。",
            color=discord.Color.red(),
        )

        embed.add_field(
            name="Status",
            value="OFFLINE",
            inline=True,
        )

        await interaction.followup.send(
            embed=embed
        )

        return

    # ----------------------------------------
    # RCON確認
    # ----------------------------------------

    rcon_ok, rcon_response = await asyncio.to_thread(
        check_rcon
    )

    # ----------------------------------------
    # RCON接続不可
    # ----------------------------------------

    if not rcon_ok:

        embed = discord.Embed(
            title="🟡 ASA Server",
            description="ASAプロセスは起動していますが、RCONに接続できません。",
            color=discord.Color.orange(),
        )

        embed.add_field(
            name="Process",
            value="ONLINE",
            inline=True,
        )

        embed.add_field(
            name="RCON",
            value="OFFLINE",
            inline=True,
        )

        embed.add_field(
            name="Error",
            value=f"```{rcon_response}```",
            inline=False,
        )

        await interaction.followup.send(embed=embed)
        return


    # ----------------------------------------
    # プレイヤー情報
    # ----------------------------------------

    players = await asyncio.to_thread(
        get_players
    )

    if players is None:

        player_text = "取得失敗"

    elif len(players) == 0:

        player_text = "0"

    else:

        player_text = str(len(players))

    # ----------------------------------------
    # ONLINE
    # ----------------------------------------

    embed = discord.Embed(
        title="🟢 ASA Server",
        description="サーバーは **オンライン** です。",
        color=discord.Color.green(),
    )

    embed.add_field(
        name="Map",
        value=ASA_MAP,
        inline=True,
    )

    embed.add_field(
        name="Players",
        value=f"{player_text} / {ASA_MAX_PLAYERS}",
        inline=True,
    )

    embed.add_field(
        name="RCON",
        value="ONLINE",
        inline=True,
    )

    await interaction.followup.send(
        embed=embed
    )


# ============================================================
# /players
# ============================================================

@bot.tree.command(
    name="players",
    description="ASAに接続中のプレイヤーを表示します。",
)
async def players(
    interaction: discord.Interaction,
):

    await interaction.response.defer()

    process_running = await asyncio.to_thread(
        get_asa_process
    )

    if not process_running:

        await interaction.followup.send(
            "🔴 ASAサーバーは停止しています。"
        )

        return

    result = await asyncio.to_thread(
        get_players
    )

    if result is None:

        await interaction.followup.send(
            "⚠️ RCONに接続できません。"
        )

        return

    if len(result) == 0:

        text = "現在プレイヤーはいません。"

    else:

        text = "\n".join(
            f"• {player}"
            for player in result
        )

    embed = discord.Embed(
        title="👥 ASA Players",
        description=text,
        color=discord.Color.blue(),
    )

    embed.set_footer(
        text=f"{len(result)} player(s)"
    )

    await interaction.followup.send(
        embed=embed
    )


# ============================================================
# Bot起動
# ============================================================

@bot.event
async def on_ready():

    print("----------------------------------------")
    print(f"Bot Login : {bot.user}")
    print(f"ASA Path  : {ASA_DIRECTORY}")
    print(f"ASA EXE   : {ASA_EXECUTABLE}")
    print("----------------------------------------")

    try:

        if DISCORD_GUILD_ID != 0:

            guild = discord.Object(
                id=DISCORD_GUILD_ID
            )

            bot.tree.copy_global_to(
                guild=guild
            )

            synced = await bot.tree.sync(
                guild=guild
            )

        else:

            synced = await bot.tree.sync()

        print(
            f"Slash Commands synced: {len(synced)}"
        )

    except Exception as e:

        print(
            f"Slash Command sync error: {e}"
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if DISCORD_TOKEN == "ここにDiscord Bot Token":

        print(
            "Discord Bot Tokenを設定してください。"
        )

    else:

        bot.run(DISCORD_TOKEN)
