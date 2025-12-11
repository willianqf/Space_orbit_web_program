import asyncio
import websockets
import json
import random
import math

# --- CONFIGURAÇÕES ---
SERVER_URL = "ws://localhost:8765"
RAMP_UP_DELAY = 0.2    
INPUT_RATE = 15        

# Quantidade de Bots
TARGET_PVE = 47
TARGET_PVP = 15

UPGRADE_ITEMS = ["motor", "dano", "escudo", "max_health", "auxiliar"]

class IntelligentBot:
    def __init__(self, bot_id, mode):
        self.bot_id = bot_id
        self.mode = mode
        self.requested_name = f"SmartBot_{mode}_{bot_id}"
        self.real_id = None
        self.running = True
        self.websocket = None
        self.my_data = None
        self.latest_state = None
        self.current_target_id = None
        self.tick_count = 0

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

                # 2. Handshake
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    welcome = json.loads(response)
                    
                    if welcome.get("type") != "WELCOME":
                        print(f"[{self.requested_name}] Login recusado.")
                        return
                    
                    self.real_id = welcome.get("id")
                    print(f"[{self.requested_name}] Conectado como {self.real_id}")
                    
                except asyncio.TimeoutError:
                    print(f"[{self.requested_name}] Timeout no login.")
                    return

                # Loops
                reader = asyncio.create_task(self.read_loop())
                writer = asyncio.create_task(self.write_loop())
                
                await asyncio.wait([reader, writer], return_when=asyncio.FIRST_COMPLETED)
                reader.cancel()
                writer.cancel()

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
                    
                    # --- CORREÇÃO DO RESPAWN ---
                    # O servidor não envia jogadores mortos no JSON.
                    # Se eu estava vivo antes e sumi da lista, significa que morri.
                    found_me = False
                    for p in players:
                        if p["id"] == self.real_id:
                            self.my_data = p
                            found_me = True
                            break
                    
                    if self.my_data and not found_me:
                        # Força HP a 0 para ativar a lógica de respawn no write_loop
                        self.my_data["hp"] = 0
                        
        except Exception:
            pass

    async def write_loop(self):
        while self.running:
            if not self.websocket: break
            if not self.latest_state or not self.my_data:
                await asyncio.sleep(0.1)
                continue

            try:
                self.tick_count += 1
                if self.mode == "PVE":
                    await self.logic_pve()
                else:
                    await self.logic_pvp()
            except Exception as e:
                print(f"Erro lógica bot: {e}")
                break

            await asyncio.sleep(1 / INPUT_RATE)

    async def check_and_buy_upgrades(self):
        if self.my_data and self.my_data.get("pts_up", 0) > 0:
            item = random.choice(UPGRADE_ITEMS)
            await self.websocket.send(json.dumps({"type": "UPGRADE", "item": item}))

    # --- LÓGICA DE ALVO UNIFICADA ---
    async def manage_targeting(self, target):
        """
        Envia comando TARGET para 'marcar' o inimigo (botão direito).
        Não usa SPACE. Confia no servidor para atirar automaticamente.
        """
        if target:
            # Se mudou de alvo OU faz tempo que não manda o lock (reforço)
            if self.current_target_id != target.get("id") or (self.tick_count % 30 == 0):
                self.current_target_id = target.get("id")
                await self.websocket.send(json.dumps({
                    "type": "TARGET", 
                    "x": int(target["x"]), 
                    "y": int(target["y"])
                }))
        else:
            # Se não tem alvo e tinhamos um antes, destrava clicando no vazio (opcional)
            if self.current_target_id is not None:
                self.current_target_id = None
                # Envia um target numa posição aleatória vazia para limpar o lock
                await self.websocket.send(json.dumps({
                    "type": "TARGET", 
                    "x": -9999, 
                    "y": -9999
                }))

    async def logic_pve(self):
        me = self.my_data
        
        # 1. Renascer se morto (Correção aplicada no read_loop garante que entra aqui)
        if me["hp"] <= 0:
            print(f"[{self.requested_name}] Morreu. Tentando Respawn...")
            await self.websocket.send(json.dumps({"type": "RESPAWN"}))
            await asyncio.sleep(1.0)
            return

        await self.check_and_buy_upgrades()

        # Busca alvos (NPCs e Players)
        npcs = self.latest_state.get("npcs", [])
        players = self.latest_state.get("players", [])
        possible_targets = [n for n in npcs if n.get("hp", 0) > 0]
        possible_targets.extend([p for p in players if p["id"] != self.real_id and p.get("hp", 0) > 0])

        target = self.find_closest(me, possible_targets)
        
        # Gerencia o Lock-on (Marcação)
        await self.manage_targeting(target)
        
        # Movimentação
        cmd = self.calculate_movement_only(me, target)
        await self.websocket.send(json.dumps(cmd))

    async def logic_pvp(self):
        me = self.my_data
        pvp_info = self.latest_state.get("pvp", {})
        state = pvp_info.get("state", "WAITING")

        if state in ["LOBBY_COUNTDOWN", "WAITING"]:
            await self.check_and_buy_upgrades()
            # Movimento aleatório no lobby
            await self.websocket.send(json.dumps({
                "type": "INPUT",
                "w": random.choice([True, False]), "a": random.choice([True, False]),
                "s": random.choice([True, False]), "d": random.choice([True, False]),
                "space": False
            }))
            return

        if state == "PLAYING" and me["hp"] > 0:
            await self.check_and_buy_upgrades()

            players = self.latest_state.get("players", [])
            enemies = [p for p in players if p["id"] != self.real_id and p.get("hp", 0) > 0]
            
            target = self.find_closest(me, enemies)
            
            # Gerencia o Lock-on (Marcação)
            await self.manage_targeting(target)
            
            # Movimentação
            cmd = self.calculate_movement_only(me, target)
            await self.websocket.send(json.dumps(cmd))

        elif state == "PLAYING" and me["hp"] <= 0:
            await self.websocket.send(json.dumps({"type": "INPUT"}))

    def find_closest(self, me, entities):
        closest = None; min_dist = float('inf')
        for e in entities:
            dx = e["x"] - me["x"]; dy = e["y"] - me["y"]
            d = dx*dx + dy*dy
            if d < min_dist: min_dist = d; closest = e
        return closest

    def calculate_movement_only(self, me, target):
        # Apenas WASD. Não controla mouse nem space (pois usamos Lock-on)
        cmd = {
            "type": "INPUT",
            "w": False, "a": False, "s": False, "d": False, "space": False,
            # Mouse aponta para frente do movimento ou aleatório, já que o tiro é automático pelo Lock
            "mouse_x": int(me["x"]), "mouse_y": int(me["y"]) 
        }

        if not target:
            # Patrulha
            cmd["w"] = random.choice([True, False])
            cmd["d"] = random.choice([True, False])
            return cmd

        dx = target["x"] - me["x"]; dy = target["y"] - me["y"]
        dist = math.sqrt(dx*dx + dy*dy)
        hp_perc = me["hp"] / me["max_hp"]

        # Se tiver com vida baixa, foge
        if hp_perc < 0.30:
            if abs(dx) > 20:
                if dx > 0: cmd["a"] = True # Foge para esquerda se alvo está a direita
                else: cmd["d"] = True
            if abs(dy) > 20:
                if dy > 0: cmd["w"] = True
                else: cmd["s"] = True
        else:
            # Kiting (Mantém distância)
            ideal_dist = 350
            if dist > ideal_dist + 50: # Aproxima
                if abs(dx) > 20:
                    if dx > 0: cmd["d"] = True
                    else: cmd["a"] = True
                if abs(dy) > 20:
                    if dy > 0: cmd["s"] = True
                    else: cmd["w"] = True
            elif dist < ideal_dist - 50: # Afasta
                if abs(dx) > 20:
                    if dx > 0: cmd["a"] = True
                    else: cmd["d"] = True
                if abs(dy) > 20:
                    if dy > 0: cmd["w"] = True
                    else: cmd["s"] = True
            else: # Strafe (Esquiva lateral)
                cmd["w"] = random.choice([True, False])
                cmd["a"] = random.choice([True, False])
                cmd["s"] = random.choice([True, False])
                cmd["d"] = random.choice([True, False])

        # Opcional: Faz o mouse "olhar" para o alvo para efeito visual, 
        # mas quem controla o tiro é o servidor via 'alvo_lock'
        cmd["mouse_x"] = int(target["x"])
        cmd["mouse_y"] = int(target["y"])
        
        return cmd

async def main():
    print(f"--- TESTE INTELIGENTE V2 (Respawn Fix + Lock-on) ---")
    tasks = []
    
    for i in range(TARGET_PVE):
        bot = IntelligentBot(i, "PVE")
        tasks.append(asyncio.create_task(bot.connect()))
        if i % 5 == 0: await asyncio.sleep(RAMP_UP_DELAY)

    for i in range(TARGET_PVP):
        bot = IntelligentBot(i, "PVP")
        tasks.append(asyncio.create_task(bot.connect()))
        if i % 5 == 0: await asyncio.sleep(RAMP_UP_DELAY)

    print("\nBots rodando. Ctrl+C para parar.")
    try: await asyncio.gather(*tasks)
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass