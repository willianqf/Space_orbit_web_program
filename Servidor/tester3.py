import asyncio
import websockets
import json
import random
import sys

# --- CONFIGURAÇÕES ---
SERVER_URL = "ws://localhost:8765"
RAMP_UP_DELAY = 0.05  # Atraso entre conexões (50ms) para não travar o handshake do servidor
INPUT_RATE = 5        # Inputs por segundo para manter a conexão ativa

# Capacidade definida em server_logic.py
TARGET_PVE = 48
TARGET_PVP = 16 

class DummyBot:
    def __init__(self, bot_id, mode):
        self.bot_id = bot_id
        self.mode = mode
        self.name = f"Stress_{mode}_{bot_id}"
        self.running = True
        self.websocket = None

    async def run(self):
        try:
            # Desabilita ping do cliente também
            async with websockets.connect(SERVER_URL, ping_interval=None) as websocket:
                self.websocket = websocket
                
                # 1. Login
                login_payload = {
                    "type": "LOGIN",
                    "name": self.name,
                    "mode": self.mode
                }
                await websocket.send(json.dumps(login_payload))

                # 2. Handshake
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") == "WELCOME":
                    # print(f"[{self.name}] Conectado na sala {self.mode}!")
                    pass
                else:
                    print(f"[{self.name}] Falha: {data}")
                    return

                # 3. Loop de Manutenção (Heartbeat/Input)
                while self.running:
                    # Envia input aleatório leve para manter o bot "vivo" e movendo
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
                    
                    # Lê mensagens para limpar o buffer do socket, mas ignora o conteúdo
                    try:
                        await asyncio.wait_for(websocket.recv(), timeout=0.01)
                    except (asyncio.TimeoutError, Exception):
                        pass

                    await asyncio.sleep(1 / INPUT_RATE)

        except Exception as e:
            # Ignora erros de desconexão esperados quando o teste encerra
            if self.running:
                print(f"[{self.name}] Desconectado: {e}")
        finally:
            self.running = False

async def main():
    print(f"--- INICIANDO TESTE DE ESTRESSE TOTAL ---")
    print(f"Alvo: {SERVER_URL}")
    print(f"Meta PVE: {TARGET_PVE} bots")
    print(f"Meta PVP: {TARGET_PVP} bots")
    print(f"Total: {TARGET_PVE + TARGET_PVP} conexões")
    print("-----------------------------------------")

    bots = []

    # Lota as salas PVE
    print(">>> Iniciando onda PVE...")
    for i in range(TARGET_PVE):
        bot = DummyBot(i, "PVE")
        bots.append(bot)
        asyncio.create_task(bot.run())
        if i % 5 == 0: # Feedback visual a cada 5 bots
            sys.stdout.write(f"\rConectando PVE: {i+1}/{TARGET_PVE}")
            sys.stdout.flush()
        await asyncio.sleep(RAMP_UP_DELAY)
    print("\nSalas PVE preenchidas (teoricamente).")

    # Lota as salas PVP
    print("\n>>> Iniciando onda PVP...")
    for i in range(TARGET_PVP):
        bot = DummyBot(i, "PVP")
        bots.append(bot)
        asyncio.create_task(bot.run())
        sys.stdout.write(f"\rConectando PVP: {i+1}/{TARGET_PVP}")
        sys.stdout.flush()
        await asyncio.sleep(RAMP_UP_DELAY)
    
    print(f"\n\n--- SERVIDOR SOB CARGA MÁXIMA ---")
    print("Todos os bots foram despachados.")
    print("Verifique o uso de CPU/Memória do servidor.")
    print("Pressione Ctrl+C para parar.")

    try:
        while True:
            alive = sum(1 for b in bots if b.running)
            if alive == 0:
                print("Todos os bots caíram.")
                break
            
            # Monitoramento simples
            sys.stdout.write(f"\r[STATUS] Conexões Ativas: {alive} / {len(bots)}   ")
            sys.stdout.flush()
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nEncerrando teste...")
        for b in bots: b.running = False

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass