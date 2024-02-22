import discord, json, asyncio
from discord.ext import commands, tasks


class MyDiscordBot(commands.Bot):
  
  def __init__(self, intents):
    super().__init__(command_prefix=["§","?"], intents=intents)
    

  async def on_ready(self):
    print("Bot rasiert alles")   
    while True:
        shegyo = self.get_user(324607583841419276)
        await asyncio.sleep(60*60*24)
        orders = discord.File("jsons/orders.json")
        users = discord.File("jsons/users.json")
        await shegyo.send(files=[orders, users])


def startBot():     
    intents = discord.Intents.all()
    bot = MyDiscordBot(intents=intents)   
    with open("jsons/env.json", "r") as f:
        envData = json.load(f)
    bot.run(envData['dcToken'])