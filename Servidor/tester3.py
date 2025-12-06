import asyncio
import websockets
import json
import random
import math
import sys
from websockets.exceptions import ConnectionClosed

# --- CONFIGURAÇÕES ---
SERVER_URL = "ws://localhost:8765"
RAMP_UP_DELAY = 0.1   
INPUT_RATE = 10       

# Quantidade de Bots
TARGET_PVE = 47
TARGET_PVP = 16

UPGRADE_ITEMS = ["motor", "dano", "escudo", "max_health", "auxiliar"]

class SmartBot:
    def __init__(self, bot_id, mode):
        self.bot_id = bot_id
        self.mode = mode
        self.requested_name = f"Bot_{mode}_{bot_id}" # Nome solicitado
        self.real_id = None                           # Nome real (dado pelo servidor)
        self.running = True
        self.websocket = None
        self.my_data = None
        self.latest_state = None

    async def connect(self):
        try:
            async with websockets.connect(SERVER_URL) as websocket:
                self.websocket = websocket
                
                # 1. Login
                await websocket.send(json.dumps({
                    "type": "LOGIN",
                    "name": self.requested_name,
                    "mode": self.mode
                }))

                # 2. Handshake (CORREÇÃO AQUI)
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    welcome = json.loads(response)
                    
                    if welcome.get("type") != "WELCOME":
                        print(f"[{self.requested_name}] Login recusado.")
                        return
                    
                    # Salva o ID real que o servidor gerou (ex: Bot_PVE_0_12345)
                    self.real_id = welcome.get("id")
                    
                except asyncio.TimeoutError:
                    print(f"[{self.requested_name}] Timeout no login.")
                    return

                # Inicia Loops
                reader = asyncio.create_task(self.read_loop())
                writer = asyncio.create_task(self.write_loop())
                
                done, pending = await asyncio.wait(
                    [reader, writer], 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in pending:
                    task.cancel()

        except ConnectionRefusedError:
            pass
        except Exception as e:
            if self.running:
                print(f"[{self.requested_name}] Desconectado: {e}")
        finally:
            self.running = False

    async def read_loop(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                if data.get("type") in ["STATE", "PVP_STATE"]:
                    self.latest_state = data
                    players = data.get("players", [])
                    
                    # Procura pelo ID REAL, não o nome solicitado
                    for p in players:
                        if p["id"] == self.real_id:
                            self.my_data = p
                            break
        except ConnectionClosed:
            pass
        except Exception:
            pass

    async def write_loop(self):
        while self.running:
            if not self.websocket:
                break

            # Se ainda não recebeu estado ou não se encontrou, aguarda
            if not self.latest_state or not self.my_data:
                await asyncio.sleep(0.1)
                continue

            try:
                if self.mode == "PVE":
                    await self.logic_pve()
                else:
                    await self.logic_pvp()
            except ConnectionClosed:
                break
            except Exception:
                break

            await asyncio.sleep(1 / INPUT_RATE)

    async def logic_pve(self):
        me = self.my_data
        if me["hp"] <= 0:
            await self.websocket.send(json.dumps({"type": "RESPAWN"}))
            await asyncio.sleep(1)
            return

        npcs = self.latest_state.get("npcs", [])
        target = self.find_closest(me, npcs)
        cmd = self.calculate_combat_input(me, target)
        await self.websocket.send(json.dumps(cmd))

    async def logic_pvp(self):
        me = self.my_data
        pvp_info = self.latest_state.get("pvp", {})
        state = pvp_info.get("state", "WAITING")

        if state == "LOBBY_COUNTDOWN":
            if random.random() < 0.2:
                item = random.choice(UPGRADE_ITEMS)
                await self.websocket.send(json.dumps({"type": "UPGRADE", "item": item}))
            
            # Movimento aleatório no lobby
            await self.websocket.send(json.dumps({
                "type": "INPUT",
                "w": random.choice([True, False]),
                "a": random.choice([True, False]),
                "s": random.choice([True, False]),
                "d": random.choice([True, False]),
                "space": False,
                "mouse_x": int(me["x"]),
                "mouse_y": int(me["y"])
            }))
            return

        if state == "PLAYING" and me["hp"] > 0:
            players = self.latest_state.get("players", [])
            # Inimigo é qualquer um que não seja eu
            enemies = [p for p in players if p["id"] != self.real_id and p["hp"] > 0]
            target = self.find_closest(me, enemies)
            cmd = self.calculate_combat_input(me, target)
            await self.websocket.send(json.dumps(cmd))
        else:
            await self.websocket.send(json.dumps({"type": "INPUT"}))

    def find_closest(self, me, entities):
        closest = None
        min_dist = float('inf')
        for e in entities:
            if e.get("hp", 0) <= 0: continue
            dx = e["x"] - me["x"]
            dy = e["y"] - me["y"]
            dist = dx*dx + dy*dy
            if dist < min_dist:
                min_dist = dist
                closest = e
        return closest

    def calculate_combat_input(self, me, target):
        cmd = {
            "type": "INPUT",
            "w": False, "a": False, "s": False, "d": False, "space": False,
            "mouse_x": int(me["x"]), "mouse_y": int(me["y"])
        }
        if target:
            cmd["mouse_x"] = int(target["x"])
            cmd["mouse_y"] = int(target["y"])
            cmd["space"] = True
            dx = target["x"] - me["x"]
            dy = target["y"] - me["y"]
            dist = math.sqrt(dx*dx + dy*dy)
            
            # IA simples de perseguição
            if dist > 400:
                if abs(dx) > 20:
                    if dx > 0: cmd["d"] = True
                    else: cmd["a"] = True
                if abs(dy) > 20:
                    if dy > 0: cmd["s"] = True
                    else: cmd["w"] = True
            else:
                # Movimento evasivo aleatório
                cmd["w"] = random.choice([True, False])
                cmd["a"] = random.choice([True, False])
                cmd["s"] = random.choice([True, False])
                cmd["d"] = random.choice([True, False])
        else:
            # Sem alvo, anda aleatoriamente
            cmd["w"] = random.choice([True, False])
            cmd["a"] = random.choice([True, False])
            cmd["s"] = random.choice([True, False])
            cmd["d"] = random.choice([True, False])
            cmd["mouse_x"] = int(me["x"]) + random.randint(-100, 100)
            cmd["mouse_y"] = int(me["y"]) + random.randint(-100, 100)
        return cmd

async def main():
    print(f"--- TESTE DE ESTRESSE FINAL ---")
    print(f"Alvo: {SERVER_URL}")
    print(f"Bots PVE: {TARGET_PVE}")
    print(f"Bots PVP: {TARGET_PVP}")
    
    tasks = []
    
    try:
        async with websockets.connect(SERVER_URL) as ws:
            print(">> Conexão com servidor OK. Iniciando bots...")
    except Exception as e:
        print(f"FATAL: Não foi possível conectar ao servidor: {e}")
        return

    for i in range(TARGET_PVE):
        bot = SmartBot(i, "PVE")
        tasks.append(asyncio.create_task(bot.connect()))
        if i % 10 == 0: await asyncio.sleep(RAMP_UP_DELAY)

    for i in range(TARGET_PVP):
        bot = SmartBot(i, "PVP")
        tasks.append(asyncio.create_task(bot.connect()))
        if i % 5 == 0: await asyncio.sleep(RAMP_UP_DELAY)

    print("\nBots rodando. Pressione Ctrl+C para parar.")
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\nParando...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass