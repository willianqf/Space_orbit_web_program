import asyncio
import websockets
import json
import math
import random
import sys

# --- CONFIGURAÇÕES ---
SERVER_URL = "ws://localhost:8765"
NUM_BOTS = 3           # 3 Bots para preencher a sala (deixando 1 vaga para você)
RAMP_UP_DELAY = 0.2    # Delay entre conexões para não sobrecarregar o login

class SmartPvpBot:
    def __init__(self, bot_id):
        self.bot_id = bot_id
        self.name = f"KillerBot_{bot_id+1}"
        self.my_id = None
        self.running = True
        self.websocket = None
        
        # Estado Local
        self.x = 0
        self.y = 0
        self.hp = 100
        self.max_hp = 100
        self.pts_up = 0 # Pontos de upgrade disponíveis
        self.alive = True
        
        # "Cérebro"
        self.current_target = None # Objeto do alvo atual
        self.locked_target_id = None # ID do alvo que o servidor SABE que travamos
        
        self.strafe_dir = 1 # 1 ou -1
        self.strafe_timer = 0
        self.reaction_delay = 0

    async def run(self):
        try:
            async with websockets.connect(SERVER_URL) as websocket:
                self.websocket = websocket
                
                # 1. Login
                print(f"[{self.name}] Conectando...")
                await websocket.send(json.dumps({
                    "type": "LOGIN",
                    "name": self.name,
                    "mode": "PVP"
                }))

                # 2. Handshake
                response = await websocket.recv()
                data = json.loads(response)
                if data.get("type") == "WELCOME":
                    self.my_id = data.get("id")
                    print(f"[{self.name}] Logado com ID: {self.my_id}")
                else:
                    print(f"[{self.name}] Login falhou: {data}")
                    return

                # Inicia tarefas paralelas (Escutar e Agir)
                await asyncio.gather(
                    self.listen_loop(),
                    self.logic_loop()
                )
        except Exception as e:
            print(f"[{self.name}] Desconectado: {e}")
        finally:
            self.running = False

    async def listen_loop(self):
        """Escuta atualizações do servidor e atualiza o estado local do bot"""
        try:
            async for message in self.websocket:
                msg = json.loads(message)
                if msg.get("type") == "PVP_STATE":
                    self.process_state(msg)
        except:
            pass

    def process_state(self, state_msg):
        """Processa o JSON do jogo para tomar decisões"""
        players = state_msg.get("players", [])
        
        # 1. Atualiza meus dados
        me = next((p for p in players if p["id"] == self.my_id), None)
        if me:
            self.x = me["x"]
            self.y = me["y"]
            self.hp = me["hp"]
            self.pts_up = me.get("pts_up", 0) # Atualiza pontos de upgrade
            self.alive = (self.hp > 0)
        else:
            # Se não estou na lista, provavelmente morri ou sou espectador
            self.alive = False

        # 2. Procura alvos (Jogadores vivos que não sejam eu)
        if self.alive:
            enemies = [p for p in players if p["id"] != self.my_id and p["hp"] > 0]
            self.current_target = self.choose_best_target(enemies)

    def choose_best_target(self, enemies):
        """Escolhe o inimigo mais próximo"""
        if not enemies: return None
        
        best_target = None
        min_dist_sq = float('inf')
        
        for enemy in enemies:
            dx = enemy["x"] - self.x
            dy = enemy["y"] - self.y
            dist_sq = dx*dx + dy*dy
            
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                best_target = enemy
                
        return best_target

    async def logic_loop(self):
        """Loop de decisão (IA)"""
        while self.running:
            if not self.alive:
                # Se morto, espera um pouco e tenta de novo
                await asyncio.sleep(1)
                continue
            
            # --- LÓGICA DE UPGRADE ---
            if self.pts_up > 0:
                if random.random() < 0.05:
                    shop_items = ["motor", "dano", "max_health", "escudo", "auxiliar"]
                    chosen_item = random.choice(shop_items)
                    if self.websocket:
                        try:
                            await self.websocket.send(json.dumps({ "type": "UPGRADE", "item": chosen_item }))
                        except Exception: break
            # -------------------------

            # Inputs padrão (parado)
            cmd = {
                "type": "INPUT",
                "w": False, "a": False, "s": False, "d": False, "space": False,
                "mouse_x": int(self.x), "mouse_y": int(self.y)
            }

            if self.current_target:
                t_x = self.current_target["x"]
                t_y = self.current_target["y"]
                t_id = self.current_target["id"]
                
                dx = t_x - self.x
                dy = t_y - self.y
                dist = math.sqrt(dx*dx + dy*dy)
                
                # --- LÓGICA DE TRAVAR MIRA (TARGET LOCK) ---
                # Se o alvo mudou, envia o comando TARGET para o servidor
                if self.locked_target_id != t_id:
                    if self.websocket:
                        try:
                            # Simula o clique direito do mouse exatamente sobre o inimigo
                            await self.websocket.send(json.dumps({
                                "type": "TARGET", 
                                "x": int(t_x), 
                                "y": int(t_y)
                            }))
                            self.locked_target_id = t_id
                            # print(f"[{self.name}] Travou mira em {t_id}")
                        except Exception: break
                # -------------------------------------------

                # 1. Mirar (Aim) com erro humano
                aim_x = t_x + random.randint(-20, 20)
                aim_y = t_y + random.randint(-20, 20)
                cmd["mouse_x"] = int(aim_x)
                cmd["mouse_y"] = int(aim_y)
                
                # 2. Atirar
                if dist < 800:
                    cmd["space"] = True
                
                # 3. Mover
                if dist > 400:
                    cmd["w"] = True
                elif dist < 150:
                    cmd["s"] = True
                else:
                    self.strafe_timer += 1
                    if self.strafe_timer > 20:
                        self.strafe_dir *= -1
                        self.strafe_timer = 0
                    if self.strafe_dir > 0: cmd["d"] = True
                    else: cmd["a"] = True

            else:
                # Sem alvo: Reseta lock
                self.locked_target_id = None
                
                # Vagar aleatoriamente
                if random.random() < 0.05: self.strafe_dir *= -1
                if self.strafe_dir > 0: cmd["d"] = True
                else: cmd["a"] = True
                cmd["w"] = True

            # Envia comando de Input
            if self.websocket:
                try:
                    await self.websocket.send(json.dumps(cmd))
                except Exception:
                    break
            
            await asyncio.sleep(0.05)

async def main():
    print(f"--- INICIANDO TESTE PVP INTELIGENTE (COM TARGET LOCK) ---")
    print(f"Alvo: {SERVER_URL}")
    print(f"Bots: {NUM_BOTS}")
    
    bots = []
    for i in range(NUM_BOTS):
        bot = SmartPvpBot(i)
        bots.append(bot)
        asyncio.create_task(bot.run())
        sys.stdout.write(f"\rBot {i+1} conectado...")
        sys.stdout.flush()
        await asyncio.sleep(RAMP_UP_DELAY)
    
    print("\nTodos os bots conectados! Entre na sala PVP para lutar.")
    
    try:
        while True:
            alive = sum(1 for b in bots if b.running)
            if alive == 0: break
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nParando bots...")
        for b in bots: b.running = False

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass