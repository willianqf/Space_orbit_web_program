import asyncio
import websockets
import json
import random
import sys

# Configurações
SERVER_URL = "ws://localhost:8765"
NUM_BOTS = 31          # Total de bots para o teste
RAMP_UP_DELAY = 0.1     # Intervalo de conexão (evita travar o server no login)
INPUT_RATE = 15         # Comandos por segundo

class BotClient:
    def __init__(self, bot_id):
        self.bot_id = bot_id
        self.name_prefix = f"Tester_{bot_id}"
        self.my_server_id = None 
        self.running = True
        self.websocket = None
        self.is_dead = False
        self.hp = 100

    async def run(self):
        try:
            async with websockets.connect(SERVER_URL) as websocket:
                self.websocket = websocket
                
                # 1. Login
                login_payload = {
                    "type": "LOGIN",
                    "name": self.name_prefix,
                    "mode": "PVE"
                }
                await websocket.send(json.dumps(login_payload))

                # 2. Identificação
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") == "WELCOME":
                    self.my_server_id = data.get("id")
                else:
                    return # Falha no login

                # Inicia escuta do servidor
                receive_task = asyncio.create_task(self.receive_loop())
                
                # Loop de Ação
                try:
                    while self.running:
                        if self.is_dead:
                            # Se morreu: Pede Respawn e espera
                            # print(f"[{self.name_prefix}] Morreu. Pedindo Respawn...")
                            await websocket.send(json.dumps({"type": "RESPAWN"}))
                            
                            # Assume que reviveu para não spammar o comando
                            self.is_dead = False 
                            self.hp = 100 
                            
                            # Espera 2s para garantir que o server processou
                            await asyncio.sleep(2.0) 
                        else:
                            # Se vivo: Joga (envia inputs)
                            input_payload = {
                                "type": "INPUT",
                                "w": random.choice([True, False]),
                                "a": random.choice([True, False]),
                                "s": random.choice([True, False]),
                                "d": random.choice([True, False]),
                                "space": random.random() < 0.2, # 20% chance de tiro
                                "mouse_x": random.randint(0, 8000),
                                "mouse_y": random.randint(0, 8000)
                            }
                            await websocket.send(json.dumps(input_payload))
                            await asyncio.sleep(1 / INPUT_RATE)
                        
                except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                    pass
                except Exception as e:
                    print(f"[{self.name_prefix}] Erro envio: {e}")
                finally:
                    self.running = False
                    receive_task.cancel()
                    
        except Exception:
            self.running = False

    async def receive_loop(self):
        """Escuta o servidor para saber HP e Morte"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data.get("type") == "STATE":
                    players = data.get("players", [])
                    # Procura meu ID na lista de jogadores vivos
                    me = next((p for p in players if p["id"] == self.my_server_id), None)
                    
                    if me:
                        self.hp = me["hp"]
                        # Server diz que estou vivo (estou na lista)
                        if self.hp <= 0: 
                            self.is_dead = True
                    else:
                        # IMPORTANTE: Se não estou na lista 'players', é porque morri (HP <= 0)
                        # O servidor filtra mortos para economizar banda.
                        self.hp = 0
                        self.is_dead = True

        except Exception:
            pass

async def main():
    print(f"--- TESTE DE ESTRESSE: BOT RESPAWN ---")
    print(f"Alvo: {SERVER_URL} | Bots: {NUM_BOTS}")
    
    bots = []
    for i in range(NUM_BOTS):
        bot = BotClient(i)
        bots.append(bot)
        asyncio.create_task(bot.run())
        
        sys.stdout.write(f"\rConectando: {i+1}/{NUM_BOTS}")
        sys.stdout.flush()
        await asyncio.sleep(RAMP_UP_DELAY)

    print("\n\nBots rodando. Pressione Ctrl+C para parar.")
    
    try:
        while True:
            # Monitoramento
            alive_conns = sum(1 for bot in bots if bot.running)
            dead_ingame = sum(1 for bot in bots if bot.is_dead)
            
            status = f"\r[STATUS] Conexões: {alive_conns}/{NUM_BOTS} | Mortos/Respawnando: {dead_ingame}   "
            sys.stdout.write(status)
            sys.stdout.flush()
            
            if alive_conns == 0:
                print("\nTodas as conexões caíram.")
                break
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        print("\nEncerrando...")
        for bot in bots: bot.running = False

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass