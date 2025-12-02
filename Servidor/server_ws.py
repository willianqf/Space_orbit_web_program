# Servidor/server_ws.py
import asyncio
import websockets
import json
import time
import random
import math
import settings as s
import multi.pvp_settings as pvp_s
import server_bot_ai

from server_logic import (
    server_calcular_posicao_spawn, server_comprar_upgrade, update_player_logic,
    update_projectile_physics, update_npc_generic_logic, update_mothership_logic,
    update_boss_congelante_logic, update_minion_logic, calc_hit_angle_rad,
    server_spawnar_inimigo_aleatorio, server_spawnar_mothership, 
    server_spawnar_boss_congelante, server_spawnar_minion_mothership,
    server_spawnar_minion_congelante, server_spawnar_obstaculo, server_ganhar_pontos,
    COOLDOWN_TIRO, MAX_PLAYERS_PVE, MAX_PLAYERS_PVP, REGEN_TICK_RATE_MS, 
    REGEN_POR_TICK, PONTOS_LIMIARES_PARA_UPGRADE, VIDA_POR_NIVEL, 
    MAX_DISTANCIA_TIRO_SQ, REDUCAO_DANO_POR_NIVEL, COLISAO_JOGADOR_PROJ_DIST_SQ,
    TARGET_CLICK_SIZE_SQ, COLISAO_JOGADOR_NPC_DIST_SQ,
    AUX_POSICOES, AUX_COOLDOWN_TIRO, AUX_DISTANCIA_TIRO_SQ, _rotate_vector,
    QTD_SALAS_PVE, QTD_SALAS_PVP # Importando quantidades configuradas no server_logic
)

PORT = 8765 
TICK_RATE = 30 # Mantido em 30 Hz para performance
REFERENCE_FPS = 60.0 # Base de velocidade (Physics são baseadas em 60fps)

class GameRoom:
    def __init__(self, room_id, game_mode, max_players):
        self.room_id = room_id
        self.game_mode = game_mode
        self.max_players = max_players
        self.clients = set() 
        self.players = {}    
        self.projectiles = []
        self.npcs = []
        self.obstaculos = [] 
        self.next_npc_id = 0
        self.agora_ms = 0
        
        self.state_globals = {'player_states': self.players, 'network_npcs': self.npcs}
        self.logic_callbacks = {'spawn_calculator': server_calcular_posicao_spawn, 'upgrade_purchaser': server_comprar_upgrade}
        
        if game_mode == "PVE":
            self.bot_manager = server_bot_ai.ServerBotManager(s, self.state_globals, self.logic_callbacks)

    def is_full(self):
        """Verifica se a sala atingiu o limite de jogadores humanos (sockets)."""
        return len(self.clients) >= self.max_players

    async def broadcast(self, message_dict):
        if not self.clients: return
        message_str = json.dumps(message_dict)
        
        # --- CORREÇÃO REAL ---
        # Removemos qualquer filtro de estado. Tentamos enviar para todos.
        # Se um cliente desconectou, o send falha, o gather ignora (return_exceptions=True)
        # e o handler principal remove o cliente da lista depois.
        await asyncio.gather(
            *[client.send(message_str) for client in self.clients],
            return_exceptions=True
        )

    def remove_player(self, websocket):
        if websocket in self.clients:
            self.clients.remove(websocket)
            if websocket in self.players:
                # print(f"[SALA {self.room_id}] {self.players[websocket]['nome']} saiu.") # Opcional: comentar para reduzir spam no log
                del self.players[websocket]

    def update(self, dt_multiplier=1.0):
        self.agora_ms = int(time.time() * 1000)
        
        if self.game_mode == "PVE":
            # --- Gerenciamento de NPCs Inimigos ---
            count_normais = 0; count_motherships = 0; count_bosses = 0
            for n in self.npcs:
                if n.get('hp') <= 0: continue
                t = n['tipo']
                if t == 'mothership': count_motherships += 1
                elif t == 'boss_congelante': count_bosses += 1
                elif 'minion' not in t and t != 'obstaculo': count_normais += 1

            refs = [(p['x'], p['y']) for p in self.players.values()]

            if count_normais < s.MAX_INIMIGOS:
                npc = server_spawnar_inimigo_aleatorio(0, 0, f"npc_{self.next_npc_id}")
                sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
                npc['x'], npc['y'] = sx, sy; self.npcs.append(npc); self.next_npc_id += 1
            
            if count_motherships < s.MAX_MOTHERSHIPS:
                ms = server_spawnar_mothership(0, 0, f"ms_{self.next_npc_id}")
                sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
                ms['x'], ms['y'] = sx, sy; self.npcs.append(ms); self.next_npc_id += 1
            
            if count_bosses < s.MAX_BOSS_CONGELANTE:
                boss = server_spawnar_boss_congelante(0, 0, f"boss_{self.next_npc_id}")
                sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
                boss['x'], boss['y'] = sx, sy; self.npcs.append(boss); self.next_npc_id += 1

            # --- Lógica de Bots (IA Aliada) ---
            humanos_count = len(self.clients)
            
            MAX_ENTIDADES_DESEJADAS = 10 
            MAX_BOTS_PERMITIDOS = s.MAX_BOTS 
            
            slots_para_bots = max(0, MAX_ENTIDADES_DESEJADAS - humanos_count)
            target_bots = min(MAX_BOTS_PERMITIDOS, slots_para_bots)

            bots_remover = self.bot_manager.manage_bot_population(target_bots)
            
            for bot_key in bots_remover:
                key_to_delete = None
                for k, v in self.players.items():
                    if v['nome'] == bot_key and v.get('is_bot'):
                        key_to_delete = k
                        break
                if key_to_delete:
                    del self.players[key_to_delete]

            self._update_game_logic(dt_multiplier)

    def _update_game_logic(self, dt=1.0):
        living_players = [p for p in self.players.values() if p.get('hp') > 0]
        
        if len(self.obstaculos) < s.MAX_OBSTACULOS:
            refs = [(p['x'], p['y']) for p in self.players.values()]
            obs = server_spawnar_obstaculo(refs, s.MAP_WIDTH, s.MAP_HEIGHT, f"obs_{self.next_npc_id}")
            self.obstaculos.append(obs); self.next_npc_id += 1

        living_targets = living_players + self.npcs + self.obstaculos
        novos_projeteis = []

        # Update Players (Passando dt)
        for p in living_players:
            if p.get('is_bot'): self.bot_manager.process_bot_logic(p, living_players, self.agora_ms)
            if p.get('esta_regenerando'):
                if (p['teclas']['w'] or p['teclas']['a'] or p['teclas']['s'] or p['teclas']['d'] or p['alvo_mouse']): p['esta_regenerando'] = False
                elif p['hp'] < p['max_hp']:
                    if self.agora_ms - p.get('ultimo_tick_regeneracao', 0) > REGEN_TICK_RATE_MS:
                        p['hp'] = min(p['max_hp'], p['hp'] + REGEN_POR_TICK); p['ultimo_tick_regeneracao'] = self.agora_ms
                else: p['esta_regenerando'] = False

            new_proj = update_player_logic(p, living_targets, self.agora_ms, s.MAP_WIDTH, s.MAP_HEIGHT, dt)
            if new_proj: novos_projeteis.append(new_proj)

            if p.get('nivel_aux', 0) > 0 and p.get('alvo_lock'):
                t_id = p['alvo_lock']
                target = next((x for x in living_targets if x.get('id', x.get('nome')) == t_id), None)
                if target and target.get('hp', 0) > 0:
                    for i in range(p['nivel_aux']):
                        while len(p['aux_cooldowns']) <= i: p['aux_cooldowns'].append(0)
                        if self.agora_ms > p['aux_cooldowns'][i]:
                            off_x, off_y = _rotate_vector(AUX_POSICOES[i][0], AUX_POSICOES[i][1], -p['angulo'])
                            ax, ay = p['x'] + off_x, p['y'] + off_y
                            dist_sq = (ax - target['x'])**2 + (ay - target['y'])**2
                            if dist_sq < AUX_DISTANCIA_TIRO_SQ:
                                p['aux_cooldowns'][i] = self.agora_ms + AUX_COOLDOWN_TIRO
                                dist = math.sqrt(dist_sq)
                                dir_x = (target['x'] - ax) / dist if dist > 0 else 0
                                dir_y = (target['y'] - ay) / dist if dist > 0 else -1
                                tipo_aux = 'player_pve'
                                if p['nivel_dano'] >= s.MAX_NIVEL_DANO: tipo_aux += '_max'
                                novos_projeteis.append({'id': f"{p['nome']}_aux{i}_{self.agora_ms}", 'owner_nome': p['nome'], 'x': ax, 'y': ay, 'pos_inicial_x': ax, 'pos_inicial_y': ay, 'dano': s.DANO_POR_NIVEL[p['nivel_dano']], 'tipo': tipo_aux, 'tipo_proj': 'teleguiado', 'velocidade': 14, 'alvo_id': t_id, 'timestamp_criacao': self.agora_ms, 'vel_x': dir_x * 14, 'vel_y': dir_y * 14})

        # Update NPCs (Passando dt)
        for npc in self.npcs:
            if npc.get('hp') <= 0: continue
            new_proj = None
            if npc['tipo'] == 'mothership': update_mothership_logic(npc, self.players, self.agora_ms, self, dt)
            elif npc['tipo'] == 'boss_congelante': new_proj = update_boss_congelante_logic(npc, self.players, self.agora_ms, self, dt)
            elif 'minion' in npc['tipo']: new_proj = update_minion_logic(npc, self.players, self.agora_ms, self, dt)
            else: new_proj = update_npc_generic_logic(npc, self.players, self.agora_ms, dt)
            if new_proj: novos_projeteis.append(new_proj)

        self.projectiles.extend(novos_projeteis)

        # Colisões
        toremove_proj = []
        toremove_obs = []

        def aplicar_dano(alvo, dano, atacante_nome, pos_ataque_x=None, pos_ataque_y=None):
            reducao = min(alvo['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL, 75) / 100.0
            alvo['hp'] -= dano * (1.0 - reducao)
            alvo['ultimo_hit_tempo'] = self.agora_ms
            alvo['esta_regenerando'] = False
            
            if alvo['nivel_escudo'] >= s.MAX_NIVEL_ESCUDO:
                angulo_hit = 0
                if pos_ataque_x is not None:
                    angulo_hit = calc_hit_angle_rad(alvo['x'], alvo['y'], pos_ataque_x, pos_ataque_y)
                alvo['shield_hit'] = {'time': self.agora_ms, 'angle': angulo_hit}

            if alvo['hp'] <= 0:
                for p_scorer in self.players.values():
                    if p_scorer['nome'] == atacante_nome:
                        pts = 50 if alvo.get('is_bot', False) else 100
                        server_ganhar_pontos(p_scorer, pts)
                        break

        # Ramming (Player vs NPC)
        for p in living_players:
            for npc in self.npcs:
                if npc.get('hp') <= 0: continue
                raio_npc = npc.get('tamanho', 30) / 2
                dist_colisao_sq = (15 + raio_npc)**2
                if (p['x'] - npc['x'])**2 + (p['y'] - npc['y'])**2 < dist_colisao_sq:
                    dano_no_player = 5 if npc['tipo'] == 'bomba' else 1
                    aplicar_dano(p, dano_no_player, npc['id'], npc['x'], npc['y'])
                    npc['hp'] -= 1
                    npc['ultimo_hit_tempo'] = self.agora_ms
                    if npc['tipo'] == 'bomba': npc['hp'] = 0
                    if npc['hp'] <= 0: server_ganhar_pontos(p, npc.get('pontos_por_morte', 5))

        # Ramming (Player vs Player) - Opcional
        # ...

        # Projéteis (Passando dt)
        for proj in self.projectiles:
            update_projectile_physics(proj, living_targets, self.agora_ms, dt)
            
            dist_percorrida_sq = (proj['x'] - proj['pos_inicial_x'])**2 + (proj['y'] - proj['pos_inicial_y'])**2
            if dist_percorrida_sq > MAX_DISTANCIA_TIRO_SQ: toremove_proj.append(proj); continue
            if not (0 <= proj['x'] <= s.MAP_WIDTH and 0 <= proj['y'] <= s.MAP_HEIGHT): toremove_proj.append(proj); continue

            # Colisão com Obstáculos
            hit = False
            for obs in self.obstaculos:
                if obs in toremove_obs: continue
                if (obs['x'] - proj['x'])**2 + (obs['y'] - proj['y'])**2 < (obs['raio'] + 5)**2:
                    obs['hp'] -= proj['dano']
                    hit = True
                    if obs['hp'] <= 0:
                        toremove_obs.append(obs)
                        owner = next((p for p in self.players.values() if p['nome'] == proj['owner_nome']), None)
                        if owner: server_ganhar_pontos(owner, obs.get('pontos_por_morte', 1))
                    break
            if hit: toremove_proj.append(proj); continue

            # Colisão com Players/NPCs
            if proj['tipo'].startswith('player') or proj['tipo'] == 'npc':
                for target in living_players:
                    if target['nome'] == proj['owner_nome']: continue
                    if (target['x'] - proj['x'])**2 + (target['y'] - proj['y'])**2 < COLISAO_JOGADOR_PROJ_DIST_SQ:
                        aplicar_dano(target, proj['dano'], proj['owner_nome'], proj['x'], proj['y'])
                        hit = True; break
            if hit: toremove_proj.append(proj); continue

            if proj['tipo'].startswith('player'):
                for npc in self.npcs:
                    if npc.get('hp') <= 0: continue
                    raio_npc = npc.get('tamanho', 30) / 2
                    if (npc['x'] - proj['x'])**2 + (npc['y'] - proj['y'])**2 < (raio_npc + 5)**2:
                        npc['hp'] -= proj['dano']
                        npc['ultimo_hit_tempo'] = self.agora_ms
                        hit = True
                        if npc['hp'] <= 0:
                            for p in self.players.values():
                                if p['nome'] == proj['owner_nome']:
                                    server_ganhar_pontos(p, npc.get('pontos_por_morte', 10))
                                    break
                        break
            if hit: toremove_proj.append(proj)

        for p in toremove_proj:
            if p in self.projectiles: self.projectiles.remove(p)
        self.npcs[:] = [n for n in self.npcs if n.get('hp') > 0]
        for obs in toremove_obs:
            if obs in self.obstaculos: self.obstaculos.remove(obs)

    def get_state_json(self):
        players_list = []
        for p in self.players.values():
            if p['hp'] > 0:
                p_data = {
                    "id": p['nome'],
                    "x": round(p['x'], 1),
                    "y": round(p['y'], 1),
                    "angle": int(p['angulo']),
                    "hp": round(p['hp'], 1),
                    "max_hp": p['max_hp'],
                    "score": p['pontos'],
                    "regen": p.get('esta_regenerando', False),
                    "pts_up": p['pontos_upgrade_disponiveis'],
                    "nv_motor": p['nivel_motor'],
                    "nv_dano": p['nivel_dano'],
                    "nv_hp": p['nivel_max_vida'],
                    "nv_escudo": p['nivel_escudo'],
                    "nv_aux": p['nivel_aux'],
                    "is_bot": p.get('is_bot', False)
                }
                
                if p.get('shield_hit'):
                    if self.agora_ms - p['shield_hit']['time'] < 200:
                        p_data['shield_hit'] = True
                        p_data['shield_angle'] = p['shield_hit']['angle']
                    else:
                        del p['shield_hit']

                if p['alvo_mouse']:
                    p_data["tx"] = int(p['alvo_mouse'][0])
                    p_data["ty"] = int(p['alvo_mouse'][1])
                
                players_list.append(p_data)
        
        proj_list = []
        for pr in self.projectiles:
            proj_list.append({"id": pr['id'], "x": round(pr['x'], 1), "y": round(pr['y'], 1), "type": pr['tipo']})

        npcs_list = []
        for n in self.npcs:
            if n.get('hp') > 0:
                npcs_list.append({"id": n['id'], "x": round(n['x'], 1), "y": round(n['y'], 1), "angle": int(n.get('angulo', 0)), "type": n['tipo'], "size": n.get('tamanho', 30), "hp": round(n['hp']), "max_hp": n.get('max_hp', 1)})
        
        for o in self.obstaculos:
            npcs_list.append({"id": o['id'], "x": round(o['x'], 1), "y": round(o['y'], 1), "type": "obstaculo", "size": o['raio'], "hp": o['hp'], "max_hp": o['max_hp']})

        return { "type": "STATE", "timestamp": self.agora_ms, "players": players_list, "projectiles": proj_list, "npcs": npcs_list }

# --- Inicialização Dinâmica de Salas ---
ROOMS = {}

# Cria salas PVE
for i in range(QTD_SALAS_PVE):
    room_id = f"PVE_{i+1}"
    ROOMS[room_id] = GameRoom(room_id, "PVE", MAX_PLAYERS_PVE)

# Cria salas PVP
for i in range(QTD_SALAS_PVP):
    room_id = f"PVP_{i+1}"
    ROOMS[room_id] = GameRoom(room_id, "PVP", MAX_PLAYERS_PVP)

def find_available_room(mode):
    """Encontra a primeira sala do modo especificado que não esteja cheia."""
    for room in ROOMS.values():
        if room.game_mode == mode and not room.is_full():
            return room
    return None

async def game_loop():
    print(f"Servidor de Jogo Iniciado. Salas PVE: {QTD_SALAS_PVE}, PVP: {QTD_SALAS_PVP}. Tick Rate: {TICK_RATE}")
    
    # Cálculo do multiplicador DT (Delta Time)
    dt_multiplier = REFERENCE_FPS / TICK_RATE
    print(f"Delta Time Multiplier: {dt_multiplier}x")

    while True:
        start_time = time.time()
        for room in ROOMS.values():
            room.update(dt_multiplier) # Passa o DT
            state = room.get_state_json()
            await room.broadcast(state)
        elapsed = time.time() - start_time
        await asyncio.sleep(max(0, (1.0 / TICK_RATE) - elapsed))

async def handler(websocket):
    print(f"Novo cliente conectado: {websocket.remote_address}")
    current_room = None
    try:
        message = await websocket.recv()
        data = json.loads(message)
        
        if data.get("type") != "LOGIN": 
            await websocket.close()
            return

        player_name = data.get("name", "Player")
        requested_mode = data.get("mode", "PVE")
        
        current_room = find_available_room(requested_mode)
        
        if not current_room:
            print(f"Conexão rejeitada para {player_name}: Todas as salas {requested_mode} estão cheias.")
            await websocket.close(1008, "Servidor cheio") 
            return

        print(f"Cliente {player_name} entrando na sala {current_room.room_id}")

        spawn_x, spawn_y = server_calcular_posicao_spawn([], s.MAP_WIDTH, s.MAP_HEIGHT)
        hp_inicial = float(s.VIDA_POR_NIVEL[1])
        
        player_state = {
            'nome': f"{player_name}_{int(time.time())}", 'x': spawn_x, 'y': spawn_y, 'angulo': 0, 
            'hp': hp_inicial, 'max_hp': hp_inicial, 'teclas': {'w':False, 'a':False, 's':False, 'd':False, 'space':False},
            'alvo_mouse': None, 'alvo_lock': None, 'pontos': 0, 'cooldown_tiro': COOLDOWN_TIRO, 'ultimo_tiro_tempo': 0,
            'nivel_motor': 1, 'nivel_dano': 1, 'nivel_max_vida': 1, 'nivel_escudo': 0, 
            'pontos_upgrade_disponiveis': 0,
            'total_upgrades_feitos': 0,
            'nivel_aux': 0, 'aux_cooldowns': [0]*4, 'is_bot': False, 'esta_regenerando': False,
            '_pontos_acumulados_para_upgrade': 0, '_limiar_pontos_atual': PONTOS_LIMIARES_PARA_UPGRADE[0], '_indice_limiar': 0
        }
        
        current_room.clients.add(websocket)
        current_room.players[websocket] = player_state
        await websocket.send(json.dumps({"type": "WELCOME", "id": player_state['nome'], "x": spawn_x, "y": spawn_y, "mode": current_room.game_mode, "map_width": s.MAP_WIDTH, "map_height": s.MAP_HEIGHT}))

        async for message in websocket:
            try:
                cmd = json.loads(message)
                if cmd.get("type") == "INPUT":
                    player_state['teclas']['w'] = cmd.get('w', False); player_state['teclas']['a'] = cmd.get('a', False)
                    player_state['teclas']['s'] = cmd.get('s', False); player_state['teclas']['d'] = cmd.get('d', False)
                    player_state['teclas']['space'] = cmd.get('space', False)
                    if 'mouse_x' in cmd: player_state['alvo_mouse'] = (cmd['mouse_x'], cmd['mouse_y'])
                elif cmd.get("type") == "UPGRADE": server_comprar_upgrade(player_state, cmd.get("item"))
                elif cmd.get("type") == "TARGET":
                    click_x, click_y = cmd.get('x'), cmd.get('y')
                    melhor_dist = float('inf'); melhor_id = None
                    candidatos = []
                    candidatos.extend(current_room.npcs); candidatos.extend(current_room.obstaculos)
                    for p in current_room.players.values():
                        if p['nome'] != player_state['nome']: candidatos.append(p)
                    for alvo in candidatos:
                        if alvo.get('hp', 0) <= 0: continue
                        dist_sq = (alvo['x'] - click_x)**2 + (alvo['y'] - click_y)**2
                        if dist_sq < TARGET_CLICK_SIZE_SQ and dist_sq < melhor_dist:
                            melhor_dist = dist_sq; melhor_id = alvo.get('id', alvo.get('nome'))
                    player_state['alvo_lock'] = melhor_id
                elif cmd.get("type") == "TOGGLE_REGEN":
                    if not player_state.get('esta_regenerando') and player_state['hp'] < player_state['max_hp']: player_state['esta_regenerando'] = True
                    else: player_state['esta_regenerando'] = False
                elif cmd.get("type") == "ENTER_SPECTATOR": player_state['hp'] = 0; player_state['esta_regenerando'] = False
                elif cmd.get("type") == "RESPAWN":
                    if player_state['hp'] <= 0:
                        spawn_x, spawn_y = server_calcular_posicao_spawn([], s.MAP_WIDTH, s.MAP_HEIGHT)
                        player_state['x'] = spawn_x; player_state['y'] = spawn_y
                        hp_inicial = float(s.VIDA_POR_NIVEL[1])
                        player_state['nivel_max_vida'] = 1; player_state['max_hp'] = hp_inicial; player_state['hp'] = hp_inicial
                        player_state['pontos'] = 0; player_state['pontos_upgrade_disponiveis'] = 0; player_state['total_upgrades_feitos'] = 0
                        player_state['_pontos_acumulados_para_upgrade'] = 0; player_state['_limiar_pontos_atual'] = PONTOS_LIMIARES_PARA_UPGRADE[0]; player_state['_indice_limiar'] = 0
                        player_state['nivel_motor'] = 1; player_state['nivel_dano'] = 1; player_state['nivel_escudo'] = 0; player_state['nivel_aux'] = 0
                        player_state['alvo_lock'] = None; player_state['alvo_mouse'] = None
            except json.JSONDecodeError: pass
    except Exception as e: 
        if not isinstance(e, websockets.exceptions.ConnectionClosed):
            print(f"Erro no handler: {e}")
    finally:
        if current_room: current_room.remove_player(websocket)

async def main():
    server = await websockets.serve(handler, "0.0.0.0", PORT)
    print(f"Servidor WebSocket rodando na porta {PORT}...")
    await asyncio.gather(server.wait_closed(), game_loop())

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Servidor encerrado.")