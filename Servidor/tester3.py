import asyncio
import websockets
import json
import random
import sys
from websockets.exceptions import ConnectionClosed

# --- CONFIGURAÇÕES ---
SERVER_URL = "ws://localhost:8765"
RAMP_UP_DELAY = 0.05  # Atraso entre conexões
INPUT_RATE = 5        # Inputs por segundo

# Defina a quantidade de bots aqui
TARGET_PVE = 48
TARGET_PVP = 16

class DummyBot:
    def __init__(self, bot_id, mode):
        self.bot_id = bot_id
        self.mode = mode
        self.name = f"Stress_{mode}_{bot_id}"
        self.running = True
        self.websocket = None

    async def drain_messages(self):
        """
        Tarefa de fundo para limpar o buffer de leitura.
        """
        try:
            async for _ in self.websocket:
                pass
        except ConnectionClosed:
            self.running = False
        except Exception:
            self.running = False

    async def run(self):
        try:
            # ping_interval=None desativa pings do cliente
            async with websockets.connect(SERVER_URL, ping_interval=None) as websocket:
                self.websocket = websocket
                
                # --- 1. LOGIN ---
                login_payload = {
                    "type": "LOGIN",
                    "name": self.name,
                    "mode": self.mode
                }
                await websocket.send(json.dumps(login_payload))

                # --- 2. HANDSHAKE ---
                try:
                    response = await websocket.recv()
                    data = json.loads(response)
                    
                    if data.get("type") != "WELCOME":
                        print(f"[{self.name}] Falha no Login: {data}")
                        return
                except Exception as e:
                    print(f"[{self.name}] Erro no handshake: {e}")
                    return

                # --- 3. INICIAR DRENAGEM ---
                read_task = asyncio.create_task(self.drain_messages())

                # --- 4. LOOP DE INPUT (Escrita) ---
                try:
                    while self.running:
                        # CORREÇÃO: Removemos o check 'if not websocket.open'
                        # Se a conexão fechar, o send() abaixo vai gerar erro e cair no except
                        
                        cmd = {
                            "type": "INPUT",
                            "w": random.choice([True, False]),
                            "a": random.choice([True, False]),
                            "s": random.choice([True, False]),
                            "d": random.choice([True, False]),
                            "space": random.random() < 0.1,
                            "mouse_x": random.randint(0, 8000),
                            "mouse_y": random.randint(0, 8000)
                        }
                        
                        await websocket.send(json.dumps(cmd))
                        await asyncio.sleep(1 / INPUT_RATE)

                except ConnectionClosed:
                    pass 
                except Exception as e:
                    print(f"[{self.name}] Erro no loop de escrita: {e}")
                finally:
                    self.running = False
                    read_task.cancel()
                    try:
                        await read_task
                    except asyncio.CancelledError:
                        pass

        except Exception as e:
            if self.running:
                print(f"[{self.name}] Falha de conexão inicial: {e}")
        finally:
            self.running = False

async def main():
    print(f"--- INICIANDO TESTE DE ESTRESSE (CORRIGIDO) ---")
    print(f"Alvo: {SERVER_URL}")
    print(f"Meta PVE: {TARGET_PVE} bots")
    print(f"Meta PVP: {TARGET_PVP} bots")
    print(f"Total: {TARGET_PVE + TARGET_PVP} conexões")
    print("-----------------------------------------------")

    bots = []

    # --- ONDA PVE ---
    print(">>> Iniciando bots PVE...")
    for i in range(TARGET_PVE):
        bot = DummyBot(i, "PVE")
        bots.append(bot)
        asyncio.create_task(bot.run())
        
        if i % 10 == 0:
            sys.stdout.write(f"\rConectando PVE: {i+1}/{TARGET_PVE}")
            sys.stdout.flush()
        await asyncio.sleep(RAMP_UP_DELAY)
    print("\nSalas PVE preenchidas.")

    # --- ONDA PVP ---
    print("\n>>> Iniciando bots PVP...")
    for i in range(TARGET_PVP):
        bot = DummyBot(i, "PVP")
        bots.append(bot)
        asyncio.create_task(bot.run())
        
        sys.stdout.write(f"\rConectando PVP: {i+1}/{TARGET_PVP}")
        sys.stdout.flush()
        await asyncio.sleep(RAMP_UP_DELAY)
    
    print(f"\n\n--- CARGA MÁXIMA ATINGIDA ---")
    print("Monitorando conexões ativas...")
    print("Pressione Ctrl+C para parar.")

    try:
        while True:
            alive = sum(1 for b in bots if b.running)
            total = len(bots)
            
            if alive == 0 and total > 0:
                print("\nTodos os bots foram desconectados.")
                break
            
            sys.stdout.write(f"\r[STATUS] Conexões: {alive} / {total} | Quedas: {total - alive}   ")
            sys.stdout.flush()
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nEncerrando teste...")
        for b in bots: 
            b.running = False
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass